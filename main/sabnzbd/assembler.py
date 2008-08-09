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
sabnzbd.assembler - threaded assembly/decoding of files
"""
#------------------------------------------------------------------------------

__NAME__ = "assembler"

#OSX
import sys

import os
import Queue
import binascii
import logging
import sabnzbd

from sabnzbd.interface import CheckFreeSpace
from sabnzbd.misc import getFilepath, sanitize_filename
from threading import Thread
from time import sleep
if os.name == 'nt':
    import subprocess


#------------------------------------------------------------------------------
## sabnzbd.pause_downloader
class Assembler(Thread):
    def __init__ (self, download_dir, queue = None):
        Thread.__init__(self)

        self.download_dir = download_dir
        self.queue = queue

        if not self.queue:
            self.queue = Queue.Queue()

    def stop(self):
        self.process(None)

    def process(self, nzf):
        self.queue.put(nzf)

    def run(self):
        while 1:
            nzo_nzf_tuple = self.queue.get()
            if not nzo_nzf_tuple:
                logging.info("[%s] Shutting down", __NAME__)
                break

            nzo, nzf = nzo_nzf_tuple

            if nzf:
                CheckFreeSpace()
                filename = sanitize_filename(nzf.get_filename())
                nzf.set_filename(filename)

                dupe = nzo.check_for_dupe(nzf)

                filepath = getFilepath(self.download_dir, nzo, filename)

                if filepath:
                    logging.info('[%s] Decoding %s %s', __NAME__, filepath, nzf.get_type())
                    try:
                        # OSX fix for unicode chars
                        if sys.platform == 'darwin':
                            filepath = filepath.encode('utf8')
                            logging.info('utf8 filepath: ' + filepath)
                        _assemble(nzf, filepath, dupe)
                    except IOError, (errno, strerror):
                        # 28 == disk full => pause downloader
                        if errno == 28:
                            logging.error('[%s] Disk full! Forcing Pause', __NAME__)
                            sabnzbd.pause_downloader()
                        else:
                            logging.error('[%s] Disk error on creating file %s', __NAME__, filepath)
            else:
                sabnzbd.postprocess_nzo(nzo)


def _assemble(nzf, path, dupe):
    if os.path.exists(path):
        unique_path = get_unique_path(path, create_dir = False)
        if dupe:
            path = unique_path
        else:
            os.rename(path, unique_path)

    fout = open(path, 'ab')

    _type = nzf.get_type()
    decodetable = nzf.get_decodetable()

    for articlenum in decodetable:
        sleep(0.01)
        article = decodetable[articlenum]

        data = sabnzbd.load_article(article)

        if not data:
            logging.warning('[%s] %s missing', __NAME__, article)
        else:
            # yenc data already decoded, flush it out
            if _type == 'yenc':
                fout.write(data)
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
                            logging.info('[%s] Decode failed in part %s: %s',
                                         __NAME__, article.article, msg)
                fout.write(''.join(chunks))

    fout.flush()
    fout.close()
