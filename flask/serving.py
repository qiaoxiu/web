"""A WSGI and HTTP server for use **during development only**. This
server is convenient to use, but is not designed to be particularly
stable, secure, or efficient. Use a dedicate WSGI server and HTTP
server when deploying to production.
It provides features like interactive debugging and code reloading. Use
``run_simple`` to start the server. Put this in a ``run.py`` script:
.. code-block:: python
    from myapp import create_app
    from werkzeug import run_simple
"""
import io
import os
import platform
import signal
import socket
import socketserver
import sys
from datetime import datetime as dt
from datetime import timedelta
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer

from ._internal import _log
from ._internal import _wsgi_encoding_dance
from .exceptions import InternalServerError
from .urls import uri_to_iri
from .urls import url_parse
from .urls import url_unquote

try:
    import ssl
except ImportError:

    class _SslDummy:
        def __getattr__(self, name):
            raise RuntimeError("SSL support unavailable")

    ssl = _SslDummy()  # type: ignore

try:
    import click
except ImportError:
    click = None

can_fork = hasattr(os, "fork")

if can_fork:
    ForkingMixIn = socketserver.ForkingMixIn
else:

    class ForkingMixIn:  # type: ignore
        pass


try:
    af_unix = socket.AF_UNIX
except AttributeError:
    af_unix = None

LISTEN_QUEUE = 128
can_open_by_fd = not platform.system() == "Windows" and hasattr(socket, "fromfd")


class DechunkedInput(io.RawIOBase):
    """An input stream that handles Transfer-Encoding 'chunked'"""

    def __init__(self, rfile):
        self._rfile = rfile
        self._done = False
        self._len = 0

    def readable(self):
        return True

    def read_chunk_len(self):
        try:
            line = self._rfile.readline().decode("latin1")
            _len = int(line.strip(), 16)
        except ValueError:
            raise OSError("Invalid chunk header")
        if _len < 0:
            raise OSError("Negative chunk length not allowed")
        return _len

    def readinto(self, buf):
        read = 0
        while not self._done and read < len(buf):
            if self._len == 0:
                # This is the first chunk or we fully consumed the previous
                # one. Read the next length of the next chunk
                self._len = self.read_chunk_len()

            if self._len == 0:
                # Found the final chunk of size 0. The stream is now exhausted,
                # but there is still a final newline that should be consumed
                self._done = True

            if self._len > 0:
                # There is data (left) in this chunk, so append it to the
                # buffer. If this operation fully consumes the chunk, this will
                # reset self._len to 0.
                n = min(len(buf), self._len)
                buf[read : read + n] = self._rfile.read(n)
                self._len -= n
                read += n

            if self._len == 0:
                # Skip the terminating newline of a chunk that has been fully
                # consumed. This also applies to the 0-sized final chunk
                terminator = self._rfile.readline()
                if terminator not in (b"\n", b"\r\n", b"\r"):
                    raise OSError("Missing chunk terminating newline")

        return read


