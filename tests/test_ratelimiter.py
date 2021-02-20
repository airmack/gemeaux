# import pytest

from gemeaux import ConnectionLimiter, NoRateLimiter, RateLimiter, SpeedLimiter, SpeedAndConnectionLimiter


def test_connection_rate_limiter():
    for rl in [ ConnectionLimiter(), SpeedAndConnectionLimiter()]:
        for i in range(0, 9):
            assert rl.AddNewConnection("::1") is True

        for i in range(0, 9):
            assert rl.AddNewConnection("::1") is False


def test_connection_rate_limiter_with_reset():
    for rl in [ ConnectionLimiter(), SpeedAndConnectionLimiter()]:
        for i in range(0, 9):
            assert rl.AddNewConnection("::1") is True
        rl.ResetClientList()
        assert rl.AddNewConnection("::1") is True
        for i in range(0, 8):
            assert rl.AddNewConnection("::1") is True
        assert rl.AddNewConnection("::1") is False


def test_speed_limiter():
    MAX_DOWNLOAD_LIMIT_PER_MINUTE = SpeedLimiter().MAX_DOWNLOAD_LIMIT_PER_MINUTE
    for rl in [SpeedLimiter(), SpeedAndConnectionLimiter()]:
        for i in range(0, 9):
            if isinstance(rl, SpeedAndConnectionLimiter):
                assert rl.sl.GetToken("::1", MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10) is True
            else:
                assert rl.GetToken("::1", MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10) is True
        if isinstance(rl, SpeedAndConnectionLimiter):
            assert rl.sl.GetToken("::1", MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10) is False
        else:
            assert rl.GetToken("::1", MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10) is False


def test_speed_limiter_with_reset():
    MAX_DOWNLOAD_LIMIT_PER_MINUTE = SpeedLimiter().MAX_DOWNLOAD_LIMIT_PER_MINUTE
    for rl in [SpeedLimiter(), SpeedAndConnectionLimiter()]:
        for i in range(0, 8):
            assert rl.GetToken("::1", MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10) is True
        rl.ResetClientList()
        if isinstance(rl, SpeedAndConnectionLimiter):
            assert abs(rl.sl.tokenDict["::1"] * 4 - MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10 * 8) < 1
        else:
            assert abs(rl.tokenDict["::1"] * 4 - MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10 * 8) < 1
        for i in range(0, 4):
            rl.ResetClientList()
        if isinstance(rl, SpeedAndConnectionLimiter):
            assert ("::1" not in rl.sl.tokenDict) is True
        else:
            assert ("::1" not in rl.tokenDict) is True


def test_no_rate_limiter():
    rl = NoRateLimiter()
    for i in range(0, 10):
        assert rl.GetToken("::1", 1) is True

    rl.ResetClientList()

    for i in range(0, 10):
        assert rl.GetToken("::1", 1) is True
