#!/usr/bin/python -OO
# Copyright 2008-2009 The SABnzbd-Team <team@sabnzbd.org>
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
import datetime
from threading import Thread
from nntplib import NNTPPermanentError
import socket

import sabnzbd
from sabnzbd.decorators import synchronized_CV, CV
from sabnzbd.decoder import Decoder
from sabnzbd.newswrapper import NewsWrapper, request_server_info
from sabnzbd.utils import osx
from sabnzbd.constants import *
import sabnzbd.config as config
import sabnzbd.cfg as cfg
import sabnzbd.bpsmeter as bpsmeter
import sabnzbd.scheduler
import sabnzbd.nzbqueue
from sabnzbd.lang import T, Ta

#------------------------------------------------------------------------------
# Timeout penalty in minutes for each cause
_PENALTY_UNKNOWN = 3    # Unknown cause
_PENALTY_502     = 5    # Unknown 502
_PENALTY_TIMEOUT = 10   # Server doesn't give an answer (multiple times)
_PENALTY_SHARE   = 10   # Account sharing detected
_PENALTY_TOOMANY = 10   # Too many connections
_PENALTY_PERM    = 10   # Permanent error, like bad username/password
_PENALTY_SHORT   = 1    # Minimal penalty when no_penalties is set

#------------------------------------------------------------------------------
# Wrapper functions

__DOWNLOADER = None  # Global pointer to post-proc instance


def init(paused):
    global __DOWNLOADER
    if __DOWNLOADER:
        __DOWNLOADER.__init__(paused or __DOWNLOADER.paused)
    else:
        __DOWNLOADER = Downloader(paused)

def start():
    global __DOWNLOADER
    if __DOWNLOADER: __DOWNLOADER.start()


def servers():
    global __DOWNLOADER
    if __DOWNLOADER: return __DOWNLOADER.servers

def stop():
    global __DOWNLOADER
    CV.acquire()
    try:
        __DOWNLOADER.stop()
    finally:
        CV.notifyAll()
        CV.release()
    try:
        __DOWNLOADER.join()
    except:
        pass

def alive():
    global __DOWNLOADER
    if __DOWNLOADER:
        return __DOWNLOADER.isAlive()
    else:
        return False

#------------------------------------------------------------------------------

@synchronized_CV
def pause_downloader(save=True):
    global __DOWNLOADER
    if __DOWNLOADER:
        __DOWNLOADER.pause()
        if cfg.AUTODISCONNECT():
            __DOWNLOADER.disconnect()
        if save:
            sabnzbd.save_state()

@synchronized_CV
def resume_downloader():
    global __DOWNLOADER
    if __DOWNLOADER: __DOWNLOADER.resume()

@synchronized_CV
def delay_downloader():
    global __DOWNLOADER
    if __DOWNLOADER: __DOWNLOADER.delay()

@synchronized_CV
def undelay_downloader():
    global __DOWNLOADER
    if __DOWNLOADER: __DOWNLOADER.undelay()

@synchronized_CV
def idle_downloader():
    global __DOWNLOADER
    if __DOWNLOADER: __DOWNLOADER.wait_postproc()

@synchronized_CV
def unidle_downloader():
    global __DOWNLOADER
    if __DOWNLOADER: __DOWNLOADER.resume_postproc()

@synchronized_CV
def limit_speed(value):
    global __DOWNLOADER
    if __DOWNLOADER: __DOWNLOADER.limit_speed(int(value))
    logging.info("Bandwidth limit set to %s", value)

def update_server(oldserver, newserver):
    global __DOWNLOADER
    try:
        CV.acquire()
        try:
            __DOWNLOADER.init_server(oldserver, newserver)
        finally:
            CV.notifyAll()
            CV.release()
    except:
        logging.exception("Error accessing DOWNLOADER?")

@synchronized_CV
def set_paused(state):
    global __DOWNLOADER
    if __DOWNLOADER: __DOWNLOADER.paused = state

