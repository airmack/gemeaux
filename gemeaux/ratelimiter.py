import _thread
import time
from collections import Counter


class RateLimiter:
    def __init__(self):
        self.tokenDict = Counter()
        self.globaltokenDict = Counter()
        self.tokenLock = _thread.allocate_lock()
        self.SLEEPTIME = 60  # seconds
        self.PENALTY = 1  # penalty for acting naughty

    def ResetClientList(self):
        self.tokenLock.acquire(1)
        self.tokenDict = Counter()
        self.tokenLock.release()

    def run(self):
        while True:
            self.ResetClientList()
            time.sleep(self.SLEEPTIME)

    def GetToken(self, client, amount=1):
        return False


class NoRateLimiter(RateLimiter):
    """
    The NoRateLimiter will be used for when threading is disabled
    """

    def __init__(self):
        super().__init__()

    def ResetClientList(self):
        pass

    def run(self):
        pass

    def GetToken(self, client, amount=1):
        return True


class ConnectionLimiter(RateLimiter):
    """
    The ConnectionLimiter will hand out tokens to every client that conencts.
    Every client has a defined number of tokes that can be retrieved. If the pool of tokes is exhausted the connection is dropped.
    Drawback: Will not distinguis how much data is transferred therefore the share of traffic will not be equal
    """

    def __init__(self):
        super().__init__()

        self.CONNECTIONS_PER_SECOND = 10  # ~1MB
        self.SLEEPTIME = 1  # seconds
        self.PENALTY = 1

    def ResetClientList(self):
        self.tokenLock.acquire(1)
        self.tokenDict = Counter()
        self.tokenLock.release()

    def GetToken(self, client, amount=1):
        if not self.tokenLock.acquire(0):
            return False
        if client not in self.tokenDict:
            self.tokenDict[client] = amount
            self.tokenLock.release()
            return True
        self.tokenDict[client] += amount
        if self.tokenDict[client] >= self.CONNECTIONS_PER_SECOND:
            self.tokenLock.release()
            print(f"Client {client} used all its tokens {self.tokenDict[client]}")
            return False
        self.tokenLock.release()
        return True


class SpeedLimiter(RateLimiter):
    def __init__(self):
        self.MAX_DOWNLOAD_LIMIT_PER_MINUTE = 1000 * 1024  # ~1MB
        self.RESET_DOWNLOAD_LIMIT_PER_MINUTE = 10 * 1024  # 10 kB
        self.tokenDict = Counter()
        self.globaltokenDict = Counter()
        self.tokenLock = _thread.allocate_lock()
        self.SLEEPTIME = 60  # seconds
        self.PENALTY = 1000  # 1k penalty for acting naughty
        self.DEGREDATION = True

    def ResetClientList(self):
        self.tokenLock.acquire(1)
        deleteList = []
        for i in self.tokenDict:
            self.tokenDict[i] = int(self.tokenDict[i] / 4)
            if self.tokenDict[i] < self.RESET_DOWNLOAD_LIMIT_PER_MINUTE:
                deleteList.append(i)
        for i in deleteList:
            del self.tokenDict[i]
        self.tokenLock.release()

    def GetToken(self, client, amount=1):
        if not self.tokenLock.acquire(0):
            return False
        if client not in self.tokenDict:
            self.tokenDict[client] = amount
            self.tokenLock.release()
            return True
        self.tokenDict[client] += amount
        if self.tokenDict[client] >= self.MAX_DOWNLOAD_LIMIT_PER_MINUTE:
            self.tokenLock.release()
            print(f"Client {client} used all its tokens {self.tokenDict[client]}")
            return False
        self.tokenLock.release()
        return True

    pass
