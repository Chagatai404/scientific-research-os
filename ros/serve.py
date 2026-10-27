"""The portal: one page per record at ``http://127.0.0.1:<port>/``, served by this process, which is the record's single
writer for as long as it runs. Open it in any browser or in Obsidian's core Web Viewer.

    GET  /                  the page
    GET  /static/...        the page's code, KaTeX and fonts (cached)
    GET  /api/<tool>?a=b    a read-only tool from ``ros.api``
    POST /api/<tool>        any tool, JSON body; requires the header ``X-ROS: 1``
    GET  /media/<path>      bundle media and lesson logs, with byte ranges for seeking
    GET  /vault/<path>      a note, PDF or image from the Obsidian vault's Research OS folder (read only)
    GET  /events?record=    server-sent ``change`` whenever the selected record grows (default if omitted)

Every tool call takes an optional ``record`` (a record's name) to work on another record the person has: the page shows
one at a time and switches. Only loopback clients are served, and only with a loopback ``Host`` header (no DNS
rebinding). Writes need the custom header, which a cross-site form cannot send. ``/vault`` serves only files below the
vault's Research OS folder, of a short list of types, never a hidden file and never through a link that leaves it.
"""
from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, unquote, urlparse
import webbrowser

from . import api, home, runner
from .store import Record

STATIC = Path(__file__).resolve().parent / "portal"
MEDIA_DIRS = ("bundles", "logs")
VAULT_TYPES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".md", ".canvas", ".base"}
LOOPBACK = {"127.0.0.1", "localhost", "[::1]"}
TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".woff2": "font/woff2",
         ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml", ".md": "text/markdown; charset=utf-8",
         ".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".mp4": "video/mp4", ".png": "image/png",
         ".webm": "video/webm", ".json": "application/json"}


