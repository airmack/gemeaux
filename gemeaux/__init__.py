import _thread
import signal
import ssl
import sys
import time
import traceback
from collections.abc import Mapping
from socket import (
    AF_INET,
    AF_INET6,
    SHUT_RDWR,
    SO_REUSEADDR,
    SOL_SOCKET,
    setdefaulttimeout,
    timeout,
)
from ssl import PROTOCOL_TLS_SERVER, SSLContext
from urllib.parse import urlparse

from .confparser import ArgsConfig
from .exceptions import (
    BadRequestException,
    ImproperlyConfigured,
    ProxyRequestRefusedException,
    SlowDownException,
    TemplateError,
    TimeoutException,
)
from .handlers import Handler, StaticHandler, TemplateHandler
from .log import LoggingBuilder
from .ratelimiter import (
    ConnectionLimiter,
    HallOfShame,
    NoRateLimiter,
    RateLimiter,
    RateLimiterBuilder,
    SpeedAndConnectionLimiter,
    SpeedLimiter,
)
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
    SlowDownResponse,
    SuccessResponse,
    TemplateResponse,
    TextResponse,
    crlf,
)

__version__ = "0.0.3.dev14"


class ZeroConfig(ArgsConfig):
    def __init__(self):
        self.SetDefaultServerParamters()
        self.SetDefaultLimitParameters()
        self.SetDefaultLogginggParameters()

    def SetDefaultServerParamters(self):
        self.ip = "localhost"
        self.port = 1965
        self.certfile = "cert.pem"
        self.keyfile = "key.pem"
        self.nb_connections = 5
        self.threading = True
        self.systemd = False
        self.ipv6 = True
        self.version = False


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
    """
    Basic check for IPv6Braces
    at maximum there should be one [ and one ] in the the order of first [ then ]
    """
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
        self.log = LoggingBuilder("main", "/var/log/gemeaux/", "gemeaux.log")
        self.errorlog = LoggingBuilder("error", "/var/log/gemeaux/", "error.log")
        self.accesslog = LoggingBuilder("access", "/var/log/gemeaux/", "access.log")
        # Check the urls
        if not isinstance(urls, Mapping):
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
        self.config = config or ArgsConfig(self.log)
        if self.config.version:
            self.log.debug(f"Version: {__version__}")
            sys.exit(__version__)

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
            self.accesslog.warning(message)
        else:
            self.accesslog.info(message)

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

    def exception_handling(self, exception, connection, clientAddress=None):
        """
        Handle exceptions and errors when the client is requesting a resource.
        """
        response = None

        if isinstance(
            exception, ssl.CertificateError
        ):  # this needs to be put here otherwise it will be interpreted as OSError
            response = ProxyRequestRefusedResponse()
        elif isinstance(exception, BrokenPipeError):
            self.errorlog.warning(
                "Client disconnected in exception handling after sendall response"
            )
            connection = None
        elif isinstance(exception, UnicodeDecodeError):
            if clientAddress:
                self.rl.AddNewConnection(clientAddress)  # PENALTY for Unicode FUP
            response = BadRequestResponse("Unicode Decode Error")
        elif isinstance(exception, BadRequestException):
            response = BadRequestResponse()
        elif isinstance(exception, ValueError):
            response = BadRequestResponse()
        elif isinstance(exception, ProxyRequestRefusedException):
            response = ProxyRequestRefusedResponse()
        elif isinstance(exception, SlowDownException):
            response = SlowDownResponse(exception.timeout)
        elif isinstance(exception, TimeoutException):
            self.errorlog.warning(f"Connection {connection} timed out")
        elif isinstance(exception, ConnectionResetError):
            # No response sent
            self.errorlog.warning(f"Connection {connection} reset by peer...")
        elif isinstance(
            exception,
            (
                ssl.SSLError,
                IOError,
                ssl.SSLEOFError,
            ),
        ):
            response = PermanentFailureResponse("Connection Error")
            if clientAddress:
                self.rl.AddNewConnection(clientAddress)  # PENALTY for disconnect
                connection = None

        elif isinstance(exception, OSError):
            response = PermanentFailureResponse("OS Error")
            self.unwindConnection(connection)
            connection = None
        else:
            self.errorlog.error(f"{format_exception(exception)}")

        try:
            if response and connection:
                connection.sendall(bytes(response))
        except ssl.SSLError:
            self.errorlog.warning(f"SSL Error while sending response {connection}")
        except IOError:
            self.errorlog.warning(f"Client {connection} disconnected")
            connection = None
        except Exception as exc:
            self.errorlog.error(
                f"Exception while processing exception… {format_exception(exc)}"
            )

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
            self.errorlog.warning(f"URL: {url} causing {type(exc)} / {reason}")

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
        """ Business logic for handling single connection and their response """
        do_log = False
        url = ""
        try:
            url = self.ReceiveMessage(connection)
            # Check URL conformity.
            check_url(url, self.port, self.cert)
            response = self.get_response(url)
            message = bytes(response)
            tokens = len(message)
            if not self.rl.GetToken(address, tokens):  # pay in bytes
                raise SlowDownException(self.rl.GetPenaltyTime(address))
            connection.sendall(message)
            do_log = True

        except Exception as exc:
            connection = self.exception_handling(exc, connection, address)
        finally:
            self.unwindConnection(connection)

            if do_log:
                self.log_access(address, url, response)
            if self.config.threading:
                _thread.exit()

    def unwindConnection(self, connection):
        if connection:
            s = None
            try:
                s = connection.unwrap()
            except ssl.SSLError:
                self.errorlog.warning(f"SSL Error while unwinding {connection}")
            except IOError:
                self.errorlog.warning(
                    f"Client disconnected before unwinding {connection}"
                )
            finally:
                if s:
                    try:
                        s.shutdown(SHUT_RDWR)
                    except ssl.SSLError:
                        pass
                    finally:
                        s.close()

    def mainloop(self, tls):
        connection = None

        if self.config.systemd is True:
            import systemd.daemon

            systemd.daemon.notify("READY=1")
        self.rl = RateLimiterBuilder(self.config)
        if self.config.threading:
            _thread.start_new_thread(self.rl.run, ())

        while True:
            try:
                s = tls.accept()
                connection = s[0]
                address = s[1][0]
                if not self.rl.AddNewConnection(address):  # basic token costs
                    raise SlowDownException(self.rl.GetPenaltyTime(address))

                self.log.debug("Starting session with " + str(s[1][0]))

                if self.config.threading:
                    _thread.start_new_thread(self.do_business, (connection, address))
                else:
                    self.do_business(connection, address)
            except KeyboardInterrupt:
                self.unwind()
            except timeout:  # socket.timeout is ignored
                continue
            except SlowDownException as exc:
                if connection:
                    connection = self.exception_handling(exc, connection, address)
                self.unwindConnection(connection)
            except Exception as exc:
                self.exception_handling(exc, None, None)

    def unwind(self, signal_number, stack_frame):
        if self.config.systemd is True:
            import systemd.daemon

            systemd.daemon.notify("STOPPING=1")

        self.log.info(f"Shutting down Gemeaux on {self.config.ip}:{self.config.port}")
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

            self.log.debug("Using IPv6.")
            af = AF_INET6
            dualstack_ipv6 = True
            # without default timeout we will get in trouble with the ssl socket, which will be created blocking and might cause the main thread to be caught in a blocking state while accepting new connection

        setdefaulttimeout(10)
        ip_port = (self.config.ip, self.config.port)
        with socket.create_server(
            ip_port, family=af, dualstack_ipv6=dualstack_ipv6
        ) as server:
            server.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
            server.listen(self.config.nb_connections)
            self.log.info(self.BANNER)
            with context.wrap_socket(server, server_side=True) as tls:
                self.log.info(
                    f"Application started…, listening to {self.config.ip}:{self.config.port}"
                )
                self.mainloop(tls)


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
    # Ratelimiter
    "ConnectionLimiter",
    "HallOfShame",
    "NoRateLimiter",
    "RateLimiter",
    "RateLimiterBuilder",
    "SpeedAndConnectionLimiter",
    "SpeedLimiter",
]
