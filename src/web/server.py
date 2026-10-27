"""A small local web server: HTTP in, services out.

Security (see docs/web-ui-plan.md, section 4): bound to 127.0.0.1 only; a
Host-header allowlist (blocks DNS rebinding); a random per-launch token that
every API call must send in a header (which also rules out cross-site calls,
since there are no CORS headers); a strict content policy; streamed, size-
limited uploads that are validated before they are kept.
"""
import hmac
import html
import json
import logging
import mimetypes
import re
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from src.services import files
from src.version import VERSION
from src.services.errors import ServiceError
from src.services.runs import RunManager
from src.services.workspace import Workspace
from src.web import api

logger = logging.getLogger("pptx_alt_text")

HERE = Path(__file__).parent
STATIC = HERE / "static"
PAGES = HERE / "pages"
TEMPLATES = HERE / "templates"
_META = re.compile(r"\A<!--\s*(.*?)\s*-->\n", re.S)
_SLUG = re.compile(r"[a-z0-9-]+")
MAX_JSON_BYTES = 64 * 1024
DEFAULT_PORT = 8765
TOKEN_HEADER = "X-Cappv1-Token"

_CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

_STATUS_FOR_CODE = {
    "bad_name": 400, "not_pptx": 400, "bad_service": 400, "no_model": 400, "no_key": 400, "bad_request": 400,
    "no_output": 404, "not_found": 404,
    "busy": 409, "nothing_to_do": 409, "no_files": 409, "not_configured": 409, "model_missing": 409,
    "length_required": 411, "too_big": 413,
    "network": 502, "ollama_down": 503,
}


def render_page(slug: str) -> bytes | None:
    """A page fragment wrapped in its layout (templates/), with the version and the
    current nav entry filled in. None when there is no such page."""
    path = PAGES / f"{slug}.html"
    if not _SLUG.fullmatch(slug) or not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    m = _META.match(text)
    meta = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1))) if m else {}
    page = (TEMPLATES / f"{meta.get('layout', 'app')}.html").read_text(encoding="utf-8")
    script = f'<script type="module" src="/{meta["script"]}"></script>' if meta.get("script") else ""
    page = page.replace("{{content}}", text[m.end():] if m else text)
    for key, value in (("title", html.escape(meta.get("title", "cappv1"))), ("description", html.escape(meta.get("description", ""))),
                       ("version", VERSION), ("script", script), ("width", meta.get("width", "narrow"))):
        page = page.replace("{{" + key + "}}", value)
    if meta.get("nav"):
        page = page.replace(f'data-nav="{meta["nav"]}"', f'data-nav="{meta["nav"]}" aria-current="page"')
    return page.encode("utf-8")


