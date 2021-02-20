# import pytest

from gemeaux import ConnectionLimiter, NoRateLimiter, RateLimiter, SpeedLimiter


def test_connection_rate_limiter():
    rl = ConnectionLimiter()
    for i in range(0, 9):
        assert rl.GetToken("::1", 1) is True

    for i in range(0, 9):
        assert rl.GetToken("::1", 1) is False


def test_connection_rate_limiter_with_reset():
    rl = ConnectionLimiter()
    for i in range(0, 9):
        assert rl.GetToken("::1", 1) is True
    rl.ResetClientList()
    assert rl.GetToken("::1", 1) is True
    for i in range(0, 8):
        assert rl.GetToken("::1", 1) is True
    assert rl.GetToken("::1", 1) is False


def test_speed_limiter():
    rl = SpeedLimiter()
    for i in range(0, 9):
        assert rl.GetToken("::1", rl.MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10) is True
    assert rl.GetToken("::1", rl.MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10) is False


def test_speed_limiter_with_reset():
    rl = SpeedLimiter()
    for i in range(0, 8):
        assert rl.GetToken("::1", rl.MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10) is True
    rl.ResetClientList()
    assert abs(rl.tokenDict["::1"] * 4 - rl.MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10 * 8) < 1
    for i in range(0, 4):
        rl.ResetClientList()
    assert ("::1" not in rl.tokenDict) is True


def test_no_rate_limiter():
    rl = NoRateLimiter()
    for i in range(0, 10):
        assert rl.GetToken("::1", 1) is True

    rl.ResetClientList()

    for i in range(0, 10):
        assert rl.GetToken("::1", 1) is True
