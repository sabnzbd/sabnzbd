#!/usr/bin/python -OO
# Copyright 2007-2018 The SABnzbd-Team <team@sabnzbd.org>
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
from threading import Thread, RLock
from nntplib import NNTPPermanentError
import socket
import random
import sys
import queue

import sabnzbd
from sabnzbd.decorators import synchronized, NzbQueueLocker, DOWNLOADER_CV
from sabnzbd.constants import MAX_DECODE_QUEUE, LIMIT_DECODE_QUEUE
from sabnzbd.decoder import Decoder
from sabnzbd.newswrapper import NewsWrapper, request_server_info
from sabnzbd.articlecache import ArticleCache
import sabnzbd.notifier as notifier
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.bpsmeter import BPSMeter
import sabnzbd.scheduler
from sabnzbd.misc import from_units, nntp_to_msg
from sabnzbd.utils.happyeyeballs import happyeyeballs


# Timeout penalty in minutes for each cause
_PENALTY_UNKNOWN = 3      # Unknown cause
_PENALTY_502 = 5          # Unknown 502
_PENALTY_TIMEOUT = 10     # Server doesn't give an answer (multiple times)
_PENALTY_SHARE = 10       # Account sharing detected
_PENALTY_TOOMANY = 10     # Too many connections
_PENALTY_PERM = 10        # Permanent error, like bad username/password
_PENALTY_SHORT = 1        # Minimal penalty when no_penalties is set
_PENALTY_VERYSHORT = 0.1  # Error 400 without cause clues


TIMER_LOCK = RLock()


class Server(object):

    def __init__(self, id, displayname, host, port, timeout, threads, priority, ssl, ssl_verify, ssl_ciphers,
                 send_group, username=None, password=None, optional=False, retention=0):

        self.id = id
        self.newid = None
        self.restart = False
        self.displayname = displayname
        self.host = host
        self.port = port
        self.timeout = timeout
        self.threads = threads
        self.priority = priority
        self.ssl = ssl
        self.ssl_verify = ssl_verify
        self.ssl_ciphers = ssl_ciphers
        self.optional = optional
        self.retention = retention
        self.send_group = send_group

        self.username = username
        self.password = password

        self.busy_threads = []
        self.idle_threads = []
        self.active = True
        self.bad_cons = 0
        self.errormsg = ''
        self.warning = ''
        self.info = None     # Will hold getaddrinfo() list
        self.ssl_info = ''  # Will hold the type and cipher of SSL connection
        self.request = False  # True if a getaddrinfo() request is pending
        self.have_body = 'free.xsusenet.com' not in host
        self.have_stat = True  # Assume server has "STAT", until proven otherwise

        for i in range(threads):
            self.idle_threads.append(NewsWrapper(self, i + 1))

    @property
    def hostip(self):
        """ In case a server still has active connections, we use the same IP again
            If new connection then based on value of load_balancing() and self.info:
            0 - return the first entry, so all threads use the same IP
            1 - and self.info has more than 1 entry (read: IP address): Return a random entry from the possible IPs
            2 - and self.info has more than 1 entry (read: IP address): Return the quickest IP based on the happyeyeballs algorithm
            In case of problems: return the host name itself
        """
        # Check if already a successful ongoing connection
        if self.busy_threads and self.busy_threads[0].nntp:
            # Re-use that IP
            logging.debug('%s: Re-using address %s', self.host, self.busy_threads[0].nntp.host)
            return self.busy_threads[0].nntp.host

        # Determine new IP
        if cfg.load_balancing() == 0 and self.info:
            # Just return the first one, so all next threads use the same IP
            ip = self.info[0][4][0]
            logging.debug('%s: Connecting to address %s', self.host, ip)

        elif cfg.load_balancing() == 1 and self.info and len(self.info) > 1:
            # Return a random entry from the possible IPs
            rnd = random.randint(0, len(self.info) - 1)
            ip = self.info[rnd][4][0]
            logging.debug('%s: Connecting to address %s', self.host, ip)

        elif cfg.load_balancing() == 2 and self.info and len(self.info) > 1:
            # RFC6555 / Happy Eyeballs:
            ip = happyeyeballs(self.host, port=self.port, ssl=self.ssl)
            if ip:
                logging.debug('%s: Connecting to address %s', self.host, ip)
            else:
                # nothing returned, so there was a connection problem
                ip = self.host
                logging.debug('%s: No successful IP connection was possible', self.host)
        else:
            ip = self.host
        return ip

    def stop(self, readers, writers):
        for nw in self.idle_threads:
            try:
                fno = nw.nntp.sock.fileno()
            except:
                fno = None
            if fno and fno in readers:
                readers.pop(fno)
            if fno and fno in writers:
                writers.pop(fno)
            nw.terminate(quit=True)
        self.idle_threads = []

    def __repr__(self):
        return "%s:%s" % (self.host, self.port)


