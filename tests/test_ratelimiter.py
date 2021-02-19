import pytest

from gemeaux import (
    RateLimiter
)


def test_basic_rate_limiter():
    rl = RateLimiter()
    for i in range(0,9):
        assert rl.GetToken("bla", int(rl.MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10)) is True

    for i in range(0,9):
        assert rl.GetToken("bla", int(rl.MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10)) is False

def test_basic_rate_limiter():
    rl = RateLimiter()
    for i in range(0,9):
        assert rl.GetToken("bla", int(rl.MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10)) is True
    rl.DEGREDATION = False
    rl.ResetClientList()
    assert rl.GetToken("bla", int(rl.MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10)) is True
    for i in range(0,8):
        assert rl.GetToken("bla", int(rl.MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10)) is True
    assert rl.GetToken("bla", int(rl.MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10)) is False


