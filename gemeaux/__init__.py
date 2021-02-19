import _thread
import threading
import collections
import logging
import signal
import ssl
import sys
import time
import traceback
from argparse import ArgumentParser
from os import makedirs
from os.path import exists
from socket import AF_INET, AF_INET6, SO_REUSEADDR, SOL_SOCKET
from ssl import PROTOCOL_TLS_SERVER, SSLContext
from urllib.parse import urlparse

from .ratelimiter import (RateLimiter)
from .exceptions import (
    BadRequestException,
    ImproperlyConfigured,
    ProxyRequestRefusedException,
    TemplateError,
    TimeoutException,
)
from .handlers import Handler, StaticHandler, TemplateHandler
from .responses import (
    BadRequestResponse,
    DirectoryListingResponse,
    DocumentResponse,
    InputResponse,
    NotFoundResponse,
    PermanentFailureResponse,
    PermanentRedirectResponse,
    ProxyRequestRefusedResponse,
    RedirectResponse,
    Response,
    SensitiveInputResponse,
    SuccessResponse,
    TemplateResponse,
    TextResponse,
    crlf,
)

__version__ = "0.0.3.dev5"


class ZeroConfig:
    ip = "localhost"
    port = 1965
    certfile = "cert.pem"
    keyfile = "key.pem"
    nb_connections = 5


class ArgsConfig:
    def __init__(self):

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
        parser.set_defaults(systemd=False)
        parser.set_defaults(ipv6=True)
        parser.set_defaults(threading=True)

        args = parser.parse_args()

        if args.version:
            sys.exit(__version__)

        self.ip = args.ip
        self.port = args.port
        self.certfile = args.certfile
        self.keyfile = args.keyfile
        self.systemd = args.systemd
        self.ipv6 = args.ipv6
        self.nb_connections = args.nb_connections
        self.threading = args.threading
        logging.debug(f"Version: {__version__}")
        logging.debug("Config: {args} ")


def get_path(url):
    """
    Parse a URL and return a path relative to the root
    """
    url = url.strip()
    parsed = urlparse(url, "gemini")
    path = parsed.path
    return path


def check_url(
    url,
    server_port,
    cert={
        "subjectAltName": (
            ("DNS", "localhost"),
            ("IP Adress", "127.0.0.1"),
            ("IP Adress", "::1"),
        )
    },
):
    """
    Check for the client URL conformity.

    Raise exception or return None
    except localhost and 127.0.0.1 as default
    """
    parsed = urlparse(url, "gemini")

    # Check for bad request
    # Note: the URL will be cleaned before being used
    if not url.endswith("\r\n"):
        # TimeoutException will cause no response
        raise TimeoutException((url, parsed))
    # Other than Gemini will trigger a PROXY ERROR
    if parsed.scheme != "gemini":
        raise ProxyRequestRefusedException
    # You need to provide the right scheme
    if not url.startswith("gemini://"):
        # BadRequestException will return BadRequestResponse
        raise BadRequestException
    # URL max length is 1024.
    if len(url.strip()) > 1024:
        # BadRequestException will return BadRequestResponse
        raise BadRequestException
    location = parsed.netloc.strip()  # remove whitespaces e.g. for \n\r
    location, port = split_host_port(location)
    if int(port) != server_port:
        raise ProxyRequestRefusedException
    ssl.match_hostname(cert, location)
    return True


def handleIpv6Braces(string):
    if string.count("[") > 1:
        raise ValueError("Invalid IPv6 URL")
    if string.count("]") > 1:
        raise ValueError("Invalid IPv6 URL")
    if string.count("[") != string.count("]"):
        raise ValueError("Invalid IPv6 URL")
    if string.find("[") > string.find("]"):
        raise ValueError("Invalid IPv6 URL")
    return string.replace("[", "").replace("]", "")


def split_host_port(string):
    if not string.rsplit(":", 1)[-1].isdigit():
        host = handleIpv6Braces(string)
        return (host, 1965)

    string = string.rsplit(":", 1)

    host = handleIpv6Braces(string[0])
    if int(string[1]) <= 0:
        raise ValueError("Negative Port specified")
    port = int(string[1])

    return (host, port)


