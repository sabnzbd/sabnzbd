import logging
import time
import pickle
import queue
from threading import Thread

import sabnzbd


class Unpickler(Thread):
    def __init__(self):
        Thread.__init__(self)
        logging.debug("Initializing unpickler")
        self.shutdown = False

        self.unpickle_queue = queue.PriorityQueue()
        self.sequence = 0

    def run(self):
        while 1:
            nzf = None
            priority, nzf, source = self.unpickle_queue.get()
            if not nzf:
                logging.info("Shutting down unpickler")
                while not self.unpickle_queue.empty():
                    try:
                        self.unpickle_queue.get(False)
                    except Empty:
                        continue
                break

            nzf.unpickle_articles(source)
            logging.debug("Unpickled pri %d article from %s", priority, source)
            time.sleep(0.001)

    def stop(self):
        self.sequence += 1
        self.unpickle_queue.put((1000 + self.sequence, None, None))

    def process(self, priority, nzf, source):
        logging.debug("Adding %s to unpickle queue. pri %d, source: %s", nzf.filename, priority, source)
        self.sequence += 1
        self.unpickle_queue.put((priority + self.sequence, nzf, source))
