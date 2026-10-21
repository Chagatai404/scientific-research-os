"""The portal: one page per record at ``http://127.0.0.1:<port>/``, served by this process, which is the record's single
writer for as long as it runs. Open it in any browser or in Obsidian's core Web Viewer.

    GET  /                  the page
    GET  /static/...        the page's code, KaTeX and fonts (cached)
    GET  /api/<tool>?a=b    a read-only tool from ``ros.api``
    POST /api/<tool>        any tool, JSON body; requires the header ``X-ROS: 1``
    GET  /media/<path>      bundle media and lesson logs, with byte ranges for seeking
    GET  /events            server-sent events: ``change`` whenever the record grows (a grade arrives, a task is done)

Only loopback clients are served, and only with a loopback ``Host`` header (no DNS rebinding). Writes need the
custom header, which a cross-site form cannot send.
"""
from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, unquote, urlparse
import webbrowser

from . import api
from .store import Record

STATIC = Path(__file__).resolve().parent / "portal"
MEDIA_DIRS = ("bundles", "logs")
LOOPBACK = {"127.0.0.1", "localhost", "[::1]"}
TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".woff2": "font/woff2",
         ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml", ".md": "text/markdown; charset=utf-8",
         ".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".mp4": "video/mp4", ".png": "image/png",
         ".webm": "video/webm", ".json": "application/json"}


def make_handler(rec: Record):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ResearchOS"
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # quiet: the terminal belongs to the tutor
            pass

        def finish(self):
            try:
                super().finish()
            except (BrokenPipeError, ConnectionResetError):  # the browser left; nothing to tell it
                pass

        # ---- guards ----------------------------------------------------------------------------------------
        def _allowed(self) -> bool:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if self.client_address[0] not in ("127.0.0.1", "::1") or host not in LOOPBACK:
                self._send(HTTPStatus.FORBIDDEN, {"error": "the portal serves this computer only"})
                return False
            return True

        def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
            data = body if isinstance(body, bytes) else (
                body.encode("utf-8") if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode())
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; "
                             "media-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-src https://www.youtube-nocookie.com")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        # ---- routes ----------------------------------------------------------------------------------------
        def do_GET(self):
            if not self._allowed():
                return
            url = urlparse(self.path)
            path = unquote(url.path)
            if path in ("/", "/index.html"):
                return self._file(STATIC / "index.html", cache=False)
            if path.startswith("/static/"):
                return self._file(STATIC / path[len("/static/"):], cache=True)
            if path.startswith("/api/"):
                args = {k: _arg(v[-1]) for k, v in parse_qs(url.query).items()}
                return self._tool(path[5:], args, write=False)
            if path.startswith("/media/"):
                rel = path[len("/media/"):]
                parts = rel.split("/")
                if parts[0] not in MEDIA_DIRS or any(p in ("", ".", "..") for p in parts) or "\\" in rel:
                    return self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return self._file(rec.root / rel, cache=False, base=rec.root / parts[0])
            if path == "/events":
                return self._events()
            self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})

        do_HEAD = do_GET

        def do_POST(self):
            if not self._allowed():
                return
            if self.headers.get("X-ROS") != "1":
                return self._send(HTTPStatus.FORBIDDEN, {"error": "writes need the X-ROS header"})
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            if length > 32 << 20:
                return self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "too large"})
            try:
                args = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(args, dict):
                    raise ValueError
            except ValueError:
                return self._send(HTTPStatus.BAD_REQUEST, {"error": "the body is a JSON object of arguments"})
            if not path.startswith("/api/"):
                return self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            self._tool(path[5:], args, write=True)

        def _tool(self, name, args, write):
            t = api.TOOLS.get(name)
            if t is None:
                return self._send(HTTPStatus.NOT_FOUND, {"error": f"no tool {name}"})
            if t.writes and not write:
                return self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"error": f"{name} writes: use POST"})
            try:
                result = t.call(rec, args)
            except (ValueError, KeyError) as exc:
                return self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc.args[0] if exc.args else exc)})
            self._send(HTTPStatus.OK, {"result": result})

        def _file(self, path: Path, cache: bool, base: Path | None = None):
            base = (base or STATIC).resolve()
            try:
                target = path.resolve()
            except OSError:
                target = None
            if target is None or (base != target and base not in target.parents) or not target.is_file():
                return self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            ctype = TYPES.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            size = target.stat().st_size
            extra = {"Cache-Control": "max-age=31536000, immutable" if cache and "/vendor/" in target.as_posix()
                     else "no-cache", "Accept-Ranges": "bytes"}
            rng = self.headers.get("Range")
            if rng and rng.startswith("bytes="):
                start_s, _, end_s = rng[6:].split(",")[0].partition("-")
                try:
                    start = int(start_s) if start_s else max(0, size - int(end_s))
                    end = min(int(end_s), size - 1) if end_s and start_s else size - 1
                except ValueError:
                    start, end = 0, -1
                if not 0 <= start <= end < size:
                    return self._send(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, b"", ctype,
                                      {"Content-Range": f"bytes */{size}"})
                with target.open("rb") as f:
                    f.seek(start)
                    data = f.read(end - start + 1)
                extra["Content-Range"] = f"bytes {start}-{end}/{size}"
                return self._send(HTTPStatus.PARTIAL_CONTENT, data, ctype, extra)
            self._send(HTTPStatus.OK, target.read_bytes(), ctype, extra)

        def _events(self):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            files = [rec.events_path, rec.nodes_path, rec.edges_path]
            last = None
            try:
                deadline = time.monotonic() + 600  # the page reconnects; no connection lives forever
                while time.monotonic() < deadline:
                    sizes = tuple(f.stat().st_size if f.exists() else 0 for f in files)
                    if sizes != last:
                        self.wfile.write(f"event: change\ndata: {sum(sizes)}\n\n".encode())
                        self.wfile.flush()
                        last = sizes
                    else:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                    time.sleep(0.5)
            except OSError:  # the browser closed the stream
                pass
            self.close_connection = True

    return Handler


def _arg(text: str):
    try:
        return json.loads(text)
    except ValueError:
        return text


def start(rec: Record, port: int = 8737) -> ThreadingHTTPServer:
    """Start the portal in a background thread (used by ``ros mcp --portal``) and return the server."""
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(rec))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def run(rec: Record, port: int = 8737, open_browser: bool = False) -> int:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(rec))
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Research OS portal for {rec.root.name}: {url}  (Ctrl+C to stop)", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
