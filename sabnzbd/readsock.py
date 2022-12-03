import socket
import time
from typing import List


def readsock(sock: socket.socket):
    data: List[bytes] = []
    readcount: int = 0
    totalsize: int = 0
    chunksize: int = 0
    endtime: float = time.time() + 0.00011
    while 1:
        data.append(sock.recv(16384))
        chunksize = len(data[-1])
        totalsize += chunksize
        readcount += 1
        if readcount >= 16 or chunksize < 16384 or time.time() > endtime:
            return data, chunksize
