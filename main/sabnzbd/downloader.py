#!/usr/bin/python -OO
# Copyright 2008 The SABnzbd-Team <team@sabnzbd.org>
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

__NAME__ = 'downloader'

import time
import select
import logging
import sabnzbd
import datetime

from threading import Thread

from sabnzbd.decoder import Decoder
from sabnzbd.newswrapper import NewsWrapper
from sabnzbd.misc import Notify
from sabnzbd.constants import *
import sabnzbd.config as config
import sabnzbd.cfg as cfg


#------------------------------------------------------------------------------

def GetParm(server, keyword):
    """ Get named server parameter in a safe way """
    try:
        value = server[keyword]
    except:
        value = ''
    server[keyword] = value
    return value

def GetParmInt(server, keyword, default):
    """ Get integer server parameter in a safe way """
    value = GetParm(server, keyword)
    try:
        value = int(value)
    except:
        value = default
    server[keyword] = value
    return value


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
            nw.terminate()
        self.idle_threads = []

    def __repr__(self):
        return "%s:%s" % (self.host, self.port)

#------------------------------------------------------------------------------

class BPSMeter:
    def __init__(self, bytes_sum = 0):
        t = time.time()

        self.start_time = t
        self.log_time = t
        self.last_update = t
        self.bps = 0.0
        self.bytes_total = 0
        self.bytes_sum = bytes_sum

    def update(self, bytes_recvd):
        self.bytes_total += bytes_recvd
        self.bytes_sum += bytes_recvd

        t = time.time()
        try:
            self.bps = (self.bps * (self.last_update - self.start_time)
                        + bytes_recvd) / (t - self.start_time)
        except:
            self.bps = 0.0

        self.last_update = t

        check_time = t - 5.0

        if self.start_time < check_time:
            self.start_time = check_time

        if self.bps < 0.01:
            self.reset()
            
        elif self.log_time < check_time:
            logging.debug("[%s] bps: %s", __NAME__, self.bps)
            self.log_time = t

    def get_sum(self):
        return self.bytes_sum

    def reset(self):
        self.__init__(bytes_sum = self.bytes_sum)

    def get_bps(self):
        return self.bps

#------------------------------------------------------------------------------