class App:

    TIMESTAMP_FORMAT = "%d/%b/%Y:%H:%M:%S %z"

    BANNER = f"""
♊ Welcome to your Gémeaux server (v{__version__}) ♊
"""

    def __init__(self, urls, config=None):
        setupLoging()
        # Check the urls
        if not isinstance(urls, collections.Mapping):
            # Not of the dict type
            raise ImproperlyConfigured("Bad url configuration: not a dict or dict-like")

        if not urls:
            # Empty dictionary or Falsy value
            raise ImproperlyConfigured("Bad url configuration: empty dict")

        for k, v in urls.items():
            if not isinstance(v, (Handler, Response)):
                msg = f"URL configuration: wrong type for `{k}`. Should be of type Handler or Response."
                raise ImproperlyConfigured(msg)

        self.urls = urls
        self.config = config or ArgsConfig()

    def log_access(self, address, url, response=None):
        """
        Log for access to the server
        """
        status = mimetype = "??"
        response_size = 0
        if response:
            error = response.status > 20
            status = response.status
            response_size = len(response)
            mimetype = response.mimetype.split(";")[0]
        else:
            error = True
        message = '{} [{}] "{}" {} {} {}'.format(
            address,
            time.strftime(self.TIMESTAMP_FORMAT, time.localtime()),
            url.strip(),
            mimetype,
            status,
            response_size,
        )
        if error:
            logging.warning(message)
        else:
            logging.debug(message)

    def get_route(self, path):

        matching = []

        for k_url, k_value in self.urls.items():
            if not k_url:  # Skip the catchall
                continue
            if path.startswith(k_url):
                matching.append(k_url)

        # One match or more. We'll take the "biggest" match.
        if len(matching) >= 1:
            k_url = max(matching, key=len)
            return (k_url, self.urls[k_url])

        # Catch all
        if "" in self.urls:
            return "", self.urls[""]

        raise FileNotFoundError("Route Not Found")

    def exception_handling(self, exception, connection):
        """
        Handle exceptions and errors when the client is requesting a resource.
        """
        response = None
        if isinstance(
            exception, ssl.CertificateError
        ):  # this needs to be put here otherwise it will be interpreted as OSError
            response = ProxyRequestRefusedResponse()
        elif isinstance(exception, OSError):
            response = PermanentFailureResponse("OS Error")
        elif isinstance(exception, (ssl.SSLEOFError, ssl.SSLError)):
            response = PermanentFailureResponse("SSL Error")
        elif isinstance(exception, UnicodeDecodeError):
            response = BadRequestResponse("Unicode Decode Error")
        elif isinstance(exception, BadRequestException):
            response = BadRequestResponse()
        elif isinstance(exception, ValueError):
            response = BadRequestResponse()
        elif isinstance(exception, ProxyRequestRefusedException):
            response = ProxyRequestRefusedResponse()
        elif isinstance(exception, ConnectionResetError):
            # No response sent
            logging.warning("Connection reset by peer...")
        else:
            logging.error(f"Exception: {exception} / {type(exception)}")

        try:
            if response and connection:
                connection.sendall(bytes(response))
        except BrokenPipeError:
            logging.warning(
                "Client disconnected in exception handling after sendall response"
            )
            connection = None
        except Exception as exc:
            logging.error(f"Exception while processing exception… {exc}")

        return connection

    def get_response(self, url):
        path = get_path(url)
        reason = None
        try:
            k_url, k_value = self.get_route(path)
            if isinstance(k_value, Handler):
                return k_value.handle(k_url, path)
            elif isinstance(k_value, Response):
                return k_value
        except TemplateError as exc:
            if exc.args:
                reason = exc.args[0]
            return PermanentFailureResponse(reason)
        except Exception as exc:
            if exc.args:
                reason = exc.args[0]
            url = url.replace("\r", "").replace("\n", "")
            logging.warning(f"URL: {url} causing {type(exc)} / {reason}")

        return NotFoundResponse(reason)

    def ReceiveMessage(self, connection):
        # receive messages and be able to deal with framgented mes...sages
        url = ""
        while True:
            s = connection.recv(2048).decode()
            if len(s) == 0:
                break
            url += s
            if url.find("\r\n") != -1:
                break
            if len(url) >= 2048:
                break
        return url

    def do_business(self, connection, address):
        do_log = False
        url = ""
        try:
            url = self.ReceiveMessage(connection)
        except (BrokenPipeError, ConnectionResetError):
            url = ""
            self.rl.GetToken(address, self.rl.PENALTY) # PENALTY
            connection = None
        except UnicodeDecodeError as exc:
            self.rl.GetToken(address, self.rl.PENALTY) # PENALTY
            if connection:
                connection = self.exception_handling(exc, connection)
        try:
            # Check URL conformity.
            check_url(url, self.port, self.cert)
            response = self.get_response(url)
            tokens = len(bytes(response))
            if not self.rl.GetToken(address, tokens): # pay in bytes
                url = ""
                s = connection.unwrap()
                s.close()
                return
            try:
                connection.sendall(bytes(response))
            except BrokenPipeError:
                logging.warning(
                    "Client disconnected in exception handling after sendall response"
                )
                connection = None
            do_log = True

        except Exception as exc:
            if connection:
                connection = self.exception_handling(exc, connection)
        finally:
            if connection:
                s = None
                try:
                    s = connection.unwrap()
                except ssl.SSLWantReadError:
                    logging.warning("client got SSLWantReadError as expected")
                finally:
                    if s:
                        s.close()
            if do_log:
                self.log_access(address, url, response)
            _thread.exit()

    def threadcounter(self):
        while True:
            pass

    def mainloop(self, tls):
        connection = None

        if self.config.systemd is True:
            import systemd.daemon

            systemd.daemon.notify("READY=1")
        if self.config.threading:
            _thread.start_new_thread(self.threadcounter, ())
            self.rl = RateLimiter()
            _thread.start_new_thread(self.rl.run, ())

        while True:
            try:
                s = tls.accept()
                connection = s[0]
                address = s[1][0]
                if not self.rl.GetToken(address): # basic token costs 1
                    s = connection.unwrap()
                    s.close()
                    continue

                logging.debug("Starting session with" + str(s[1][0]))

                if self.config.threading:
                    _thread.start_new_thread(self.do_business, (connection, address))
                else:
                    self.do_business(connection, address)
            except KeyboardInterrupt:
                self.unwind()
            except ssl.SSLEOFError:
                logging.warning("Premature client exit")
            except ssl.SSLError as e:
                logging.warning(format_exception(e))
            except Exception as exc:
                logging.warning(format_exception(exc))

    def unwind(self, signal_number, stack_frame):
        if self.config.systemd is True:
            import systemd.daemon

            systemd.daemon.notify("STOPPING=1")

        logging.info(f"Shutting down Gemeaux on {self.config.ip}:{self.config.port}")
        sys.exit(0)

    def ReadCert(self):
        # using undocumented api
        self.cert = ssl._ssl._test_decode_cert(self.config.certfile)

    def run(self):
        """
        Main run function.

        Load the configuration from the command line args.
        Launch the server
        """
        # Loading config only at runtime, not initialization

        self.port = self.config.port
        context = SSLContext(PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.config.certfile, self.config.keyfile)
        self.ReadCert()

        signal.signal(signal.SIGINT, self.unwind)
        signal.signal(signal.SIGTERM, self.unwind)
        af = AF_INET

        import socket

        if self.config.ipv6 and socket.has_dualstack_ipv6():

            logging.debug("Using IPv6.")
            af = AF_INET6
            dualstack_ipv6 = True

        ip_port = (self.config.ip, self.config.port)
        with socket.create_server(
            ip_port, family=af, dualstack_ipv6=dualstack_ipv6
        ) as server:
            server.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
            server.listen(self.config.nb_connections)
            logging.info(self.BANNER)
            with context.wrap_socket(server, server_side=True) as tls:
                logging.info(
                    f"Application started…, listening to {self.config.ip}:{self.config.port}"
                )
                self.mainloop(tls)


