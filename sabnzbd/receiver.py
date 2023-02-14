#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.receiver - article receiver
"""

import logging
import queue
import ssl
from threading import Thread
from typing import Tuple, Optional

import sabnzbd.cfg as cfg
from sabnzbd.newswrapper import NewsWrapper


class Receiver:
    """Implement thread-like coordinator for the receivers"""

    def __init__(self):
        # Initialize queue and servers
        self.request_queue = queue.Queue()
        self.result_queue = queue.Queue()

        # Initialize receivers
        receivers = cfg.receive_threads()
        logging.debug("Initializing %d receiver(s)", receivers)
        self.receiver_workers = []
        for _ in range(receivers):
            self.receiver_workers.append(ReceiverWorker(self.request_queue, self.result_queue))

    def start(self):
        for receiver_worker in self.receiver_workers:
            receiver_worker.start()

    def is_alive(self) -> bool:
        # Check all workers
        for receiver_worker in self.receiver_workers:
            if not receiver_worker.is_alive():
                return False
        return True

    def stop(self):
        # Put multiple to stop all receivers
        for _ in self.receiver_workers:
            self.request_queue.put(None)
            self.result_queue.put((None, 0, False))

    def join(self):
        # Wait for all receivers to finish
        for receiver_worker in self.receiver_workers:
            try:
                receiver_worker.join()
            except:
                pass

    def process(self, nw: NewsWrapper):
        self.request_queue.put(nw)

    def get_result(self):
        return self.result_queue.get()


class ReceiverWorker(Thread):
    """Checks newswrappers in the queue for new data"""

    def __init__(self, request_queue, result_queue):
        super().__init__()
        logging.debug("Initializing receiver %s", self.name)
        self.request_queue: queue.Queue[Optional[NewsWrapper]] = request_queue
        self.result_queue: queue.Queue[Tuple[Optional[NewsWrapper], int, bool]] = result_queue

    def run(self):
        while 1:
            nw = None
            nw = self.request_queue.get()

            if not nw:
                logging.debug("Shutting down receiver %s", self.name)
                break

            try:
                bytes_received, done = nw.recv_chunk()
                self.result_queue.put((nw, bytes_received, done))
            except ssl.SSLWantReadError:
                self.result_queue.put((nw, 0, False))
            except:
                self.result_queue.put((nw, 0, True))
