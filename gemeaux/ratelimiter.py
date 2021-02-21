import _thread
import time
from collections import Counter

from .log import LoggingBuilder


class HallOfShame:
    """ A hall of shame for clients that do not honour slow down message or are otherwise naughty"""

    def __init__(self):
        self.STRIKES_TO_BAN = 3
        self.hall = Counter()
        self.log = LoggingBuilder(
            "HallOfShame", "/var/log/gemeaux/", "hall_of_shame.log"
        )

    def AddToHall(self, client):
        if client not in self.hall:
            self.hall[client] = 1
        else:
            self.hall[client] += 1
        if self.hall[client] > self.STRIKES_TO_BAN:
            self.AddLogEntry(client)

    def AddLogEntry(self, client):
        self.log.critical(f"{client} is temporarily disabled")


class RateLimiter:
    """ Base class for rate limiter defining the default behavior of the subclasses """

    def __init__(self):
        self.tokenDict = Counter()
        self.tokenLock = _thread.allocate_lock()
        self.hallOfShame = HallOfShame()
        self.SLEEPTIME = 60  # seconds
        self.PENALTY = 1  # penalty for acting naughty
        self.penaltyTime = self.SLEEPTIME
        self.log = LoggingBuilder("RateLimiter", "/var/log/gemeaux/", "RateLimiter.log")

    def ResetClientList(self):
        self.tokenLock.acquire(1)
        self.tokenDict = Counter()
        self.tokenLock.release()

    def AddNewConnection(self, client, amount=1):
        return self.GetToken(client, amount)

    def run(self):
        while True:
            time.sleep(self.SLEEPTIME)
            for client in self.tokenDict:
                if self.IsClientInViolation(client):
                    self.hallOfShame.AddToHall(client)
            self.ResetClientList()

    def GetToken(self, client, amount=1):
        return True

    def GetPenaltyTime(self, client):
        if self.IsClientInViolation(client):
            return self.penaltyTime
        return 0

    def IsClientInViolation(self, client):
        return False


class NoRateLimiter(RateLimiter):
    """
    The NoRateLimiter will be used for when threading is disabled
    """

    def __init__(self):
        super().__init__()

    def ResetClientList(self):
        pass

    def AddNewConnection(self, client, amount=1):
        return self.GetToken(client, 1)

    def run(self):
        pass

    def GetToken(self, client, amount=1):
        return True


class ConnectionLimiter(RateLimiter):
    """
    The ConnectionLimiter will hand out tokens to every client that conencts.
    Every client has a defined number of tokes that can be retrieved. If the pool of tokes is exhausted the connection is dropped.
    Drawback: Will not distinguish how much data is transferred therefore the share of traffic will not be equal
    """

    def __init__(self):
        super().__init__()

        self.CONNECTIONS_PER_SECOND = 10  # 10 Connections per
        self.SLEEPTIME = 1  # seconds
        self.PENALTY = 1
        self.penaltyTime = self.SLEEPTIME

    def AddNewConnection(self, client, amount=1):
        if not self.tokenLock.acquire(0):
            return False
        if client not in self.tokenDict:
            self.tokenDict[client] = amount
        else:
            self.tokenDict[client] += amount
        if self.tokenDict[client] >= self.CONNECTIONS_PER_SECOND:
            self.tokenLock.release()
            if amount != 0:
                self.log.warning(
                    f"Client {client} used all its connections-tokens {self.tokenDict[client]}"
                )
            return False
        self.tokenLock.release()
        return True

    def ResetClientList(self):
        self.tokenLock.acquire(1)
        self.tokenDict = Counter()
        self.tokenLock.release()

    def GetToken(self, client, amount=1):
        return True

    def IsClientInViolation(self, client):
        return not self.AddNewConnection(client, 0)


class SpeedLimiter(RateLimiter):
    """
    The SpeedLimiter will hand out tokens to every clients transferrate in bytes.
    Every client has a defined number of tokes-bytes that can be retrieved. If the pool of tokes is exhausted the connection is dropped.
    Drawback: Will not distinguish how many connection were made and therefore clients with no traffic will not use up any tokens.
    """

    def __init__(self):
        super().__init__()
        self.MAX_DOWNLOAD_LIMIT_PER_MINUTE = 1000 * 1024  # ~1MB
        self.RESET_DOWNLOAD_LIMIT_PER_MINUTE = 10 * 1024  # 10 kB
        self.tokenDict = Counter()
        self.tokenLock = _thread.allocate_lock()
        self.SLEEPTIME = 60  # seconds
        self.PENALTY = 1000  # 1k penalty for acting naughty
        self.DEGRADATION_FACTOR = 4
        self.penaltyTime = self.SLEEPTIME

    def ResetClientList(self):
        self.tokenLock.acquire(1)
        deleteList = []
        for i in self.tokenDict:
            self.tokenDict[i] = int(self.tokenDict[i] / self.DEGRADATION_FACTOR)
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
        else:
            self.tokenDict[client] += amount
        if self.tokenDict[client] >= self.MAX_DOWNLOAD_LIMIT_PER_MINUTE:
            self.tokenLock.release()
            if amount != 0:
                self.log.warning(
                    f"Client {client} used all its byte-tokens {self.tokenDict[client]}"
                )
            return False
        self.tokenLock.release()
        return True

    def IsClientInViolation(self, client):
        return not self.GetToken(client, 0)


class SpeedAndConnectionLimiter(RateLimiter):
    def __init__(self):

        self.sl = SpeedLimiter()
        self.cl = ConnectionLimiter()

    def ResetClientList(self):
        self.sl.ResetClientList()
        self.cl.ResetClientList()

    def AddNewConnection(self, client, amount=1):
        return self.cl.AddNewConnection(client, amount)

    def GetToken(self, client, amount=1):
        return self.sl.GetToken(client, amount)

    def run(self):
        _thread.start_new_thread(self.cl.run, ())
        _thread.start_new_thread(self.sl.run, ())

    def IsClientInViolation(self, client):
        for limiter in [self.sl, self.cl]:
            if limiter.IsClientInViolation(client):
                return True
        return False

    def GetPenaltyTime(self, client):
        maxPenaltyTime = 0
        for limiter in [self.sl, self.cl]:
            maxPenaltyTime = max(maxPenaltyTime, limiter.GetPenaltyTime(client))
        return maxPenaltyTime
