from unittest.mock import patch

from tempfilehandler import TemporaryFileHandler

from gemeaux import (
    ArgsConfig,
    ConnectionLimiter,
    HallOfShame,
    NoRateLimiter,
    RateLimiter,
    RateLimiterBuilder,
    SpeedAndConnectionLimiter,
    SpeedLimiter,
    ZeroConfig,
)


def DoNothing(text):
    pass


def test_HOS():
    hos = HallOfShame(3, "/tmp/test")
    hos.AddLogEntry = DoNothing  # monkey patch
    assert len(hos.hall.keys()) == 0
    hos.AddToHall("::1")
    assert hos.hall["::1"] == 1

    hos.AddToHall("::1")
    assert hos.hall["::1"] == 2
    hos.AddToHall("::1")
    assert hos.hall["::1"] == 3

    hos.AddToHall("::1")
    assert hos.hall["::1"] == 4


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
        tc = rl
        if isinstance(rl, SpeedAndConnectionLimiter):
            tc = rl.sl
        for i in range(0, 9):
            assert tc.GetToken("::1", MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10) is True
        assert tc.GetToken("::1", MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10) is False

        tc.ResetClientList()
        tc.tokenLock.acquire(0)
        tc.GetToken("::1", MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10) is False
        tc.tokenLock.release()


def test_speed_limiter_with_reset():
    MAX_DOWNLOAD_LIMIT_PER_MINUTE = SpeedLimiter().MAX_DOWNLOAD_LIMIT_PER_MINUTE
    for rl in [SpeedLimiter(), SpeedAndConnectionLimiter()]:
        tc = rl
        if isinstance(rl, SpeedAndConnectionLimiter):
            tc = rl.sl

        for i in range(0, 8):
            assert tc.GetToken("::1", MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10) is True
        tc.ResetClientList()
        assert abs(tc.tokenDict["::1"] * 4 - MAX_DOWNLOAD_LIMIT_PER_MINUTE / 10 * 8) < 1
        for i in range(0, 4):
            tc.ResetClientList()
        assert ("::1" not in tc.tokenDict) is True


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

        limiter.ResetClientList()
        assert limiter.IsClientInViolation("::1") is False


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


def test_builder_Function_None():
    rl = RateLimiterBuilder(None)
    assert isinstance(rl, SpeedAndConnectionLimiter) is True


def test_builder_Function_ZeroConfig():
    config = ZeroConfig()
    rl = RateLimiterBuilder(config)
    assert isinstance(rl, SpeedAndConnectionLimiter) is True
    assert rl.sl.hallOfShame is rl.cl.hallOfShame  # test for single hall of shame

    # if we are in a singlethread  we disable rate limiting
    config.threading = False
    rl = RateLimiterBuilder(config)
    assert isinstance(rl, NoRateLimiter) is True


def test_builder_Function_ZeroConfig_advanced():
    f = TemporaryFileHandler()
    f.singleWrite(
        """[RateLimiter]
HOS_strikes_to_ban = 5
SpeedLimiter_max_download_limit_per_minute = 12347
SpeedLimiter_reset_download_limit_per_minute = 12
SpeedLimiter_sleeptime = 160
SpeedLimiter_penealty = 1200
SpeedLimiter_degradation_factor = 5
SpeedLimiter_penaltyTime = 20
ConnectionLimiter_connections_per_second=1
ConnectionLimiter_sleeptime=2
ConnectionLimiter_penalty=2
ConnectionLimiter_penaltyTime=2

[Logging]
logpath=/tmp/test/
"""
    )
    testargs = ["prog", "-c" + f.name]
    config = None
    with patch("sys.argv", testargs):
        config = ArgsConfig()

    rl = RateLimiterBuilder(config)
    assert isinstance(rl, SpeedAndConnectionLimiter) is True
    assert rl.sl.hallOfShame is rl.cl.hallOfShame  # test for single hall of shame
    assert rl.sl.hallOfShame.STRIKES_TO_BAN == 5
    assert rl.sl.MAX_DOWNLOAD_LIMIT_PER_MINUTE == 12347
    assert rl.sl.RESET_DOWNLOAD_LIMIT_PER_MINUTE == 12
    assert rl.sl.SLEEPTIME == 160
    assert rl.sl.PENALTY == 1200
    assert rl.sl.DEGRADATION_FACTOR == 5
    assert rl.sl.penaltyTime == 20

    assert rl.cl.CONNECTIONS_PER_SECOND == 1
    assert rl.cl.SLEEPTIME == 2
    assert rl.cl.PENALTY == 2
    assert rl.cl.penaltyTime == 2
