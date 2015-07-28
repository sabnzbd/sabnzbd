#!/usr/bin/python -OO
# Copyright 2008-2015 The SABnzbd-Team <team@sabnzbd.org>
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

import sabnzbd
from sabnzbd.decorators import synchronized, synchronized_CV, CV
from sabnzbd.decoder import Decoder
from sabnzbd.newswrapper import NewsWrapper, request_server_info
import sabnzbd.growler as growler
from sabnzbd.constants import *
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.bpsmeter import BPSMeter
import sabnzbd.scheduler

#------------------------------------------------------------------------------
# Timeout penalty in minutes for each cause
_PENALTY_UNKNOWN = 3    # Unknown cause
_PENALTY_502     = 5    # Unknown 502
_PENALTY_TIMEOUT = 10   # Server doesn't give an answer (multiple times)
_PENALTY_SHARE   = 10   # Account sharing detected
_PENALTY_TOOMANY = 10   # Too many connections
_PENALTY_PERM    = 10   # Permanent error, like bad username/password
_PENALTY_SHORT   = 1    # Minimal penalty when no_penalties is set
_PENALTY_VERYSHORT = 0.1 # Error 400 without cause clues


TIMER_LOCK = RLock()

#------------------------------------------------------------------------------
class Server(object):
    def __init__(self, id, displayname, host, port, timeout, threads, priority, ssl, ssl_type, send_group, username = None,
                 password = None, optional=False, retention=0, categories = None):
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
        self.ssl_type = ssl_type
        self.optional = optional
        self.retention = retention
        self.send_group = send_group

        self.username = username
        self.password = password

        self.categories = categories

        self.busy_threads = []
        self.idle_threads = []
        self.active = True
        self.bad_cons = 0
        self.errormsg = ''
        self.warning = ''
        self.info = None     # Will hold getaddrinfo() list
        self.request = False # True if a getaddrinfo() request is pending
        self.have_body = 'free.xsusenet.com' not in host
        self.have_stat = True # Assume server has "STAT", until proven otherwise

        for i in range(threads):
            self.idle_threads.append(NewsWrapper(self, i+1))

    @property
    def hostip(self):
        """ Return a random entry from the possible IPs
        """
        if cfg.randomize_server_ip() and self.info and len(self.info) > 1:
            rnd = random.randint(0, len(self.info)-1)
            ip = self.info[rnd][4][0]
            logging.debug('For server %s, using IP %s' % (self.host, ip))
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


#------------------------------------------------------------------------------

