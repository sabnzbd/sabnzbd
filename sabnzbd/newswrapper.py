#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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
sabnzbd.newswrapper
"""

import errno
import socket
import threading
from collections import deque
from contextlib import suppress
from selectors import EVENT_READ, EVENT_WRITE
from threading import Thread
import time
import logging
import ssl
from typing import Optional, Tuple, Union, Callable

import sabctools
import sabnzbd
import sabnzbd.cfg
from sabnzbd.constants import DEF_NETWORKING_TIMEOUT, NNTP_BUFFER_SIZE, Status, FORCE_PRIORITY
from sabnzbd.encoding import utob
from sabnzbd.get_addrinfo import AddrInfo
from sabnzbd.decorators import synchronized, DOWNLOADER_LOCK

# Set pre-defined socket timeout
socket.setdefaulttimeout(DEF_NETWORKING_TIMEOUT)


class NNTPPermanentError(Exception):
    def __init__(self, msg: str, code: int):
        super().__init__()
        self.msg = msg
        self.code = code

    def __str__(self) -> str:
        return self.msg


class NewsWrapper:
    # Pre-define attributes to save memory
    __slots__ = (
        "server",
        "thrdnum",
        "blocking",
        "timeout",
        "decoder",
        "nntp",
        "connected",
        "user_sent",
        "pass_sent",
        "group",
        "user_ok",
        "pass_ok",
        "force_login",
        "next_request",
        "concurrent_requests",
        "_response_queue",
        "selector_events",
        "lock",
        "generation",
        "tls_wants_write",
    )

    def __init__(self, server: "sabnzbd.downloader.Server", thrdnum: int, block: bool = False, generation: int = 0):
        self.server: sabnzbd.downloader.Server = server
        self.thrdnum: int = thrdnum
        self.blocking: bool = block
        self.generation: int = generation
        if getattr(self, "lock", None) is None:
            self.lock: threading.Lock = threading.Lock()

        self.timeout: Optional[float] = None

        self.decoder: Optional[sabctools.Decoder] = None

        self.nntp: Optional[NNTP] = None

        self.connected: bool = False
        self.user_sent: bool = False
        self.pass_sent: bool = False
        self.user_ok: bool = False
        self.pass_ok: bool = False
        self.force_login: bool = False
        self.group: Optional[str] = None

        # Command queue and concurrency
        self.next_request: Optional[tuple[bytes, Optional["sabnzbd.nzb.Article"]]] = None
        self.concurrent_requests: threading.BoundedSemaphore = threading.BoundedSemaphore(
            self.server.pipelining_requests()
        )
        self._response_queue: deque[Optional[sabnzbd.nzb.Article]] = deque()
        self.selector_events = 0
        self.tls_wants_write: bool = False

    @property
    def article(self) -> Optional["sabnzbd.nzb.Article"]:
        """The article currently being downloaded"""
        with self.lock:
            if self._response_queue:
                return self._response_queue[0]
            return None

    def init_connect(self):
        """Setup the connection in NNTP object"""
        # Sanity check, especially for the server test
        if not self.server.addrinfo:
            raise socket.error(errno.EADDRNOTAVAIL, T("Invalid server address."))

        # Construct buffer and NNTP object
        self.decoder = sabctools.Decoder(NNTP_BUFFER_SIZE)
        self.nntp = NNTP(self, self.server.addrinfo)
        self.timeout = time.time() + self.server.timeout

        # On connect the first "response" will be 200 Welcome
        self._response_queue.append(None)
        self.concurrent_requests.acquire()

    def finish_connect(self, code: int, message: str) -> None:
        """Perform login options"""
        if not (self.server.username or self.server.password or self.force_login):
            self.connected = True
            self.user_sent = True
            self.user_ok = True
            self.pass_sent = True
            self.pass_ok = True

        if code == 480:
            self.force_login = True
            self.connected = False
            self.user_sent = False
            self.user_ok = False
            self.pass_sent = False
            self.pass_ok = False

        if code in (400, 500, 502):
            raise NNTPPermanentError(message, code)
        elif not self.user_sent:
            command = utob("authinfo user %s\r\n" % self.server.username)
            self.queue_command(command)
            self.user_sent = True
        elif not self.user_ok:
            if code == 381:
                self.user_ok = True
            elif code == 281:
                # No login required
                self.user_ok = True
                self.pass_sent = True
                self.pass_ok = True
                self.connected = True

        if self.user_ok and not self.pass_sent:
            command = utob("authinfo pass %s\r\n" % self.server.password)
            self.queue_command(command)
            self.pass_sent = True
        elif self.user_ok and not self.pass_ok:
            if code != 281:
                # Assume that login failed (code 481 or other)
                raise NNTPPermanentError(message, code)
            else:
                self.connected = True

        self.timeout = time.time() + self.server.timeout

    def queue_command(
        self,
        command: bytes,
        article: Optional["sabnzbd.nzb.Article"] = None,
    ) -> None:
        """Add a command to the command queue"""
        self.next_request = command, article

    def body(self, article: "sabnzbd.nzb.Article") -> tuple[bytes, "sabnzbd.nzb.Article"]:
        """Request the body of the article"""
        self.timeout = time.time() + self.server.timeout
        if article.nzf.nzo.precheck:
            if self.server.have_stat:
                command = utob("STAT <%s>\r\n" % article.article)
            else:
                command = utob("HEAD <%s>\r\n" % article.article)
        elif self.server.have_body:
            command = utob("BODY <%s>\r\n" % article.article)
        else:
            command = utob("ARTICLE <%s>\r\n" % article.article)
        return command, article

    def on_response(self, response: sabctools.NNTPResponse, article: Optional["sabnzbd.nzb.Article"]) -> None:
        """A response to a NNTP request is received"""
        self.concurrent_requests.release()
        server = self.server
        article_done = response.status_code in (220, 222) and article

        if article_done:
            with DOWNLOADER_LOCK:
                # Update statistics only when we fetched a whole article
                # The side effect is that we don't count things like article-not-available messages
                article.nzf.nzo.update_download_stats(sabnzbd.BPSMeter.bps, server.id, response.bytes_read)

        # Response code depends on request command:
        # 220 = ARTICLE, 222 = BODY
        if not article_done:
            if not self.connected or not article or response.status_code in (281, 381, 480, 481, 482):
                self.discard(article, count_article_try=False)
                if not sabnzbd.Downloader.finish_connect_nw(self, response):
                    return
                if self.connected:
                    logging.info("Connecting %s@%s finished", self.thrdnum, server.host)

            elif response.status_code == 223:
                article_done = True
                logging.debug("Article <%s> is present on %s", article.article, server.host)

            elif response.status_code in (411, 423, 430, 451):
                article_done = True
                logging.debug(
                    "Thread %s@%s: Article %s missing (error=%s)",
                    self.thrdnum,
                    server.host,
                    article.article,
                    response.status_code,
                )

            elif response.status_code == 500:
                if article.nzf.nzo.precheck:
                    # Assume "STAT" command is not supported
                    server.have_stat = False
                    logging.debug("Server %s does not support STAT", server.host)
                else:
                    # Assume "BODY" command is not supported
                    server.have_body = False
                    logging.debug("Server %s does not support BODY", server.host)
                self.discard(article, count_article_try=False)

            else:
                # Don't warn for (internal) server errors during downloading
                if response.status_code not in (400, 502, 503):
                    logging.warning(
                        T("%s@%s: Received unknown status code %s for article %s"),
                        self.thrdnum,
                        server.host,
                        response.status_code,
                        article.article,
                    )

                # Ditch this thread, we don't know what data we got now so the buffer can be bad
                sabnzbd.Downloader.reset_nw(
                    self, f"Server error or unknown status code: {response.status_code}", wait=False, article=article
                )
                return

        if article_done:
            # Successful data, clear "bad" counter
            server.bad_cons = 0
            server.errormsg = server.warning = ""

            # Decode
            sabnzbd.Downloader.decode(article, response)

            if sabnzbd.LOG_ALL:
                logging.debug("Thread %s@%s: %s done", self.thrdnum, server.host, article.article)

    def read(
        self,
        nbytes: int = 0,
        on_response: Optional[Callable[[int, str], None]] = None,
        generation: Optional[int] = None,
    ) -> Tuple[int, Optional[int]]:
        """Receive data, return #bytes, #pendingbytes
        :param nbytes: maximum number of bytes to read
        :param on_response: callback for each complete response received
        :param generation: expected reset generation
        :return: #bytes, #pendingbytes
        """
        if generation is None:
            generation = self.generation

        # NewsWrapper is being reset
        if self.decoder is None:
            return 0, None

        # Receive data into the decoder pre-allocated buffer
        if not nbytes and self.nntp.nw.server.ssl and not self.nntp.nw.blocking and sabctools.openssl_linked:
            # Use patched version when downloading
            bytes_recv = sabctools.unlocked_ssl_recv_into(self.nntp.sock, self.decoder)
        else:
            bytes_recv = self.nntp.sock.recv_into(self.decoder, nbytes=nbytes)

        # No data received
        if bytes_recv == 0:
            raise ConnectionError("Server closed connection")

        # Success, move timeout
        self.timeout = time.time() + self.server.timeout

        self.decoder.process(bytes_recv)
        if self.decoder:
            for response in self.decoder:
                with self.lock:
                    # Check generation under lock to avoid racing with hard_reset
                    if self.generation != generation or not self._response_queue:
                        break
                    article = self._response_queue.popleft()
                if on_response:
                    on_response(response.status_code, response.message)
                self.on_response(response, article)

            # After each response this socket may need to be made available to write the next request,
            # or removed from socket monitoring to prevent hot looping.
            if self.prepare_request():
                # There is either a next_request or an inflight request
                # If there is a next_request to send, ensure the socket is registered for write events
                # Checks before calling modify_socket to prevent locks on the hot path
                if self.next_request and self.selector_events != EVENT_READ | EVENT_WRITE:
                    sabnzbd.Downloader.modify_socket(self, EVENT_READ | EVENT_WRITE)
            else:
                # Only remove the socket if it's not SSL or has no pending data, otherwise the recursive call may
                # call prepare_request again and find a request, but the socket would have already been removed.
                if not self.server.ssl or not self.nntp or not self.nntp.sock.pending():
                    # No further work for this socket
                    sabnzbd.Downloader.remove_socket(self)

        # The SSL-layer might still contain data even though the socket does not. Another Downloader-loop would
        # not identify this socket anymore as it is not returned by select(). So, we have to forcefully trigger
        # another recv_chunk so the buffer is increased and the data from the SSL-layer is read. See #2752.
        if self.server.ssl and self.nntp and (pending := self.nntp.sock.pending()):
            return bytes_recv, pending
        return bytes_recv, None

    def prepare_request(self) -> bool:
        """Queue an article request if appropriate."""
        server = self.server

        # Do not pipeline requests until authentication is completed (connected)
        if self.connected or not self._response_queue:
            server_ready = (
                server.active
                and not server.restart
                and not (
                    sabnzbd.Downloader.no_active_jobs()
                    or sabnzbd.Downloader.shutdown
                    or sabnzbd.Downloader.paused_for_postproc
                )
            )

            if server_ready:
                # Queue the next article if none exists
                if not self.next_request and (article := server.get_article()):
                    self.next_request = self.body(article)
                    return True
            else:
                # Server not ready, discard any queued next_request
                if self.next_request and self.next_request[1]:
                    self.discard(self.next_request[1], count_article_try=False, retry_article=True)
                    self.next_request = None

        # Return True if there is work queued or in flight
        return bool(self.next_request or self._response_queue)

    def write(self):
        """Send data to server"""
        server = self.server

        try:
            # If available, try to send new command
            if self.prepare_request():
                # Nothing to send but already requests in-flight
                if not self.next_request:
                    sabnzbd.Downloader.modify_socket(self, EVENT_READ)
                    return

                if self.concurrent_requests.acquire(blocking=False):
                    command, article = self.next_request
                    if article:
                        nzo = article.nzf.nzo
                        if nzo.removed_from_queue or nzo.status is Status.PAUSED and nzo.priority is not FORCE_PRIORITY:
                            self.discard(article, count_article_try=False, retry_article=True)
                            self.concurrent_requests.release()
                            self.next_request = None
                            return

                    if sabnzbd.LOG_ALL:
                        logging.debug("Thread %s@%s: %s", self.thrdnum, server.host, command)

                    # If this fails, it will propagate and throw a Downloader-error
                    self.nntp.sock.sendall(command)
                    self._response_queue.append(article)
                    self.next_request = None
                else:
                    # Concurrency limit reached; wait until a response is read to prevent hot looping on EVENT_WRITE
                    sabnzbd.Downloader.modify_socket(self, EVENT_READ)
            else:
                # No further work for this socket
                sabnzbd.Downloader.remove_socket(self)
        except socket.error as err:
            logging.info("Looks like server closed connection: %s, type: %s", err, type(err))
            sabnzbd.Downloader.reset_nw(self, "Server broke off connection", warn=True, wait=False)
        except Exception:
            logging.error(T("Suspect error in downloader"))
            logging.info("Traceback: ", exc_info=True)
            sabnzbd.Downloader.reset_nw(self, "Server broke off connection", warn=True)

    def hard_reset(self, wait: bool = True):
        """Destroy and restart"""
        with self.lock:
            # Drain unsent requests
            if self.next_request:
                _, article = self.next_request
                if article:
                    self.discard(article, count_article_try=False, retry_article=True)
                self.next_request = None
            # Drain responses
            while self._response_queue:
                if article := self._response_queue.popleft():
                    self.discard(article, count_article_try=False, retry_article=True)

            if self.nntp:
                sabnzbd.Downloader.remove_socket(self)
                self.nntp.close(send_quit=self.connected)
                self.nntp = None

            # Reset all variables (including the NNTP connection) and increment the generation counter
            self.__init__(self.server, self.thrdnum, generation=self.generation + 1)

        # Wait before re-using this newswrapper
        if wait:
            # Reset due to error condition, use server timeout
            self.timeout = time.time() + self.server.timeout
        else:
            # Reset for internal reasons, just wait 5 sec
            self.timeout = time.time() + 5

    def discard(
        self,
        article: Optional["sabnzbd.nzb.Article"],
        count_article_try: bool = True,
        retry_article: bool = True,
    ) -> None:
        """Discard an article back to the queue"""
        if article and not article.nzf.nzo.removed_from_queue:
            # Only some errors should count towards the total tries for each server
            if count_article_try:
                article.tries += 1

            # Do we discard, or try again for this server
            if not retry_article or (not self.server.required and article.tries > sabnzbd.cfg.max_art_tries()):
                # Too many tries on this server, consider article missing
                sabnzbd.Downloader.decode(article)
                article.tries = 0
            else:
                # Allow all servers again for this article
                # Do not use the article_queue, as the server could already have been disabled when we get here!
                article.allow_new_fetcher()

    def __repr__(self):
        return "<NewsWrapper: server=%s:%s, thread=%s, connected=%s>" % (
            self.server.host,
            self.server.port,
            self.thrdnum,
            self.connected,
        )


class NNTP:
    # Pre-define attributes to save memory
    __slots__ = ("nw", "addrinfo", "error_msg", "sock", "fileno", "closed")

    def __init__(self, nw: NewsWrapper, addrinfo: AddrInfo):
        self.nw: NewsWrapper = nw
        # Add local reference to prevent crash in case the server.addrinfo is reset
        self.addrinfo: AddrInfo = addrinfo
        self.error_msg: Optional[str] = None

        # Prevent closing this socket until it's done connecting
        self.closed = False

        # Create SSL-context if it is needed and not created yet
        if self.nw.server.ssl and not self.nw.server.ssl_context:
            # Setup the SSL socket
            # Set Certificate validation: 0=Disabled, 1=Minimal, 2=Medium, 3=Strict
            self.nw.server.ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

            # Allow those pesky virus-scanners to inject their scanning certificates
            if self.nw.server.ssl_verify <= 2:
                self.nw.server.ssl_context.verify_flags &= ~ssl.VERIFY_X509_STRICT
                # This flag is only available for Python 3.10 and above
                if hasattr(ssl, "VERIFY_X509_PARTIAL_CHAIN"):
                    self.nw.server.ssl_context.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
            else:
                # Make sure it's enabled for Strict mode, also pre-3.13
                self.nw.server.ssl_context.verify_flags |= ssl.VERIFY_X509_STRICT
                # This flag is only available for Python 3.10 and above
                if hasattr(ssl, "VERIFY_X509_PARTIAL_CHAIN"):
                    self.nw.server.ssl_context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN

            # Only verify hostname when Medium or Strict
            if self.nw.server.ssl_verify <= 1:
                self.nw.server.ssl_context.check_hostname = False

            # Certificates optional
            if self.nw.server.ssl_verify <= 0:
                self.nw.server.ssl_context.verify_mode = ssl.CERT_NONE

            # Did the user set a custom cipher-string?
            if self.nw.server.ssl_ciphers:
                # At their own risk, socket will error out in case it was invalid
                self.nw.server.ssl_context.set_ciphers(self.nw.server.ssl_ciphers)
                # Python does not allow setting ciphers on TLSv1.3, so have to force TLSv1.2 as the maximum
                self.nw.server.ssl_context.maximum_version = ssl.TLSVersion.TLSv1_2
            else:
                # Support at least TLSv1.2+ ciphers, as some essential ones are removed by default in Python 3.10
                self.nw.server.ssl_context.set_ciphers("HIGH")

            if sabnzbd.cfg.allow_old_ssl_tls():
                # Allow anything that the system has
                self.nw.server.ssl_context.minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
            else:
                # We want a modern TLS (1.2 or higher), so we disallow older protocol versions (<= TLS 1.1)
                self.nw.server.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

        # Create socket and store fileno of the socket
        self.sock: Union[socket.socket, ssl.SSLSocket] = socket.socket(self.addrinfo.family, self.addrinfo.type)
        self.fileno: int = self.sock.fileno()

        # Open the connection in a separate thread due to avoid blocking
        # For server-testing we do want blocking
        if not self.nw.blocking:
            Thread(target=self.connect).start()
        else:
            self.connect()

    def connect(self):
        """Start of connection, can be performed a-sync"""
        try:
            # Wait the defined timeout during connect and SSL-setup
            self.sock.settimeout(self.nw.server.timeout)

            # Connect
            if outgoing_nntp_ip := sabnzbd.cfg.outgoing_nntp_ip():
                try:
                    self.sock.bind((outgoing_nntp_ip, 0))
                    socket_info = self.sock.getsockname()
                    logging.debug(
                        "%s@%s: Successfully bound to following ip address: %s at following port: %d",
                        self.nw.thrdnum,
                        self.nw.server.host,
                        socket_info[0],
                        socket_info[1],
                    )
                except socket.error:
                    raise ConnectionError(f"Could not bind to outgoing interface {outgoing_nntp_ip}")

            self.sock.connect(self.addrinfo.sockaddr)

            # Secured or unsecured?
            if self.nw.server.ssl:
                # Wrap socket and log SSL/TLS diagnostic info
                self.sock = self.nw.server.ssl_context.wrap_socket(self.sock, server_hostname=self.nw.server.host)
                logging.info(
                    "%s@%s: Connected using %s (%s)",
                    self.nw.thrdnum,
                    self.nw.server.host,
                    self.sock.version(),
                    self.sock.cipher()[0],
                )
                self.nw.server.ssl_info = "%s (%s)" % (self.sock.version(), self.sock.cipher()[0])

            # Skip during server test
            if not self.nw.blocking:
                # Set to non-blocking mode
                self.sock.setblocking(False)
                # Only add to active sockets if it's not somehow already closing
                # Locked, so it can't interleave with any of the Downloader "__nw" actions
                with DOWNLOADER_LOCK:
                    if not self.closed:
                        sabnzbd.Downloader.add_socket(self.nw)
        except OSError as e:
            self.error(e)

    def error(self, error: OSError):
        raw_error_str = str(error)
        if "SSL23_GET_SERVER_HELLO" in str(error) or "SSL3_GET_RECORD" in raw_error_str:
            error = T("This server does not allow SSL on this port")

        # Catch certificate errors
        if type(error) == ssl.CertificateError or "CERTIFICATE_VERIFY_FAILED" in raw_error_str:
            # Log the raw message for debug purposes
            logging.info("Certificate error for host %s: %s", self.nw.server.host, raw_error_str)

            # Try to see if we should catch this message and provide better text
            if "hostname" in raw_error_str:
                raw_error_str = T(
                    "Certificate hostname mismatch: the server hostname is not listed in the certificate. This is a server issue."
                )
            elif "certificate verify failed" in raw_error_str:
                raw_error_str = T(
                    "Certificate could not be validated. This could be a server issue or due to a locally injected certificate (for example by firewall or virus scanner). Try setting Certificate verification to Medium."
                )

            # Reformat error and overwrite str-representation
            error_str = T("Server %s uses an untrusted certificate [%s]") % (self.nw.server.host, raw_error_str)
            error_str = "%s - %s: %s" % (error_str, T("Wiki"), "https://sabnzbd.org/certificate-errors")
            error.strerror = error_str

            # Prevent throwing a lot of errors or when testing server
            if error_str not in self.nw.server.warning and not self.nw.blocking:
                logging.error(error_str)

            # Pass to server-test
            if self.nw.blocking:
                raise error

        # Blocking = server-test, pass directly to display code
        if self.nw.blocking:
            raise socket.error(errno.ECONNREFUSED, str(error))

        # Ignore if the socket was already closed, resulting in errors
        if not self.closed:
            msg = T("Failed to connect: %s %s@%s:%s (%s)") % (
                str(error),
                self.nw.thrdnum,
                self.nw.server.host,
                self.nw.server.port,
                self.addrinfo.canonname,
            )
            self.error_msg = msg
            self.nw.server.next_busy_threads_check = 0
            if self.nw.server.warning == msg:
                logging.info(msg)
            else:
                logging.warning(msg)
            self.nw.server.warning = msg

    @synchronized(DOWNLOADER_LOCK)
    def close(self, send_quit: bool):
        """Safely close socket.
        Locked to match connect(), even though most likely the caller already holds the same lock."""
        # Set status first, so any calls in connect/error are handled correctly
        self.closed = True
        try:
            if send_quit:
                with suppress(socket.error):
                    self.sock.sendall(b"QUIT\r\n")
                    time.sleep(0.01)
            self.sock.close()
        except Exception as e:
            logging.info("%s@%s: Failed to close socket (error=%s)", self.nw.thrdnum, self.nw.server.host, str(e))

    def __repr__(self):
        return "<NNTP: %s:%s>" % (self.addrinfo.canonname, self.nw.server.port)
