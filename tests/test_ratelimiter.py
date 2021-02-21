# import pytest

from gemeaux import (
    ConnectionLimiter,
    NoRateLimiter,
    RateLimiter,
    SpeedAndConnectionLimiter,
    SpeedLimiter,
)


def test_connection_rate_limiter():
    for rl in [ConnectionLimiter(), SpeedAndConnectionLimiter()]:
        for i in range(0, 9):
            assert rl.AddNewConnection("::1") is True

        for i in range(0, 9):
            assert rl.AddNewConnection("::1") is False


def test_connection_rate_limiter_with_reset():
    for rl in [ConnectionLimiter(), SpeedAndConnectionLimiter()]:
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
            assert (
                abs(rl.sl.tokenDict["::1"] * 4 - MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10 * 8)
                < 1
            )
        else:
            assert (
                abs(rl.tokenDict["::1"] * 4 - MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10 * 8)
                < 1
            )
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


def test_violation_checker():
    for limiter in [RateLimiter(), NoRateLimiter()]:
        for i in range(0, 11):
            assert limiter.AddNewConnection("::1", 1) is True
            assert limiter.IsClientInViolation("::1") is False


def test_violation_limiter():
    for limiter in [ConnectionLimiter(), SpeedLimiter(), SpeedAndConnectionLimiter()]:
        for i in range(0, 9):
            assert limiter.IsClientInViolation("::1") is False


def test_violation_limiter_true():
    for limiter in [ConnectionLimiter(), SpeedAndConnectionLimiter()]:
        for i in range(0, 9):
            assert limiter.AddNewConnection("::1") is True

        assert limiter.AddNewConnection("::1") is False
        assert limiter.IsClientInViolation("::1") is True


def test_get_penalty_time_false():
    for limiter in [
        RateLimiter(),
        NoRateLimiter(),
        ConnectionLimiter(),
        SpeedLimiter(),
        SpeedAndConnectionLimiter(),
    ]:
        assert limiter.GetPenaltyTime("::1") == 0


def test_get_penalty_time_for_connection_true():
    for limiter in [ConnectionLimiter(), SpeedAndConnectionLimiter()]:
        for i in range(0, 9):
            assert limiter.AddNewConnection("::1") is True

        assert limiter.AddNewConnection("::1") is False
        assert limiter.IsClientInViolation("::1") is True
        assert limiter.GetPenaltyTime("::1") > 0


def test_get_penalty_time_for_speed_true():
    MAX_DOWNLOAD_LIMIT_PER_MINUTE = int(
        SpeedLimiter().MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10 + 0.5
    )
    for limiter in [SpeedLimiter(), SpeedAndConnectionLimiter()]:
        for i in range(0, 9):
            assert limiter.GetToken("::1", MAX_DOWNLOAD_LIMIT_PER_MINUTE) is True

        assert limiter.GetToken("::1", MAX_DOWNLOAD_LIMIT_PER_MINUTE) is False
        assert limiter.IsClientInViolation("::1") is True
        assert limiter.GetPenaltyTime("::1") > 0
