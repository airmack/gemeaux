import time
import _thread
import logging
from collections import Counter

class RateLimiter():
    def __init__(self):
        self.MAX_DOWNLOAD_LIMIT_PER_MINUTE = 1000*1024 # ~1MB
        self.RESET_DOWNLOAD_LIMIT_PER_MINUTE = 10*1024 # 10 kB
        self.tokenDict = Counter()
        self.globaltokenDict = Counter()
        self.tokenLock = _thread.allocate_lock()
        self.SLEEPTIME = 60 # seconds
        self.PENALTY = 1000 # 1k penalty for acting naughty
        self.DEGREDATION = True

    def ResetClientList(self):
        self.tokenLock.acquire(1)
        if self.DEGREDATION:
            for i in self.tokenDict:
                self.tokenDict[i] = int(self.tokenDict[i] / 4)
                if self.tokenDict[i] < self.RESET_DOWNLOAD_LIMIT_PER_MINUTE:
                    del self.tokenDict[i]
        if not self.DEGREDATION:
            self.tokenDict = Counter()
        self.tokenLock.release()

    def run(self):
        while True:
            self.ResetClientList()
            time.sleep(self.SLEEPTIME)

    def GetToken(self, client, amount = 1):
        if not self.tokenLock.acquire(0):
            return False
        if not client in self.tokenDict:
            self.tokenDict[client] = amount
            self.tokenLock.release()
            return True
        self.tokenDict[client] += amount
        if self.tokenDict[client] >= self.MAX_DOWNLOAD_LIMIT_PER_MINUTE :
            self.tokenLock.release()
            print(f"Client {client} used all its tokens {self.tokenDict[client]}")
            return False
        self.tokenLock.release()
        return True
