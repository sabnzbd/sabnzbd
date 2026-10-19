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
sabnzbd.decoder - article decoder
"""

import io
import logging
import hashlib
from typing import Optional

import sabctools
import sabnzbd
from sabnzbd.constants import SABCTOOLS_VERSION_REQUIRED, Status
from sabnzbd.nzb import Article
from sabnzbd.misc import match_str
from sabnzbd.encryption import (
    DecryptionAdapter,
    YEncEncryptionCryptoError,
    YEncEncryptionStructuralError,
    extract_and_remove_yencryption,
    neutral_ybegin_name,
)

# Check for correct SABCTools version
SABCTOOLS_VERSION = None
SABCTOOLS_SIMD = None
SABCTOOLS_OPENSSL_LINKED = None
try:
    import sabctools

    SABCTOOLS_ENABLED = True
    SABCTOOLS_VERSION = sabctools.__version__
    SABCTOOLS_SIMD = sabctools.simd
    SABCTOOLS_OPENSSL_LINKED = sabctools.openssl_linked
    # Verify version to at least match minor version by splitting on "."
    if SABCTOOLS_VERSION.split(".")[:2] != SABCTOOLS_VERSION_REQUIRED.split(".")[:2]:
        raise ImportError
except Exception:
    SABCTOOLS_ENABLED = False


class BadData(Exception):
    def __init__(self, data: bytearray):
        super().__init__()
        self.data = data


class BadYenc(Exception):
    pass


class BadUu(Exception):
    pass


class SinkFailed(Exception):
    """A streamed article could not be written, so nothing was kept.

    Deliberately not a BadYenc: that handler inspects the response lines and can decide
    the article was fine after all, which would mark an article as successful when it
    is not on disk anywhere.
    """


def _get_decryption_adapter(article: Article, password: Optional[str]) -> DecryptionAdapter:
    """Retrieve cached DecryptionAdapter from the parent Nzo or create a new one."""
    nzo = article.nzf.nzo
    with nzo.lock:
        adapter = getattr(nzo, "_decryption_adapter", None)
        if adapter is not None and adapter.password == password:
            return adapter
        adapter = DecryptionAdapter(password=password)
        nzo._decryption_adapter = adapter
        return adapter


def decode(article: Article, decoder: sabctools.NNTPResponse):
    decoded_data: Optional[bytearray] = None
    nzo = article.nzf.nzo
    is_encrypted = bool(nzo.yenc_encrypted)
    art_id = article.article

    # Keeping track
    article_success = False

    try:
        if nzo.precheck:
            raise BadYenc

        if sabnzbd.LOG_ALL:
            logging.debug("Decoding %s", art_id)

        if is_encrypted:
            decoded_data = decode_yenc(article, decoder)
        elif decoder.format is sabctools.EncodingFormat.UU:
            decoded_data = decode_uu(article, decoder)
        else:
            decoded_data = decode_yenc(article, decoder)

        article_success = True

    except MemoryError:
        logging.warning(T("Decoder failure: Out of memory"))
        logging.info("Cache: %d, %d, %d", *sabnzbd.ArticleCache.cache_info())
        logging.info("Traceback: ", exc_info=True)
        sabnzbd.Downloader.pause()

        # This article should be fetched again
        article.allow_new_fetcher()
        return

    except BadData as error:
        # Continue to the next one if we found new server
        if search_new_server(article):
            return

        # Store data, maybe par2 can still fix it
        decoded_data = error.data

    except BadUu:
        # UU articles in an encrypted release were rejected before dispatch, so this
        # BadUu always belongs to an unencrypted article.
        logging.info("Badly formed uu article in %s", art_id)

        # Try the next server
        if search_new_server(article):
            return

    except YEncEncryptionStructuralError as error:
        # Structural metadata failure (missing password, unsupported mode): fail the
        # article without trying other servers (METADATA_VALIDATION tier). No other
        # server can resolve a local structural error, so retrying remaining articles
        # would only waste fetches and could register successes that falsely revive
        # the job. End the whole job through the existing fail-to-history lifecycle:
        # the queue stops scheduling the job and post-processing records it as
        # FAILED with the fail_msg preserved.
        logging.error(T("Structural yEnc-encryption failure in %s: %s"), art_id, error)
        # Several articles of one job are normally in flight when the first
        # structural error aborts it. A second in-flight article failing
        # structurally must not run the fail-to-history lifecycle again:
        # PostProcessor.process would re-queue the already-FAILED job for a
        # second post-processing pass (and re-run it once more in history).
        if nzo.removed_from_queue:
            return
        nzo.fail_msg = T("Structural yEnc-encryption failure: missing or invalid metadata")
        nzo.set_unpack_info("Download", nzo.fail_msg)
        # Mark failed so pp_or_finished discards any in-flight articles of this job
        nzo.status = Status.FAILED
        sabnzbd.NzbQueue.fail_to_history(nzo)
        return

    except YEncEncryptionCryptoError as error:
        # Crypto wire failure on encrypted articles (authentication failure, FF1
        # control-line decrypt failure, corrupt bootstrap, non-BODY status): log the
        # reason without secrets and query next server (retryable provider corruption).
        logging.info("Encrypted article %s rejected (%s), trying next server", art_id, error)

        # Continue to the next one if we found new server
        if search_new_server(article):
            return

        decoded_data = None

    except SinkFailed:
        # The file went away under the article, so it has to be fetched again. Any
        # part of it already written is overwritten at the same offsets next time.
        logging.info("Could not write %s to its file, fetching it again", art_id)

        if search_new_server(article):
            return

    except OSError as error:
        # The same response the assembler gives a failed write. Fetching the article
        # again cannot fix a full disk, and doing so would spend its retries and then
        # fail the job as incomplete - so pause instead and leave the article to be
        # picked up again once there is room.
        if sabnzbd.filesystem.out_of_space(error):
            logging.error(T("Disk full! Forcing Pause"))
        else:
            logging.error(T("Disk error on creating file %s"), error.filename)
        logging.info("Traceback: ", exc_info=True)
        sabnzbd.Downloader.pause()
        article.allow_new_fetcher()
        return

    except (BadYenc, ValueError):
        # Handles precheck and badly formed articles
        if nzo.precheck and decoder.status_code == 223:
            # STAT was used, so we only get a status code
            article_success = True
        else:
            # Examine the headers (for precheck) or body (for download).
            if lines := decoder.lines:
                for line in lines:
                    lline = line.lower()
                    if lline.startswith("message-id:"):
                        article_success = True
                    # Look for DMCA clues (while skipping "X-" headers)
                    if not lline.startswith("x-") and match_str(lline, ("dmca", "removed", "cancel", "blocked")):
                        article_success = False
                        logging.info("Article removed from server (%s)", art_id)
                        break

        # Pre-check, proper article found so just register
        if nzo.precheck and article_success and sabnzbd.LOG_ALL:
            logging.debug("Server %s has article %s", article.fetcher, art_id)
        elif not article_success:
            # If not pre-check, this must be a bad article
            if not nzo.precheck:
                logging.info("Badly formed yEnc article %s", art_id)

            # Continue to the next one if we found new server
            if search_new_server(article):
                return

    except Exception:
        logging.warning(T("Unknown Error while decoding %s"), art_id)
        logging.info("Traceback: ", exc_info=True)

        # Continue to the next one if we found new server
        if search_new_server(article):
            return

    if decoded_data:
        # If the data needs to be written to disk due to full cache, this will be slow
        # Causing the decoder-queue to fill up and delay the downloader
        sabnzbd.ArticleCache.save_article(article, decoded_data)
        article.decoded = True
    elif not nzo.precheck and (article_success or not is_encrypted):
        # Either there was nothing to save, or the decoder streamed it straight to the
        # file. Both are on disk as far as the rest of the pipeline is concerned; the
        # assembler advances past an on_disk article on its own when it next runs.
        article.on_disk = True

    sabnzbd.NzbQueue.register_article(article, article_success)


def decode_yenc(article: Article, response: sabctools.NNTPResponse) -> Optional[bytearray]:
    """Record what the decoder produced.

    data is None when the article was streamed straight to its file rather than
    decoded into memory. Everything the caller needs is still reported - sizes, offset,
    CRC - so the only difference is that there is nothing left to cache or assemble.
    """
    # The job was deleted while the article was arriving, or the write failed. The
    # decoder consumed the response anyway so the connection survives, but nothing was
    # kept, so this is a failed article rather than one on disk.
    if response.sink_failed:
        # A closed file means the job went away while the article was arriving, and it
        # only needs fetching again. Anything else is a real disk error - a full disk,
        # most often - and is re-raised as the OSError it came from so it gets the same
        # handling as a failed write from the assembler.
        if isinstance(response.sink_error, OSError):
            raise response.sink_error
        raise SinkFailed

    nzf = article.nzf

    # Encrypted articles are only accepted from BODY (222), whose response starts at the
    # yEnc body. An ARTICLE (220) response starts with NNTP headers whose blank-line
    # boundary sabctools does not report, and the body must never be found by trial
    # decryption (Body Standard v1.2 section 9). Any other status fails closed as
    # provider failover.
    is_encrypted = bool(nzf.nzo.yenc_encrypted)
    if is_encrypted and response.status_code != 222:
        raise YEncEncryptionCryptoError(
            f"Encrypted article {article.article} answered with status {response.status_code}, not BODY"
        )

    # Body Standard v1.2 section 9: reject substitutions before format dispatch,
    # metadata mutation, salvage, or caching. Only encrypted wire lines may proceed.
    if is_encrypted and (
        response.format is sabctools.EncodingFormat.UU or response.bytes_decoded or not response.lines
    ):
        raise YEncEncryptionCryptoError(
            f"UNAUTHENTICATED_ARTICLE: unencrypted article {article.article} in a yEnc-encrypted release"
        )

    # Encrypted wire response: sabctools couldn't decode because control lines were FF1-encrypted
    if is_encrypted:
        lines = [line.encode("latin-1") if isinstance(line, str) else line for line in response.lines]

        password = nzf.nzo.password
        adapter = _get_decryption_adapter(article, password=password)

        # Dot-unstuffing adapter (RFC 3977 §3.1.1 transport boundary). On the encrypted
        # path sabctools cannot recognize yEnc (the =ybegin line is FF1-encrypted), so
        # response.lines carry RAW presentation bytes with '..' intact - unlike the data
        # path, where sabctools unstuffs during yEnc decoding. Producers MUST dot-stuff
        # (a Line 1 salt byte can legitimately be 0x2E); consumers MUST unstuff before
        # line splitting/bootstrap extraction: '..' maps to content '.', and a lone
        # single '.' is the article terminator (already consumed by sabctools here).
        lines = [line[1:] if line.startswith(b"..") else line for line in lines]

        # NewsWrapper already normalizes encrypted transport framing for sabctools.
        # NNTPResponse.lines has no terminators; control tweaks depend on line indices.
        raw_wire = b"\r\n".join(lines) + b"\r\n"

        restored_block, salt_line1, seg_idx_line1 = adapter.restore_control_lines(raw_wire)
        yenc_params, clean_yenc = extract_and_remove_yencryption(restored_block)

        if yenc_params["salt"] != salt_line1:
            # Salt is debug-only; the INFO line for this failure must not carry it
            logging.debug(
                "Salt mismatch: control line 1 %s, =yencryption %s",
                salt_line1.hex(),
                yenc_params["salt"].hex(),
            )
            raise YEncEncryptionCryptoError("Salt mismatch between control line 1 and =yencryption")

        if yenc_params["segment_index"] != seg_idx_line1:
            raise YEncEncryptionCryptoError(
                "Dual index mismatch between control line 1 and =yencryption: segment index differs"
            )

        # Constant synthetic response status; the sub-decoder never reads the Message-ID.
        # sabctools requires CRLF framing for its internal parsing state machine.
        clean_yenc = neutral_ybegin_name(clean_yenc)
        clean_wire = b"222 0 <x>\r\n" + clean_yenc + b".\r\n"

        dec = sabctools.Decoder(len(clean_wire))
        reader = io.BytesIO(clean_wire)
        reader.readinto(dec)
        dec.process(len(clean_wire))
        try:
            sub_resp = next(dec)
        except StopIteration:
            raise YEncEncryptionCryptoError("Truncated or malformed yEnc block in encrypted article")

        if sub_resp.crc is None:
            raise YEncEncryptionCryptoError(f"Wire CRC error in encrypted article {article.article}")

        plaintext = adapter.decrypt_body(
            ciphertext=bytes(sub_resp.data or b""),
            tag=yenc_params["tag"],
            salt=yenc_params["salt"],
            segment_index=seg_idx_line1,
            aad=yenc_params["aad"],
        )

        # Body Standard v1.2 §2.1: the Poly1305 tag authenticates the DECLARED
        # geometry (=ybegin size / =ypart range) carried in the AAD, but a corrupted
        # or truncated-then-reCRC'd article can carry plaintext whose ACTUAL length
        # differs from that declaration. sabctools' sub-decoder does not validate
        # actual-vs-declared (part_size mirrors the declared keywords), so this check
        # is made here, before any article mutation or cache write, so a wrong-length
        # plaintext can never reach the cache or disk. Treated as provider corruption
        # (PROVIDER_FAILOVER tier), like other corrupt-provider-copy failures.
        if len(plaintext) != yenc_params["segment_bytes"]:
            raise YEncEncryptionCryptoError(
                f"LENGTH_MISMATCH: decrypted plaintext is {len(plaintext)} bytes but declared geometry is "
                f"{yenc_params['segment_bytes']} bytes"
            )

        decoded_data = bytearray(plaintext)
        article.file_size = sub_resp.file_size
        article.data_begin = sub_resp.part_begin
        article.data_size = sub_resp.part_size
        article.decoded_size = len(decoded_data)
        # Never persist the ciphertext CRC into any verification path. The wire CRC
        # covers ciphertext, not plaintext; PAR2 verifies the authenticated plaintext.
        article.crc32 = None
        nzf.type = "yenc"

        if not nzf.filename_checked and (file_name := yenc_params.get("file_name")):
            if article.lowest_partnum:
                nzf.md5of16k = hashlib.md5(memoryview(decoded_data)[:16384]).digest()
            nzf.nzo.verify_nzf_filename(nzf, file_name)

        return decoded_data

    # Let SABCTools do all the heavy lifting
    decoded_data = response.data
    article.file_size = response.file_size
    article.data_begin = response.part_begin
    article.data_size = response.part_size
    article.decoded_size = response.bytes_decoded

    # Assume it is yenc
    nzf.type = "yenc"

    # Only set the name if it was found and not obfuscated. Streamed articles never
    # reach here: a sink is only handed out once the filename has been checked, exactly
    # because this needs the bytes.
    if decoded_data is not None and not nzf.filename_checked and (file_name := response.file_name):
        # Set the md5-of-16k if this is the first article
        if article.lowest_partnum:
            nzf.md5of16k = hashlib.md5(memoryview(decoded_data)[:16384]).digest()

        # Try the rename, even if it's not the first article
        # For example when the first article was missing
        nzf.nzo.verify_nzf_filename(nzf, file_name)

    # CRC check
    if (crc := response.crc) is None:
        logging.info("CRC Error in %s", article.article)
        # A streamed article is already on disk, so there is nothing to hand back; the
        # bytes stay put either way, so par2 has the same chance of repairing it
        raise BadData(decoded_data)

    article.crc32 = crc

    return decoded_data


def decode_uu(article: Article, response: sabctools.NNTPResponse) -> bytearray:
    """Process a uu-decoded response"""
    if not response.bytes_decoded:
        logging.debug("No data to decode")
        raise BadUu

    if response.baddata:
        raise BadData(response.data)

    decoded_data = response.data
    article.decoded_size = response.bytes_decoded
    nzf = article.nzf
    nzf.type = "uu"

    # Only set the name if it was found and not obfuscated
    if not nzf.filename_checked and (file_name := response.file_name):
        # Set the md5-of-16k if this is the first article
        if article.lowest_partnum:
            nzf.md5of16k = hashlib.md5(memoryview(decoded_data)[:16384]).digest()

        # Try the rename, even if it's not the first article
        # For example when the first article was missing
        nzf.nzo.verify_nzf_filename(nzf, file_name)

    article.crc32 = response.crc

    return decoded_data


def search_new_server(article: Article) -> bool:
    """Shorthand for searching new server or else increasing bad_articles"""
    # Continue to the next one if we found new server
    if not article.search_new_server():
        # Increase bad articles if no new server was found
        article.nzf.nzo.increase_bad_articles_counter("bad_articles")
        return False
    return True