class Downloader(Thread):
    def __init__(self, paused = False):
        Thread.__init__(self)

        logging.debug("[%s] Initializing downloader/decoder", __NAME__)

        # Used for scheduled pausing
        self.paused = paused
        
        #used for throttling bandwidth and scheduling bandwidth changes
        self.bandwidth_limit = cfg.BANDWIDTH_LIMIT.get()
        cfg.BANDWIDTH_LIMIT.callback(self.speed_set)

        # Used for reducing speed
        self.delayed = False

        self.postproc = False

        self.shutdown = False
        self.__restart = 0

        self.force_disconnect = False

        self.read_fds = {}
        self.write_fds = {}

        self.servers = []

        primary = False
        for server in config.get_servers():
            if self.init_server(None, server):
                primary = True

        if not primary:
            logging.warning('[%s] No active primary servers defined, will not download!', __NAME__)

        self.decoder = Decoder(self.servers)


    def init_server(self, oldserver, newserver):
        """ Setup or re-setup single server
            When oldserver is defined and in use, delay startup.
            Return True when newserver is primary
        """

        primary = False
        create = False

        servers = config.get_servers()
        if newserver in servers:
            srv = servers[newserver]
            enabled = srv.enable.get()
            host = srv.host.get()
            port = srv.port.get()
            timeout = srv.timeout.get()
            threads = srv.connections.get()
            fillserver = srv.fillserver.get()
            primary = primary or (enabled and (not fillserver) and (threads > 0))
            ssl = srv.ssl.get() and sabnzbd.newswrapper.HAVE_SSL
            username = srv.username.get()
            password = srv.password.get()
            optional = srv.optional.get()
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

    def resume(self):
        logging.info("[%s] Resuming", __NAME__)
        Notify("SAB_Resume", None)
        self.paused = False

    def pause(self):
        logging.info("[%s] Pausing", __NAME__)
        Notify("SAB_Paused", None)
        self.paused = True

    def delay(self):
        logging.info("[%s] Delaying", __NAME__)
        self.delayed = True

    def undelay(self):
        logging.info("[%s] Undelaying", __NAME__)
        self.delayed = False

    def wait_postproc(self):
        logging.info("[%s] Waiting for post-processing to finish", __NAME__)
        self.postproc = True

    def resume_postproc(self):
        logging.info("[%s] Post-processing finished, resuming download", __NAME__)
        self.postproc = False

    def disconnect(self):
        self.force_disconnect = True

    def limit_speed(self, value):
        self.bandwidth_limit = value

    def get_limit(self):
        return self.bandwidth_limit

    def speed_set(self):
        self.bandwidth_limit = cfg.BANDWIDTH_LIMIT.get()
        
    def run(self):
        self.decoder.start()

        while 1:
            for server in self.servers:
                for nw in server.busy_threads[:]:
                    if nw.timeout and time.time() > nw.timeout:
                        self.__reset_nw(nw, "timed out")

                if server.restart:
                    if not server.busy_threads:
                        newid = server.newid
                        server.stop(self.read_fds, self.write_fds)
                        self.servers.remove(server)
                        if newid:
                            self.init_server(None, newid)
                        self.__restart -= 1
                        # Have to leave this loop, because we removed element
                        break
                    else:
                        # Restart pending, don't add new articles
                        continue

                if not server.idle_threads or server.restart or self.paused or self.shutdown or self.delayed or self.postproc:
                    continue

                if not sabnzbd.has_articles_for(server):
                    continue

                for nw in server.idle_threads[:]:
                    if nw.timeout:
                        if time.time() < nw.timeout:
                            continue
                        else:
                            nw.timeout = None

                    article = sabnzbd.get_article(server)

                    if not article:
                        break

                    else:
                        server.idle_threads.remove(nw)
                        server.busy_threads.append(nw)

                        nw.article = article

                        if nw.connected:
                            if cfg.SEND_GROUP.get() and nw.article.nzf.nzo.get_group() != nw.group:
                                logging.info("[%s] Sending group", __NAME__)
                                self.__send_group(nw)
                            else:
                                self.__request_article(nw)

                        else:
                            try:
                                logging.info("[%s] %s@%s:%s: Initiating connection",
                                                  __NAME__, nw.thrdnum, server.host,
                                                  server.port)
                                nw.init_connect()
                                self.write_fds[nw.nntp.sock.fileno()] = nw
                            except:
                                logging.error("[%s] Failed to initialize %s@%s:%s",
                                                  __NAME__, nw.thrdnum, server.host,
                                                  server.port)
                                logging.debug("[%s] Traceback: ", __NAME__, exc_info = True)
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

                    logging.info("[%s] Shutting down", __NAME__)
                    break

            if self.force_disconnect:
                for server in self.servers:
                    for nw in server.idle_threads[:]:
                        self.__reset_nw(nw, "forcing disconnect", warn=False, wait=False)
                    for nw in server.busy_threads[:]:
                        self.__reset_nw(nw, "forcing disconnect", warn=False, wait=False)

                self.force_disconnect = False

            # => Select
            readkeys = self.read_fds.keys()
            writekeys = self.write_fds.keys()

            if readkeys or writekeys:
                read, write, error = select.select(readkeys, writekeys, (), 1.0)

            else:
                read, write, error = ([], [], [])

                sabnzbd.reset_bpsmeter()

                time.sleep(1.0)

                sabnzbd.CV.acquire()
                while (not sabnzbd.has_articles() or self.paused or self.delayed or self.postproc) and not \
                       self.shutdown and not self.__restart:
                    sabnzbd.CV.wait()
                sabnzbd.CV.release()

                self.force_disconnect = False

            for selected in write:
                nw = self.write_fds[selected]

                fileno = nw.nntp.sock.fileno()

                if fileno not in self.read_fds:
                    self.read_fds[fileno] = nw

                if fileno in self.write_fds:
                    self.write_fds.pop(fileno)

            if not read:
                sabnzbd.update_bytes(0)
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
                    sabnzbd.update_bytes(0)
                    continue

                if bytes < 1:
                    self.__reset_nw(nw, "server closed connection", warn=False, wait=False)
                    continue

                else:
                    if self.bandwidth_limit:
                        bps = sabnzbd.get_bps()
                        bps += bytes
                        limit = self.bandwidth_limit * 1024
                        if bps > limit:
                            sleeptime = (bps/limit)-1
                            if sleeptime > 0 and sleeptime < 10:
                                #logging.debug("[%s] Sleeping %s second(s) bps:%s limit:%s", __NAME__,sleeptime, bps/1024, limit/1024)
                                time.sleep(sleeptime)
                    sabnzbd.update_bytes(bytes)
                    
                    if nzo:
                        nzo.update_bytes(bytes)
                        nzo.update_avg_kbs(sabnzbd.get_bps())

                if len(nw.lines) == 1:
                    if not nw.connected:
                        done = False

                        try:
                            nw.finish_connect()
                            logging.debug("[%s] %s@%s:%s last message -> %s",
                                         __NAME__, nw.thrdnum, nw.server.host,
                                         nw.server.port, nw.lines[0])
                            nw.lines = []
                            nw.data = ''
                        except:
                            logging.error("[%s] Connecting %s@%s:%s failed, message=%s",
                                              __NAME__, nw.thrdnum,
                                              nw.server.host, nw.server.port, nw.lines[0])
                            # No reset-warning needed, above logging is sufficient
                            self.__reset_nw(nw, None, warn=False)

                        if nw.connected:
                            logging.info("[%s] Connecting %s@%s:%s finished",
                                         __NAME__, nw.thrdnum, nw.server.host,
                                         nw.server.port)
                            self.__request_article(nw)

                    elif nw.lines[0][:3] in ('211'):
                        done = False

                        logging.debug("[%s] group command ok -> %s", __NAME__,
                                      nw.lines)
                        nw.group = nw.article.nzf.nzo.get_group()
                        nw.lines = []
                        nw.data = ''
                        self.__request_article(nw)

                    elif nw.lines[0][:3] in ('411', '423', '430'):
                        done = True
                        nw.lines = None

                        logging.info('[%s] Thread %s@%s:%s: Article ' + \
                                        '%s missing',
                                        __NAME__, nw.thrdnum, nw.server.host,
                                        nw.server.port, article.article)
                        
                    elif nw.lines[0][:3] in ('480'):
                        msg = '[%s] Server %s:%s requires user/password' % (__NAME__, nw.server.host, nw.server.port)
                        self.__reset_nw(nw, msg)

                if done:
                    logging.info('[%s] Thread %s@%s:%s: %s done',
                                 __NAME__, nw.thrdnum, server.host,
                                 server.port, article.article)
                    self.decoder.decode(article, nw.lines)

                    nw.soft_reset()
                    server.busy_threads.remove(nw)
                    server.idle_threads.append(nw)

    def __reset_nw(self, nw, errormsg, warn=True, wait=True):
        server = nw.server
        article = nw.article
        fileno = None

        if nw.nntp:
            fileno = nw.nntp.sock.fileno()

        if warn and errormsg:
            logging.warning('[%s] Thread %s@%s:%s: ' + errormsg,
                             __NAME__, nw.thrdnum, server.host, server.port)
        elif errormsg:
            logging.info('[%s] Thread %s@%s:%s: ' + errormsg,
                             __NAME__, nw.thrdnum, server.host, server.port)

        if nw in server.busy_threads:
            server.busy_threads.remove(nw)
        if nw not in server.idle_threads:
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
            sabnzbd.reset_try_lists(nzf, nzo)

        nw.hard_reset(wait)

    def __request_article(self, nw):
        try:
            logging.info('[%s] Thread %s@%s:%s: fetching %s',
                         __NAME__, nw.thrdnum, nw.server.host,
                         nw.server.port, nw.article.article)

            fileno = nw.nntp.sock.fileno()

            nw.body()

            if fileno not in self.read_fds:
                self.read_fds[fileno] = nw
        except:
            logging.error("[%s] Exception?", __NAME__)
            self.__reset_nw(nw, "server broke off connection")

    def __send_group(self, nw):
        try:
            nzo = nw.article.nzf.nzo
            _group = nzo.get_group()
            logging.info('[%s] Thread %s@%s:%s: group <%s>',
                         __NAME__, nw.thrdnum, nw.server.host,
                         nw.server.port, _group)

            fileno = nw.nntp.sock.fileno()

            nw.send_group(_group)

            if fileno not in self.read_fds:
                self.read_fds[fileno] = nw
        except:
            logging.error("[%s] Exception?", __NAME__)
            self.__reset_nw(nw, "server broke off connection")