class Downloader(Thread):
    """ Singleton Downloader Thread """
    do = None

    def __init__(self, paused=False):
        Thread.__init__(self)

        logging.debug("Initializing downloader/decoder")

        # Used for scheduled pausing
        self.paused = paused

        # used for throttling bandwidth and scheduling bandwidth changes
        cfg.bandwidth_perc.callback(self.speed_set)
        cfg.bandwidth_max.callback(self.speed_set)
        self.speed_set()

        # Used for reducing speed
        self.delayed = False

        # Used to see if we can add a slowdown to the Downloader-loop
        self.can_be_slowed = None
        self.can_be_slowed_timer = 0

        self.postproc = False

        self.shutdown = False

        # A user might change server parms again before server restart is ready.
        # Keep a counter to prevent multiple restarts
        self.__restart = 0

        self.force_disconnect = False

        self.read_fds = {}
        self.write_fds = {}

        self.servers = []
        self.server_dict = {} # For faster lookups, but is not updated later!
        self.server_nr = 0
        self._timers = {}

        for server in config.get_servers():
            self.init_server(None, server)

        self.decoder_queue = queue.Queue()

        # Initialize decoders, only 1 for non-SABYenc
        self.decoder_workers = []
        nr_decoders = 2 if sabnzbd.decoder.SABYENC_ENABLED else 1
        for i in range(nr_decoders):
            self.decoder_workers.append(Decoder(self.servers, self.decoder_queue))

        Downloader.do = self

    def init_server(self, oldserver, newserver):
        """ Setup or re-setup single server
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
            retention = float(srv.retention() * 24 * 3600)  # days ==> seconds
            send_group = srv.send_group()
            create = True

        if oldserver:
            for n in range(len(self.servers)):
                if self.servers[n].id == oldserver:
                    # Server exists, do re-init later
                    create = False
                    self.servers[n].newid = newserver
                    self.servers[n].restart = True
                    self.__restart += 1
                    break

        if create and enabled and host and port and threads:
            server = Server(newserver, displayname, host, port, timeout, threads, priority, ssl, ssl_verify,
                                    ssl_ciphers, send_group, username, password, optional, retention)
            self.servers.append(server)
            self.server_dict[newserver] = server

        # Update server-count
        self.server_nr = len(self.servers)

        return

    @NzbQueueLocker
    def set_paused_state(self, state):
        """ Set downloader to specified paused state """
        self.paused = state

    @NzbQueueLocker
    def resume(self):
        # Do not notify when SABnzbd is still starting
        if self.paused and sabnzbd.WEB_DIR:
            logging.info("Resuming")
            notifier.send_notification("SABnzbd", T('Resuming'), 'download')
        self.paused = False

    @NzbQueueLocker
    def pause(self):
        """ Pause the downloader, optionally saving admin """
        if not self.paused:
            self.paused = True
            logging.info("Pausing")
            notifier.send_notification("SABnzbd", T('Paused'), 'download')
            if self.is_paused():
                BPSMeter.do.reset()
            if cfg.autodisconnect():
                self.disconnect()

    def delay(self):
        logging.debug("Delaying")
        self.delayed = True

    @NzbQueueLocker
    def undelay(self):
        logging.debug("Undelaying")
        self.delayed = False

    def wait_for_postproc(self):
        logging.info("Waiting for post-processing to finish")
        self.postproc = True

    @NzbQueueLocker
    def resume_from_postproc(self):
        logging.info("Post-processing finished, resuming download")
        self.postproc = False

    def disconnect(self):
        self.force_disconnect = True

    def limit_speed(self, value):
        ''' Set the actual download speed in Bytes/sec
            When 'value' ends with a '%' sign or is within 1-100, it is interpreted as a pecentage of the maximum bandwidth
            When no '%' is found, it is interpreted as an absolute speed (including KMGT notation).
        '''
        if value:
            mx = cfg.bandwidth_max.get_int()
            if '%' in str(value) or (from_units(value) > 0 and from_units(value) < 101):
                limit = value.strip(' %')
                self.bandwidth_perc = from_units(limit)
                if mx:
                    self.bandwidth_limit = mx * self.bandwidth_perc / 100
                else:
                    logging.warning(T('You must set a maximum bandwidth before you can set a bandwidth limit'))
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

    def is_paused(self):
        if not self.paused:
            return False
        else:
            if sabnzbd.nzbqueue.NzbQueue.do.has_forced_items():
                return False
            else:
                return True

    def highest_server(self, me):
        """ Return True when this server has the highest priority of the active ones
            0 is the highest priority
        """
        for server in self.servers:
            if server is not me and server.active and server.priority < me.priority:
                return False
        return True

    def nzo_servers(self, nzo):
        return list(filter(nzo.server_in_try_list, self.servers))

    def maybe_block_server(self, server):
        # Was it resolving problem?
        if server.info is False:
            # Warn about resolving issues
            errormsg = T('Cannot connect to server %s [%s]') % (server.id, T('Server name does not resolve'))
            if server.errormsg != errormsg:
                server.errormsg = errormsg
                logging.warning(errormsg)
                logging.warning(T('Server %s will be ignored for %s minutes'), server.id, _PENALTY_TIMEOUT)

            # Not fully the same as the code below for optional servers
            server.bad_cons = 0
            server.active = False
            self.plan_server(server.id, _PENALTY_TIMEOUT)

        # Optional and active server had too many problems.
        # Disable it now and send a re-enable plan to the scheduler
        if server.optional and server.active and (server.bad_cons / server.threads) > 3:
            server.bad_cons = 0
            server.active = False
            logging.warning(T('Server %s will be ignored for %s minutes'), server.id, _PENALTY_TIMEOUT)
            self.plan_server(server.id, _PENALTY_TIMEOUT)

            # Remove all connections to server
            for nw in server.idle_threads + server.busy_threads:
                self.__reset_nw(nw, "forcing disconnect", warn=False, wait=False, quit=False)
            # Make sure server address resolution is refreshed
            server.info = None

            sabnzbd.nzbqueue.NzbQueue.do.reset_all_try_lists()

    def decode(self, article, lines, raw_data):
        self.decoder_queue.put((article, lines, raw_data))
        # See if there's space left in cache, pause otherwise
        # But do allow some articles to enter queue, in case of full cache
        qsize = self.decoder_queue.qsize()
        if (not ArticleCache.do.reserve_space(lines) and qsize > MAX_DECODE_QUEUE) or (qsize > LIMIT_DECODE_QUEUE):
            sabnzbd.downloader.Downloader.do.delay()

    def run(self):
        # First check IPv6 connectivity
        sabnzbd.EXTERNAL_IPV6 = sabnzbd.test_ipv6()
        logging.debug('External IPv6 test result: %s', sabnzbd.EXTERNAL_IPV6)

        # Then we check SSL certifcate checking
        sabnzbd.CERTIFICATE_VALIDATION = sabnzbd.test_cert_checking()
        logging.debug('SSL verification test: %s', sabnzbd.CERTIFICATE_VALIDATION)

        # Start decoders
        for decoder in self.decoder_workers:
            decoder.start()

        # Kick BPS-Meter to check quota
        BPSMeter.do.update()

        while 1:
            for server in self.servers:
                for nw in server.busy_threads[:]:
                    if (nw.nntp and nw.nntp.error_msg) or (nw.timeout and time.time() > nw.timeout):
                        if nw.nntp and nw.nntp.error_msg:
                            self.__reset_nw(nw, "", warn=False)
                        else:
                            self.__reset_nw(nw, "timed out")
                        server.bad_cons += 1
                        self.maybe_block_server(server)
                if server.restart:
                    if not server.busy_threads:
                        newid = server.newid
                        server.stop(self.read_fds, self.write_fds)
                        self.servers.remove(server)
                        if newid:
                            self.init_server(None, newid)
                        self.__restart -= 1
                        sabnzbd.nzbqueue.NzbQueue.do.reset_all_try_lists()
                        # Have to leave this loop, because we removed element
                        break
                    else:
                        # Restart pending, don't add new articles
                        continue

                if not server.idle_threads or server.restart or self.is_paused() or self.shutdown or self.delayed or self.postproc:
                    continue

                if not server.active:
                    continue

                for nw in server.idle_threads[:]:
                    if nw.timeout:
                        if time.time() < nw.timeout:
                            continue
                        else:
                            nw.timeout = None

                    if not server.info:
                        # Only request info if there's stuff in the queue
                        if not sabnzbd.nzbqueue.NzbQueue.do.is_empty():
                            self.maybe_block_server(server)
                            request_server_info(server)
                        break

                    article = sabnzbd.nzbqueue.NzbQueue.do.get_article(server, self.servers)

                    if not article:
                        break

                    if server.retention and article.nzf.nzo.avg_stamp < time.time() - server.retention:
                        # Let's get rid of all the articles for this server at once
                        logging.info('Job %s too old for %s, moving on', article.nzf.nzo.work_name, server.id)
                        while article:
                            self.decode(article, None, None)
                            article = article.nzf.nzo.get_article(server, self.servers)
                        break

                    server.idle_threads.remove(nw)
                    server.busy_threads.append(nw)

                    nw.article = article

                    if nw.connected:
                        self.__request_article(nw)
                    else:
                        try:
                            logging.info("%s@%s: Initiating connection", nw.thrdnum, server.id)
                            nw.init_connect(self.write_fds)
                        except:
                            logging.error(T('Failed to initialize %s@%s with reason: %s'), nw.thrdnum, server.id, sys.exc_info()[1])
                            self.__reset_nw(nw, "failed to initialize")

            # Exit-point
            if self.shutdown:
                empty = True
                for server in self.servers:
                    if server.busy_threads:
                        empty = False
                        break

                if empty:
                    # Start decoders
                    for decoder in self.decoder_workers:
                        decoder.stop()
                        decoder.join()

                    for server in self.servers:
                        server.stop(self.read_fds, self.write_fds)

                    logging.info("Shutting down")
                    break

            if self.force_disconnect:
                for server in self.servers:
                    for nw in server.idle_threads + server.busy_threads:
                        quit = nw.connected and server.active
                        self.__reset_nw(nw, "forcing disconnect", warn=False, wait=False, quit=quit)
                    # Make sure server address resolution is refreshed
                    server.info = None

                self.force_disconnect = False

            # => Select
            readkeys = list(self.read_fds.keys())
            writekeys = list(self.write_fds.keys())

            if readkeys or writekeys:
                read, write, error = select.select(readkeys, writekeys, (), 1.0)

                # Why check so often when so few things happened?
                if self.can_be_slowed and len(readkeys) >= 8 and len(read) <= 2:
                    time.sleep(0.01)

                # Need to initialize the check during first 20 seconds
                if self.can_be_slowed is None or self.can_be_slowed_timer:
                    # Wait for stable speed to start testing
                    if not self.can_be_slowed_timer and BPSMeter.do.get_stable_speed(timespan=10):
                        self.can_be_slowed_timer = time.time()

                    # Check 10 seconds after enabling slowdown
                    if self.can_be_slowed_timer and time.time() > self.can_be_slowed_timer + 10:
                        # Now let's check if it was stable in the last 10 seconds
                        self.can_be_slowed = BPSMeter.do.get_stable_speed(timespan=10)
                        self.can_be_slowed_timer = 0
                        logging.debug('Downloader-slowdown: %r', self.can_be_slowed)

            else:
                read, write, error = ([], [], [])

                BPSMeter.do.reset()

                time.sleep(1.0)

                DOWNLOADER_CV.acquire()
                while (sabnzbd.nzbqueue.NzbQueue.do.is_empty() or self.is_paused() or self.delayed or self.postproc) and not \
                       self.shutdown and not self.__restart:
                    DOWNLOADER_CV.wait()
                DOWNLOADER_CV.release()

                self.force_disconnect = False

            for selected in write:
                nw = self.write_fds[selected]

                fileno = nw.nntp.sock.fileno()

                if fileno not in self.read_fds:
                    self.read_fds[fileno] = nw

                if fileno in self.write_fds:
                    self.write_fds.pop(fileno)

            if not read:
                BPSMeter.do.update()
                continue

            for selected in read:
                nw = self.read_fds[selected]
                article = nw.article
                server = nw.server

                if article:
                    nzo = article.nzf.nzo

                try:
                    bytes, done, skip = nw.recv_chunk()
                except:
                    bytes, done, skip = (0, False, False)

                if skip:
                    BPSMeter.do.update()
                    continue

                if bytes < 1:
                    self.__reset_nw(nw, "server closed connection", warn=False, wait=False)
                    continue

                else:
                    if self.bandwidth_limit:
                        bps = BPSMeter.do.get_bps()
                        bps += bytes
                        limit = self.bandwidth_limit
                        if bps > limit:
                            while BPSMeter.do.get_bps() > limit:
                                time.sleep(0.05)
                                BPSMeter.do.update()
                    BPSMeter.do.update(server.id, bytes)

                    if nzo:
                        nzo.update_download_stats(BPSMeter.do.get_bps(), server.id, bytes)

                if not done and nw.status_code != 222:
                    if not nw.connected or nw.status_code == 480:
                        done = False
                        try:
                            nw.finish_connect(nw.status_code)
                            if sabnzbd.LOG_ALL:
                                logging.debug("%s@%s last message -> %s", nw.thrdnum, nw.server.id, nntp_to_msg(nw.data))
                            nw.clear_data()
                        except NNTPPermanentError as error:
                            # Handle login problems
                            block = False
                            penalty = 0
                            msg = error.response
                            ecode = int(msg[:3])
                            display_msg = ' [%s]' % msg
                            logging.debug('Server login problem: %s, %s', ecode, msg)
                            if ecode in (502, 400, 481, 482) and clues_too_many(msg):
                                # Too many connections: remove this thread and reduce thread-setting for server
                                # Plan to go back to the full number after a penalty timeout
                                if server.active:
                                    errormsg = T('Too many connections to server %s') % display_msg
                                    if server.errormsg != errormsg:
                                        server.errormsg = errormsg
                                        logging.warning(T('Too many connections to server %s'), server.id)
                                    self.__reset_nw(nw, None, warn=False, destroy=True, quit=True)
                                    self.plan_server(server.id, _PENALTY_TOOMANY)
                                    server.threads -= 1
                            elif ecode in (502, 481, 482) and clues_too_many_ip(msg):
                                # Account sharing?
                                if server.active:
                                    errormsg = T('Probable account sharing') + display_msg
                                    if server.errormsg != errormsg:
                                        server.errormsg = errormsg
                                        name = ' (%s)' % server.id
                                        logging.warning(T('Probable account sharing') + name)
                                penalty = _PENALTY_SHARE
                                block = True
                            elif ecode in (481, 482, 381) or (ecode == 502 and clues_login(msg)):
                                # Cannot login, block this server
                                if server.active:
                                    errormsg = T('Failed login for server %s') % display_msg
                                    if server.errormsg != errormsg:
                                        server.errormsg = errormsg
                                        logging.error(T('Failed login for server %s'), server.id)
                                penalty = _PENALTY_PERM
                                block = True
                            elif ecode in (502, 482):
                                # Cannot connect (other reasons), block this server
                                if server.active:
                                    errormsg = T('Cannot connect to server %s [%s]') % ('', display_msg)
                                    if server.errormsg != errormsg:
                                        server.errormsg = errormsg
                                        logging.warning(T('Cannot connect to server %s [%s]'), server.id, msg)
                                if clues_pay(msg):
                                    penalty = _PENALTY_PERM
                                else:
                                    penalty = _PENALTY_502
                                block = True
                            elif ecode == 400:
                                # Temp connection problem?
                                if server.active:
                                    logging.debug('Unspecified error 400 from server %s', server.id)
                                penalty = _PENALTY_VERYSHORT
                                block = True
                            else:
                                # Unknown error, just keep trying
                                if server.active:
                                    errormsg = T('Cannot connect to server %s [%s]') % ('', display_msg)
                                    if server.errormsg != errormsg:
                                        server.errormsg = errormsg
                                        logging.warning(T('Cannot connect to server %s [%s]'), server.id, msg)
                                penalty = _PENALTY_UNKNOWN
                                block = True
                            if block or (penalty and server.optional):
                                if server.active:
                                    server.active = False
                                    if penalty and (block or server.optional):
                                        self.plan_server(server.id, penalty)
                                    sabnzbd.nzbqueue.NzbQueue.do.reset_all_try_lists()
                                self.__reset_nw(nw, None, warn=False, quit=True)
                            continue
                        except:
                            logging.error(T('Connecting %s@%s failed, message=%s'),
                                              nw.thrdnum, nw.server.id, nntp_to_msg(nw.data))
                            # No reset-warning needed, above logging is sufficient
                            self.__reset_nw(nw, None, warn=False)

                        if nw.connected:
                            logging.info("Connecting %s@%s finished", nw.thrdnum, nw.server.id)
                            self.__request_article(nw)

                    elif nw.status_code == 223:
                        done = True
                        logging.debug('Article <%s> is present', article.article)

                    elif nw.status_code == 211:
                        done = False
                        logging.debug("group command ok -> %s", nntp_to_msg(nw.data))
                        nw.group = nw.article.nzf.nzo.group
                        nw.clear_data()
                        self.__request_article(nw)

                    elif nw.status_code in (411, 423, 430):
                        done = True
                        logging.debug('Thread %s@%s: Article %s missing (error=%s)',
                                        nw.thrdnum, nw.server.id, article.article, nw.status_code)
                        nw.clear_data()

                    elif nw.status_code == 480:
                        if server.active:
                            server.active = False
                            server.errormsg = T('Server %s requires user/password') % ''
                            self.plan_server(server.id, 0)
                            sabnzbd.nzbqueue.NzbQueue.do.reset_all_try_lists()
                        msg = T('Server %s requires user/password') % nw.server.id
                        self.__reset_nw(nw, msg, quit=True)

                    elif nw.status_code == 500:
                        if nzo.precheck:
                            # Assume "STAT" command is not supported
                            server.have_stat = False
                            logging.debug('Server %s does not support STAT', server.id)
                        else:
                            # Assume "BODY" command is not supported
                            server.have_body = False
                            logging.debug('Server %s does not support BODY', server.id)
                        nw.clear_data()
                        self.__request_article(nw)

                if done:
                    server.bad_cons = 0  # Succesful data, clear "bad" counter
                    server.errormsg = server.warning = ''
                    if sabnzbd.LOG_ALL:
                        logging.debug('Thread %s@%s: %s done', nw.thrdnum, server.id, article.article)
                    self.decode(article, nw.lines, nw.data)

                    nw.soft_reset()
                    server.busy_threads.remove(nw)
                    server.idle_threads.append(nw)

    def __lookup_nw(self, nw):
        """ Find the fileno matching the nw, needed for closed connections """
        for f in self.read_fds:
            if self.read_fds[f] == nw:
                return f
        for f in self.write_fds:
            if self.read_fds[f] == nw:
                return f
        return None

    def __reset_nw(self, nw, errormsg, warn=True, wait=True, destroy=False, quit=False):
        server = nw.server
        article = nw.article
        fileno = None

        if nw.nntp:
            try:
                fileno = nw.nntp.sock.fileno()
            except:
                fileno = self.__lookup_nw(nw)
                destroy = True
            nw.nntp.error_msg = None

        if warn and errormsg:
            server.warning = errormsg
            logging.info('Thread %s@%s: ' + errormsg, nw.thrdnum, server.id)
        elif errormsg:
            logging.info('Thread %s@%s: ' + errormsg, nw.thrdnum, server.id)

        if nw in server.busy_threads:
            server.busy_threads.remove(nw)
        if not (destroy or nw in server.idle_threads):
            server.idle_threads.append(nw)

        if fileno and fileno in self.write_fds:
            self.write_fds.pop(fileno)
        if fileno and fileno in self.read_fds:
            self.read_fds.pop(fileno)

        if article:
            if article.tries > cfg.max_art_tries() and (article.fetcher.optional or not cfg.max_art_opt()):
                # Too many tries on this server, consider article missing
                self.decode(article, None, None)
            else:
                # Allow all servers to iterate over each nzo/nzf again
                sabnzbd.nzbqueue.NzbQueue.do.reset_try_lists(article)

        if destroy:
            nw.terminate(quit=quit)
        else:
            nw.hard_reset(wait, quit=quit)

        # Empty SSL info, it might change on next connect
        server.ssl_info = ''

    def __request_article(self, nw):
        try:
            nzo = nw.article.nzf.nzo
            if nw.server.send_group and nzo.group != nw.group:
                group = nzo.group
                if sabnzbd.LOG_ALL:
                    logging.debug('Thread %s@%s: GROUP <%s>', nw.thrdnum, nw.server.id, group)
                nw.send_group(group)
            else:
                if sabnzbd.LOG_ALL:
                    logging.debug('Thread %s@%s: BODY %s', nw.thrdnum, nw.server.id, nw.article.article)
                nw.body(nzo.precheck)

            fileno = nw.nntp.sock.fileno()
            if fileno not in self.read_fds:
                self.read_fds[fileno] = nw
        except socket.error as err:
            logging.info('Looks like server closed connection: %s', err)
            self.__reset_nw(nw, "server broke off connection", quit=False)
        except:
            logging.error(T('Suspect error in downloader'))
            logging.info("Traceback: ", exc_info=True)
            self.__reset_nw(nw, "server broke off connection", quit=False)

    #------------------------------------------------------------------------------
    # Timed restart of servers admin.
    # For each server all planned events are kept in a list.
    # When the first timer of a server fires, all other existing timers
    # are neutralized.
    # Each server has a dictionary entry, consisting of a list of timestamps.

    @synchronized(TIMER_LOCK)
    def plan_server(self, server_id, interval):
        """ Plan the restart of a server in 'interval' minutes """
        if cfg.no_penalties() and interval > _PENALTY_SHORT:
            # Overwrite in case of no_penalties
            interval = _PENALTY_SHORT

        logging.debug('Set planned server resume %s in %s mins', server_id, interval)
        if server_id not in self._timers:
            self._timers[server_id] = []
        stamp = time.time() + 60.0 * interval
        self._timers[server_id].append(stamp)
        if interval:
            sabnzbd.scheduler.plan_server(self.trigger_server, [server_id, stamp], interval)

    @synchronized(TIMER_LOCK)
    def trigger_server(self, server_id, timestamp):
        """ Called by scheduler, start server if timer still valid """
        logging.debug('Trigger planned server resume %s', server_id)
        if server_id in self._timers:
            if timestamp in self._timers[server_id]:
                del self._timers[server_id]
                self.init_server(server_id, server_id)

    @NzbQueueLocker
    @synchronized(TIMER_LOCK)
    def unblock(self, server_id):
        # Remove timer
        try:
            del self._timers[server_id]
        except KeyError:
            pass
        # Activate server if it was inactive
        for server in self.servers:
            if server.id == server_id and not server.active:
                logging.debug('Unblock server %s', server_id)
                self.init_server(server_id, server_id)
                break

    def unblock_all(self):
        for server_id in self._timers.keys():
            self.unblock(server_id)

    @NzbQueueLocker
    @synchronized(TIMER_LOCK)
    def check_timers(self):
        """ Make sure every server without a non-expired timer is active """
        # Clean expired timers
        now = time.time()
        kicked = []
        for server_id in self._timers.keys():
            if not [stamp for stamp in self._timers[server_id] if stamp >= now]:
                logging.debug('Forcing re-evaluation of server %s', server_id)
                del self._timers[server_id]
                self.init_server(server_id, server_id)
                kicked.append(server_id)
        # Activate every inactive server without an active timer
        for server in self.servers:
            if server.id not in self._timers:
                if server.id not in kicked and not server.active:
                    logging.debug('Forcing activation of server %s', server.id)
                    self.init_server(server.id, server.id)

    def update_server(self, oldserver, newserver):
        self.init_server(oldserver, newserver)

    @NzbQueueLocker
    def wakeup(self):
        """ Just rattle the semaphore """
        pass

    def stop(self):
        self.shutdown = True
        notifier.send_notification("SABnzbd", T('Shutting down'), 'startup')


def stop():
    DOWNLOADER_CV.acquire()
    try:
        Downloader.do.stop()
    finally:
        DOWNLOADER_CV.notify_all()
        DOWNLOADER_CV.release()
    try:
        Downloader.do.join()
    except:
        pass


def clues_login(text):
    """ Check for any "failed login" clues in the response code """
    text = text.lower()
    for clue in ('username', 'password', 'invalid', 'authen', 'access denied'):
        if clue in text:
            return True
    return False


def clues_too_many(text):
    """ Check for any "too many connections" clues in the response code """
    text = text.lower()
    for clue in ('exceed', 'connections', 'too many', 'threads', 'limit'):
        # Not 'download limit exceeded' error
        if (clue in text) and ('download' not in text) and ('byte' not in text):
            return True
    return False


def clues_too_many_ip(text):
    """ Check for any "account sharing" clues in the response code """
    text = text.lower()
    for clue in ('simultaneous ip', 'multiple ip'):
        if clue in text:
            return True
    return False


def clues_pay(text):
    """ Check for messages about payments """
    text = text.lower()
    for clue in ('credits', 'paym', 'expired', 'exceeded'):
        if clue in text:
            return True
    return False