@synchronized_CV
def unblock(server):
    global __DOWNLOADER
    if __DOWNLOADER: return __DOWNLOADER.unblock(server)

@synchronized_CV
def unblock_all():
    global __DOWNLOADER
    if __DOWNLOADER: __DOWNLOADER.unblock_all()

@synchronized_CV
def wakeup():
    # Just let the decorator rattle the semaphore
    pass


#------------------------------------------------------------------------------

def paused():
    global __DOWNLOADER
    if __DOWNLOADER: return __DOWNLOADER.paused

def get_limit():
    global __DOWNLOADER
    if __DOWNLOADER: return __DOWNLOADER.get_limit()

def disconnect():
    global __DOWNLOADER
    if __DOWNLOADER: __DOWNLOADER.disconnect()

def delayed():
    global __DOWNLOADER
    if __DOWNLOADER: return __DOWNLOADER.delayed

def active_primaries():
    global __DOWNLOADER
    if __DOWNLOADER: return __DOWNLOADER.active_primaries()

#------------------------------------------------------------------------------
class Server:
    def __init__(self, id, host, port, timeout, threads, fillserver, ssl, username = None,
                 password = None, optional=False):
        self.id = id
        self.newid = None
        self.restart = False
        self.host = host
        self.port = port
        self.timeout = timeout
        self.threads = threads
        self.fillserver = fillserver
        self.ssl = ssl
        self.optional = optional

        self.username = username
        self.password = password

        self.busy_threads = []
        self.idle_threads = []
        self.active = True
        self.bad_cons = 0
        self.errormsg = ''
        self.warning = ''
        self.info = None     # Will hold getaddrinfo() list
        self.request = False # True if a getaddrinfo() request is pending

        for i in range(threads):
            self.idle_threads.append(NewsWrapper(self, i+1))

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
    def __init__(self, paused = False):
        Thread.__init__(self)

        logging.debug("Initializing downloader/decoder")

        # Used for scheduled pausing
        self.paused = paused

        #used for throttling bandwidth and scheduling bandwidth changes
        self.bandwidth_limit = cfg.BANDWIDTH_LIMIT()
        cfg.BANDWIDTH_LIMIT.callback(self.speed_set)

        # Used for reducing speed
        self.delayed = False

        self.postproc = False

        self.shutdown = False

        # A user might change server parsm again before server restart is ready.
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


    def init_server(self, oldserver, newserver):
        """ Setup or re-setup single server
            When oldserver is defined and in use, delay startup.
            Return True when newserver is primary
            Note that the server names are "host:port" strings!
        """

        primary = False
        create = False

        servers = config.get_servers()
        if newserver in servers:
            srv = servers[newserver]
            enabled = srv.enable()
            host = srv.host()
            port = srv.port()
            timeout = srv.timeout()
            threads = srv.connections()
            fillserver = srv.fillserver()
            primary = enabled and (not fillserver) and (threads > 0)
            ssl = srv.ssl() and sabnzbd.newswrapper.HAVE_SSL
            username = srv.username()
            password = srv.password()
            optional = srv.optional()
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
            self.servers.append(Server(newserver, host, port, timeout, threads, fillserver, ssl,
                                            username, password, optional))

        return primary

    def stop(self):
        self.shutdown = True
        osx.sendGrowlMsg("SABnzbd",T('grwl-shutdown-begin-msg'),osx.NOTIFICATION['startup'])

    def resume(self):
        logging.info("Resuming")
        self.paused = False

    def pause(self):
        logging.info("Pausing")
        osx.sendGrowlMsg("SABnzbd",T('grwl-paused-msg'),osx.NOTIFICATION['download'])
        self.paused = True
        if self.is_paused():
            bpsmeter.method.reset()

    def delay(self):
        logging.info("Delaying")
        self.delayed = True

    def undelay(self):
        logging.info("Undelaying")
        self.delayed = False

    def wait_postproc(self):
        logging.info("Waiting for post-processing to finish")
        self.postproc = True

    def resume_postproc(self):
        logging.info("Post-processing finished, resuming download")
        self.postproc = False

    def disconnect(self):
        self.force_disconnect = True

    def limit_speed(self, value):
        self.bandwidth_limit = value

    def get_limit(self):
        return self.bandwidth_limit

    def speed_set(self):
        self.bandwidth_limit = cfg.BANDWIDTH_LIMIT()

    def is_paused(self):
        if not self.paused:
            return False
        else:
            if sabnzbd.nzbqueue.has_forced_items():
                return False
            else:
                return True

    def active_primaries(self):
        """ Check if any primary server is defined and active """
        for server in self.servers:
            if server.active and not server.fillserver:
                return True
        return False

    def maybe_block_server(self, server):
        if server.optional and server.active and (server.bad_cons/server.threads) > 3:
            # Optional and active server had too many problems,
            # disable it now and send a re-enable plan to the scheduler
            server.bad_cons = 0
            server.active = False
            server.errormsg = T('warn-ignoreServer@2') % ('', _PENALTY_TIMEOUT)
            logging.warning(Ta('warn-ignoreServer@2'), server.id, _PENALTY_TIMEOUT)
            self.plan_server(server.id, _PENALTY_TIMEOUT)
            sabnzbd.nzbqueue.reset_all_try_lists()


    def run(self):
        self.decoder.start()

        while 1:
            for server in self.servers:
                for nw in server.busy_threads[:]:
                    if nw.nntp.error_msg or (nw.timeout and time.time() > nw.timeout):
                        if nw.nntp.error_msg:
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
                        sabnzbd.nzbqueue.reset_all_try_lists()
                        # Have to leave this loop, because we removed element
                        break
                    else:
                        # Restart pending, don't add new articles
                        continue

                if not server.idle_threads or server.restart or self.is_paused() or self.shutdown or self.delayed or self.postproc:
                    continue

                if not (server.active and sabnzbd.nzbqueue.has_articles_for(server)):
                    continue

                for nw in server.idle_threads[:]:
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

                    article = sabnzbd.nzbqueue.get_article(server)

                    if not article:
                        break

                    else:
                        server.idle_threads.remove(nw)
                        server.busy_threads.append(nw)

                        nw.article = article

                        if nw.connected:
                            self.__request_article(nw)
                        else:
                            try:
                                logging.info("%s@%s:%s: Initiating connection",
                                                  nw.thrdnum, server.host, server.port)
                                nw.init_connect()
                                self.write_fds[nw.nntp.sock.fileno()] = nw
                            except:
                                logging.error(Ta('error-noInit@3'),
                                                  nw.thrdnum, server.host,
                                                  server.port)
                                logging.debug("Traceback: ", exc_info = True)
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

                bpsmeter.method.reset()

                time.sleep(1.0)

                CV.acquire()
                while (not sabnzbd.nzbqueue.has_articles() or self.is_paused() or self.delayed or self.postproc) and not \
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
                bpsmeter.method.update(0)
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
                    bpsmeter.method.update(0)
                    continue

                if bytes < 1:
                    self.__reset_nw(nw, "server closed connection", warn=False, wait=False)
                    continue

                else:
                    if self.bandwidth_limit:
                        bps = bpsmeter.method.get_bps()
                        bps += bytes
                        limit = self.bandwidth_limit * 1024
                        if bps > limit:
                            while bpsmeter.method.get_bps() > limit:
                                time.sleep(0.05)
                                bpsmeter.method.update(0)
                    bpsmeter.method.update(bytes)

                    if nzo:
                        nzo.update_bytes(bytes)
                        nzo.update_avg_kbs(bpsmeter.method.get_bps())

                if len(nw.lines) == 1:
                    code = nw.lines[0][:3]
                    if not nw.connected:
                        done = False

                        try:
                            nw.finish_connect()
                            logging.debug("%s@%s:%s last message -> %s",
                                         nw.thrdnum, nw.server.host,
                                         nw.server.port, nw.lines[0])
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
                            if ((ecode in ('502', '400')) and clues_too_many(msg)) or \
                                (ecode == '481' and clues_too_many(msg)):
                                # Too many connections: remove this thread and reduce thread-setting for server
                                # Plan to go back to the full number after a penalty timeout
                                if server.active:
                                    server.errormsg = Ta('error-serverTooMany@2') % ('', display_msg)
                                    logging.error(Ta('error-serverTooMany@2'), server.host, server.port)
                                    self.__reset_nw(nw, None, warn=False, destroy=True, quit=True)
                                    self.plan_server(server.id, _PENALTY_TOOMANY)
                                    server.threads -= 1
                            elif ecode in ('502', '481') and clues_too_many_ip(msg):
                                # Account sharing?
                                if server.active:
                                    server.errormsg = Ta('error-accountSharing') + display_msg
                                    name = ' (%s:%s)' % (server.host, server.port)
                                    logging.error(Ta('error-accountSharing') + name)
                                    penalty = _PENALTY_SHARE
                            elif ecode in ('481', '482', '381') or (ecode == '502' and clues_login(msg)):
                                # Cannot login, block this server
                                if server.active:
                                    server.errormsg = Ta('error-serverLogin@1') % display_msg
                                    logging.error(Ta('error-serverLogin@1'), '%s:%s' % (server.host, server.port))
                                penalty = _PENALTY_PERM
                                block = True
                            elif ecode == '502':
                                # Cannot connect (other reasons), block this server
                                if server.active:
                                    server.errormsg = Ta('warn-noConnectServer@2') % ('', display_msg)
                                    logging.warning(Ta('warn-noConnectServer@2'), '%s:%s' % (server.host, server.port), msg)
                                penalty = _PENALTY_502
                                block = True
                            else:
                                # Unknown error, just keep trying
                                if server.active:
                                    server.errormsg = Ta('error-serverNoConn@2') % ('', display_msg)
                                    logging.error(Ta('error-serverNoConn@2'),  '%s:%s' % (server.host, server.port), msg)
                                    penalty = _PENALTY_UNKNOWN
                            if block or (penalty and server.optional):
                                if server.active:
                                    server.active = False
                                    if (not server.optional) and cfg.NO_PENALTIES.get():
                                        penalty = _PENALTY_SHORT
                                    if penalty and (block or server.optional):
                                        logging.info('Server %s ignored for %s minutes', server.id, penalty)
                                        self.plan_server(server.id, penalty)
                                    sabnzbd.nzbqueue.reset_all_try_lists()
                                self.__reset_nw(nw, None, warn=False, quit=True)
                            continue
                        except:
                            logging.error(Ta('error-serverFailed@4'),
                                              nw.thrdnum,
                                              nw.server.host, nw.server.port, nw.lines[0])
                            # No reset-warning needed, above logging is sufficient
                            self.__reset_nw(nw, None, warn=False)

                        if nw.connected:
                            logging.info("Connecting %s@%s:%s finished",
                                         nw.thrdnum, nw.server.host,
                                         nw.server.port)
                            self.__request_article(nw)

                    elif code == '211':
                        done = False

                        logging.debug("group command ok -> %s",
                                      nw.lines)
                        nw.group = nw.article.nzf.nzo.get_group()
                        nw.lines = []
                        nw.data = ''
                        self.__request_article(nw)

                    elif code in ('411', '423', '430'):
                        done = True
                        nw.lines = None

                        logging.info('Thread %s@%s:%s: Article ' + \
                                        '%s missing',
                                        nw.thrdnum, nw.server.host,
                                        nw.server.port, article.article)

                    elif code == '480':
                        if server.active:
                            server.active = False
                            server.errormsg = T('error-serverCred@1') % ''
                            self.plan_server(server.id, 0)
                            sabnzbd.nzbqueue.reset_all_try_lists()
                        msg = T('error-serverCred@1') % ('%s:%s' % (nw.server.host, nw.server.port))
                        self.__reset_nw(nw, msg, quit=True)

                if done:
                    logging.info('Thread %s@%s:%s: %s done',
                                 nw.thrdnum, server.host,
                                 server.port, article.article)
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
            logging.info('Thread %s@%s:%s: ' + errormsg,
                             nw.thrdnum, server.host, server.port)
        elif errormsg:
            logging.info('Thread %s@%s:%s: ' + errormsg,
                             nw.thrdnum, server.host, server.port)

        if nw in server.busy_threads:
            server.busy_threads.remove(nw)
        if not (destroy or nw in server.idle_threads):
            server.idle_threads.append(nw)

        if fileno and fileno in self.write_fds:
            self.write_fds.pop(fileno)
        if fileno and fileno in self.read_fds:
            self.read_fds.pop(fileno)

        # Remove this server from try_list
        if article:
            article.fetcher = None

            nzf = article.nzf
            nzo = nzf.nzo

            ## Allow all servers to iterate over each nzo/nzf again ##
            sabnzbd.nzbqueue.reset_try_lists(nzf, nzo)

        if destroy:
            nw.terminate(quit=quit)
        else:
            nw.hard_reset(wait, quit=quit)

    def __request_article(self, nw):
        try:
            if cfg.SEND_GROUP() and nw.article.nzf.nzo.get_group() != nw.group:
                group = nw.article.nzf.nzo.get_group()
                logging.info('Thread %s@%s:%s: GROUP <%s>',
                             nw.thrdnum, nw.server.host,
                             nw.server.port, group)
                nw.send_group(group)
            else:
                logging.info('Thread %s@%s:%s: BODY %s',
                             nw.thrdnum, nw.server.host,
                             nw.server.port, nw.article.article)
                nw.body()

            fileno = nw.nntp.sock.fileno()
            if fileno not in self.read_fds:
                self.read_fds[fileno] = nw
        except socket.error, err:
            logging.info('Looks like server closed connection: %s', err)
            self.__reset_nw(nw, "server broke off connection", quit=False)
        except:
            logging.error('Suspect error in downloader')
            logging.debug("Traceback: ", exc_info = True)
            self.__reset_nw(nw, "server broke off connection", quit=False)

    #------------------------------------------------------------------------------
    # Timed restart of servers admin.
    # For each server all planned events are kept in a list.
    # When the first timer of a server fires, all other existing timers
    # are neutralized.
    # Each server has a dictionary entry, consisting of a list of timestamps.

    def plan_server(self, server_id, interval):
        """ Plan the restart of a server in 'interval' minutes """
        logging.debug('Set planned server resume %s in %s mins', server_id, interval)
        if server_id not in self._timers:
            self._timers[server_id] = []
        stamp = datetime.datetime.now()
        self._timers[server_id].append(stamp)
        if interval:
            sabnzbd.scheduler.plan_server(self.trigger_server, [server_id, stamp], interval)

    def trigger_server(self, server_id, timestamp):
        """ Called by scheduler, start server if timer still valid """
        logging.debug('Trigger planned server resume %s', server_id)
        if server_id in self._timers:
            if timestamp in self._timers[server_id]:
                del self._timers[server_id]
                self.init_server(server_id, server_id)

    def unblock(self, server_id):
        # Remove timer
        try:
            # Use this instead of if/del, because the line below is atomic
            # an if/del could be victim of a race condition
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


#------------------------------------------------------------------------------
def clues_login(text):
    """ Check for any "failed login" clues in the response code
    """
    text = text.lower()
    for clue in ('username', 'password', 'invalid', 'authen'):
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