def setupLoging():

    # Critical:= An unrecoverable error, this closes the application
    # Error   := this should not have happend and is a serious flaw
    # Warning := some hickup but we can still continue within the application
    # Info    := General information
    # Debug   := Verbosity for easier debuging
    loggingpath = "/var/log/gemini/"
    try:
        if not exists(loggingpath):
            makedirs(loggingpath)
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
            datefmt="%m-%d %H:%M",
            filename=loggingpath + "gemeaux.log",
            filemode="w",
        )
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        formatter = logging.Formatter("%(name)-12s: %(levelname)-8s %(message)s")
        console.setFormatter(formatter)
        logging.getLogger("").addHandler(console)

    except PermissionError:
        loggingpath = "./"
        logging.basicConfig(
            level=logging.NOTSET,
            format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
            datefmt="%m-%d %H:%M",
        )
        logging.error(
            "Only use streaming handler for logging. No file output is generated."
        )
        formatter = logging.Formatter("%(name)-12s: %(levelname)-8s %(message)s")

    logging.info("Logging started")


# https://stackoverflow.com/questions/6086976/how-to-get-a-complete-exception-stack-trace-in-python
# currently used for debuging stack traces
def format_exception(e):
    exception_list = traceback.format_stack()
    exception_list = exception_list[:-2]
    exception_list.extend(traceback.format_tb(sys.exc_info()[2]))
    exception_list.extend(
        traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
    )

    exception_str = "Traceback (most recent call last):\n"
    exception_str += "".join(exception_list)
    # Removing the last \n
    exception_str = exception_str[:-1]

    return exception_str


__all__ = [
    # Core
    "App",
    # Exceptions
    "ImproperlyConfigured",
    "TemplateError",
    # Handlers
    "Handler",
    "StaticHandler",
    "TemplateHandler",
    # Responses
    "crlf",  # Response tool
    "Response",
    "SuccessResponse",  # Basic brick for building "OK" content
    "InputResponse",
    "SensitiveInputResponse",
    "RedirectResponse",
    "PermanentRedirectResponse",
    "PermanentFailureResponse",
    "NotFoundResponse",
    "BadRequestResponse",
    # Advanced responses
    "DocumentResponse",
    "DirectoryListingResponse",
    "TextResponse",
    "TemplateResponse",
]
