#!/usr/bin/python3 -OO
# Copyright 2007-2026 by The SABnzbd-Team (sabnzbd.org)
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
sabnzbd.downloader - download engine
"""

import logging
import selectors
from collections import deque
from threading import Thread, RLock, current_thread
import socket
import sys
import ssl
import time
from datetime import date
from typing import Optional, Union, Deque, Callable

import sabctools

import sabnzbd
from sabnzbd.decorators import synchronized, NzbQueueLocker, DOWNLOADER_CV, DOWNLOADER_LOCK
from sabnzbd.newswrapper import NewsWrapper, NNTPPermanentError
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.misc import from_units, helpful_warning, int_conv, MultiAddQueue, to_units
from sabnzbd.get_addrinfo import get_fastest_addrinfo, AddrInfo

# Timeout penalty in minutes for each cause
_PENALTY_UNKNOWN = 3  # Unknown cause
_PENALTY_502 = 5  # Unknown 502
_PENALTY_TIMEOUT = 10  # Server doesn't give an answer (multiple times)
_PENALTY_SHARE = 10  # Account sharing detected
_PENALTY_TOOMANY = 10  # Too many connections
_PENALTY_PERM = 10  # Permanent error, like bad username/password
_PENALTY_SHORT = 1  # Minimal penalty when no_penalties is set
_PENALTY_VERYSHORT = 0.1  # Error 400 without cause clues

# Wait this many seconds between checking idle servers for new articles or busy threads for timeout
_SERVER_CHECK_DELAY = 0.5
# Wait this many seconds between updates of the BPSMeter
_BPSMETER_UPDATE_DELAY = 0.05
# How many articles should be prefetched when checking the next articles?
_ARTICLE_PREFETCH = 20
# Minimum expected size of TCP receive buffer
_DEFAULT_CHUNK_SIZE = 32768

TIMER_LOCK = RLock()


class Server:
    # Pre-define attributes to save memory and improve get/set performance
    __slots__ = (
        "id",
        "newid",
        "restart",
        "displayname",
        "host",
        "port",
        "timeout",
        "threads",
        "priority",
        "ssl",
        "ssl_verify",
        "ssl_ciphers",
        "ssl_context",
        "required",
        "optional",
        "retention",
        "username",
        "password",
        "pipelining_requests",
        "busy_threads",
        "next_busy_threads_check",
        "idle_threads",
        "next_article_search",
        "active",
        "bad_cons",
        "errormsg",
        "warning",
        "addrinfo",
        "ssl_info",
        "request",
        "have_body",
        "have_stat",
        "article_queue",
    )

    def __init__(
        self,
        server_id,
        displayname,
        host,
        port,
        timeout,
        threads,
        priority,
        use_ssl,
        ssl_verify,
        ssl_ciphers,
        pipelining_requests,
        username=None,
        password=None,
        required=False,
        optional=False,
        retention=0,
    ):
        self.id: str = server_id
        self.newid: Optional[str] = None
        self.restart: bool = False
        self.displayname: str = displayname
        self.host: str = host
        self.port: int = port
        self.timeout: int = timeout
        self.threads: int = threads  # Total number of configured connections, not dynamic
        self.priority: int = priority
        self.ssl: bool = use_ssl
        self.ssl_verify: int = ssl_verify
        self.ssl_ciphers: str = ssl_ciphers
        self.ssl_context: Optional[ssl.SSLContext] = None
        self.required: bool = required
        self.optional: bool = optional
        self.retention: int = retention
        self.username: Optional[str] = username
        self.password: Optional[str] = password
        self.pipelining_requests: Callable[[], int] = pipelining_requests

        self.busy_threads: set[NewsWrapper] = set()
        self.next_busy_threads_check: float = 0
        self.idle_threads: set[NewsWrapper] = set()
        self.next_article_search: float = 0
        self.active: bool = True
        self.bad_cons: int = 0
        self.errormsg: str = ""
        self.warning: str = ""
        self.addrinfo: Union[AddrInfo, None, bool] = None  # Will hold fasted address information
        self.ssl_info: str = ""  # Will hold the type and cipher of SSL connection
        self.request: bool = False  # True if a getaddrinfo() request is pending
        self.have_body: bool = True  # Assume server has "BODY", until proven otherwise
        self.have_stat: bool = True  # Assume server has "STAT", until proven otherwise
        self.article_queue: Deque[sabnzbd.nzb.Article] = deque()

        # Skip during server testing
        if threads:
            # Initialize threads
            for i in range(threads):
                self.idle_threads.add(NewsWrapper(self, i + 1))

            # Tell the BPSMeter about this server
            sabnzbd.BPSMeter.init_server_stats(self.id)

    def deactivate(self):
        """Deactivate server and reset queued articles"""
        self.active = False
        self.reset_article_queue()

    def stop(self):
        """Remove all connections and cached articles from server"""
        for nw in self.idle_threads:
            nw.hard_reset()
        self.idle_threads = set()
        self.reset_article_queue()

    @synchronized(DOWNLOADER_LOCK)
    def get_article(self, peek: bool = False):
        """Get article from pre-fetched and pre-fetch new ones if necessary.
        Articles that are too old for this server are immediately marked as tried"""
        if self.article_queue:
            return self.article_queue[0] if peek else self.article_queue.popleft()

        if self.next_article_search < time.time():
            # Pre-fetch new articles
            sabnzbd.NzbQueue.get_articles(self, sabnzbd.Downloader.servers, _ARTICLE_PREFETCH)
            if self.article_queue:
                article = self.article_queue[0] if peek else self.article_queue.popleft()
                # Mark expired articles as tried on this server
                if self.retention and article.nzf.nzo.avg_stamp < time.time() - self.retention:
                    if not peek:
                        sabnzbd.Downloader.decode(article)
                    # sabnzbd.NzbQueue.get_articles stops after each nzo with articles.
                    # As a result, if one article is out of retention, all remaining
                    # entries in article_queue will also be out of retention.
                    while self.article_queue:
                        sabnzbd.Downloader.decode(self.article_queue.pop())
                else:
                    return article
            else:
                # No available articles, skip this server for a short time
                self.next_article_search = time.time() + _SERVER_CHECK_DELAY
        return None

    @synchronized(DOWNLOADER_LOCK)
    def reset_article_queue(self):
        """Reset articles queued for the Server. Locked to prevent
        articles getting stuck in the Server when enabled/disabled"""
        logging.debug("Resetting article queue for %s (%s)", self, self.article_queue)
        while self.article_queue:
            try:
                article = self.article_queue.popleft()
                article.allow_new_fetcher()
            except IndexError:
                pass

    def request_addrinfo(self):
        """Launch async request to resolve server address and select the fastest.
        In some situations this can be slow and result in delayed starts and timeouts on connections.
        Because of this, the results will be cached in the server object."""
        if not self.request:
            self.request = True
            Thread(target=self.request_addrinfo_blocking).start()

    def request_addrinfo_blocking(self):
        """Blocking attempt to run getaddrinfo() and address selection for specified server"""
        logging.debug("Retrieving server address information for %s", self)

        # Disable IPV6 if desired
        family = socket.AF_UNSPEC
        if not cfg.ipv6_servers():
            family = socket.AF_INET

        self.addrinfo = get_fastest_addrinfo(self.host, self.port, self.timeout, family)
        if not self.addrinfo:
            self.bad_cons += self.threads
            # Notify next call to maybe_block_server
            self.addrinfo = False
        else:
            self.bad_cons = 0
        self.request = False
        sabnzbd.Downloader.wakeup()

    def __repr__(self):
        return "<Server: id=%s, host=%s:%s>" % (self.id, self.host, self.port)


class Downloader(Thread):
    """Singleton Downloader Thread"""

    # Improves get/set performance, even though it's inherited from Thread
    # Due to the huge number of get-calls in run(), it can actually make a difference
    __slots__ = (
        "paused",
        "bandwidth_limit",
        "bandwidth_perc",
        "sleep_time",
        "paused_for_postproc",
        "shutdown",
        "server_restarts",
        "force_disconnect",
        "selector",
        "servers",
        "timers",
        "last_max_chunk_size",
        "max_chunk_size",
    )

    def __init__(self, paused=False):
        super().__init__()

        logging.debug("Initializing downloader")

        # Used for scheduled pausing
        self.paused: bool = paused

        # Used for reducing speed, should always be int and not float
        self.bandwidth_limit: int = 0
        self.bandwidth_perc: int = 0
        cfg.bandwidth_perc.callback(self.speed_set)
        cfg.bandwidth_max.callback(self.speed_set)
        self.speed_set()

        # Used to see if we can add a slowdown to the Downloader-loop
        self.sleep_time: float = 0.0
        self.sleep_time_set()
        cfg.downloader_sleep_time.callback(self.sleep_time_set)

        # Sleep check variables
        self.last_max_chunk_size: int = 0
        self.max_chunk_size: int = _DEFAULT_CHUNK_SIZE

        self.paused_for_postproc: bool = False
        self.shutdown: bool = False

        # A user might change server parms again before server restart is ready.
        # Keep a counter to prevent multiple restarts
        self.server_restarts: int = 0

        self.force_disconnect: bool = False

        # macOS/BSD will default to KqueueSelector, it's very efficient but produces separate events for READ and WRITE.
        # Which causes problems when two receive threads are both trying to use the connection while it is resetting.
        if selectors.DefaultSelector is getattr(selectors, "KqueueSelector", None):
            self.selector: selectors.BaseSelector = selectors.PollSelector()
        else:
            self.selector: selectors.BaseSelector = selectors.DefaultSelector()

        self.servers: list[Server] = []
        self.timers: dict[str, list[float]] = {}

        for server in config.get_servers():
            self.init_server(None, server)

    def init_server(self, oldserver: Optional[str], newserver: str):
        """Setup or re-setup single server
        When oldserver is defined and in use, delay startup.
        Note that the server names are "host:port" strings!
        """

        create = False

        servers = config.get_servers()
        if newserver in servers:
            srv = servers[newserver]
            enabled = srv.enable()
            displayname = srv.displayname()
            host = srv.host()
            port = srv.port()
            timeout = srv.timeout()
            threads = srv.connections()
            priority = srv.priority()
            ssl = srv.ssl()
            ssl_verify = srv.ssl_verify()
            ssl_ciphers = srv.ssl_ciphers()
            pipelining_requests = srv.pipelining_requests
            username = srv.username()
            password = srv.password()
            required = srv.required()
            optional = srv.optional()
            retention = int(srv.retention() * 24 * 3600)  # days ==> seconds
            create = True

        if oldserver:
            for server in self.servers:
                if server.id == oldserver:
                    # Server exists, do re-init later
                    create = False
                    server.newid = newserver
                    server.restart = True
                    self.server_restarts += 1
                    break

        if create and enabled and host and port and threads:
            self.servers.append(
                Server(
                    newserver,
                    displayname,
                    host,
                    port,
                    timeout,
                    threads,
                    priority,
                    ssl,
                    ssl_verify,
                    ssl_ciphers,
                    pipelining_requests,
                    username,
                    password,
                    required,
                    optional,
                    retention,
                )
            )

            # Sort the servers for performance
            self.servers.sort(key=lambda svr: "%02d%s" % (svr.priority, svr.displayname.lower()))

    @synchronized(DOWNLOADER_LOCK)
    def add_socket(self, nw: NewsWrapper):
        """Add a socket to be watched for read or write availability"""
        if nw.nntp:
            nw.server.idle_threads.discard(nw)
            nw.server.busy_threads.add(nw)
            try:
                self.selector.register(nw.nntp.fileno, selectors.EVENT_READ | selectors.EVENT_WRITE, nw)
                nw.selector_events = selectors.EVENT_READ | selectors.EVENT_WRITE
            except KeyError:
                pass

    @synchronized(DOWNLOADER_LOCK)
    def modify_socket(self, nw: NewsWrapper, events: int):
        """Modify the events socket are watched for"""
        if nw.nntp and nw.selector_events != events and not nw.blocking:
            try:
                self.selector.modify(nw.nntp.fileno, events, nw)
                nw.selector_events = events
            except KeyError:
                pass

    @synchronized(DOWNLOADER_LOCK)
    def remove_socket(self, nw: NewsWrapper):
        """Remove a socket to be watched"""
        if nw.nntp:
            nw.server.busy_threads.discard(nw)
            nw.server.idle_threads.add(nw)
            nw.timeout = None
            try:
                self.selector.unregister(nw.nntp.fileno)
                nw.selector_events = 0
            except KeyError:
                pass

    @NzbQueueLocker
    def set_paused_state(self, state: bool):
        """Set downloader to new paused state if it is changed"""
        if self.paused != state:
            if cfg.preserve_paused_state():
                cfg.start_paused.set(state)
            self.paused = state

    @NzbQueueLocker
    def resume(self):
        # Do not notify when SABnzbd is still starting
        if self.paused and sabnzbd.WEB_DIR:
            logging.info("Resuming")
            sabnzbd.notifier.send_notification("SABnzbd", T("Resuming"), "pause_resume")
            if cfg.preserve_paused_state():
                cfg.start_paused.set(False)
        self.paused = False

    @NzbQueueLocker
    def pause(self):
        """Pause the downloader, optionally saving admin"""
        if not self.paused:
            self.paused = True
            logging.info("Pausing")
            sabnzbd.notifier.send_notification("SABnzbd", T("Paused"), "pause_resume")
            if cfg.preserve_paused_state():
                cfg.start_paused.set(True)
            if self.no_active_jobs():
                sabnzbd.BPSMeter.reset()
            if cfg.autodisconnect():
                self.disconnect()

    def wait_for_postproc(self):
        logging.info("Waiting for post-processing to finish")
        self.paused_for_postproc = True

    @NzbQueueLocker
    def resume_from_postproc(self):
        if self.paused_for_postproc:
            logging.info("Post-processing finished, resuming download")
            self.paused_for_postproc = False

    @NzbQueueLocker
    def disconnect(self):
        logging.info("Forcing disconnect")
        self.force_disconnect = True

    def limit_speed(self, value: Union[str, int]):
        """Set the actual download speed in Bytes/sec
        When 'value' ends with a '%' sign or is within 1-100, it is interpreted as a percentage of the maximum bandwidth
        When no '%' is found, it is interpreted as an absolute speed (including KMGT notation).
        """
        if value:
            mx = cfg.bandwidth_max.get_int()
            if "%" in str(value) or (0 < from_units(value) < 101):
                limit = value.strip(" %")
                self.bandwidth_perc = int_conv(limit)
                if mx:
                    self.bandwidth_limit = int(mx * self.bandwidth_perc / 100)
                else:
                    helpful_warning(T("You must set a maximum bandwidth before you can set a bandwidth limit"))
            else:
                self.bandwidth_limit = int(from_units(value))
                if mx:
                    self.bandwidth_perc = int(self.bandwidth_limit / mx * 100)
                else:
                    self.bandwidth_perc = 100
        else:
            self.speed_set()
        logging.info("Speed limit set to %s B/s", self.bandwidth_limit)

    def speed_set(self):
        perc = cfg.bandwidth_perc()
        limit = cfg.bandwidth_max.get_int()
        if limit and perc:
            self.bandwidth_perc = int(perc)
            self.bandwidth_limit = int(limit * perc / 100)
        else:
            self.bandwidth_perc = 0
            self.bandwidth_limit = 0

        # Increase limits for faster connections
        if limit > from_units("150M"):
            if cfg.receive_threads() == cfg.receive_threads.default:
                cfg.receive_threads.set(4)
                logging.info("Receive threads set to 4")
            if cfg.assembler_max_queue_size() == cfg.assembler_max_queue_size.default:
                cfg.assembler_max_queue_size.set(30)
                logging.info("Assembler max_queue_size set to 30")

    def sleep_time_set(self):
        self.sleep_time = cfg.downloader_sleep_time() * 0.0001
        logging.debug("Sleep time: %f seconds", self.sleep_time)

    def no_active_jobs(self) -> bool:
        """Is the queue paused or is it paused but are there still forced items?"""
        return self.paused and not sabnzbd.NzbQueue.has_forced_jobs()

    def highest_server(self, me: Server):
        """Return True when this server has the highest priority of the active ones
        0 is the highest priority, servers are sorted by priority.
        """
        for server in self.servers:
            if server.priority == me.priority:
                return True
            if server.active:
                return False

    def maybe_block_server(self, server: Server):
        # Was it resolving problem?
        if server.addrinfo is False:
            # Warn about resolving issues
            errormsg = T("Cannot connect to server %s [%s]") % (server.host, T("Server name does not resolve"))
            if server.errormsg != errormsg:
                server.errormsg = errormsg
                logging.warning(errormsg)
                if not server.required:
                    logging.warning(T("Server %s will be ignored for %s minutes"), server.host, _PENALTY_TIMEOUT)

            # Not fully the same as the code below for optional servers
            server.bad_cons = 0
            if server.required:
                sabnzbd.Scheduler.plan_required_server_resume()
            else:
                server.deactivate()
                self.plan_server(server, _PENALTY_TIMEOUT)

        # Optional and active server had too many problems.
        # Disable it now and send a re-enable plan to the scheduler
        if server.optional and server.active and (server.bad_cons / server.threads) > 0.3:
            # Deactivate server
            server.bad_cons = 0
            server.deactivate()
            logging.warning(T("Server %s will be ignored for %s minutes"), server.host, _PENALTY_TIMEOUT)
            self.plan_server(server, _PENALTY_TIMEOUT)

            # Remove all connections to server
            for nw in server.idle_threads | server.busy_threads:
                self.reset_nw(nw, "Forcing disconnect", warn=False, wait=False, retry_article=False)

            # Make sure server address resolution is refreshed
            server.addrinfo = None

    @staticmethod
    def decode(article: "sabnzbd.nzb.Article", response: Optional[sabctools.NNTPResponse] = None):
        """Decode article"""
        # Need a better way of draining requests
        if article.nzf.nzo.removed_from_queue:
            return

        # Article was requested and fetched, update article stats for the server
        sabnzbd.BPSMeter.register_server_article_tried(article.fetcher.id)

        # Handle broken articles directly
        if not response or not response.bytes_decoded and not article.nzf.nzo.precheck:
            if not article.search_new_server():
                article.nzf.nzo.increase_bad_articles_counter("missing_articles")
                sabnzbd.NzbQueue.register_article(article, success=False)
            return

        # Decode and send to article cache
        sabnzbd.decoder.decode(article, response)

    def run(self):
        # Warn if there are servers defined, but none are valid
        if config.get_servers() and not self.servers:
            logging.warning(T("There are no active servers!"))

        # Kick BPS-Meter to check quota
        BPSMeter = sabnzbd.BPSMeter
        BPSMeter.update()
        next_bpsmeter_update = 0

        # Check server expiration dates
        check_server_expiration()

        # Initialize queue and threads
        process_nw_queue = MultiAddQueue()
        for _ in range(cfg.receive_threads()):
            # Started as daemon, so we don't need any shutdown logic in the worker
            # The Downloader code will make sure shutdown is handled gracefully
            Thread(target=self.process_nw_worker, args=(process_nw_queue,), daemon=True).start()

        # Catch all errors, just in case
        try:
            while 1:
                now = time.time()

                # Set Article to None so references from this
                # thread do not keep the parent objects alive (see #1628)
                article = None

                for server in self.servers:
                    # Skip this server if there's no point searching for new stuff to do
                    if server.addrinfo and not server.busy_threads and server.next_article_search > now:
                        continue

                    if server.next_busy_threads_check < now:
                        server.next_busy_threads_check = now + _SERVER_CHECK_DELAY
                        for nw in server.busy_threads.copy():
                            if (nw.nntp and nw.nntp.error_msg) or (nw.timeout and now > nw.timeout):
                                if nw.nntp and nw.nntp.error_msg:
                                    # Already showed error
                                    self.reset_nw(nw)
                                else:
                                    self.reset_nw(nw, "Timed out", warn=True)
                                server.bad_cons += 1
                                self.maybe_block_server(server)

                    if server.restart:
                        if not server.busy_threads:
                            server.stop()
                            self.servers.remove(server)
                            if newid := server.newid:
                                self.init_server(None, newid)
                            self.server_restarts -= 1
                            # Have to leave this loop, because we removed element
                            break
                        else:
                            # Restart pending, don't add new articles
                            continue

                    if (
                        not server.idle_threads
                        or self.no_active_jobs()
                        or self.shutdown
                        or self.paused_for_postproc
                        or not server.active
                    ):
                        continue

                    for nw in server.idle_threads.copy():
                        if nw.timeout:
                            if now < nw.timeout:
                                continue
                            else:
                                nw.timeout = None

                        if not server.addrinfo:
                            # Only request info if there's stuff in the queue
                            if not sabnzbd.NzbQueue.is_empty():
                                self.maybe_block_server(server)
                                server.request_addrinfo()
                            break

                        if not server.get_article(peek=True):
                            break

                        if nw.connected:
                            # Assign a request immediately if NewsWrapper is ready, if we wait until the socket is
                            # selected all idle connections will be activated when there may only be one request
                            nw.prepare_request()
                            self.add_socket(nw)
                        elif not nw.nntp:
                            try:
                                logging.info("%s@%s: Initiating connection", nw.thrdnum, server.host)
                                nw.init_connect()
                            except Exception:
                                logging.error(
                                    T("Failed to initialize %s@%s with reason: %s"),
                                    nw.thrdnum,
                                    server.host,
                                    sys.exc_info()[1],
                                )
                                self.reset_nw(nw, "Failed to initialize", warn=True)

                if self.force_disconnect or self.shutdown:
                    for server in self.servers:
                        for nw in server.idle_threads | server.busy_threads:
                            # Send goodbye if we have open socket
                            if nw.nntp:
                                self.reset_nw(nw, "Forcing disconnect", wait=False, count_article_try=False)
                        # Make sure server address resolution is refreshed
                        server.addrinfo = None
                        server.reset_article_queue()
                    self.force_disconnect = False

                    # Make sure we update the stats
                    BPSMeter.update()

                    # Exit-point
                    if self.shutdown:
                        logging.info("Shutting down")
                        break

                # If less data than possible was received then it should be ok to sleep a bit
                if self.sleep_time:
                    if self.last_max_chunk_size > self.max_chunk_size:
                        self.max_chunk_size = self.last_max_chunk_size
                    elif self.last_max_chunk_size < self.max_chunk_size / 3:
                        time.sleep(self.sleep_time)
                        now = time.time()
                    self.last_max_chunk_size = 0

                # Use select to find sockets ready for reading/writing
                if self.selector.get_map():
                    if events := self.selector.select(timeout=1.0):
                        for key, ev in events:
                            nw = key.data
                            process_nw_queue.put((nw, ev, nw.generation))
                else:
                    events = []
                    BPSMeter.reset()
                    time.sleep(0.1)
                    self.max_chunk_size = _DEFAULT_CHUNK_SIZE
                    with DOWNLOADER_CV:
                        while (
                            (sabnzbd.NzbQueue.is_empty() or self.no_active_jobs() or self.paused_for_postproc)
                            and not self.shutdown
                            and not self.force_disconnect
                            and not self.server_restarts
                        ):
                            DOWNLOADER_CV.wait()

                if now > next_bpsmeter_update:
                    # Do not update statistics and check levels every loop
                    BPSMeter.update()
                    next_bpsmeter_update = now + _BPSMETER_UPDATE_DELAY
                    self.check_assembler_levels()

                if not events:
                    continue

                # Wait for socket operation completion
                process_nw_queue.join()

        except Exception:
            logging.error(T("Fatal error in Downloader"), exc_info=True)

    def process_nw_worker(self, nw_queue: MultiAddQueue):
        """Worker for the daemon thread to process results.
        Wrapped in try/except because in case of an exception, logging
        might get lost and the queue.join() would block forever."""
        try:
            logging.debug("Starting Downloader receive thread: %s", current_thread().name)
            while True:
                self.process_nw(*nw_queue.get())
                nw_queue.task_done()
        except Exception:
            # We cannot break out of the Downloader from here, so just pause
            logging.error(T("Fatal error in Downloader"), exc_info=True)
            self.pause()

    def process_nw(self, nw: NewsWrapper, event: int, generation: int):
        """Receive data from a NewsWrapper and handle the response"""
        # Drop stale items
        if nw.generation != generation:
            return

        # Read on EVENT_READ, or on EVENT_WRITE if TLS needs a write to complete a read
        if (event & selectors.EVENT_READ) or (event & selectors.EVENT_WRITE and nw.tls_wants_write):
            self.process_nw_read(nw, generation)
            # If read caused a reset, don't proceed to write
            if nw.generation != generation:
                return
            # The read may have removed the socket, so prevent calling prepare_request again
            if not (nw.selector_events & selectors.EVENT_WRITE):
                return

        # Only attempt app-level writes if TLS is not blocked
        if (event & selectors.EVENT_WRITE) and not nw.tls_wants_write:
            nw.write()

    def process_nw_read(self, nw: NewsWrapper, generation: int) -> None:
        bytes_received: int = 0
        bytes_pending: int = 0

        while (
            nw.connected
            and nw.generation == generation
            and not self.force_disconnect
            and not self.shutdown
            and not (nw.timeout and time.time() > nw.timeout)
        ):
            try:
                n, bytes_pending = nw.read(nbytes=bytes_pending, generation=generation)
                bytes_received += n
                nw.tls_wants_write = False
            except ssl.SSLWantReadError:
                return
            except ssl.SSLWantWriteError:
                # TLS needs to write handshake/key-update data before we can continue reading
                nw.tls_wants_write = True
                self.modify_socket(nw, selectors.EVENT_READ | selectors.EVENT_WRITE)
                return
            except (ConnectionError, ConnectionAbortedError):
                # The ConnectionAbortedError is also thrown by sabctools in case of fatal SSL-layer problems
                self.reset_nw(nw, "Server closed connection", wait=False)
                return
            except BufferError:
                # The BufferError is thrown when exceeding maximum buffer size
                # Make sure to discard the article
                self.reset_nw(nw, "Maximum data buffer size exceeded", wait=False, retry_article=False)
                return

            if not bytes_pending:
                break

        # Ignore metrics for reset connections
        if nw.generation != generation:
            return

        server = nw.server

        with DOWNLOADER_LOCK:
            sabnzbd.BPSMeter.update(server.id, bytes_received)
            if bytes_received > self.last_max_chunk_size:
                self.last_max_chunk_size = bytes_received
            # Check speedlimit
            if (
                self.bandwidth_limit
                and sabnzbd.BPSMeter.bps + sabnzbd.BPSMeter.sum_cached_amount > self.bandwidth_limit
            ):
                sabnzbd.BPSMeter.update()
                while self.bandwidth_limit and sabnzbd.BPSMeter.bps > self.bandwidth_limit:
                    time.sleep(0.01)
                    sabnzbd.BPSMeter.update()

    def check_assembler_levels(self):
        """Check the Assembler queue to see if we need to delay, depending on queue size"""
        if not sabnzbd.Assembler.is_busy() or (delay := sabnzbd.Assembler.delay()) <= 0:
            return
        time.sleep(delay)
        sabnzbd.BPSMeter.delayed_assembler += 1
        start_time = time.monotonic()
        deadline = start_time + 5
        next_log = start_time + 1.0
        logged_counter = 0

        while not self.shutdown and sabnzbd.Assembler.is_busy() and time.monotonic() < deadline:
            if (delay := sabnzbd.Assembler.delay()) <= 0:
                break
            # Sleep for the current delay (but cap to remaining time)
            sleep_time = max(0.001, min(delay, deadline - time.monotonic()))
            time.sleep(sleep_time)
            # Make sure the BPS-meter is updated
            sabnzbd.BPSMeter.update()
            # Only log/update once every second
            if time.monotonic() >= next_log:
                logged_counter += 1
                logging.debug(
                    "Delayed - %d seconds - Assembler queue: %s",
                    logged_counter,
                    to_units(sabnzbd.Assembler.total_ready_bytes()),
                )
                next_log += 1.0

    @synchronized(DOWNLOADER_LOCK)
    def finish_connect_nw(self, nw: NewsWrapper, response: sabctools.NNTPResponse) -> bool:
        server = nw.server
        try:
            nw.finish_connect(response.status_code, response.message)
            if sabnzbd.LOG_ALL:
                logging.debug("%s@%s last message -> %d", nw.thrdnum, server.host, response.status_code)
        except NNTPPermanentError as error:
            # Handle login problems
            block = False
            penalty = 0
            errormsg = None
            logging.debug("Server login problem: %s", error.msg)
            if error.code in (502, 400, 481, 482) and clues_too_many(error.msg):
                # Too many connections: remove this thread and reduce thread-setting for server
                # Plan to go back to the full number after a penalty timeout
                errormsg = T("Too many connections to server %s [%s]") % (server.host, error.msg)
                if server.active:
                    # Don't count this for the tries (max_art_tries) on this server
                    self.reset_nw(nw)
                    self.plan_server(server, _PENALTY_TOOMANY)
            elif error.code in (502, 481, 482) and clues_too_many_ip(error.msg):
                # Login from (too many) different IP addresses
                errormsg = T(
                    "Login from too many different IP addresses to server %s [%s] - https://sabnzbd.org/multiple-adresses"
                ) % (server.host, error.msg)
                penalty = _PENALTY_SHARE
                block = True
            elif error.code in (452, 481, 482, 381) or (error.code in (500, 502) and clues_login(error.msg)):
                # Cannot login, block this server
                errormsg = T("Failed login for server %s [%s]") % (server.host, error.msg)
                penalty = _PENALTY_PERM
                block = True
            elif error.code in (502, 482):
                # Cannot connect (other reasons), block this server
                errormsg = T("Cannot connect to server %s [%s]") % (server.host, error.msg)
                if clues_pay(error.msg):
                    penalty = _PENALTY_PERM
                else:
                    penalty = _PENALTY_502
                block = True
            elif error.code == 400:
                # Temp connection problem?
                logging.debug("Unspecified error 400 from server %s", server.host)
                penalty = _PENALTY_VERYSHORT
                block = True
            else:
                # Unknown error, just keep trying
                errormsg = T("Cannot connect to server %s [%s]") % (server.host, error.msg)
                penalty = _PENALTY_UNKNOWN
                block = True

            # Set error for server and warn user if it was first time thrown
            if errormsg and server.active and server.errormsg != errormsg:
                server.errormsg = errormsg
                logging.warning(errormsg)

            # Take action on the problem
            if block or (penalty and server.optional):
                retry_article = False
                if server.active:
                    if server.required:
                        sabnzbd.Scheduler.plan_required_server_resume()
                        retry_article = True
                    else:
                        server.deactivate()
                        if penalty and (block or server.optional):
                            self.plan_server(server, penalty)
                # Note that the article is discard for this server if the server is not required
                self.reset_nw(nw, retry_article=retry_article)
            return False
        except Exception as err:
            logging.error(
                T("Connecting %s@%s failed, message=%s"),
                nw.thrdnum,
                nw.server.host,
                err,
            )
            logging.info("Traceback: ", exc_info=True)
            # No reset-warning needed, above logging is sufficient
            self.reset_nw(nw, retry_article=False)
        return True

    @synchronized(DOWNLOADER_LOCK)
    def reset_nw(
        self,
        nw: NewsWrapper,
        reset_msg: Optional[str] = None,
        warn: bool = False,
        wait: bool = True,
        count_article_try: bool = True,
        retry_article: bool = True,
        article: Optional["sabnzbd.nzb.Article"] = None,
    ):
        # Some warnings are errors, and not added as server.warning
        if warn and reset_msg:
            nw.server.warning = reset_msg
            logging.info("Thread %s@%s: %s", nw.thrdnum, nw.server.host, reset_msg)
        elif reset_msg:
            logging.debug("Thread %s@%s: %s", nw.thrdnum, nw.server.host, reset_msg)

        # Discard the article request which failed
        nw.discard(article, count_article_try=count_article_try, retry_article=retry_article)

        # Reset connection object
        nw.hard_reset(wait)

        # Empty SSL info, it might change on next connect
        nw.server.ssl_info = ""

    # ------------------------------------------------------------------------------
    # Timed restart of servers admin.
    # For each server all planned events are kept in a list.
    # When the first timer of a server fires, all other existing timers
    # are neutralized.
    # Each server has a dictionary entry, consisting of a list of timestamps.

    @synchronized(TIMER_LOCK)
    def plan_server(self, server: Server, interval: int):
        """Plan the restart of a server in 'interval' minutes"""
        if cfg.no_penalties() and interval > _PENALTY_SHORT:
            # Overwrite in case of no_penalties
            interval = _PENALTY_SHORT

        logging.debug("Set planned server resume %s in %s mins", server.host, interval)
        if server.id not in self.timers:
            self.timers[server.id] = []
        stamp = time.time() + 60.0 * interval
        self.timers[server.id].append(stamp)
        if interval:
            sabnzbd.Scheduler.plan_server(self.trigger_server, [server.id, stamp], interval)

    @synchronized(TIMER_LOCK)
    def trigger_server(self, server_id: str, timestamp: float):
        """Called by scheduler, start server if timer still valid"""
        logging.debug("Trigger planned server resume for server-id %s", server_id)
        if server_id in self.timers:
            if timestamp in self.timers[server_id]:
                del self.timers[server_id]
                self.init_server(server_id, server_id)

    @NzbQueueLocker
    @synchronized(TIMER_LOCK)
    def unblock(self, server_id: str):
        # Remove timer
        try:
            del self.timers[server_id]
        except KeyError:
            pass
        # Activate server if it was inactive
        for server in self.servers:
            if server.id == server_id and not server.active:
                logging.debug("Unblock server %s", server.host)
                self.init_server(server_id, server_id)
                break

    def unblock_all(self):
        for server_id in self.timers.keys():
            self.unblock(server_id)

    @NzbQueueLocker
    @synchronized(TIMER_LOCK)
    def check_timers(self):
        """Make sure every server without a non-expired timer is active"""
        # Clean expired timers
        now = time.time()
        kicked = []
        # Create a copy so we can remove during iteration
        for server_id in list(self.timers):
            if not [stamp for stamp in self.timers[server_id] if stamp >= now]:
                logging.debug("Forcing re-evaluation of server-id %s", server_id)
                del self.timers[server_id]
                self.init_server(server_id, server_id)
                kicked.append(server_id)
        # Activate every inactive server without an active timer
        for server in self.servers:
            if server.id not in self.timers:
                if server.id not in kicked and not server.active:
                    logging.debug("Forcing activation of server %s", server.host)
                    self.init_server(server.id, server.id)

    def update_server(self, oldserver: str, newserver: Optional[str]):
        """Update the server and make sure we trigger
        the update in the loop to do housekeeping"""
        self.init_server(oldserver, newserver)
        self.wakeup()

    @NzbQueueLocker
    def wakeup(self):
        """Just rattle the semaphore"""
        pass

    @NzbQueueLocker
    def stop(self):
        """Shutdown, wrapped so the semaphore is notified"""
        self.shutdown = True
        sabnzbd.notifier.send_notification("SABnzbd", T("Shutting down"), "startup")


def clues_login(text: str) -> bool:
    """Check for any "failed login" clues in the response code"""
    text = text.lower()
    for clue in ("username", "password", "invalid", "authen", "access denied"):
        if clue in text:
            return True
    return False


def clues_too_many(text: str) -> bool:
    """Check for any "too many connections" clues in the response code"""
    text = text.lower()
    for clue in ("exceed", "connections", "too many", "threads", "limit"):
        # Not 'download limit exceeded' error
        if (clue in text) and ("download" not in text) and ("byte" not in text):
            return True
    return False


def clues_too_many_ip(text: str) -> bool:
    """Check for any "account sharing" clues in the response code"""
    text = text.lower()
    for clue in ("simultaneous ip", "multiple ip"):
        if clue in text:
            return True
    return False


def clues_pay(text: str) -> bool:
    """Check for messages about payments"""
    text = text.lower()
    for clue in ("credits", "paym", "expired", "exceeded"):
        if clue in text:
            return True
    return False


def check_server_expiration():
    """Check if user should get warning about server date expiration"""
    for server in config.get_servers().values():
        if server.expire_date():
            try:
                days_to_expire = (date.fromisoformat(server.expire_date()) - date.today()).days
            except ValueError:
                # In case of invalid date, just warn
                days_to_expire = 0

            # Notify from 5 days in advance
            if days_to_expire < 6:
                logging.warning(T("Server %s is expiring in %s day(s)"), server.displayname(), days_to_expire)
                # Reset on the day of expiration
                if days_to_expire <= 0:
                    server.expire_date.set("")
                    config.save_config()


def check_server_quota():
    """Check quota on servers"""
    for srv, server in config.get_servers().items():
        if server.quota():
            if server.quota.get_int() + server.usage_at_start() < sabnzbd.BPSMeter.grand_total.get(srv, 0):
                logging.warning(T("Server %s has used the specified quota"), server.displayname())
                sabnzbd.notifier.send_notification(
                    T("Quota"),
                    T("Server %s has used the specified quota") % server.displayname(),
                    "quota",
                )
                server.quota.set("")
                config.save_config()


def pause_all():
    """Pause all activities than cause disk access"""
    sabnzbd.PAUSED_ALL = True
    sabnzbd.Downloader.pause()
    logging.debug("PAUSED_ALL active")


def unpause_all():
    """Resume all activities"""
    sabnzbd.PAUSED_ALL = False
    sabnzbd.Downloader.resume()
    logging.debug("PAUSED_ALL inactive")
