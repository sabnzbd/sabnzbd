import logging

import time
import os

# import gc
# import psutil
import zlib
import time

# import pprint
# from inspect import getmembers

import pickle
import queue
from threading import Thread
from collections import namedtuple

import sabnzbd


class Unpickler(Thread):
    def __init__(self):
        Thread.__init__(self)
        logging.debug("Initializing unpickler")
        self.shutdown = False

        self.unpickle_queue = queue.PriorityQueue()

    def run(self):
        while 1:
            priority, nzf, source = self.unpickle_queue.get()
            if not nzf:
                logging.info("Shutting down unpickler")
                break

            nzf.unpickle_articles(source)
            logging.debug("Unpickled pri %f article from %s", priority, source)
            time.sleep(0.01)

    def stop(self):
        self.decoder_queue.put((1, None, None))

    def process(self, priority, nzf, source):
        logging.debug("Adding %s to unpickle queue. pri %f, source: %s", nzf.filename, priority, source)
        self.unpickle_queue.put((priority, nzf, source))
