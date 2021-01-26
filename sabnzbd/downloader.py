#!/usr/bin/python3 -OO
# Copyright 2007-2021 The SABnzbd-Team <team@sabnzbd.org>
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

import time
import select
import logging
from math import ceil
from threading import Thread, RLock
from nntplib import NNTPPermanentError
import socket
import random
import sys
from typing import List, Dict, Optional, Union

import sabnzbd
from sabnzbd.decorators import synchronized, NzbQueueLocker, DOWNLOADER_CV
from sabnzbd.newswrapper import NewsWrapper
import sabnzbd.notifier
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.misc import from_units, nntp_to_msg, int_conv, get_server_addrinfo
from sabnzbd.utils.happyeyeballs import happyeyeballs


# Timeout penalty in minutes for each cause
_PENALTY_UNKNOWN = 3  # Unknown cause
_PENALTY_502 = 5  # Unknown 502
_PENALTY_TIMEOUT = 10  # Server doesn't give an answer (multiple times)
_PENALTY_SHARE = 10  # Account sharing detected
_PENALTY_TOOMANY = 10  # Too many connections
_PENALTY_PERM = 10  # Permanent error, like bad username/password
_PENALTY_SHORT = 1  # Minimal penalty when no_penalties is set
_PENALTY_VERYSHORT = 0.1  # Error 400 without cause clues


TIMER_LOCK = RLock()