def _engine(request: dict, timeout: int = 200) -> dict:
    """Run optional providers outside api.LOCK; no shell or browser-supplied executable/path."""
    env = dict(os.environ, PYTHONPATH=str(STATIC.parents[1]) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    try:
        result = subprocess.run([sys.executable, "-m", "ros.lib.dialogue"], input=json.dumps(request),
                                capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                                timeout=timeout, **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return {"ok": False, "error": "The local provider did not finish. Your message is saved; check its setup and try again."}


def _chat_response(rec: Record, result: dict, request: dict) -> None:
    answer = _engine(request)
    api.call("workspace_chat_complete", rec, conversation=result["conversation"], request=result["request"],
             text=answer.get("text") or answer.get("error") or "No response received.",
             model=request["model"], error=not answer.get("ok"))


class Pool:
    """The records a portal can work on: the one it was started for, and any other record of the home, opened on first use
    and kept (each a single writer inside this process, serialized by ``api.LOCK``)."""

    def __init__(self, default: Record):
        self.default = default
        self._records = {default.root.name: default}
        self._lock = threading.Lock()

    def get(self, name: str | None = None) -> Record:
        if not name or name == self.default.root.name:
            return self.default
        if not isinstance(name, str) or name not in home.projects():
            raise ValueError(f"no record {name!r}")
        with self._lock:
            if name not in self._records:
                self._records[name] = Record(home.home() / "projects" / name)
            return self._records[name]

    def all(self) -> list[Record]:
        with self._lock:
            return list(self._records.values())

    def close(self) -> None:
        with self._lock:
            for r in self._records.values():
                if r is not self.default:
                    r.close()
            self._records = {self.default.root.name: self.default}


def make_handler(rec: "Record | Pool"):
    pool = rec if isinstance(rec, Pool) else Pool(rec)
    rec = pool.default

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
            if path == "/services/catalog":
                return self._send(HTTPStatus.OK, {"result": _engine({"action": "catalog"}, timeout=15)})
            if path in ("/", "/index.html"):
                return self._file(STATIC / "index.html", cache=False)
            if path in ("/workspace", "/workspace/"):
                return self._file(STATIC / "workspace" / "index.html", cache=False)
            if path.startswith("/workspace/"):
                return self._file(STATIC / path.lstrip("/"), cache=True, base=STATIC / "workspace")
            if path.startswith("/static/"):
                return self._file(STATIC / path[len("/static/"):], cache=True)
            if path.startswith("/api/"):
                args = {k: _arg(v[-1]) for k, v in parse_qs(url.query).items()}
                return self._tool(path[5:], args, write=False)
            if path.startswith("/media/"):
                rel = path[len("/media/"):]
                parts = rel.split("/")
                handout_figure = (len(parts) >= 4 and parts[0] == "handouts" and parts[2] == "figures"
                                  and Path(rel).suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".webp", ".pdf"})
                if (parts[0] not in MEDIA_DIRS and not handout_figure) or any(p in ("", ".", "..") for p in parts) or "\\" in rel:
                    return self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                try:
                    mine = pool.get(parse_qs(url.query).get("record", [None])[-1])
                except ValueError:
                    return self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return self._file(mine.root / rel, cache=False, base=mine.root / parts[0])
            if path.startswith("/vault/"):
                return self._vault(path[len("/vault/"):])
            if path == "/events":
                try:
                    target = pool.get(_arg(parse_qs(url.query).get("record", [""])[-1]))
                except ValueError as exc:
                    return self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return self._events(target)
            self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})

        do_HEAD = do_GET

        def do_POST(self):
            if not self._allowed():
                return
            if self.headers.get("X-ROS") != "1":
                return self._send(HTTPStatus.FORBIDDEN, {"error": "writes need the X-ROS header"})
            path = urlparse(self.path).path
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._send(HTTPStatus.BAD_REQUEST, {"error": "Content-Length is not a number"})
            if length > 32 << 20:
                return self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "too large"})
            try:
                args = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(args, dict):
                    raise ValueError
            except ValueError:
                return self._send(HTTPStatus.BAD_REQUEST, {"error": "the body is a JSON object of arguments"})
            if not path.startswith("/api/"):
                if path in ("/services/speech", "/services/transcribe"):
                    if self.headers.get("Sec-Fetch-Site") != "same-origin":
                        return self._send(HTTPStatus.FORBIDDEN, {"error": "voice requests must come from the portal"})
                    try:
                        target = pool.get(args.get("record"))
                    except ValueError:
                        return self._send(HTTPStatus.BAD_REQUEST, {"error": "unknown record"})
                    if path.endswith("speech"):
                        text = args.get("text")
                        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
                            return self._send(HTTPStatus.BAD_REQUEST, {"error": "speech needs between 1 and 12000 characters"})
                        root = target.root / "logs" / "conversation-voice"
                        if not root.resolve().is_relative_to(target.root.resolve()):
                            return self._send(HTTPStatus.BAD_REQUEST, {"error": "voice cache must stay inside the record"})
                        result = _engine({"action": "speech", "text": text, "root": str(root)})
                        if result.get("ok"):
                            audio = Path(result["audio"])
                            if audio.is_absolute():
                                try:
                                    audio = audio.relative_to(root.resolve())
                                except ValueError:
                                    return self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid voice output"})
                            if audio.suffix != ".wav" or not (root / audio).resolve().is_relative_to(root.resolve()):
                                return self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid voice output"})
                            result["audio"] = "/media/logs/conversation-voice/" + audio.as_posix() + "?record=" + target.root.name
                    else:
                        audio = args.get("audio")
                        language = args.get("language")
                        if not isinstance(audio, str) or len(audio) > 16 << 20 or language not in (None, "", "en", "tr"):
                            return self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid recording or language"})
                        result = _engine({"action": "transcribe", "audio": audio, "language": language})
                    return self._send(HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST, {"result": result, **({"error": result.get("error")} if not result.get("ok") else {})})
                return self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            self._tool(path[5:], args, write=True)

        def _vault(self, rel: str):
            """A file from the vault's Research OS folder: confined, typed, never hidden, never through a link out."""
            try:
                root = api.call("vault_root", rec)
            except (ValueError, KeyError):
                root = None
            parts = rel.split("/")
            if not root or any(p in ("", ".", "..") or p.startswith(".") for p in parts) or "\\" in rel \
                    or Path(rel).suffix.lower() not in VAULT_TYPES:
                return self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            base = Path(root)
            # the page asks for paths as they appear in the vault ("Research OS/Courses/..."): drop the folder itself
            sub = "/".join(parts[1:]) if parts[0] == base.name else rel
            return self._file(base / sub, cache=False, base=base)

        def _tool(self, name, args, write):
            t = api.TOOLS.get(name)
            if t is None:
                return self._send(HTTPStatus.NOT_FOUND, {"error": f"no tool {name}"})
            try:
                target = pool.get(args.pop("record", None))
            except ValueError as exc:
                return self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            if t.writes and not write:
                return self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"error": f"{name} writes: use POST"})
            if t.human and self.headers.get("Sec-Fetch-Site") != "same-origin":
                # a browser sets this header on a page's own requests and a script cannot take it from the page, so
                # a decision made by `curl` or an agent's HTTP client is not taken for the researcher's click
                return self._send(HTTPStatus.FORBIDDEN, {"error": f"{name} is a person's decision: make it in the "
                                                                  "portal page"})
            try:
                result = t.call(target, args)
            except (ValueError, KeyError) as exc:
                return self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc.args[0] if exc.args else exc)})
            engine = result.pop("_engine", None) if name == "workspace_chat_send" else None
            self._send(HTTPStatus.OK, {"result": result})
            if engine:
                threading.Thread(target=_chat_response, args=(target, result, engine), daemon=True).start()

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

        def _events(self, target: Record):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            files = [target.events_path, target.nodes_path, target.edges_path]
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


