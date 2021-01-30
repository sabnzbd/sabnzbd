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
        self.sequence: int = 0
        self.previous_nzf: str = ""

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
            if priority < 100:
                time.sleep(0.01)
            logging.debug("Unpickled pri %d article from %s", priority, source)

    def stop(self):
        self.unpickle_queue.put((0, None, None))

    def process(self, priority, nzf, source):
        # The same nzf will be re-added every time it's hit by a server
        if self.previous_nzf == nzf.nzf_id:
            return
        else:
            self.previous_nzf = nzf.nzf_id
        self.sequence += 1
        self.unpickle_queue.put((priority + self.sequence, nzf, source))
