import logging
import sys
from argparse import ArgumentParser
from configparser import ConfigParser


class ArgsConfig:
    def __init__(self, log=logging):
        args = self.CreateArgumentparser()

        if args.config is not None:
            log.debug(f"Loading Config from file {args.config}")
            config = ConfigParser()
            try:
                config.read(args.config)
            except Exception as e:
                log.error(e)
                log.critical(f"Failed to load config file: {args.config}")
                sys.exit(0)

            self.GetServerParameters(config, args, log)
            self.GetRateLimitParameters(config)
            self.GetLoggingParameters(config)

        else:
            self.SetDefaultLimitParameters()
            self.SetDefaultLogginggParameters()
            arguments = vars(args)
            for i in arguments:
                setattr(self, i, arguments[i])

            self.ip = args.ip
            self.port = args.port
            self.certfile = args.certfile
            self.keyfile = args.keyfile
            self.systemd = args.systemd
            self.ipv6 = args.ipv6
            self.version = args.version
            self.nb_connections = args.nb_connections
            self.threading = args.threading
        log.info(f"Config: {args} ")

    def CreateArgumentparser(self):

        parser = ArgumentParser("Gemeaux: a Python Gemini server")
        parser.add_argument(
            "--ip",
            default="localhost",
            help="IP/Host of your server — default: localhost.",
        )
        parser.add_argument(
            "--port", default=1965, type=int, help="Listening port — default: 1965."
        )
        parser.add_argument("--certfile", default="cert.pem")
        parser.add_argument("--keyfile", default="key.pem")
        parser.add_argument(
            "--nb-connections",
            default=5,
            type=int,
            help="Maximum number of connections — default: 5",
        )
        parser.add_argument(
            "--version",
            help="Return version and exits",
            action="store_true",
            default=False,
        )
        parser.add_argument("--systemd", dest="systemd", action="store_true")
        parser.add_argument("--no-systemd", dest="systemd", action="store_false")
        parser.add_argument("--disable-ipv6", dest="ipv6", action="store_false")
        parser.add_argument("--no-threading", dest="threading", action="store_false")
        parser.add_argument("-c", "--config", help="Provide config file for input")
        parser.set_defaults(systemd=False)
        parser.set_defaults(ipv6=True)
        parser.set_defaults(threading=True)
        args = parser.parse_args()
        return args

    def GetServerParameters(self, config, args, log):
        convert = dict(
            {"ipv6": bool, "nb-connections": int, "port": int, "systemd": bool}
        )
        if config.has_section("Server"):
            for key, content in config["Server"].items():
                replaced_key = key.replace("-", "_")
                if key in convert:
                    setattr(self, replaced_key, convert[key](content))
                else:
                    setattr(self, replaced_key, content)

        var = vars(args)
        for i in var:
            replaced_key = i.replace("_", "-")
            if not config.has_section("Server"):
                setattr(self, i, var[i])
            elif replaced_key not in list(config["Server"].keys()):
                setattr(self, i, var[i])
                log.warning(
                    f"Using {i} from commandline parameters. If not provided default values are used."
                )

    def SetDefaultLimitParameters(self):
        defaultRateLimit = self.GetDefaultRateLimit()
        for i in defaultRateLimit:
            setattr(self, i, defaultRateLimit[i])

    def GetRateLimitParameters(self, config):
        self.SetDefaultLimitParameters()
        if config.has_section("RateLimiter"):
            for key, content in config["RateLimiter"].items():
                setattr(self, key, int(content))

    def SetDefaultLogginggParameters(self):
        defaultLogging = self.GetLoggingFilter()
        for i in defaultLogging:
            setattr(self, i, defaultLogging[i])

    def GetLoggingParameters(self, config):
        self.SetDefaultLogginggParameters()
        if config.has_section("Logging"):
            for key, content in config["Logging"].items():
                setattr(self, key, content)

    def GetDefaultRateLimit(self):
        return dict(
            {
                "hos_strikes_to_ban": 3,
                "speedlimiter_max_download_limit_per_minute": 1024000,
                "speedlimiter_reset_download_limit_per_minute": 10240,
                "speedlimiter_sleeptime": 60,
                "speedlimiter_penealty": 1000,
                "speedlimiter_degradation_factor": 4,
                "speedlimiter_penaltytime": 60,
                "connectionlimiter_connections_per_second": 10,
                "connectionlimiter_sleeptime": 1,
                "connectionlimiter_penalty": 1,
                "connectionlimiter_penaltytime": 1,
            }
        )

    def GetLoggingFilter(self):
        return dict({"logpath": "/var/log/gemeaux/"})