class PortalServer(ThreadingHTTPServer):
    """Refuses a port another process already listens on. Windows lets a second listener share a port (the default
    ``SO_REUSEADDR`` there), so two portals, possibly for different records, would answer the same URL."""
    allow_reuse_address = os.name != "nt"
    daemon_threads = True

    def server_close(self):
        super().server_close()
        if hasattr(self, "pool"):
            self.pool.close()  # also close records opened by the switcher (Windows keeps their SQLite files locked)

    def handle_error(self, request, client_address):
        if not isinstance(sys.exc_info()[1], ConnectionError):  # a browser that left is not worth a traceback
            super().handle_error(request, client_address)

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class AlreadyRunning(ValueError):
    """Another portal of ours already answers on the port; ``url`` is where. ``run`` opens it instead of failing."""

    def __init__(self, url: str):
        super().__init__(f"a Research OS portal already runs at {url}: use it, or pass --port N (0 for any free port)")
        self.url = url


def _ours(port: int) -> bool:
    """Whether what listens on this port is a Research OS portal (it says so in its ``Server`` header)."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.5) as c:
            c.sendall(b"GET /api/records HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
            c.settimeout(1.5)
            return b"Server: ResearchOS" in c.recv(2048)
    except OSError:
        return False


def _bind(rec: "Record | Pool", port: int) -> PortalServer:
    try:
        pool = rec if isinstance(rec, Pool) else Pool(rec)
        server = PortalServer(("127.0.0.1", port), make_handler(pool))
        server.pool = pool
        return server
    except OSError as exc:
        if port and _ours(port):
            raise AlreadyRunning(f"http://127.0.0.1:{port}/") from exc
        raise ValueError(f"port {port} is in use (is another 'ros serve' running?): pass --port N, or 0 for any "
                         f"free port") from exc


def start(rec: Record, port: int = 8737) -> ThreadingHTTPServer:
    """Start the portal in a background thread (used by ``ros mcp --portal``) and return the server."""
    server = _bind(rec, port)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def run(rec: Record, port: int = 8737, open_browser: bool = False) -> int:
    pool = Pool(rec)
    try:
        server = _bind(pool, port)
    except AlreadyRunning as other:  # one portal is enough: open it
        print(f"Research OS is already running: {other.url}", flush=True)
        if open_browser:
            webbrowser.open(other.url)
        return 0
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Research OS portal for {rec.root.name}: {url}  (Ctrl+C to stop)", flush=True)
    if open_browser:
        webbrowser.open(url)
    timer = runner.Runner(pool.all).start()  # the portal keeps every record it has open in step on its own
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        timer.stop()
        server.server_close()
        pool.close()
    return 0
