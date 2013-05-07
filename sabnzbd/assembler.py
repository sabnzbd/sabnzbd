#!/usr/bin/python -OO
# Copyright 2008-2012 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.assembler - threaded assembly/decoding of files
"""

import os
import Queue
import binascii
import logging
import struct
from threading import Thread
from time import sleep
try:
    import hashlib
    new_md5 = hashlib.md5
except:
    import md5
    new_md5 = md5.new

import sabnzbd
from sabnzbd.misc import get_filepath, sanitize_filename, get_unique_path, renamer, \
                         set_permissions, flag_file
from sabnzbd.constants import QCHECK_FILE
import sabnzbd.cfg as cfg
from sabnzbd.articlecache import ArticleCache
from sabnzbd.postproc import PostProcessor
import sabnzbd.downloader
from sabnzbd.utils.rarfile import RarFile, is_rarfile
from sabnzbd.encoding import latin1, unicoder, is_utf8


#------------------------------------------------------------------------------
class Assembler(Thread):
    do = None # Link to the instance of this method

    def __init__ (self, queue = None):
        Thread.__init__(self)

        if queue:
            self.queue = queue
        else:
            self.queue = Queue.Queue()
        Assembler.do = self

    def stop(self):
        self.process(None)

    def process(self, job):
        self.queue.put(job)

    def run(self):
        import sabnzbd.nzbqueue
        while 1:
            job = self.queue.get()
            if not job:
                logging.info("Shutting down")
                break

            nzo, nzf = job

            if nzf:
                sabnzbd.CheckFreeSpace()
                filename = sanitize_filename(nzf.filename)
                nzf.filename = filename

                dupe = nzo.check_for_dupe(nzf)

                filepath = get_filepath(cfg.download_dir.get_path(), nzo, filename)

                if filepath:
                    logging.info('Decoding %s %s', filepath, nzf.type)
                    try:
                        filepath = _assemble(nzf, filepath, dupe)
                    except IOError, (errno, strerror):
                        if nzo.deleted:
                            # Job was deleted, ignore error
                            pass
                        else:
                            # 28 == disk full => pause downloader
                            if errno == 28:
                                logging.error(Ta('Disk full! Forcing Pause'))
                            else:
                                logging.error(Ta('Disk error on creating file %s'), latin1(filepath))
                            # Pause without saving
                            sabnzbd.downloader.Downloader.do.pause(save=False)
                    except:
                        logging.error('Fatal error in Assembler', exc_info = True)
                        break

                    nzf.remove_admin()
                    setname = nzf.setname
                    if nzf.is_par2 and (nzo.md5packs.get(setname) is None):
                        pack = GetMD5Hashes(filepath)[0]
                        if pack:
                            nzo.md5packs[setname] = pack
                            logging.debug('Got md5pack for set %s', setname)

                    if check_encrypted_rar(nzo, filepath):
                        if cfg.pause_on_pwrar() == 1:
                            logging.warning(Ta('WARNING: Paused job "%s" because of encrypted RAR file'), latin1(nzo.final_name))
                            nzo.pause()
                        else:
                            logging.warning(Ta('WARNING: Aborted job "%s" because of encrypted RAR file'), latin1(nzo.final_name))
                            nzo.fail_msg = T('Aborted, encryption detected')
                            import sabnzbd.nzbqueue
                            sabnzbd.nzbqueue.NzbQueue.do.end_job(nzo)
                    nzf.completed = True
            else:
                sabnzbd.nzbqueue.NzbQueue.do.remove(nzo.nzo_id, add_to_history=False, cleanup=False)
                PostProcessor.do.process(nzo)


def _assemble(nzf, path, dupe):
    if os.path.exists(path):
        unique_path = get_unique_path(path, create_dir = False)
        if dupe:
            path = unique_path
        else:
            renamer(path, unique_path)

    fout = open(path, 'ab')

    if cfg.quick_check():
        md5 = new_md5()
    else:
        md5 = None

    _type = nzf.type
    decodetable = nzf.decodetable

    for articlenum in decodetable:
        sleep(0.001)
        article = decodetable[articlenum]

        data = ArticleCache.do.load_article(article)

        if not data:
            logging.info(Ta('%s missing'), article)
        else:
            # yenc data already decoded, flush it out
            if _type == 'yenc':
                fout.write(data)
                if md5: md5.update(data)
            # need to decode uu data now
            elif _type == 'uu':
                data = data.split('\r\n')

                chunks = []
                for line in data:
                    if not line:
                        continue

                    if line == '-- ' or line.startswith('Posted via '):
                        continue
                    try:
                        tmpdata = binascii.a2b_uu(line)
                        chunks.append(tmpdata)
                    except binascii.Error, msg:
                        ## Workaround for broken uuencoders by
                        ##/Fredrik Lundh
                        nbytes = (((ord(line[0])-32) & 63) * 4 + 5) / 3
                        try:
                            tmpdata = binascii.a2b_uu(line[:nbytes])
                            chunks.append(tmpdata)
                        except binascii.Error, msg:
                            logging.info('Decode failed in part %s: %s', article.article, msg)
                data = ''.join(chunks)
                fout.write(data)
                if md5: md5.update(data)

    fout.flush()
    fout.close()
    set_permissions(path)
    if md5:
        nzf.md5sum = md5.digest()
        del md5

    return path


def file_has_articles(nzf):
    """ Do a quick check to see if any articles are present for this file.
        Destructive: only to be used to differentiate between unknown encoding and no articles.
    """
    has = False
    decodetable = nzf.decodetable
    for articlenum in decodetable:
        sleep(0.01)
        article = decodetable[articlenum]
        data = ArticleCache.do.load_article(article)
        if data:
            has = True
    return has


# For a full description of the par2 specification, visit:
# http://parchive.sourceforge.net/docs/specifications/parity-volume-spec/article-spec.html

def GetMD5Hashes(fname, force=False):
    """ Get the hash table from a PAR2 file
        Return as dictionary, indexed on names and True for utf8-encoded names
    """
    new_encoding = True
    table = {}
    if force or not flag_file(os.path.split(fname)[0], QCHECK_FILE):
        try:
            f = open(fname, 'rb')
        except:
            return table, new_encoding

        new_encoding = False
        try:
            header = f.read(8)
            while header:
                name, hash = ParseFilePacket(f, header)
                new_encoding |= is_utf8(name)
                if name:
                    table[name] = hash
                header = f.read(8)

        except (struct.error, IndexError):
            logging.info('Cannot use corrupt par2 file for QuickCheck, "%s"', fname)
            table = {}
        except:
            logging.debug('QuickCheck parser crashed in file %s', fname)
            logging.info('Traceback: ', exc_info = True)
            table = {}

        f.close()
    return table, new_encoding


def ParseFilePacket(f, header):
    """ Look up and analyse a FileDesc package """

    nothing = None, None

    if header != 'PAR2\0PKT':
        return nothing

    # Length must be multiple of 4 and at least 20
    len = struct.unpack('<Q', f.read(8))[0]
    if int(len/4)*4 != len or len < 20:
        return nothing

    # Next 16 bytes is md5sum of this packet
    md5sum = f.read(16)

    # Read and check the data
    data = f.read(len-32)
    md5 = new_md5()
    md5.update(data)
    if md5sum != md5.digest():
        return nothing

    # The FileDesc packet looks like:
    # 16 : "PAR 2.0\0FileDesc"
    # 16 : FileId
    # 16 : Hash for full file **
    # 16 : Hash for first 16K
    #  8 : File length
    # xx : Name (multiple of 4, padded with \0 if needed) **

    # See if it's the right packet and get name + hash
    for offset in range(0, len, 8):
        if data[offset:offset+16] == "PAR 2.0\0FileDesc":
            hash = data[offset+32:offset+48]
            filename = data[offset+72:].strip('\0')
            return filename, hash

    return nothing


def is_cloaked(path, names):
    """ Return True if this is likely to be a cloaked encrypted post """
    fname = unicoder(os.path.split(path)[1]).lower()
    fname = os.path.splitext(fname)[0]
    for name in names:
        name = os.path.split(name.lower())[1]
        name, ext = os.path.splitext(unicoder(name))
        if (ext == u'.rar' and fname == name):
            logging.debug('File %s is probably encrypted due to RAR with same name inside this RAR', fname)
            return True
        elif 'password' in name:
            logging.debug('RAR %s is probably encrypted: "password" in filename %s', fname, name)
            return True
    return False


def check_encrypted_rar(nzo, filepath):
    """ Check if file is rar and is encrypted """
    encrypted = False
    if  not nzo.password and not nzo.meta.get('password') and cfg.pause_on_pwrar() and is_rarfile(filepath):
        try:
            zf = RarFile(filepath, all_names=True)
            encrypted = zf.encrypted or is_cloaked(filepath, zf.namelist())
            if encrypted and int(nzo.encrypted) < 2 and not nzo.reuse:
                nzo.encrypted = 1
            else:
                encrypted = False
            zf.close()
            del zf
        except:
            logging.debug('RAR file %s cannot be inspected', filepath)
    return encrypted