class WSGIRequestHandler(BaseHTTPRequestHandler):
    # 最終調用的這個hanlder 來處理 請求參數設定等工作 然後 調用 app__call__ 來實現 uwsgi 和app 的連接
    """A request handler that implements WSGI dispatching."""

    @property
    def server_version(self):
        from . import __version__

        return f"Werkzeug/{__version__}"

    def make_environ(self):
        request_url = url_parse(self.path)

        def shutdown_server():
            self.server.shutdown_signal = True

        url_scheme = "http" if self.server.ssl_context is None else "https"
        if not self.client_address:
            self.client_address = "<local>"
        if isinstance(self.client_address, str):
            self.client_address = (self.client_address, 0)
        else:
            pass

        # If there was no scheme but the path started with two slashes,
        # the first segment may have been incorrectly parsed as the
        # netloc, prepend it to the path again.
        if not request_url.scheme and request_url.netloc:
            path_info = f"/{request_url.netloc}{request_url.path}"
        else:
            path_info = request_url.path

        path_info = url_unquote(path_info)

        environ = {
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": url_scheme,
            "wsgi.input": self.rfile,
            "wsgi.errors": sys.stderr,
            "wsgi.multithread": self.server.multithread,
            "wsgi.multiprocess": self.server.multiprocess,
            "wsgi.run_once": False,
            "werkzeug.server.shutdown": shutdown_server,
            "SERVER_SOFTWARE": self.server_version,
            "REQUEST_METHOD": self.command,
            "SCRIPT_NAME": "",
            "PATH_INFO": _wsgi_encoding_dance(path_info),
            "QUERY_STRING": _wsgi_encoding_dance(request_url.query),
            # Non-standard, added by mod_wsgi, uWSGI
            "REQUEST_URI": _wsgi_encoding_dance(self.path),
            # Non-standard, added by gunicorn
            "RAW_URI": _wsgi_encoding_dance(self.path),
            "REMOTE_ADDR": self.address_string(),
            "REMOTE_PORT": self.port_integer(),
            "SERVER_NAME": self.server.server_address[0],
            "SERVER_PORT": str(self.server.server_address[1]),
            "SERVER_PROTOCOL": self.request_version,
        }
        # 通過slectors 讀取構造成header 處理 header
        for key, value in self.headers.items():
            key = key.upper().replace("-", "_")
            value = value.replace("\r\n", "")
            if key not in ("CONTENT_TYPE", "CONTENT_LENGTH"):
                key = f"HTTP_{key}"
                if key in environ:
                    value = f"{environ[key]},{value}"
            environ[key] = value

        if environ.get("HTTP_TRANSFER_ENCODING", "").strip().lower() == "chunked":
            environ["wsgi.input_terminated"] = True
            environ["wsgi.input"] = DechunkedInput(environ["wsgi.input"])

        # Per RFC 2616, if the URL is absolute, use that as the host.
        # We're using "has a scheme" to indicate an absolute URL.
        if request_url.scheme and request_url.netloc:
            environ["HTTP_HOST"] = request_url.netloc

        try:
            # binary_form=False gives nicer information, but wouldn't be compatible with
            # what Nginx or Apache could return.
            peer_cert = self.connection.getpeercert(binary_form=True)
            if peer_cert is not None:
                # Nginx and Apache use PEM format.
                environ["SSL_CLIENT_CERT"] = ssl.DER_cert_to_PEM_cert(peer_cert)
        except ValueError:
            # SSL handshake hasn't finished.
            self.server.log("error", "Cannot fetch SSL peer certificate info")
        except AttributeError:
            # Not using TLS, the socket will not have getpeercert().
            pass

        return environ

    def run_wsgi(self):
        # 最終 通過調用DO_GET DO_POST 函數後 最總要調用  run_wsgi
        if self.headers.get("Expect", "").lower().strip() == "100-continue":
            self.wfile.write(b"HTTP/1.1 100 Continue\r\n\r\n")
        # 根據slectors 讀取的網絡數據 構造 上下文環境
        self.environ = environ = self.make_environ()
        headers_set = []
        headers_sent = []

        def write(data):
            # 將flask app 返回的resonse 對象 進行 處理 header body 然後寫入緩存 給網絡
            assert headers_set, "write() before start_response"
            if not headers_sent:
                status, response_headers = headers_sent[:] = headers_set
                try:
                    code, msg = status.split(None, 1)
                except ValueError:
                    code, msg = status, ""
                code = int(code)
                self.send_response(code, msg)
                header_keys = set()
                for key, value in response_headers:
                    self.send_header(key, value)
                    key = key.lower()
                    header_keys.add(key)
                if not (
                    "content-length" in header_keys
                    or environ["REQUEST_METHOD"] == "HEAD"
                    or code < 200
                    or code in (204, 304)
                ):
                    self.close_connection = True
                    self.send_header("Connection", "close")
                if "server" not in header_keys:
                    self.send_header("Server", self.version_string())
                if "date" not in header_keys:
                    self.send_header("Date", self.date_time_string())
                self.end_headers()

            assert isinstance(data, bytes), "applications must write bytes"
            self.wfile.write(data)
            self.wfile.flush()
        # 回調函數 ， 調用完app 業務hanlder 調用該函數 返回給webserver
        def start_response(status, response_headers, exc_info=None):
            if exc_info:
                try:
                    if headers_sent:
                        raise exc_info[1].with_traceback(exc_info[2])
                finally:
                    exc_info = None
            elif headers_set:
                raise AssertionError("Headers already set")
            headers_set[:] = [status, response_headers]
            return write

        def execute(app):
            # 該處最終的連接 flask app__call__ 業務邏輯hanlder  完成flask app 連接
            application_iter = app(environ, start_response)
            try:
                for data in application_iter:
                    # 根據 resonse 對象 回寫數據
                    write(data)
                if not headers_sent:
                    write(b"")
            finally:
                if hasattr(application_iter, "close"):
                    application_iter.close()

        try:
            execute(self.server.app)
        except (ConnectionError, socket.timeout) as e:
            self.connection_dropped(e, environ)
        except Exception:
            if self.server.passthrough_errors:
                raise
            from .debug.tbtools import get_current_traceback

            traceback = get_current_traceback(ignore_system_exceptions=True)
            try:
                # if we haven't yet sent the headers but they are set
                # we roll back to be able to set them again.
                if not headers_sent:
                    del headers_set[:]
                execute(InternalServerError())
            except Exception:
                pass
            self.server.log("error", "Error on request:\n%s", traceback.plaintext)

    def handle(self):
        """Handles a request ignoring dropped connections."""
        try:
            BaseHTTPRequestHandler.handle(self)
        except (ConnectionError, socket.timeout) as e:
            self.connection_dropped(e)
        except Exception as e:
            if self.server.ssl_context is None or not is_ssl_error(e):
                raise
        if self.server.shutdown_signal:
            self.initiate_shutdown()

    def initiate_shutdown(self):
        if is_running_from_reloader():
            # Windows does not provide SIGKILL, go with SIGTERM then.
            sig = getattr(signal, "SIGKILL", signal.SIGTERM)
            os.kill(os.getpid(), sig)

        self.server._BaseServer__shutdown_request = True

    def connection_dropped(self, error, environ=None):
        """Called if the connection was closed by the client.  By default
        nothing happens.
        """

    def handle_one_request(self):
        """Handle a single HTTP request."""
        self.raw_requestline = self.rfile.readline()
        if not self.raw_requestline:
            self.close_connection = 1
        elif self.parse_request():
            return self.run_wsgi()

    def send_response(self, code, message=None):
        """Send the response header and log the response code."""
        self.log_request(code)
        if message is None:
            message = self.responses[code][0] if code in self.responses else ""
        if self.request_version != "HTTP/0.9":
            hdr = f"{self.protocol_version} {code} {message}\r\n"
            self.wfile.write(hdr.encode("ascii"))

    def version_string(self):
        return BaseHTTPRequestHandler.version_string(self).strip()

    def address_string(self):
        if getattr(self, "environ", None):
            return self.environ["REMOTE_ADDR"]
        elif not self.client_address:
            return "<local>"
        elif isinstance(self.client_address, str):
            return self.client_address
        else:
            return self.client_address[0]

    def port_integer(self):
        return self.client_address[1]

    def log_request(self, code="-", size="-"):
        try:
            path = uri_to_iri(self.path)
            msg = f"{self.command} {path} {self.request_version}"
        except AttributeError:
            # path isn't set if the requestline was bad
            msg = self.requestline

        code = str(code)

        if click:
            color = click.style

            if code[0] == "1":  # 1xx - Informational
                msg = color(msg, bold=True)
            elif code[0] == "2":  # 2xx - Success
                msg = color(msg, fg="white")
            elif code == "304":  # 304 - Resource Not Modified
                msg = color(msg, fg="cyan")
            elif code[0] == "3":  # 3xx - Redirection
                msg = color(msg, fg="green")
            elif code == "404":  # 404 - Resource Not Found
                msg = color(msg, fg="yellow")
            elif code[0] == "4":  # 4xx - Client Error
                msg = color(msg, fg="red", bold=True)
            else:  # 5xx, or any other response
                msg = color(msg, fg="magenta", bold=True)

        self.log("info", '"%s" %s %s', msg, code, size)

    def log_error(self, *args):
        self.log("error", *args)

    def log_message(self, format, *args):
        self.log("info", format, *args)

    def log(self, type, message, *args):
        _log(
            type,
            f"{self.address_string()} - - [{self.log_date_time_string()}] {message}\n",
            *args,
        )


