import logging
#import hashlib
#import queue
import time
import os
#import gc
#import psutil
import zlib
import time
#import pprint
#from inspect import getmembers

import pickle
from threading import Thread
from collections import namedtuple

import sabnzbd
#import sabnzbd.cfg as cfg
#from sabnzbd.constants import SABYENC_VERSION_REQUIRED
#from sabnzbd.nzbstuff import Article
#from sabnzbd.misc import match_str

class Pickler(Thread):

    def __init__(self):
        Thread.__init__(self)
        logging.debug("Initializing pickler")

        # self.unpickle_queue: queue.Queue()

    def run(self):
        #proc = psutil.Process(os.getpid())
        before = 0
        after = 0
        # while 1:
        # before = proc.memory_info().rss
        # logging.debug("Memusage before gc: %d (%d)", before/1024, (before - after) / 1024)
        # gc.collect()
        # after = proc.memory_info().rss
        # logging.debug("Memusage after gc: %d (%d)", after/1024, (after - before) / 1024)
        # time.sleep(30)
        while 1:
            time.sleep(30)
            sabnzbd.NzbQueue.pickle()
