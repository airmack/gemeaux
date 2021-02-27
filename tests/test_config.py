from unittest.mock import patch

from tempfilehandler import TemporaryFileHandler

from gemeaux import ArgsConfig, ZeroConfig


def test_zero_config():
    config = ZeroConfig()
    assert config.ip == "localhost"
    assert config.port == 1965
    assert config.certfile == "cert.pem"
    assert config.keyfile == "key.pem"
    assert config.nb_connections == 5


def test_args_config():
    testargs = ["prog"]
    with patch("sys.argv", testargs):
        config = ArgsConfig()
    assert config.ip == "localhost"
    assert config.port == 1965
    assert config.certfile == "cert.pem"
    assert config.keyfile == "key.pem"
    assert config.nb_connections == 5


def test_args_config_file():
    f = TemporaryFileHandler()
    f.singleWrite(
        """[Server]
ip=localhost
port=1975
certfile=cert123.pem
keyfile=key123.pem
nb-connections=10
systemd=True"""
    )
    testargs = ["prog", "-c" + f.name]
    with patch("sys.argv", testargs):
        config = ArgsConfig()
    assert config.ip == "localhost"
    assert config.port == 1975
    assert config.certfile == "cert123.pem"
    assert config.keyfile == "key123.pem"
    assert config.systemd is True
    assert config.ipv6 is True
    assert config.nb_connections == 10
    assert config.threading is True


def test_args_config_file_advanced():
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
    with patch("sys.argv", testargs):
        config = ArgsConfig()
    # check default parameter
    assert config.ip == "localhost"
    assert config.port == 1965
    assert config.certfile == "cert.pem"
    assert config.keyfile == "key.pem"
    assert config.systemd is False
    assert config.ipv6 is True
    assert config.nb_connections == 5
    assert config.threading is True
    # check for deviation from default
    assert config.hos_strikes_to_ban == 5
    assert config.speedlimiter_max_download_limit_per_minute == 12347
    assert config.speedlimiter_reset_download_limit_per_minute == 12
    assert config.speedlimiter_sleeptime == 160
    assert config.speedlimiter_penealty == 1200
    assert config.speedlimiter_degradation_factor == 5
    assert config.speedlimiter_penaltytime == 20
    assert config.connectionlimiter_connections_per_second == 1
    assert config.connectionlimiter_sleeptime == 2
    assert config.connectionlimiter_penalty == 2
    assert config.connectionlimiter_penaltytime == 2
    assert config.logpath == "/tmp/test/"