#: backwards compatible name if someone is subclassing it
BaseRequestHandler = WSGIRequestHandler


def generate_adhoc_ssl_pair(cn=None):
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        raise TypeError("Using ad-hoc certificates requires the cryptography library.")
    pkey = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )

    # pretty damn sure that this is not actually accepted by anyone
    if cn is None:
        cn = "*"

    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Dummy Certificate"),
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(pkey.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(dt.utcnow())
        .not_valid_after(dt.utcnow() + timedelta(days=365))
        .add_extension(x509.ExtendedKeyUsage([x509.OID_SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("*")]), critical=False)
        .sign(pkey, hashes.SHA256(), default_backend())
    )
    return cert, pkey


def make_ssl_devcert(base_path, host=None, cn=None):
    """Creates an SSL key for development.  This should be used instead of
    the ``'adhoc'`` key which generates a new cert on each server start.
    It accepts a path for where it should store the key and cert and
    either a host or CN.  If a host is given it will use the CN
    ``*.host/CN=host``.
    For more information see :func:`run_simple`.
    .. versionadded:: 0.9
    :param base_path: the path to the certificate and key.  The extension
                      ``.crt`` is added for the certificate, ``.key`` is
                      added for the key.
    :param host: the name of the host.  This can be used as an alternative
                 for the `cn`.
    :param cn: the `CN` to use.
    """

    if host is not None:
        cn = f"*.{host}/CN={host}"
    cert, pkey = generate_adhoc_ssl_pair(cn=cn)

    from cryptography.hazmat.primitives import serialization

    cert_file = f"{base_path}.crt"
    pkey_file = f"{base_path}.key"

    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(pkey_file, "wb") as f:
        f.write(
            pkey.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    return cert_file, pkey_file


def generate_adhoc_ssl_context():
    """Generates an adhoc SSL context for the development server."""
    import tempfile
    import atexit

    cert, pkey = generate_adhoc_ssl_pair()

    from cryptography.hazmat.primitives import serialization

    cert_handle, cert_file = tempfile.mkstemp()
    pkey_handle, pkey_file = tempfile.mkstemp()
    atexit.register(os.remove, pkey_file)
    atexit.register(os.remove, cert_file)

    os.write(cert_handle, cert.public_bytes(serialization.Encoding.PEM))
    os.write(
        pkey_handle,
        pkey.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    )

    os.close(cert_handle)
    os.close(pkey_handle)
    ctx = load_ssl_context(cert_file, pkey_file)
    return ctx


def load_ssl_context(cert_file, pkey_file=None, protocol=None):
    """Loads SSL context from cert/private key files and optional protocol.
    Many parameters are directly taken from the API of
    :py:class:`ssl.SSLContext`.
    :param cert_file: Path of the certificate to use.
    :param pkey_file: Path of the private key to use. If not given, the key
                      will be obtained from the certificate file.
    :param protocol: A ``PROTOCOL`` constant from the :mod:`ssl` module.
        Defaults to :data:`ssl.PROTOCOL_TLS_SERVER`.
    """
    if protocol is None:
        protocol = ssl.PROTOCOL_TLS_SERVER

    ctx = ssl.SSLContext(protocol)
    ctx.load_cert_chain(cert_file, pkey_file)
    return ctx


def is_ssl_error(error=None):
    """Checks if the given error (or the current one) is an SSL error."""
    if error is None:
        error = sys.exc_info()[1]
    return isinstance(error, ssl.SSLError)


def select_address_family(host, port):
    """Return ``AF_INET4``, ``AF_INET6``, or ``AF_UNIX`` depending on
    the host and port."""
    if host.startswith("unix://"):
        return socket.AF_UNIX
    elif ":" in host and hasattr(socket, "AF_INET6"):
        return socket.AF_INET6
    return socket.AF_INET


def get_sockaddr(host, port, family):
    """Return a fully qualified socket address that can be passed to
    :func:`socket.bind`."""
    if family == af_unix:
        return host.split("://", 1)[1]
    try:
        res = socket.getaddrinfo(
            host, port, family, socket.SOCK_STREAM, socket.IPPROTO_TCP
        )
    except socket.gaierror:
        return host, port
    return res[0][4]


class BaseWSGIServer(HTTPServer):

    """Simple single-threaded, single-process WSGI server."""

    multithread = False
    multiprocess = False
    request_queue_size = LISTEN_QUEUE

    def __init__(
        self,
        host,
        port,
        app,
        handler=None,
        passthrough_errors=False,
        ssl_context=None,
        fd=None,
    ):
        if handler is None:
            handler = WSGIRequestHandler

        self.address_family = select_address_family(host, port)

        if fd is not None:
            real_sock = socket.fromfd(fd, self.address_family, socket.SOCK_STREAM)
            port = 0

        server_address = get_sockaddr(host, int(port), self.address_family)

        # remove socket file if it already exists
        if self.address_family == af_unix and os.path.exists(server_address):
            os.unlink(server_address)
        HTTPServer.__init__(self, server_address, handler)

        self.app = app
        self.passthrough_errors = passthrough_errors
        self.shutdown_signal = False
        self.host = host
        self.port = self.socket.getsockname()[1]

        # Patch in the original socket.
        if fd is not None:
            self.socket.close()
            self.socket = real_sock
            self.server_address = self.socket.getsockname()

        if ssl_context is not None:
            if isinstance(ssl_context, tuple):
                ssl_context = load_ssl_context(*ssl_context)
            if ssl_context == "adhoc":
                ssl_context = generate_adhoc_ssl_context()

            self.socket = ssl_context.wrap_socket(self.socket, server_side=True)
            self.ssl_context = ssl_context
        else:
            self.ssl_context = None

    def log(self, type, message, *args):
        _log(type, message, *args)

    def serve_forever(self):
        self.shutdown_signal = False
        try:
            HTTPServer.serve_forever(self)
        except KeyboardInterrupt:
            pass
        finally:
            self.server_close()

    def handle_error(self, request, client_address):
        if self.passthrough_errors:
            raise

        return HTTPServer.handle_error(self, request, client_address)

    def get_request(self):
        con, info = self.socket.accept()
        return con, info


class ThreadedWSGIServer(socketserver.ThreadingMixIn, BaseWSGIServer):

    """A WSGI server that does threading."""

    multithread = True
    daemon_threads = True


class ForkingWSGIServer(ForkingMixIn, BaseWSGIServer):

    """A WSGI server that does forking."""

    multiprocess = True

    def __init__(
        self,
        host,
        port,
        app,
        processes=40,
        handler=None,
        passthrough_errors=False,
        ssl_context=None,
        fd=None,
    ):
        if not can_fork:
            raise ValueError("Your platform does not support forking.")
        BaseWSGIServer.__init__(
            self, host, port, app, handler, passthrough_errors, ssl_context, fd
        )
        self.max_children = processes


def make_server(
    host=None,
    port=None,
    app=None,
    threaded=False,
    processes=1,
    request_handler=None,
    passthrough_errors=False,
    ssl_context=None,
    fd=None,
):
    """Create a new server instance that is either threaded, or forks
    or just processes one request after another.
    """
    if threaded and processes > 1:
        raise ValueError("cannot have a multithreaded and multi process server.")
    elif threaded:
        return ThreadedWSGIServer(
            host, port, app, request_handler, passthrough_errors, ssl_context, fd=fd
        )
    elif processes > 1:
        return ForkingWSGIServer(
            host,
            port,
            app,
            processes,
            request_handler,
            passthrough_errors,
            ssl_context,
            fd=fd,
        )
    else:
        return BaseWSGIServer(
            host, port, app, request_handler, passthrough_errors, ssl_context, fd=fd
        )


def is_running_from_reloader():
    """Checks if the application is running from within the Werkzeug
    reloader subprocess.
    .. versionadded:: 0.10
    """
    return os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def run_simple(
    hostname,
    port,
    application,
    use_reloader=False,
    use_debugger=False,
    use_evalex=True,
    extra_files=None,
    reloader_interval=1,
    reloader_type="auto",
    threaded=False,
    processes=1,
    request_handler=None,
    static_files=None,
    passthrough_errors=False,
    ssl_context=None,
):
    """Start a WSGI application. Optional features include a reloader,
    multithreading and fork support.
    This function has a command-line interface too::
        python -m werkzeug.serving --help
    .. versionadded:: 0.5
       `static_files` was added to simplify serving of static files as well
       as `passthrough_errors`.
    .. versionadded:: 0.6
       support for SSL was added.
    .. versionadded:: 0.8
       Added support for automatically loading a SSL context from certificate
       file and private key.
    .. versionadded:: 0.9
       Added command-line interface.
    .. versionadded:: 0.10
       Improved the reloader and added support for changing the backend
       through the `reloader_type` parameter.  See :ref:`reloader`
       for more information.
    .. versionchanged:: 0.15
        Bind to a Unix socket by passing a path that starts with
        ``unix://`` as the ``hostname``.
    :param hostname: The host to bind to, for example ``'localhost'``.
        If the value is a path that starts with ``unix://`` it will bind
        to a Unix socket instead of a TCP socket..
    :param port: The port for the server.  eg: ``8080``
    :param application: the WSGI application to execute
    :param use_reloader: should the server automatically restart the python
                         process if modules were changed?
    :param use_debugger: should the werkzeug debugging system be used?
    :param use_evalex: should the exception evaluation feature be enabled?
    :param extra_files: a list of files the reloader should watch
                        additionally to the modules.  For example configuration
                        files.
    :param reloader_interval: the interval for the reloader in seconds.
    :param reloader_type: the type of reloader to use.  The default is
                          auto detection.  Valid values are ``'stat'`` and
                          ``'watchdog'``. See :ref:`reloader` for more
                          information.
    :param threaded: should the process handle each request in a separate
                     thread?
    :param processes: if greater than 1 then handle each request in a new process
                      up to this maximum number of concurrent processes.
    :param request_handler: optional parameter that can be used to replace
                            the default one.  You can use this to replace it
                            with a different
                            :class:`~BaseHTTPServer.BaseHTTPRequestHandler`
                            subclass.
    :param static_files: a list or dict of paths for static files.  This works
                         exactly like :class:`SharedDataMiddleware`, it's actually
                         just wrapping the application in that middleware before
                         serving.
    :param passthrough_errors: set this to `True` to disable the error catching.
                               This means that the server will die on errors but
                               it can be useful to hook debuggers in (pdb etc.)
    :param ssl_context: an SSL context for the connection. Either an
                        :class:`ssl.SSLContext`, a tuple in the form
                        ``(cert_file, pkey_file)``, the string ``'adhoc'`` if
                        the server should automatically create one, or ``None``
                        to disable SSL (which is the default).
    """
    if not isinstance(port, int):
        raise TypeError("port must be an integer")
    if use_debugger:
        from .debug import DebuggedApplication

        application = DebuggedApplication(application, use_evalex)
    if static_files:
        from .middleware.shared_data import SharedDataMiddleware

        application = SharedDataMiddleware(application, static_files)

    def log_startup(sock):
        display_hostname = hostname if hostname not in ("", "*") else "localhost"
        quit_msg = "(Press CTRL+C to quit)"
        if sock.family == af_unix:
            _log("info", " * Running on %s %s", display_hostname, quit_msg)
        else:
            if ":" in display_hostname:
                display_hostname = f"[{display_hostname}]"
            port = sock.getsockname()[1]
            _log(
                "info",
                " * Running on %s://%s:%d/ %s",
                "http" if ssl_context is None else "https",
                display_hostname,
                port,
                quit_msg,
            )

    def inner():
        # uwsgi 處理 客戶端的請求連接 構造 request 和 start_reponse
        try:
            fd = int(os.environ["WERKZEUG_SERVER_FD"])
        except (LookupError, ValueError):
            fd = None

        srv = make_server(
            hostname,
            port,
            application,
            threaded,
            processes,
            request_handler,
            passthrough_errors,
            ssl_context,
            fd=fd,
        )
        # 創建線程 httpServer 來提供客戶端服務
        if fd is None:
            log_startup(srv.socket)
        # 啟動服務監聽
        srv.serve_forever()

    if use_reloader:
        # If we're not running already in the subprocess that is the
        # reloader we want to open up a socket early to make sure the
        # port is actually available.
        if not is_running_from_reloader():
            if port == 0 and not can_open_by_fd:
                raise ValueError(
                    "Cannot bind to a random port with enabled "
                    "reloader if the Python interpreter does "
                    "not support socket opening by fd."
                )

            # Create and destroy a socket so that any exceptions are
            # raised before we spawn a separate Python interpreter and
            # lose this ability.
            address_family = select_address_family(hostname, port)
            server_address = get_sockaddr(hostname, port, address_family)
            s = socket.socket(address_family, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(server_address)
            s.set_inheritable(True)

            # If we can open the socket by file descriptor, then we can just
            # reuse this one and our socket will survive the restarts.
            if can_open_by_fd:
                os.environ["WERKZEUG_SERVER_FD"] = str(s.fileno())
                s.listen(LISTEN_QUEUE)
                log_startup(s)
            else:
                s.close()
                if address_family == af_unix:
                    _log("info", "Unlinking %s", server_address)
                    os.unlink(server_address)

        from ._reloader import run_with_reloader

        run_with_reloader(inner, extra_files, reloader_interval, reloader_type)
    else:
        inner()


def run_with_reloader(*args, **kwargs):
    """Run a process with the reloader. This is not a public API, do
    not use this function.
    .. deprecated:: 2.0
        This function will be removed in version 2.1.
    """
    import warnings
    from ._reloader import run_with_reloader

    warnings.warn(
        (
            "'run_with_reloader' is a private API, it will no longer be"
            " accessible in version 2.1. Use 'run_simple' instead."
        ),
        DeprecationWarning,
        stacklevel=2,
    )
    return run_with_reloader(*args, **kwargs)


def main():
    """A simple command-line interface for :py:func:`run_simple`."""
    import argparse
    from .utils import import_string

    _log("warning", "This CLI is deprecated and will be removed in version 2.1.")

    parser = argparse.ArgumentParser(
        description="Run the given WSGI application with the development server.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "-b",
        "--bind",
        dest="address",
        help="The hostname:port the app should listen on.",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Show the interactive debugger for unhandled exceptions.",
    )
    parser.add_argument(
        "-r",
        "--reload",
        action="store_true",
        help="Reload the process if modules change.",
    )
    parser.add_argument(
        "application", help="Application to import and serve, in the form module:app."
    )
    args = parser.parse_args()
    hostname, port = None, None

    if args.address:
        hostname, _, port = args.address.partition(":")

    run_simple(
        hostname=hostname or "127.0.0.1",
        port=int(port or 5000),
        application=import_string(args.application),
        use_reloader=args.reload,
        use_debugger=args.debug,
    )


if __name__ == "__main__":
    main()