class Downloader(Thread):
    """ Singleton Downloader Thread
    """
    do = None

    def __init__(self, paused=False):
        Thread.__init__(self)

        logging.debug("Initializing downloader/decoder")

        # Used for scheduled pausing
        self.paused = paused

        #used for throttling bandwidth and scheduling bandwidth changes
        cfg.bandwidth_perc.callback(self.speed_set)
        cfg.bandwidth_max.callback(self.speed_set)
        self.speed_set()

        # Used for reducing speed
        self.delayed = False

        self.postproc = False

        self.shutdown = False

        # A user might change server parms again before server restart is ready.
        # Keep a counter to prevent multiple restarts
        self.__restart = 0

        self.force_disconnect = False

        self.read_fds = {}
        self.write_fds = {}

        self.servers = []
        self._timers = {}

        for server in config.get_servers():
            self.init_server(None, server)

        self.decoder = Decoder(self.servers)
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
            ssl = srv.ssl() and sabnzbd.newswrapper.HAVE_SSL
            ssl_type = srv.ssl_type()
            username = srv.username()
            password = srv.password()
            optional = srv.optional()
            categories = srv.categories()
            retention = float(srv.retention() * 24 * 3600) # days ==> seconds
            send_group = srv.send_group()
            create = True

        if oldserver:
            for n in xrange(len(self.servers)):
                if self.servers[n].id == oldserver:
                    # Server exists, do re-init later
                    create = False
                    self.servers[n].newid = newserver
                    self.servers[n].restart = True
                    self.__restart += 1
                    break

        if create and enabled and host and port and threads:
            self.servers.append(Server(newserver, displayname, host, port, timeout, threads, priority, ssl,
                                            ssl_type, send_group,
                                            username, password, optional, retention, categories=categories))

        return

    @synchronized_CV
    def set_paused_state(self, state):
        """ Set Downloader to specified paused state """
        self.paused = state

    @synchronized_CV
    def resume(self):
        logging.info("Resuming")
        self.paused = False

    @synchronized_CV
    def pause(self, save=True):
        """ Pause the downloader, optionally saving admin
        """
        if not self.paused:
            self.paused = True
            logging.info("Pausing")
            growler.send_notification("SABnzbd", T('Paused'), 'download')
            if self.is_paused():
                BPSMeter.do.reset()
            if cfg.autodisconnect():
                self.disconnect()
            if save:
                sabnzbd.save_state()

    @synchronized_CV
    def delay(self):
        logging.debug("Delaying")
        self.delayed = True

    @synchronized_CV
    def undelay(self):
        logging.debug("Undelaying")
        self.delayed = False

    @synchronized_CV
    def wait_for_postproc(self):
        logging.info("Waiting for post-processing to finish")
        self.postproc = True

    @synchronized_CV
    def resume_from_postproc(self):
        logging.info("Post-processing finished, resuming download")
        self.postproc = False

    def disconnect(self):
        self.force_disconnect = True

    @synchronized_CV
    def limit_speed(self, value):
        if value:
            self.bandwidth_perc = int(value)
            mx = cfg.bandwidth_max.get_int()
            if mx:
                self.bandwidth_limit = mx * int(value) / 100
            else:
                logging.warning(T('You must set a maximum bandwidth before you can set a bandwidth limit'))
        else:
            self.speed_set()
        logging.info("Bandwidth limit set to %s%%", value)

    def get_limit(self):
        return self.bandwidth_perc

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
        from sabnzbd.nzbqueue import NzbQueue
        if not self.paused:
            return False
        else:
            if NzbQueue.do.has_forced_items():
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
        return filter(nzo.server_in_try_list, self.servers)

    def maybe_block_server(self, server):
        from sabnzbd.nzbqueue import NzbQueue
        if server.optional and server.active and (server.bad_cons/server.threads) > 3:
            # Optional and active server had too many problems,
            # disable it now and send a re-enable plan to the scheduler
            server.bad_cons = 0
            server.active = False
            server.errormsg = T('Server %s will be ignored for %s minutes') % ('', _PENALTY_TIMEOUT)
            logging.warning(T('Server %s will be ignored for %s minutes'), server.id, _PENALTY_TIMEOUT)
            self.plan_server(server.id, _PENALTY_TIMEOUT)

            # Remove all connections to server
            for nw in server.idle_threads + server.busy_threads:
                self.__reset_nw(nw, "forcing disconnect", warn=False, wait=False, quit=False)
            # Make sure server address resolution is refreshed
            server.info = None

            NzbQueue.do.reset_all_try_lists()


    def run(self):
        from sabnzbd.nzbqueue import NzbQueue
        self.decoder.start()

        # Kick BPS-Meter to check quota
        BPSMeter.do.update()

        while 1:
            for server in self.servers:
                assert isinstance(server, Server)
                for nw in server.busy_threads[:]:
                    if (nw.nntp and nw.nntp.error_msg) or (nw.timeout and time.time() > nw.timeout):
                        if (nw.nntp and nw.nntp.error_msg):
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
                        NzbQueue.do.reset_all_try_lists()
                        # Have to leave this loop, because we removed element
                        break
                    else:
                        # Restart pending, don't add new articles
                        continue

                assert isinstance(server, Server)
                if not server.idle_threads or server.restart or self.is_paused() or self.shutdown or self.delayed or self.postproc:
                    continue

                if not (server.active and NzbQueue.do.has_articles_for(server)):
                    continue

                for nw in server.idle_threads[:]:
                    assert isinstance(nw, NewsWrapper)
                    if nw.timeout:
                        if time.time() < nw.timeout:
                            continue
                        else:
                            nw.timeout = None

                    if not server.active:
                        break

                    if server.info is None:
                        self.maybe_block_server(server)
                        request_server_info(server)
                        break

                    article = NzbQueue.do.get_article(server, self.servers)

                    if not article:
                        break

                    if server.retention and article.nzf.nzo.avg_stamp < time.time() - server.retention:
                        # Article too old for the server, treat as missing
                        if sabnzbd.LOG_ALL:
                            logging.debug('Article %s too old for %s', article.article, server.id)
                        self.decoder.decode(article, None)
                        break

                    server.idle_threads.remove(nw)
                    server.busy_threads.append(nw)

                    nw.article = article

                    if nw.connected:
                        self.__request_article(nw)
                    else:
                        try:
                            logging.info("%s@%s: Initiating connection",
                                              nw.thrdnum, server.id)
                            nw.init_connect(self.write_fds)
                        except:
                            logging.error(T('Failed to initialize %s@%s'), nw.thrdnum, server.id)
                            logging.info("Traceback: ", exc_info = True)
                            self.__reset_nw(nw, "failed to initialize")

            # Exit-point
            if self.shutdown:
                empty = True
                for server in self.servers:
                    if server.busy_threads:
                        empty = False
                        break

                if empty:
                    self.decoder.stop()
                    self.decoder.join()

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
            readkeys = self.read_fds.keys()
            writekeys = self.write_fds.keys()

            if readkeys or writekeys:
                read, write, error = select.select(readkeys, writekeys, (), 1.0)

            else:
                read, write, error = ([], [], [])

                BPSMeter.do.reset()

                time.sleep(1.0)

                CV.acquire()
                while (NzbQueue.do.is_empty() or self.is_paused() or self.delayed or self.postproc) and not \
                       self.shutdown and not self.__restart:
                    CV.wait()
                CV.release()

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
                        if server.id in nzo.servercount:
                            nzo.servercount[server.id] += bytes
                        else:
                            nzo.servercount[server.id] = bytes
                        nzo.bytes_downloaded += bytes
                        nzo.update_avg_kbs(BPSMeter.do.get_bps())

                if len(nw.lines) == 1:
                    code = nw.lines[0][:3]
                    if not nw.connected or code == '480':
                        done = False

                        try:
                            nw.finish_connect(code)
                            if sabnzbd.LOG_ALL:
                                logging.debug("%s@%s last message -> %s", nw.thrdnum, nw.server.id, nw.lines[0])
                            nw.lines = []
                            nw.data = ''
                        except NNTPPermanentError, error:
                            # Handle login problems
                            block = False
                            penalty = 0
                            msg = error.response
                            ecode = msg[:3]
                            display_msg = ' [%s]' % msg
                            logging.debug('Server login problem: %s, %s', ecode, msg)
                            if ecode in ('502', '481', '400') and clues_too_many(msg):
                                # Too many connections: remove this thread and reduce thread-setting for server
                                # Plan to go back to the full number after a penalty timeout
                                if server.active:
                                    server.errormsg = T('Too many connections to server %s') % display_msg
                                    logging.error(T('Too many connections to server %s'), server.id)
                                    self.__reset_nw(nw, None, warn=False, destroy=True, quit=True)
                                    self.plan_server(server.id, _PENALTY_TOOMANY)
                                    server.threads -= 1
                            elif ecode in ('502', '481') and clues_too_many_ip(msg):
                                # Account sharing?
                                if server.active:
                                    server.errormsg = T('Probable account sharing') + display_msg
                                    name = ' (%s)' % server.id
                                    logging.error(T('Probable account sharing') + name)
                                    penalty = _PENALTY_SHARE
                            elif ecode in ('481', '482', '381') or (ecode == '502' and clues_login(msg)):
                                # Cannot login, block this server
                                if server.active:
                                    server.errormsg = T('Failed login for server %s') % display_msg
                                    logging.error(T('Failed login for server %s'), server.id)
                                penalty = _PENALTY_PERM
                                block = True
                            elif ecode == '502':
                                # Cannot connect (other reasons), block this server
                                if server.active:
                                    server.errormsg = T('Cannot connect to server %s [%s]') % ('', display_msg)
                                    logging.warning(T('Cannot connect to server %s [%s]'), server.id, msg)
                                if clues_pay(msg):
                                    penalty = _PENALTY_PERM
                                else:
                                    penalty = _PENALTY_502
                                block = True
                            elif ecode == '400':
                                # Temp connection problem?
                                if server.active:
                                    logging.debug('Unspecified error 400 from server %s', server.id)
                                penalty = _PENALTY_VERYSHORT
                                block = True
                            else:
                                # Unknown error, just keep trying
                                if server.active:
                                    server.errormsg = T('Cannot connect to server %s [%s]') % ('', display_msg)
                                    logging.error(T('Cannot connect to server %s [%s]'), server.id, msg)
                                    penalty = _PENALTY_UNKNOWN
                            if block or (penalty and server.optional):
                                if server.active:
                                    server.active = False
                                    if (not server.optional) and cfg.no_penalties():
                                        penalty = _PENALTY_SHORT
                                    if penalty and (block or server.optional):
                                        logging.info('Server %s ignored for %s minutes', server.id, penalty)
                                        self.plan_server(server.id, penalty)
                                    NzbQueue.do.reset_all_try_lists()
                                self.__reset_nw(nw, None, warn=False, quit=True)
                            continue
                        except:
                            logging.error(T('Connecting %s@%s failed, message=%s'),
                                              nw.thrdnum, nw.server.id, nw.lines[0])
                            # No reset-warning needed, above logging is sufficient
                            self.__reset_nw(nw, None, warn=False)

                        if nw.connected:
                            logging.info("Connecting %s@%s finished", nw.thrdnum, nw.server.id)
                            self.__request_article(nw)

                    elif code == '223':
                        done = True
                        logging.debug('Article <%s> is present', article.article)
                        self.decoder.decode(article, nw.lines)

                    elif code == '211':
                        done = False

                        logging.debug("group command ok -> %s",
                                      nw.lines)
                        nw.group = nw.article.nzf.nzo.group
                        nw.lines = []
                        nw.data = ''
                        self.__request_article(nw)

                    elif code in ('411', '423', '430'):
                        done = True
                        nw.lines = None

                        logging.info('Thread %s@%s: Article ' + \
                                        '%s missing (error=%s)',
                                        nw.thrdnum, nw.server.id, article.article, code)

                    elif code == '480':
                        if server.active:
                            server.active = False
                            server.errormsg = T('Server %s requires user/password') % ''
                            self.plan_server(server.id, 0)
                            NzbQueue.do.reset_all_try_lists()
                        msg = T('Server %s requires user/password') % nw.server.id
                        self.__reset_nw(nw, msg, quit=True)

                    elif code == '500':
                        if nzo.precheck:
                            # Assume "STAT" command is not supported
                            server.have_stat = False
                            logging.debug('Server %s does not support STAT', server.id)
                        else:
                            # Assume "BODY" command is not supported
                            server.have_body = False
                            logging.debug('Server %s does not support BODY', server.id)
                        nw.lines = []
                        nw.data = ''
                        self.__request_article(nw)

                if done:
                    server.bad_cons = 0 # Succesful data, clear "bad" counter
                    if sabnzbd.LOG_ALL:
                        logging.debug('Thread %s@%s: %s done', nw.thrdnum, server.id, article.article)
                    self.decoder.decode(article, nw.lines)

                    nw.soft_reset()
                    server.busy_threads.remove(nw)
                    server.idle_threads.append(nw)

    def __lookup_nw(self, nw):
        ''' Find the fileno matching the nw, needed for closed connections '''
        for f in self.read_fds:
            if self.read_fds[f] == nw:
                return f
        for f in self.write_fds:
            if self.read_fds[f] == nw:
                return f
        return None

    def __reset_nw(self, nw, errormsg, warn=True, wait=True, destroy=False, quit=False):
        from sabnzbd.nzbqueue import NzbQueue
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
                self.decoder.decode(article, None)
            else:
                # Remove this server from try_list
                article.fetcher = None

                nzf = article.nzf
                nzo = nzf.nzo

                ## Allow all servers to iterate over each nzo/nzf again ##
                NzbQueue.do.reset_try_lists(nzf, nzo)

        if destroy:
            nw.terminate(quit=quit)
        else:
            nw.hard_reset(wait, quit=quit)

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
        except socket.error, err:
            logging.info('Looks like server closed connection: %s', err)
            self.__reset_nw(nw, "server broke off connection", quit=False)
        except:
            logging.error('Suspect error in downloader')
            logging.info("Traceback: ", exc_info = True)
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

    @synchronized_CV
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

    @synchronized_CV
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

    @synchronized_CV
    def update_server(self, oldserver, newserver):
        self.init_server(oldserver, newserver)

    @synchronized_CV
    def wakeup(self):
        """ Just rattle the semaphore
        """
        pass

    def stop(self):
        self.shutdown = True
        growler.send_notification("SABnzbd",T('Shutting down'), 'startup')


def stop():
    CV.acquire()
    try:
        Downloader.do.stop()
    finally:
        CV.notifyAll()
        CV.release()
    try:
        Downloader.do.join()
    except:
        pass


#------------------------------------------------------------------------------
def clues_login(text):
    """ Check for any "failed login" clues in the response code
    """
    text = text.lower()
    for clue in ('username', 'password', 'invalid', 'authen', 'access denied'):
        if clue in text:
            return True
    return False


def clues_too_many(text):
    """ Check for any "too many connections" clues in the response code
    """
    text = text.lower()
    for clue in ('exceed', 'connections', 'too many', 'threads', 'limit'):
        if clue in text:
            return True
    return False


def clues_too_many_ip(text):
    """ Check for any "account sharing" clues in the response code
    """
    text = text.lower()
    for clue in ('simultaneous ip', 'multiple ip'):
        if clue in text:
            return True
    return False


def clues_pay(text):
    """ Check for messages about payments
    """
    text = text.lower()
    for clue in ('credits', 'paym', 'expired'):
        if clue in text:
            return True
    return False
