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
sabnzbd.newswrapper
"""

from collections import deque
import errno
import socket
import threading
from contextlib import suppress
from selectors import EVENT_READ, EVENT_WRITE
from threading import Thread
import time
import logging
import ssl
from typing import Optional, Callable

import sabctools
import sabnzbd
import sabnzbd.cfg
from sabnzbd.constants import DEF_NETWORKING_TIMEOUT, NNTP_BUFFER_SIZE, Status, FORCE_PRIORITY
from sabnzbd.encoding import utob
from sabnzbd.get_addrinfo import AddrInfo
from sabnzbd.decorators import synchronized, DOWNLOADER_LOCK

# Set pre-defined socket timeout
socket.setdefaulttimeout(DEF_NETWORKING_TIMEOUT)


def _requires_body(article: "sabnzbd.nzb.Article") -> bool:
    """Whether the article must be fetched with BODY (RFC 3977 section 6.2.3).

    NZO defaults to False, so anything else is not a declared encrypted release and
    ordinary articles keep the server's chosen command.
    """
    return bool(article.nzf.nzo.yenc_encrypted)


def _captures_body(article: "sabnzbd.nzb.Article") -> bool:
    """Whether this article's raw BODY bytes must be journaled.

    This is the arming condition used before a BODY command goes out, so plain or
    precheck articles on a shared connection never journal. Retiring a bound is
    stateful, not predicate-only: _RawBodyCapture.release() retires only an
    actually armed contribution, so discarding an article that never armed (or
    whose response already released it) cannot clear a co-pipelined in-flight
    article's journal.
    """
    return _requires_body(article) and not article.nzf.nzo.precheck


class _RawBodyCapture:
    """Journal of raw transport bytes for declared-encrypted articles.

    sabctools' native Decoder has no raw mode and auto-detects ordinary yEnc from the
    wire bytes. A valid encrypted Line 1 can begin with salt bytes that look exactly
    like an ordinary "=ybegin " bootstrap, in which case sabctools consumes the whole
    article into bogus decoded data and exposes no raw lines - the article is lost
    before the restoration pipeline ever sees it (DL-R7-2). While an encrypted article
    is in flight, every byte handed to the native Decoder is journaled here so the raw
    body can be reconstructed per response.

    Only articles of a declared-encrypted job journal (encrypted-only), with an
    enforced per-article byte bound: a bound trip drops the journal and later slices
    come back empty, which fails the encrypted article closed - never wrong output.

    The journal can start (or restart) while a response is already partly received:
    the first arm, a re-arm after release() cleared the storage, and a re-arm after
    set_inactive() on reset (which also restarts the decoder and its stream). To stay
    aligned at every (re)start, the capture keeps two connection-owned running counts
    of the normalized decoder stream: every byte handed to the decoder (even while
    inactive, cheap) and every byte already attributed to a completed response. When
    the journal starts, its start offset is recorded; take() then discards only the
    part of a response the journal actually holds, so a response that began before the
    journal started (necessarily not an encrypted article: arming precedes its own
    command) never misaligns later responses (DL-R8-1).
    """

    __slots__ = (
        "_chunks",
        "_head_offset",
        "_retained",
        "_bound",
        "_dropped",
        "_processed",
        "_consumed",
        "_journal_start",
        "_armed",
    )

    def __init__(self):
        self._chunks: deque[bytes] = deque()
        # Offset into _chunks[0] already consumed by take(); the head chunk is
        # sliced only once, when it is fully consumed or the journal is cleared.
        self._head_offset = 0
        self._retained = 0
        self._bound = 0
        self._dropped = False
        # Bound contributed per article object that armed the journal. release()
        # retires only an article's own contribution (one arm each call), so a
        # never-armed or already-released article cannot subtract another
        # in-flight article's bound. id()-keyed: Article is slotted without
        # __weakref__ or __eq__, so object identity is the only stable key.
        self._armed: dict[int, int] = {}
        # Connection-owned stream accounting, in normalized decoder bytes
        self._processed = 0  # total bytes handed to the decoder
        self._consumed = 0  # bytes attributed to completed responses (FIFO)
        self._journal_start = 0  # _processed value when the journal (re)started

    @property
    def active(self) -> bool:
        return bool(self._bound)

    @property
    def retained(self) -> int:
        return self._retained

    @staticmethod
    def _article_bound(article: "sabnzbd.nzb.Article") -> int:
        """Enforced per-article journal bound.

        The raw response is the yEnc-encoded ciphertext plus control lines, status line
        and terminator: always larger than the NZB's declared plaintext article size,
        but by a bounded factor (yEnc escapes at most 1/51 bytes, one =yencryption line,
        AEAD tag). The margin covers that expansion; anything beyond it is not a valid
        article and trips the bound.
        """
        declared = article.bytes
        return declared + (declared >> 5) + 4096

    def arm(self, article: "sabnzbd.nzb.Article") -> None:
        """Arm the journal for an encrypted article being requested.

        Pipelined requests each add their own bound while in flight; the journal is
        shared and consumed FIFO per response, so arming never discards another
        in-flight article's bytes. If the journal was not running, record where in
        the decoder stream it starts, so take() can skip bytes received before
        activation (a response that began earlier is not this encrypted article's
        response, since arming precedes the command going out).
        """
        if not self.active:
            self._journal_start = self._processed
        bound = self._article_bound(article)
        self._armed[id(article)] = self._armed.get(id(article), 0) + bound
        self._bound += bound

    def release(self, article: "sabnzbd.nzb.Article") -> None:
        """Retire one armed article's bound contribution; full release frees storage.

        A no-op when the article holds no armed contribution: it never armed the
        journal, or its response already released it. Without the per-article
        record, such a discard subtracted a sibling's bound and, when the stolen
        total reached zero, cleared a co-pipelined encrypted article's journal.
        """
        armed = self._armed.get(id(article))
        if armed is None:
            return
        # One arm retires per release. Arming the same article twice (re-fetch
        # before the first response retires) leaves the second contribution.
        bound = self._article_bound(article)
        if bound >= armed:
            del self._armed[id(article)]
            retired = armed
        else:
            self._armed[id(article)] = armed - bound
            retired = bound
        self._bound = max(0, self._bound - retired)
        if not self._bound:
            self._chunks.clear()
            self._head_offset = 0
            self._retained = 0
            self._dropped = False

    def set_inactive(self) -> None:
        """Release all storage; used on connection reset.

        The decoder and its byte stream are also replaced on reset, so the stream
        accounting restarts with them.
        """
        self._chunks.clear()
        self._head_offset = 0
        self._retained = 0
        self._bound = 0
        self._dropped = False
        self._armed.clear()
        self._processed = 0
        self._consumed = 0
        self._journal_start = 0

    def add(self, chunk: bytes, /) -> None:
        """Journal one normalized transport chunk (called on the process() seam)."""
        self._processed += len(chunk)
        if not self._bound or self._dropped:
            return
        self._retained += len(chunk)
        if self._retained > self._bound:
            # Bound trip: drop instead of growing; take() then yields nothing and the
            # article fails closed through the ordinary encrypted guard.
            self._chunks.clear()
            self._head_offset = 0
            self._retained = 0
            self._dropped = True
            return
        self._chunks.append(bytes(chunk))

    def take(self, nbytes: int) -> Optional[bytes]:
        """Return the next nbytes journaled bytes (one response slice), or None.

        Every completed response consumes its bytes_read from the connection-owned
        stream, even while the journal is inactive (None) - that keeps _consumed
        aligned so a later journal start offset is correct. The requested range is
        expressed in whole-stream coordinates: only the part overlapping the journal
        is consumed. A response that began before the journal started is necessarily
        not an encrypted article's response (arming precedes the command going out),
        so skipping its absent prefix (empty slice) keeps later responses aligned
        instead of misattributing bytes. A request the journal cannot satisfy fails
        closed: None, with the stream position left untouched.
        """
        if not nbytes:
            return None
        end = self._consumed + nbytes
        if not self._bound or self._dropped:
            # Inactive or dropped journal: account the response, return no data.
            self._consumed = end
            return None
        skip = max(0, min(self._journal_start - self._consumed, nbytes))
        if skip >= nbytes:
            # Nothing of this response was journaled; the response is accounted so
            # later responses stay aligned.
            self._consumed = end
            return b""
        need = nbytes - skip
        if self._retained < need:
            return None
        out = bytearray()
        remaining = need
        while remaining:
            chunk = self._chunks[0]
            available = len(chunk) - self._head_offset
            if available <= remaining:
                out += chunk[self._head_offset :]
                remaining -= available
                self._chunks.popleft()
                self._head_offset = 0
            else:
                cut = self._head_offset + remaining
                out += chunk[self._head_offset : cut]
                self._head_offset = cut
                remaining = 0
        self._consumed = end
        self._retained -= need
        return bytes(out)


class _RawLinesResponse:
    """Duck-typed carrier that presents reconstructed raw wire lines to the decoder.

    Wraps the real sabctools NNTPResponse and overrides only the fields that native
    auto-detection made untrustworthy for an encrypted article: lines carries the raw
    body lines, bytes_decoded is 0 (the bogus native output is not authenticated
    content) and format is None. Everything else delegates to the real response, and
    no plaintext exists until decode_yenc's restoration and authentication succeed.
    """

    __slots__ = ("_response", "_raw_lines")

    def __init__(self, response: sabctools.NNTPResponse, raw_lines: list[bytes]):
        self._response = response
        self._raw_lines = raw_lines

    @property
    def lines(self) -> list[bytes]:
        return self._raw_lines

    @property
    def bytes_decoded(self) -> int:
        return 0

    @property
    def format(self):
        return None

    def __getattr__(self, name: str):
        return getattr(self._response, name)


def _raw_body_lines(raw: bytes) -> list[bytes]:
    """Split a raw BODY response into its body lines.

    raw covers exactly one response (status line, body lines, "." terminator, CRLFs),
    already normalized to CRLF framing by NewsWrapper. The status line and the
    terminator are transport framing owned by sabctools, not article content.
    """
    elements = raw.split(b"\r\n")
    # Drop the status line, the "." terminator and the element after the final CRLF.
    return elements[1:-2]


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
        "ready",
        "user_sent",
        "pass_sent",
        "group",
        "user_ok",
        "pass_ok",
        "force_login",
        "next_request",
        "selector_events",
        "lock",
        "generation",
        "tls_wants_write",
        "_prev_chunk_ended_with_cr",
        "raw_capture",
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

        self.connected: bool = False  # TCP/TLS handshake complete
        self.ready: bool = False  # Auth complete, can serve requests
        self.user_sent: bool = False
        self.pass_sent: bool = False
        self.user_ok: bool = False
        self.pass_ok: bool = False
        self.force_login: bool = False
        self.group: Optional[str] = None

        # Command queue and concurrency
        self.next_request: Optional[tuple[bytes, Optional[sabnzbd.nzb.Article]]] = None
        self.selector_events = 0
        self.tls_wants_write: bool = False

        # Whether the previous TCP chunk's last byte was an unpaired '\r'. A '\n' arriving
        # at the start of the next chunk is then the second half of a CRLF, not a bare LF.
        self._prev_chunk_ended_with_cr: bool = False

        # Raw byte journal for declared-encrypted articles (see _RawBodyCapture). Armed
        # per request in write() when the outgoing command fetches an encrypted article;
        # inactive otherwise, so ordinary traffic never journals.
        self.raw_capture: Optional[_RawBodyCapture] = _RawBodyCapture()

    @property
    def article(self) -> Optional["sabnzbd.nzb.Article"]:
        """The article currently being downloaded"""
        with self.lock:
            if self.decoder is not None and (pending := self.decoder.pending):
                return pending[0]
            return None

    def init_connect(self):
        """Setup the connection in NNTP object"""
        # Sanity check, especially for the server test
        if not self.server.addrinfo:
            raise socket.error(errno.EADDRNOTAVAIL, T("Invalid server address."))

        # Construct buffer and NNTP object
        self.decoder = sabctools.Decoder(NNTP_BUFFER_SIZE)
        # New connection: no previous chunk, so no CRLF can be split across the reset
        self._prev_chunk_ended_with_cr = False
        self.nntp = NNTP(self, self.server.addrinfo)
        self.timeout = time.time() + self.server.timeout

        # On connect the first "response" will be 200 Welcome
        self.decoder.expect(None)

    def finish_connect(self, code: int, message: str) -> None:
        """Perform login options"""
        if not (self.server.username or self.server.password or self.force_login):
            self.ready = True
            self.user_sent = True
            self.user_ok = True
            self.pass_sent = True
            self.pass_ok = True

        if code == 480:
            self.force_login = True
            self.ready = False
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
                self.ready = True

        if self.user_ok and not self.pass_sent:
            command = utob("authinfo pass %s\r\n" % self.server.password)
            self.queue_command(command)
            self.pass_sent = True
        elif self.user_ok and not self.pass_ok:
            if code != 281:
                # Assume that login failed (code 481 or other)
                raise NNTPPermanentError(message, code)
            else:
                self.ready = True

        self.timeout = time.time() + self.server.timeout

    def article_sink(self, article: Optional["sabnzbd.nzb.Article"]) -> Optional[sabctools.FileWriter]:
        """Where this article's data should be written, or None to decode into memory.

        Decided before the request goes out, which is possible because the file an
        article belongs to is known then; only the offset within it is not, and the
        decoder reads that from the yEnc headers itself.

        Streaming is refused whenever the bytes are still needed in memory. The first
        article of a file is the clearest case: until the filename has been checked,
        decode_yenc uses the data to derive md5of16k and to rename the file, and the
        file has no path to write to yet. Those articles take the cache path exactly as
        before, so the in-memory route stays live in every configuration.

        It is also refused while the download directory is not keeping up with writes
        placed where they belong.
        """
        if not article or not sabnzbd.cfg.direct_decode() or not sabnzbd.cfg.direct_write():
            return None

        if article.nzf.nzo.yenc_encrypted:
            return None

        if not sabnzbd.WriteMonitor.allow_direct_decode:
            return None

        nzf = article.nzf
        # type is only known once the first article of the file has decoded, and uu
        # carries no offsets to write at
        if nzf.type != "yenc":
            return None
        # The first article is the one decode_yenc derives md5of16k from, so its bytes
        # have to be in memory. Every other article only feeds verify_nzf_filename,
        # which gives up as soon as there is a filepath - and there is one below.
        if article.lowest_partnum:
            return None
        if not nzf.prepare_filepath():
            return None

        try:
            return sabnzbd.Assembler.get_writer(nzf, stream=True)
        except OSError:
            # Cannot open the file: fall back to memory rather than failing the article
            logging.debug("Could not open %s for streaming", nzf.filepath, exc_info=True)
            return None

    def queue_command(
        self,
        command: bytes,
        article: Optional["sabnzbd.nzb.Article"] = None,
    ) -> None:
        """Add a command to the command queue"""
        if self.next_request:
            # This should never happen, but guard in case it does
            _, article = self.next_request
            self.discard(article, count_article_try=False)
        self.next_request = command, article

    def queue_article(self, article: "sabnzbd.nzb.Article"):
        """Add an article request to the command queue"""
        self.timeout = time.time() + self.server.timeout
        if article.nzf.nzo.precheck:
            if self.server.have_stat:
                command = utob("STAT <%s>\r\n" % article.article)
            else:
                command = utob("HEAD <%s>\r\n" % article.article)
        elif self.server.have_body or _requires_body(article):
            # Encrypted articles always use BODY: ARTICLE puts NNTP headers before the
            # yEnc body and a header blank line is not visible in sabctools' line list
            # (RFC 3977 section 3.1.1, Body Standard v1.2 section 9).
            command = utob("BODY <%s>\r\n" % article.article)
        else:
            command = utob("ARTICLE <%s>\r\n" % article.article)
        self.queue_command(command, article)

    def _with_raw_lines(
        self, article: Optional["sabnzbd.nzb.Article"], response: sabctools.NNTPResponse
    ) -> sabctools.NNTPResponse:
        """Reconstruct raw wire lines for an encrypted article native auto-detection consumed.

        When sabctools recognized the raw bootstrap as ordinary yEnc (a valid encrypted
        Line 1 salt can look exactly like "=ybegin "), the article bytes are lost from
        response.lines: only bogus decoded data remains. For declared-encrypted articles
        whose raw bytes were journaled, the raw body lines are sliced out and presented
        to the decoder through a read-only carrier. The journal is consumed FIFO per
        response (bytes_read partitions the consumed stream exactly), so every response
        received while the journal is active consumes its own slice to keep later
        responses aligned; slices for non-article or non-encrypted responses are
        discarded. The real response object is returned unchanged whenever
        reconstruction is not possible, and the native decoded data is never accepted
        as authenticated content - decode_yenc's restoration/authentication still
        decides, and a missing slice fails closed through the existing guard.
        """
        raw_capture = self.raw_capture
        raw: Optional[bytes] = None
        if raw_capture is not None and response.bytes_read:
            # Every completed response consumes its slice from the connection-owned
            # stream (even while the journal is inactive) so the accounting stays
            # aligned across journal (re)starts (DL-R8-1).
            raw = raw_capture.take(response.bytes_read)
            if article is not None and _captures_body(article):
                raw_capture.release(article)

        if article is None or not _requires_body(article):
            return response
        if response.lines or response.status_code != 222 or not raw:
            # Lines present (encrypted wire not autodetected): nothing to reconstruct.
            # Non-BODY statuses are transport bookkeeping, not an article. An empty
            # slice means this response began before the journal started (it cannot be
            # this encrypted article's response) or the bound tripped; either leaves
            # the real response, whose bogus native output the existing guard rejects
            # closed.
            return response
        raw_lines = _raw_body_lines(raw)
        if not raw_lines:
            return response
        return _RawLinesResponse(response, raw_lines)

    def on_response(self, response: sabctools.NNTPResponse, article: Optional["sabnzbd.nzb.Article"]) -> None:
        """A response to a NNTP request is received"""
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
            if not self.ready or not article or response.status_code in (281, 381, 480, 481, 482):
                self.discard(article, count_article_try=False)
                if not sabnzbd.Downloader.finish_connect_nw(self, response):
                    return
                if self.ready:
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

            elif response.status_code == 500 and _requires_body(article) and not article.nzf.nzo.precheck:
                # This server cannot serve BODY, and an encrypted article has no ARTICLE
                # fallback. The bodyless 500 is treated by Downloader.decode as a
                # missing article (next-server search); decoder.decode never runs for it.
                article_done = True

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
    ) -> tuple[int, Optional[int]]:
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

        article = self.article
        encrypted = bool(article and article.nzf.nzo.yenc_encrypted) or bool(
            self.raw_capture is not None and self.raw_capture.active
        )
        if encrypted:
            # Bare LF is rewritten to CRLF below, which at most doubles a chunk. Reading at most
            # half of the decoder buffer guarantees the rewritten chunk always fits.
            half = max(1, len(memoryview(self.decoder)) // 2)
            nbytes = min(nbytes, half) if nbytes else half

        # Receive data into the decoder pre-allocated buffer.
        # Encrypted reads deliberately avoid unlocked_ssl_recv_into: encrypted jobs have
        # nbytes capped at half the decoder buffer above (settled Q-2 half-cap, so the
        # bare-LF -> CRLF rewrite always fits), so the unlocked fast path — which takes
        # no nbytes — is never taken for them; only ordinary jobs use it.
        if not nbytes and self.nntp.nw.server.ssl and not self.nntp.nw.blocking and sabctools.openssl_linked:
            # Use patched version when downloading
            bytes_recv = sabctools.unlocked_ssl_recv_into(self.nntp.sock, self.decoder)
        else:
            bytes_recv = self.nntp.sock.recv_into(self.decoder, nbytes=nbytes)

        # No data received
        if bytes_recv == 0:
            raise ConnectionError("Server closed connection")

        # Data without a request, such as an idle timeout notice (ordinary traffic;
        # encrypted/article responses always have a request in flight). Synthetic
        # unit-test decoders have no real request accounting, so only a real
        # sabctools decoder enforces this.
        if not encrypted and not self.decoder.expected and isinstance(self.decoder, sabctools.Decoder):
            raise ConnectionError("Unsolicited data from server")

        # Success, move timeout
        self.timeout = time.time() + self.server.timeout

        # Line-ending handling at native transport seam (RFC 3977 §3.1.1):
        # sabctools requires CRLF to delimit NNTP response lines; when a server emits
        # bare LF, adapt the
        # wire buffer so the native transport parser can complete the response.
        # A CRLF can also be split across TCP chunks: a chunk that begins with a lone
        # '\n' is the second half of a CRLF when the previous chunk ended with '\r',
        # and must be left byte-exact or the article terminator is corrupted.
        # The split-CRLF flag is tracked from every raw chunk, so a '\r' received while
        # no response was encrypted yet pairs correctly with a '\n' that arrives once
        # an encrypted article is armed mid-connection (DL-R9-1).
        mv = memoryview(self.decoder)
        if encrypted:
            raw_chunk = bytes(mv[:bytes_recv])
            split_crlf = raw_chunk.startswith(b"\n") and self._prev_chunk_ended_with_cr
            # A '\n' is a bare LF only when not preceded by '\r', either inside this chunk
            # or by the previous chunk's trailing '\r' for a CRLF split across chunks.
            detect_chunk = (b"\r" + raw_chunk) if split_crlf else raw_chunk
            if b"\n" in detect_chunk.replace(b"\r\n", b""):
                norm_chunk = detect_chunk.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                if split_crlf:
                    # The leading '\n' already pairs with the previous chunk's '\r' in the
                    # buffer; drop the synthetic '\r' so it stays a single CRLF.
                    norm_chunk = norm_chunk[1:]
                mv[: len(norm_chunk)] = norm_chunk
                bytes_recv = len(norm_chunk)
        # The trailing '\r' is preserved by the bare-LF rewrite above, so tracking the
        # flag from the raw chunk stays valid across normalized and unnormalized chunks.
        self._prev_chunk_ended_with_cr = mv[bytes_recv - 1] == b"\r"[0]

        # Raw byte journal for declared-encrypted articles: every normalized byte handed
        # to the native Decoder is journaled so an article consumed by native yEnc
        # auto-detection can still be reconstructed from raw bytes (DL-R7-2). Bound to
        # the declared article size; ordinary releases never arm the journal. The
        # connection-owned stream accounting runs even while the journal is inactive,
        # so a journal that starts mid-response stays aligned (DL-R8-1).
        raw_capture = self.raw_capture
        if raw_capture is not None:
            raw_capture.add(memoryview(self.decoder)[:bytes_recv])

        self.decoder.process(bytes_recv)
        if self.decoder:
            for response in self.decoder:
                with self.lock:
                    # Check generation under lock to avoid racing with hard_reset
                    if self.generation != generation:
                        return bytes_recv, None
                article = response.context
                if on_response:
                    on_response(response.status_code, response.message)
                self.on_response(self._with_raw_lines(article, response), article)

            # on_response may have reset the connection
            if self.generation != generation:
                return bytes_recv, None

            # After each response this socket may need to be made available to write the next request,
            # or removed from socket monitoring to prevent hot looping.
            if self.prepare_request():
                # There is either a next_request, partial send, or an inflight request.
                self.modify_for_write()
            else:
                # Only remove the socket if it's not SSL or has no pending data, otherwise the recursive call may
                # call prepare_request again and find a request, but the socket would have already been removed.
                if not self.server.ssl or not self.nntp or not self.nntp.sock.pending():
                    # No further work for this socket
                    sabnzbd.Downloader.remove_socket(self)
        elif self.nntp and self.nntp.write_buffer:
            # No complete responses, but may be able to send partial writes.
            self.modify_for_write()

        # The SSL-layer might still contain data even though the socket does not. Another Downloader-loop would
        # not identify this socket anymore as it is not returned by select(). So, we have to forcefully trigger
        # another recv_chunk so the buffer is increased and the data from the SSL-layer is read. See #2752.
        if self.server.ssl and self.nntp and (pending := self.nntp.sock.pending()):
            return bytes_recv, pending
        return bytes_recv, None

    def modify_for_write(self):
        """
        Monitor for read/write events if there is a queued or partially sent request.

        If there is a next_request or partial write to send, ensure the socket is registered for write events.
        Sockets may be modified to monitor only read events when the concurrency limit is reached or an
        SSLWantReadError occurs.
        Checks before calling modify_socket to prevent locks on the hot path
        """
        if (
            self.next_request or (self.nntp and self.nntp.write_buffer)
        ) and self.selector_events != EVENT_READ | EVENT_WRITE:
            sabnzbd.Downloader.modify_socket(self, EVENT_READ | EVENT_WRITE)

    def prepare_request(self) -> bool:
        """Queue an article request if appropriate."""
        server = self.server

        # Do not pipeline requests until authentication is completed (connected)
        if not self.blocking and (self.ready or not (self.decoder is not None and self.decoder.expected)):
            server_ready = (
                server.active
                and not server.restart
                and not (
                    sabnzbd.Downloader.no_active_jobs()
                    or sabnzbd.Downloader.shutdown
                    or sabnzbd.Downloader.paused_for_postproc
                    or sabnzbd.Downloader.force_disconnect
                )
            )

            if server_ready:
                # Queue the next article if none exists
                if not self.next_request and (article := server.get_article()):
                    self.queue_article(article)
                    return True
            else:
                # Server not ready, discard next_request if it is for an article
                if self.next_request:
                    _, article = self.next_request
                    if article:
                        self.discard(article, count_article_try=False, retry_article=True)
                        self.next_request = None

        # Return True if there is work queued or in flight
        return bool(self.next_request or (self.decoder is not None and self.decoder.expected))

    def write(self):
        """Send data to server"""
        server = self.server

        try:
            # Flush any buffered data
            if self.nntp.write_buffer:
                sent = self.nntp.sock.send(self.nntp.write_buffer)
                self.nntp.write_buffer = self.nntp.write_buffer[sent:]
                # If buffer still has data, wait for next write opportunity
                if self.nntp.write_buffer:
                    return

            # If available, try to send new command
            if self.prepare_request():
                # Nothing to send but already requests in-flight
                if not self.next_request:
                    sabnzbd.Downloader.modify_socket(self, EVENT_READ)
                    return

                if self.decoder.expected < server.pipelining_requests:
                    command, article = self.next_request
                    if article:
                        nzo = article.nzf.nzo
                        if nzo.removed_from_queue or (
                            nzo.status is Status.PAUSED and nzo.priority is not FORCE_PRIORITY
                        ):
                            self.discard(article, count_article_try=False, retry_article=True)
                            self.next_request = None
                            return

                    if sabnzbd.LOG_ALL:
                        logging.debug("Thread %s@%s: %s", self.thrdnum, server.host, command)

                    # Arm the encrypted raw journal for this article before the command
                    # goes out, so the bytes of its response are journaled FIFO. Precheck
                    # STAT/HEAD answers carry no article body and never journal.
                    if article is not None and _captures_body(article):
                        if self.raw_capture is None:
                            self.raw_capture = _RawBodyCapture()
                        self.raw_capture.arm(article)

                    # Non-blocking send - buffer any unsent data
                    sent = self.nntp.sock.send(command)
                    if sent < len(command):
                        logging.debug("%s@%s: Partial send", self.thrdnum, server.host)
                        self.nntp.write_buffer = command[sent:]

                    self.decoder.expect(article, self.article_sink(article))
                    self.next_request = None
                else:
                    # Concurrency limit reached; wait until a response is read to prevent hot looping on EVENT_WRITE
                    sabnzbd.Downloader.modify_socket(self, EVENT_READ)
            else:
                # No further work for this socket
                sabnzbd.Downloader.remove_socket(self)
        except ssl.SSLWantWriteError:
            # Socket not ready for writing, keep buffer and wait for next write event
            pass
        except ssl.SSLWantReadError:
            # SSL renegotiation needs read first
            sabnzbd.Downloader.modify_socket(self, EVENT_READ)
        except BlockingIOError:
            # Socket not ready for writing, keep buffer and wait for next write event
            pass
        except socket.error as err:
            logging.info("Looks like server closed connection: %s, type: %s", err, type(err))
            sabnzbd.Downloader.reset_nw(self, "Server broke off connection", warn=True, wait=False)
        except Exception:
            logging.error(T("Suspect error in downloader"))
            logging.info("Traceback: ", exc_info=True)
            sabnzbd.Downloader.reset_nw(self, "Server broke off connection", warn=True)

    @synchronized(DOWNLOADER_LOCK)
    def hard_reset(self, wait: bool = True):
        """Destroy and restart"""
        with self.lock:
            # Release any encrypted raw journal storage before the wrapper is rebuilt
            if self.raw_capture is not None:
                self.raw_capture.set_inactive()

            # Drain unsent requests
            if self.next_request:
                _, article = self.next_request
                self.discard(article, count_article_try=False, retry_article=True)
                self.next_request = None
            # Drain responses. The decoder is replaced by __init__ below, so its own
            # queue goes with it; only the articles need handing back.
            if self.decoder is not None:
                for article in self.decoder.pending:
                    if article:
                        self.discard(article, count_article_try=False, retry_article=True)

            if self.nntp:
                sabnzbd.Downloader.remove_socket(self)
                self.nntp.close(send_quit=self.ready)
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
        if article:
            # Retire this article's encrypted raw journal bound; the fetch will re-arm
            if self.raw_capture is not None and _captures_body(article):
                self.raw_capture.release(article)
            # The job might return to the queue in the future so clear the current server
            if article.nzf.nzo.removed_from_queue:
                article.allow_new_fetcher()
                return

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
            self.ready,
        )


class NNTP:
    # Pre-define attributes to save memory
    __slots__ = ("nw", "addrinfo", "error_msg", "sock", "fileno", "closed", "write_buffer")

    def __init__(self, nw: NewsWrapper, addrinfo: AddrInfo):
        self.nw: NewsWrapper = nw
        # Add local reference to prevent crash in case the server.addrinfo is reset
        self.addrinfo: AddrInfo = addrinfo
        self.error_msg: Optional[str] = None

        # Prevent closing this socket until it's done connecting
        self.closed = False

        # Buffer for non-blocking writes
        self.write_buffer: bytes = b""

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
        self.sock: socket.socket | ssl.SSLSocket = socket.socket(self.addrinfo.family, self.addrinfo.type)
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
                        self.nw.connected = True
                        sabnzbd.Downloader.add_socket(self.nw)
        except OSError as e:
            self.error(e)

    def error(self, error: OSError):
        raw_error_str = str(error)
        if "SSL23_GET_SERVER_HELLO" in str(error) or "SSL3_GET_RECORD" in raw_error_str:
            error = T("This server does not allow SSL on this port")

        # Catch certificate errors
        if isinstance(error, ssl.CertificateError) or "CERTIFICATE_VERIFY_FAILED" in raw_error_str:
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
            # No reset-warning needed, above logging is sufficient
            sabnzbd.Downloader.reset_nw(self.nw)

    @synchronized(DOWNLOADER_LOCK)
    def close(self, send_quit: bool):
        """Safely close socket.
        Locked to match connect(), even though most likely the caller already holds the same lock."""
        # Set status first, so any calls in connect/error are handled correctly
        self.closed = True
        self.write_buffer = b""
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