class Server:
    def __init__(
        self,
        server_id,
        displayname,
        host,
        port,
        timeout,
        threads,
        priority,
        ssl,
        ssl_verify,
        ssl_ciphers,
        send_group,
        username=None,
        password=None,
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
        self.threads: int = threads
        self.priority: int = priority
        self.ssl: bool = ssl
        self.ssl_verify: int = ssl_verify
        self.ssl_ciphers: str = ssl_ciphers
        self.optional: bool = optional
        self.retention: int = retention
        self.send_group: bool = send_group

        self.username: Optional[str] = username
        self.password: Optional[str] = password

        self.busy_threads: List[NewsWrapper] = []
        self.idle_threads: List[NewsWrapper] = []
        self.next_article_search: int = 0
        self.active: bool = True
        self.bad_cons: int = 0
        self.errormsg: str = ""
        self.warning: str = ""
        self.info: Optional[List] = None  # Will hold getaddrinfo() list
        self.ssl_info: str = ""  # Will hold the type and cipher of SSL connection
        self.request: bool = False  # True if a getaddrinfo() request is pending
        self.have_body: bool = True  # Assume server has "BODY", until proven otherwise
        self.have_stat: bool = True  # Assume server has "STAT", until proven otherwise

        for i in range(threads):
            self.idle_threads.append(NewsWrapper(self, i + 1))

    @property
    def hostip(self) -> str:
        """In case a server still has active connections, we use the same IP again
        If new connection then based on value of load_balancing() and self.info:
        0 - return the first entry, so all threads use the same IP
        1 - and self.info has more than 1 entry (read: IP address): Return a random entry from the possible IPs
        2 - and self.info has more than 1 entry (read: IP address): Return the quickest IP based on the happyeyeballs algorithm
        In case of problems: return the host name itself
        """
        # Check if already a successful ongoing connection
        if self.busy_threads and self.busy_threads[0].nntp:
            # Re-use that IP
            logging.debug("%s: Re-using address %s", self.host, self.busy_threads[0].nntp.host)
            return self.busy_threads[0].nntp.host

        # Determine IP
        ip = self.host
        if self.info:
            if cfg.load_balancing() == 0 or len(self.info) == 1:
                # Just return the first one, so all next threads use the same IP
                ip = self.info[0][4][0]
                logging.debug("%s: Connecting to address %s", self.host, ip)
            elif cfg.load_balancing() == 1:
                # Return a random entry from the possible IPs
                rnd = random.randint(0, len(self.info) - 1)
                ip = self.info[rnd][4][0]
                logging.debug("%s: Connecting to address %s", self.host, ip)
            elif cfg.load_balancing() == 2:
                # RFC6555 / Happy Eyeballs:
                ip = happyeyeballs(self.host, port=self.port, ssl=self.ssl)
                if ip:
                    logging.debug("%s: Connecting to address %s", self.host, ip)
                else:
                    # nothing returned, so there was a connection problem
                    logging.debug("%s: No successful IP connection was possible", self.host)
        return ip

    def stop(self):
        """Remove all connections from server"""
        for nw in self.idle_threads:
            sabnzbd.Downloader.remove_socket(nw)
            nw.hard_reset(send_quit=True)
        self.idle_threads = []

    def request_info(self):
        """Launch async request to resolve server address.
        getaddrinfo() can be very slow. In some situations this can lead
        to delayed starts and timeouts on connections.
        Because of this, the results will be cached in the server object."""
        if not self.request:
            self.request = True
            Thread(target=self._request_info_internal).start()

    def _request_info_internal(self):
        """ Async attempt to run getaddrinfo() for specified server """
        logging.debug("Retrieving server address information for %s", self.host)
        self.info = get_server_addrinfo(self.host, self.port)
        if not self.info:
            self.bad_cons += self.threads
        else:
            self.bad_cons = 0
        self.request = False
        sabnzbd.Downloader.wakeup()

    def __repr__(self):
        return "<Server: %s:%s>" % (self.host, self.port)


class Downloader(Thread):
    """ Singleton Downloader Thread """

    def __init__(self, paused=False):
        super().__init__()

        logging.debug("Initializing downloader")

        # Used for scheduled pausing
        self.paused: bool = paused

        # Used for reducing speed
        self.bandwidth_limit: int = 0
        self.bandwidth_perc: int = 0
        cfg.bandwidth_perc.callback(self.speed_set)
        cfg.bandwidth_max.callback(self.speed_set)
        self.speed_set()

        # Used to see if we can add a slowdown to the Downloader-loop
        self.can_be_slowed: Optional[bool] = None
        self.can_be_slowed_timer: int = 0
        self.sleep_time: float = 0.0
        self.sleep_time_set()
        cfg.downloader_sleep_time.callback(self.sleep_time_set)

        self.paused_for_postproc: bool = False
        self.shutdown: bool = False

        # A user might change server parms again before server restart is ready.
        # Keep a counter to prevent multiple restarts
        self.server_restarts: int = 0

        self.force_disconnect: bool = False

        self.read_fds: Dict[int, NewsWrapper] = {}

        self.servers: List[Server] = []
        self.server_dict: Dict[str, Server] = {}  # For faster lookups, but is not updated later!
        self.server_nr: int = 0
        self.timers: Dict[str, List[float]] = {}

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
            username = srv.username()
            password = srv.password()
            optional = srv.optional()
            retention = int(srv.retention() * 24 * 3600)  # days ==> seconds
            send_group = srv.send_group()
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
            server = Server(
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
                send_group,
                username,
                password,
                optional,
                retention,
            )
            self.servers.append(server)
            self.server_dict[newserver] = server

        # Update server-count
        self.server_nr = len(self.servers)

    def add_socket(self, fileno: int, nw: NewsWrapper):
        """ Add a socket ready to be used to the list to be watched """
        self.read_fds[fileno] = nw

    def remove_socket(self, nw: NewsWrapper):
        """ Remove a socket to be watched """
        if nw.nntp:
            self.read_fds.pop(nw.nntp.fileno, None)

    @NzbQueueLocker
    def set_paused_state(self, state: bool):
        """ Set downloader to specified paused state """
        self.paused = state

    @NzbQueueLocker
    def resume(self):
        # Do not notify when SABnzbd is still starting
        if self.paused and sabnzbd.WEB_DIR:
            logging.info("Resuming")
            sabnzbd.notifier.send_notification("SABnzbd", T("Resuming"), "pause_resume")
        self.paused = False

    @NzbQueueLocker
    def pause(self):
        """ Pause the downloader, optionally saving admin """
        if not self.paused:
            self.paused = True
            logging.info("Pausing")
            sabnzbd.notifier.send_notification("SABnzbd", T("Paused"), "pause_resume")
            if self.is_paused():
                sabnzbd.BPSMeter.reset()
            if cfg.autodisconnect():
                self.disconnect()

    def wait_for_postproc(self):
        logging.info("Waiting for post-processing to finish")
        self.paused_for_postproc = True

    @NzbQueueLocker
    def resume_from_postproc(self):
        logging.info("Post-processing finished, resuming download")
        self.paused_for_postproc = False

    def disconnect(self):
        self.force_disconnect = True

    def limit_speed(self, value: Union[str, int]):
        """Set the actual download speed in Bytes/sec
        When 'value' ends with a '%' sign or is within 1-100, it is interpreted as a pecentage of the maximum bandwidth
        When no '%' is found, it is interpreted as an absolute speed (including KMGT notation).
        """
        if value:
            mx = cfg.bandwidth_max.get_int()
            if "%" in str(value) or (0 < from_units(value) < 101):
                limit = value.strip(" %")
                self.bandwidth_perc = from_units(limit)
                if mx:
                    self.bandwidth_limit = mx * self.bandwidth_perc / 100
                else:
                    logging.warning_helpful(T("You must set a maximum bandwidth before you can set a bandwidth limit"))
            else:
                self.bandwidth_limit = from_units(value)
                if mx:
                    self.bandwidth_perc = self.bandwidth_limit / mx * 100
                else:
                    self.bandwidth_perc = 100
        else:
            self.speed_set()
        logging.info("Speed limit set to %s B/s", self.bandwidth_limit)

    def get_limit(self):
        return self.bandwidth_perc

    def get_limit_abs(self):
        return self.bandwidth_limit

    def speed_set(self):
        limit = cfg.bandwidth_max.get_int()
        perc = cfg.bandwidth_perc()
        if limit and perc:
            self.bandwidth_perc = perc
            self.bandwidth_limit = limit * perc / 100
        else:
            self.bandwidth_perc = 0
            self.bandwidth_limit = 0

    def sleep_time_set(self):
        self.sleep_time = cfg.downloader_sleep_time() * 0.0001
        logging.debug("Sleep time: %f seconds", self.sleep_time)

    def is_paused(self):
        if not self.paused:
            return False
        else:
            if sabnzbd.NzbQueue.has_forced_items():
                return False
            else:
                return True

    def highest_server(self, me: Server):
        """Return True when this server has the highest priority of the active ones
        0 is the highest priority
        """
        for server in self.servers:
            if server is not me and server.active and server.priority < me.priority:
                return False
        return True

    def nzo_servers(self, nzo):
        return list(filter(nzo.server_in_try_list, self.servers))

    def maybe_block_server(self, server: Server):
        # Was it resolving problem?
        if server.info is False:
            # Warn about resolving issues
            errormsg = T("Cannot connect to server %s [%s]") % (server.host, T("Server name does not resolve"))
            if server.errormsg != errormsg:
                server.errormsg = errormsg
                logging.warning(errormsg)
                logging.warning(T("Server %s will be ignored for %s minutes"), server.host, _PENALTY_TIMEOUT)

            # Not fully the same as the code below for optional servers
            server.bad_cons = 0
            server.active = False
            self.plan_server(server, _PENALTY_TIMEOUT)

        # Optional and active server had too many problems.
        # Disable it now and send a re-enable plan to the scheduler
        if server.optional and server.active and (server.bad_cons / server.threads) > 3:
            server.bad_cons = 0
            server.active = False
            logging.warning(T("Server %s will be ignored for %s minutes"), server.host, _PENALTY_TIMEOUT)
            self.plan_server(server, _PENALTY_TIMEOUT)

            # Remove all connections to server
            for nw in server.idle_threads + server.busy_threads:
                self.__reset_nw(
                    nw, "forcing disconnect", warn=False, wait=False, count_article_try=False, send_quit=False
                )

            # Make sure server address resolution is refreshed
            server.info = None

    def decode(self, article, raw_data: Optional[List[bytes]]):
        """Decode article and check the status of
        the decoder and the assembler
        """
        # Article was requested and fetched, update article stats for the server
        sabnzbd.BPSMeter.register_server_article_tried(article.fetcher.id)

        # Handle broken articles directly
        if not raw_data:
            if not article.search_new_server():
                sabnzbd.NzbQueue.register_article(article, success=False)
            return

        # Send to decoder-queue
        sabnzbd.Decoder.process(article, raw_data)

        # See if we need to delay because the queues are full
        logged = False
        while not self.shutdown and (sabnzbd.Decoder.queue_full() or sabnzbd.Assembler.queue_full()):
            if not logged:
                # Only log once, to not waste any CPU-cycles
                logging.debug(
                    "Delaying - Decoder queue: %s - Assembler queue: %s",
                    sabnzbd.Decoder.decoder_queue.qsize(),
                    sabnzbd.Assembler.queue.qsize(),
                )
                logged = True
            time.sleep(0.01)

    def run(self):
        # First check IPv6 connectivity
        sabnzbd.EXTERNAL_IPV6 = sabnzbd.test_ipv6()
        logging.debug("External IPv6 test result: %s", sabnzbd.EXTERNAL_IPV6)

        # Then we check SSL certificate checking
        sabnzbd.CERTIFICATE_VALIDATION = sabnzbd.test_cert_checking()
        logging.debug("SSL verification test: %s", sabnzbd.CERTIFICATE_VALIDATION)

        # Kick BPS-Meter to check quota
        sabnzbd.BPSMeter.update()

        # Check server expiration dates
        check_server_expiration()

        while 1:
            now = time.time()

            # Set Article to None so references from this
            # thread do not keep the parent objects alive (see #1628)
            article = None

            for server in self.servers:
                # Skip this server if there's no point searching for new stuff to do
                if server.next_article_search > now:
                    continue

                for nw in server.busy_threads[:]:
                    if (nw.nntp and nw.nntp.error_msg) or (nw.timeout and now > nw.timeout):
                        if nw.nntp and nw.nntp.error_msg:
                            # Already showed error
                            self.__reset_nw(nw)
                        else:
                            self.__reset_nw(nw, "timed out", warn=True)
                        server.bad_cons += 1
                        self.maybe_block_server(server)

                if server.restart:
                    if not server.busy_threads:
                        newid = server.newid
                        server.stop()
                        self.servers.remove(server)
                        if newid:
                            self.init_server(None, newid)
                        self.server_restarts -= 1
                        # Have to leave this loop, because we removed element
                        break
                    else:
                        # Restart pending, don't add new articles
                        continue

                if (
                    not server.idle_threads
                    or server.restart
                    or self.is_paused()
                    or self.shutdown
                    or self.paused_for_postproc
                    or not server.active
                ):
                    continue

                for nw in server.idle_threads[:]:
                    if nw.timeout:
                        if now < nw.timeout:
                            continue
                        else:
                            nw.timeout = None

                    if not server.info:
                        # Only request info if there's stuff in the queue
                        if not sabnzbd.NzbQueue.is_empty():
                            self.maybe_block_server(server)
                            server.request_info()
                        break

                    article = sabnzbd.NzbQueue.get_article(server, self.servers)

                    if not article:
                        # Skip this server for 1 second
                        server.next_article_search = now + 1
                        break

                    if server.retention and article.nzf.nzo.avg_stamp < now - server.retention:
                        # Let's get rid of all the articles for this server at once
                        logging.info("Job %s too old for %s, moving on", article.nzf.nzo.final_name, server.host)
                        while article:
                            self.decode(article, None)
                            article = article.nzf.nzo.get_article(server, self.servers)
                        break

                    server.idle_threads.remove(nw)
                    server.busy_threads.append(nw)

                    nw.article = article

                    if nw.connected:
                        self.__request_article(nw)
                    else:
                        try:
                            logging.info("%s@%s: Initiating connection", nw.thrdnum, server.host)
                            nw.init_connect()
                        except:
                            logging.error(
                                T("Failed to initialize %s@%s with reason: %s"),
                                nw.thrdnum,
                                server.host,
                                sys.exc_info()[1],
                            )
                            self.__reset_nw(nw, "failed to initialize", warn=True)

            if self.force_disconnect or self.shutdown:
                for server in self.servers:
                    for nw in server.idle_threads + server.busy_threads:
                        # Send goodbye if we have open socket
                        if nw.nntp:
                            self.__reset_nw(
                                nw,
                                "forcing disconnect",
                                wait=False,
                                count_article_try=False,
                                send_quit=True,
                            )
                    # Make sure server address resolution is refreshed
                    server.info = None
                self.force_disconnect = False

                # Exit-point
                if self.shutdown:
                    logging.info("Shutting down")
                    break

            # Use select to find sockets ready for reading/writing
            readkeys = self.read_fds.keys()
            if readkeys:
                read, _, _ = select.select(readkeys, (), (), 1.0)

                # Add a sleep if there are too few results compared to the number of active connections
                if self.can_be_slowed and len(read) < 1 + len(readkeys) / 10:
                    time.sleep(self.sleep_time)

                # Need to initialize the check during first 20 seconds
                if self.can_be_slowed is None or self.can_be_slowed_timer:
                    # Wait for stable speed to start testing
                    if not self.can_be_slowed_timer and sabnzbd.BPSMeter.get_stable_speed(timespan=10):
                        self.can_be_slowed_timer = time.time()

                    # Check 10 seconds after enabling slowdown
                    if self.can_be_slowed_timer and time.time() > self.can_be_slowed_timer + 10:
                        # Now let's check if it was stable in the last 10 seconds
                        self.can_be_slowed = sabnzbd.BPSMeter.get_stable_speed(timespan=10)
                        self.can_be_slowed_timer = 0
                        logging.debug("Downloader-slowdown: %r", self.can_be_slowed)

            else:
                read = []

                sabnzbd.BPSMeter.reset()

                time.sleep(1.0)

                with DOWNLOADER_CV:
                    while (
                        (sabnzbd.NzbQueue.is_empty() or self.is_paused() or self.paused_for_postproc)
                        and not self.shutdown
                        and not self.server_restarts
                    ):
                        DOWNLOADER_CV.wait()

                self.force_disconnect = False

            if not read:
                sabnzbd.BPSMeter.update()
                continue

            for selected in read:
                nw = self.read_fds[selected]
                article = nw.article
                server = nw.server

                try:
                    bytes_received, done, skip = nw.recv_chunk()
                except:
                    bytes_received, done, skip = (0, False, False)

                if skip:
                    sabnzbd.BPSMeter.update()
                    continue

                if bytes_received < 1:
                    self.__reset_nw(nw, "server closed connection", wait=False)
                    continue

                else:
                    try:
                        article.nzf.nzo.update_download_stats(sabnzbd.BPSMeter.bps, server.id, bytes_received)
                    except AttributeError:
                        # In case nzf has disappeared because the file was deleted before the update could happen
                        pass

                    if self.bandwidth_limit:
                        limit = self.bandwidth_limit
                        if bytes_received + sabnzbd.BPSMeter.bps > limit:
                            while sabnzbd.BPSMeter.bps > limit:
                                time.sleep(0.01)
                                sabnzbd.BPSMeter.update()
                    sabnzbd.BPSMeter.update(server.id, bytes_received)

                if not done and nw.status_code != 222:
                    if not nw.connected or nw.status_code == 480:
                        done = False
                        try:
                            nw.finish_connect(nw.status_code)
                            if sabnzbd.LOG_ALL:
                                logging.debug(
                                    "%s@%s last message -> %s", nw.thrdnum, nw.server.host, nntp_to_msg(nw.data)
                                )
                            nw.clear_data()
                        except NNTPPermanentError as error:
                            # Handle login problems
                            block = False
                            penalty = 0
                            msg = error.response
                            ecode = int_conv(msg[:3])
                            display_msg = " [%s]" % msg
                            logging.debug("Server login problem: %s, %s", ecode, msg)
                            if ecode in (502, 400, 481, 482) and clues_too_many(msg):
                                # Too many connections: remove this thread and reduce thread-setting for server
                                # Plan to go back to the full number after a penalty timeout
                                if server.active:
                                    errormsg = T("Too many connections to server %s") % display_msg
                                    if server.errormsg != errormsg:
                                        server.errormsg = errormsg
                                        logging.warning(T("Too many connections to server %s"), server.host)
                                    # Don't count this for the tries (max_art_tries) on this server
                                    self.__reset_nw(nw, count_article_try=False, send_quit=True)
                                    self.plan_server(server, _PENALTY_TOOMANY)
                                    server.threads -= 1
                            elif ecode in (502, 481, 482) and clues_too_many_ip(msg):
                                # Account sharing?
                                if server.active:
                                    errormsg = T("Probable account sharing") + display_msg
                                    if server.errormsg != errormsg:
                                        server.errormsg = errormsg
                                        name = " (%s)" % server.host
                                        logging.warning(T("Probable account sharing") + name)
                                penalty = _PENALTY_SHARE
                                block = True
                            elif ecode in (452, 481, 482, 381) or (ecode == 502 and clues_login(msg)):
                                # Cannot login, block this server
                                if server.active:
                                    errormsg = T("Failed login for server %s") % display_msg
                                    if server.errormsg != errormsg:
                                        server.errormsg = errormsg
                                        logging.error(T("Failed login for server %s"), server.host)
                                penalty = _PENALTY_PERM
                                block = True
                            elif ecode in (502, 482):
                                # Cannot connect (other reasons), block this server
                                if server.active:
                                    errormsg = T("Cannot connect to server %s [%s]") % ("", display_msg)
                                    if server.errormsg != errormsg:
                                        server.errormsg = errormsg
                                        logging.warning(T("Cannot connect to server %s [%s]"), server.host, msg)
                                if clues_pay(msg):
                                    penalty = _PENALTY_PERM
                                else:
                                    penalty = _PENALTY_502
                                block = True
                            elif ecode == 400:
                                # Temp connection problem?
                                if server.active:
                                    logging.debug("Unspecified error 400 from server %s", server.host)
                                penalty = _PENALTY_VERYSHORT
                                block = True
                            else:
                                # Unknown error, just keep trying
                                if server.active:
                                    errormsg = T("Cannot connect to server %s [%s]") % ("", display_msg)
                                    if server.errormsg != errormsg:
                                        server.errormsg = errormsg
                                        logging.warning(T("Cannot connect to server %s [%s]"), server.host, msg)
                                penalty = _PENALTY_UNKNOWN
                                block = True
                            if block or (penalty and server.optional):
                                if server.active:
                                    server.active = False
                                    if penalty and (block or server.optional):
                                        self.plan_server(server, penalty)
                                # Note that this will count towards the tries (max_art_tries) on this server!
                                self.__reset_nw(nw, send_quit=True)
                            continue
                        except:
                            logging.error(
                                T("Connecting %s@%s failed, message=%s"),
                                nw.thrdnum,
                                nw.server.host,
                                nntp_to_msg(nw.data),
                            )
                            # No reset-warning needed, above logging is sufficient
                            self.__reset_nw(nw)

                        if nw.connected:
                            logging.info("Connecting %s@%s finished", nw.thrdnum, nw.server.host)
                            self.__request_article(nw)

                    elif nw.status_code == 223:
                        done = True
                        logging.debug("Article <%s> is present", article.article)

                    elif nw.status_code == 211:
                        done = False
                        logging.debug("group command ok -> %s", nntp_to_msg(nw.data))
                        nw.group = nw.article.nzf.nzo.group
                        nw.clear_data()
                        self.__request_article(nw)

                    elif nw.status_code in (411, 423, 430):
                        done = True
                        logging.debug(
                            "Thread %s@%s: Article %s missing (error=%s)",
                            nw.thrdnum,
                            nw.server.host,
                            article.article,
                            nw.status_code,
                        )
                        nw.clear_data()

                    elif nw.status_code == 500:
                        if article.nzf.nzo.precheck:
                            # Assume "STAT" command is not supported
                            server.have_stat = False
                            logging.debug("Server %s does not support STAT", server.host)
                        else:
                            # Assume "BODY" command is not supported
                            server.have_body = False
                            logging.debug("Server %s does not support BODY", server.host)
                        nw.clear_data()
                        self.__request_article(nw)

                if done:
                    # Successful data, clear "bad" counter
                    server.bad_cons = 0
                    server.errormsg = server.warning = ""
                    if sabnzbd.LOG_ALL:
                        logging.debug("Thread %s@%s: %s done", nw.thrdnum, server.host, article.article)
                    self.decode(article, nw.data)

                    # Reset connection for new activity
                    nw.soft_reset()
                    server.busy_threads.remove(nw)
                    server.idle_threads.append(nw)
                    self.remove_socket(nw)

    def __reset_nw(
        self,
        nw: NewsWrapper,
        reset_msg: Optional[str] = None,
        warn: bool = False,
        wait: bool = True,
        count_article_try: bool = True,
        send_quit: bool = False,
    ):
        # Some warnings are errors, and not added as server.warning
        if warn and reset_msg:
            nw.server.warning = reset_msg
            logging.info("Thread %s@%s: %s", nw.thrdnum, nw.server.host, reset_msg)
        elif reset_msg:
            logging.debug("Thread %s@%s: %s", nw.thrdnum, nw.server.host, reset_msg)

        # Make sure this NewsWrapper is in the idle threads
        if nw in nw.server.busy_threads:
            nw.server.busy_threads.remove(nw)
        if nw not in nw.server.idle_threads:
            nw.server.idle_threads.append(nw)

        # Make sure it is not in the readable sockets
        self.remove_socket(nw)

        if nw.article:
            # Only some errors should count towards the total tries for each server
            if (
                count_article_try
                and nw.article.tries > cfg.max_art_tries()
                and (nw.article.fetcher.optional or not cfg.max_art_opt())
            ):
                # Too many tries on this server, consider article missing
                self.decode(nw.article, None)
            else:
                # Allow all servers to iterate over this nzo/nzf again
                sabnzbd.NzbQueue.reset_try_lists(nw.article)

        # Reset connection object
        nw.hard_reset(wait, send_quit=send_quit)

        # Empty SSL info, it might change on next connect
        nw.server.ssl_info = ""

    def __request_article(self, nw: NewsWrapper):
        try:
            nzo = nw.article.nzf.nzo
            if nw.server.send_group and nzo.group != nw.group:
                group = nzo.group
                if sabnzbd.LOG_ALL:
                    logging.debug("Thread %s@%s: GROUP <%s>", nw.thrdnum, nw.server.host, group)
                nw.send_group(group)
            else:
                if sabnzbd.LOG_ALL:
                    logging.debug("Thread %s@%s: BODY %s", nw.thrdnum, nw.server.host, nw.article.article)
                nw.body()
            # Mark as ready to be read
            self.read_fds[nw.nntp.fileno] = nw
        except socket.error as err:
            logging.info("Looks like server closed connection: %s", err)
            self.__reset_nw(nw, "server broke off connection", warn=True, send_quit=False)
        except:
            logging.error(T("Suspect error in downloader"))
            logging.info("Traceback: ", exc_info=True)
            self.__reset_nw(nw, "server broke off connection", warn=True, send_quit=False)

    # ------------------------------------------------------------------------------
    # Timed restart of servers admin.
    # For each server all planned events are kept in a list.
    # When the first timer of a server fires, all other existing timers
    # are neutralized.
    # Each server has a dictionary entry, consisting of a list of timestamps.

    @synchronized(TIMER_LOCK)
    def plan_server(self, server: Server, interval: int):
        """ Plan the restart of a server in 'interval' minutes """
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
        """ Called by scheduler, start server if timer still valid """
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
        """ Make sure every server without a non-expired timer is active """
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
        """ Just rattle the semaphore """
        pass

    @NzbQueueLocker
    def stop(self):
        """ Shutdown, wrapped so the semaphore is notified """
        self.shutdown = True
        sabnzbd.notifier.send_notification("SABnzbd", T("Shutting down"), "startup")


def clues_login(text: str) -> bool:
    """ Check for any "failed login" clues in the response code """
    text = text.lower()
    for clue in ("username", "password", "invalid", "authen", "access denied"):
        if clue in text:
            return True
    return False


def clues_too_many(text: str) -> bool:
    """ Check for any "too many connections" clues in the response code """
    text = text.lower()
    for clue in ("exceed", "connections", "too many", "threads", "limit"):
        # Not 'download limit exceeded' error
        if (clue in text) and ("download" not in text) and ("byte" not in text):
            return True
    return False


def clues_too_many_ip(text: str) -> bool:
    """ Check for any "account sharing" clues in the response code """
    text = text.lower()
    for clue in ("simultaneous ip", "multiple ip"):
        if clue in text:
            return True
    return False


def clues_pay(text: str) -> bool:
    """ Check for messages about payments """
    text = text.lower()
    for clue in ("credits", "paym", "expired", "exceeded"):
        if clue in text:
            return True
    return False


def check_server_expiration():
    """Check if user should get warning about server date expiration"""
    for server in config.get_servers().values():
        if server.expire_date():
            days_to_expire = ceil(
                (time.mktime(time.strptime(server.expire_date(), "%Y-%m-%d")) - time.time()) / (60 * 60 * 24)
            )
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
                server.quota.set("")
                config.save_config()