class Request:
    """What a route handler gets: the handler for body access, plus parsed bits."""

    def __init__(self, handler: "Handler", groups: tuple, query: dict[str, list[str]]) -> None:
        self.h, self.groups, self.query = handler, groups, query
        self.ws: Workspace = handler.app.ws
        self.runs: RunManager = handler.app.runs

    def arg(self, name: str, default: str = "") -> str:
        return self.query.get(name, [default])[0]

    def json(self) -> dict:
        length = self.h.headers.get("Content-Length")
        if length is None or not length.isdigit():
            raise ServiceError("length_required", "The request needs a Content-Length.")
        if int(length) > MAX_JSON_BYTES:
            self.h.close_connection = True
            raise ServiceError("too_big", "That request is too large.")
        raw = self.h.rfile.read(int(length)) if int(length) else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            raise ServiceError("bad_request", "The request body isn't valid JSON.") from None
        if not isinstance(body, dict):
            raise ServiceError("bad_request", "The request body must be a JSON object.")
        return body

    def upload_chunks(self):
        """The raw request body, streamed in pieces (never held whole in memory)."""
        length = self.h.headers.get("Content-Length")
        if length is None or not length.isdigit():
            raise ServiceError("length_required", "Uploads need a Content-Length.")
        remaining = int(length)
        if remaining > files.MAX_UPLOAD_BYTES:
            self.h.close_connection = True  # the body is left unread
            raise ServiceError("too_big", f"That file is larger than {files.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                               "Split the deck or compress its pictures in PowerPoint.")
        while remaining:
            block = self.h.rfile.read(min(1 << 20, remaining))
            if not block:
                raise ServiceError("bad_request", "The upload ended early.")
            remaining -= len(block)
            yield block


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "cappv1"
    sys_version = ""

    @property
    def app(self) -> "WebServer":
        return self.server.app  # type: ignore[attr-defined]

    # ---- plumbing ----------------------------------------------------------
    def log_message(self, fmt, *args) -> None:  # quiet: the terminal belongs to the session
        pass

    def _headers(self, status: int, content_type: str, length: int | None, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Content-Security-Policy", _CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def send_json(self, status: int, obj) -> None:
        body = json.dumps(obj).encode()
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def send_error_json(self, err: ServiceError) -> None:
        self.send_json(_STATUS_FOR_CODE.get(err.code, 400), {"error": err.as_dict()})

    def send_bytes(self, status: int, content_type: str, body: bytes, extra: dict[str, str] | None = None) -> None:
        self._headers(status, content_type, len(body), extra)
        if self.command != "HEAD":
            self.wfile.write(body)

    # ---- dispatch ----------------------------------------------------------
    def _host_ok(self) -> bool:
        return self.headers.get("Host", "") in self.app.allowed_hosts

    def _token_ok(self) -> bool:
        return hmac.compare_digest(self.headers.get(TOKEN_HEADER, ""), self.app.token)

    def _handle(self) -> None:
        try:
            if not self._host_ok():
                return self.send_bytes(403, "text/plain; charset=utf-8", b"Forbidden")
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                if not self._token_ok():
                    return self.send_json(401, {"error": {"code": "unauthorized", "message": "Missing or wrong token.",
                                                          "fix": "Open the address cappv1 printed, which includes the token."}})
                return self._api(parsed.path, parse_qs(parsed.query))
            if self.command in ("GET", "HEAD"):
                return self._static(parsed.path)
            self.send_bytes(405, "text/plain; charset=utf-8", b"Method not allowed", {"Allow": "GET, HEAD"})
        except ServiceError as err:
            self.send_error_json(err)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            logger.exception("web request failed: %s %s", self.command, self.path)
            self.close_connection = True
            self.send_json(500, {"error": {"code": "internal", "message": "Something went wrong.",
                                           "fix": "Try again. If it keeps happening, check the logs/ folder."}})

    do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = do_OPTIONS = do_PATCH = lambda self: self._handle()

    def _api(self, path: str, query: dict[str, list[str]]) -> None:
        for method, pattern, fn in api.ROUTES:
            m = re.fullmatch(pattern, path)
            if m and method == self.command:
                return fn(Request(self, tuple(unquote(g) for g in m.groups()), query))
        known = any(re.fullmatch(pattern, path) for _, pattern, _ in api.ROUTES)
        self.send_json(405 if known else 404, {"error": {"code": "not_found", "message": "There is no such request.", "fix": ""}})

    def _static(self, path: str) -> None:
        slug = "index" if path in ("", "/") else unquote(path).strip("/")
        page = render_page(slug)
        if page is not None:
            return self.send_bytes(200, "text/html; charset=utf-8", page)
        target = (STATIC / unquote(path).lstrip("/")).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file():
            return self.send_bytes(404, "text/html; charset=utf-8", render_page("404") or b"Not found")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send_bytes(200, ctype, target.read_bytes())


class _Httpd(ThreadingHTTPServer):
    def handle_error(self, request, client_address) -> None:
        pass  # a browser closing a tab mid-request is normal, not an error to print over the session


class WebServer:
    """The server plus what its handlers share. Start it, read .url, stop it."""

    def __init__(self, ws: Workspace, runs: RunManager | None = None, port: int = DEFAULT_PORT, token: str | None = None) -> None:
        self.ws = ws
        self.runs = runs or RunManager(ws)
        self.token = token or secrets.token_urlsafe(32)
        self._wanted_port = port
        self._httpd: _Httpd | None = None
        self.port = 0
        self.allowed_hosts: set[str] = set()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/#t={self.token}"

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self) -> str:
        if self._httpd:
            return self.url
        last_error: OSError | None = None
        # port 0 means "any free port" (tests); otherwise take the next free one
        for port in ([0] if self._wanted_port == 0 else range(self._wanted_port, self._wanted_port + 20)):
            try:
                httpd = _Httpd(("127.0.0.1", port), Handler)
                break
            except OSError as exc:
                last_error = exc
        else:
            raise ServiceError("port_busy", "Couldn't find a free port for the web page.", str(last_error))
        httpd.daemon_threads = True
        httpd.app = self  # type: ignore[attr-defined]
        self._httpd = httpd
        self.port = httpd.server_port
        self.allowed_hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        threading.Thread(target=httpd.serve_forever, daemon=True, name="cappv1-web").start()
        return self.url

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None


def serve_cli(argv: list[str]) -> int:
    """`cappv1 --web [--port N] [--no-open]`: only the web UI, until Ctrl+C."""
    from src.services.workspace import default_workspace

    port, open_browser = DEFAULT_PORT, "--no-open" not in argv
    if "--port" in argv:
        try:
            port = int(argv[argv.index("--port") + 1])
        except (IndexError, ValueError):
            print("--port needs a number, for example: cappv1 --web --port 8800")
            return 2
    server = WebServer(default_workspace(), port=port)
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")  # unexpected errors reach this terminal
    try:
        url = server.start()
    except ServiceError as err:
        print(f"{err.message} {err.fix}")
        return 1
    print(f"cappv1 web UI: {url}\nPress Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.stop()
    return 0
