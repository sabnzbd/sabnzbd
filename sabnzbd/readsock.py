import socket
import time
from typing import List

def readsock(sock: socket.socket):
    data: List[bytes] = []
    readcount: int = 0
    endtime: float = time.time() + 0.0005
    while 1:
        data.append(sock.recv(16384))
        readcount += 1
        if readcount >= 16 or time.time() > endtime or len(data[-1]) < 16384:
            return data
