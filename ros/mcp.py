"""The tools of ``ros.api`` over the Model Context Protocol (JSON-RPC 2.0, one message per line on stdio). Any MCP
client can attach: Claude Code, Codex, Gemini CLI, or a local model's harness. Calls run one at a time, so this
process is the single writer for as long as it runs.

Each tool takes an optional ``project``; without it the default project applies (see ``ros.home.resolve``).

``ros mcp`` is a thin supervisor (``supervise``) that owns the client's stdin and stdout and runs the server loop
(``serve``, started as ``ros mcp --worker``) as a child. It compares the installed ``VERSION`` file with the one it
started with; when a release is installed and nothing is in flight it restarts the child, replays the client's
``initialize`` to it and sends ``notifications/tools/list_changed``. The client's connection never breaks, and no
server keeps running old code against records a newer release has written. Only the worker runs the automation tick.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

from . import __version__, api, home, runner
from .store import Record

PROTOCOL = "2025-06-18"
INSTRUCTIONS = (
    "Research OS: the person directs, you work. Call `brief` first in every session: it says what needs the person's "
    "judgement, what is happening and what to do next. When they ask to learn a course or topic or to find something "
    "out, call `engage` with their own words; the records, lessons, notes, handouts and literature searches follow on "
    "their own. Then loop: `work` (say who you are) gives you the next task with the skill to read and the tool that "
    "finishes it; do it, finish it (pass `record` as `work` says), and call `work` again until it returns nothing. Then "
    "tell the person what now needs their judgement and where (the portal link in `brief`). Approving, deciding and "
    "waiving are theirs alone: you present the evidence (`evidence`), never decide. Teach with `start`, `answer` and "
    "`next`; grade what is waiting; never reveal a key before an answer.")
PROMPTS = {
    "continue": {"description": "Carry on: see what needs attention and do the waiting work.", "arguments": [],
                 "text": "Call `brief`, then loop `work` (by=your name) doing each task with the skill it names and "
                         "finishing it, until `work` returns no task. Then tell me what needs my judgement."},
    "learn": {"description": "Teach me a course or topic and prepare everything for it.",
              "arguments": [{"name": "what", "description": "the course or topic, in your words", "required": True}],
              "text": "I want to learn: {what}. Call `engage` with my words as the intent, then do the work it opens "
                      "(`work` in a loop). Decide how to teach it and what to prepare; tell me when the first lesson is ready."},
    "investigate": {"description": "Investigate a research question end to end.",
                    "arguments": [{"name": "question", "description": "the question, in your words", "required": True}],
                    "text": "I want to find out: {question}. Call `engage` with my words (kind research), then do the work "
                            "it opens (`work` in a loop): neutral literature searches, verification, the brief, the "
                            "experiment plan. Stop where I must judge, and show me the evidence."},
    "review": {"description": "Quiz me on what is due.", "arguments": [],
               "text": "Call `brief`; if reviews are due, `start` a review lesson (scope review:due) and teach it, grading "
                       "as you go."},
}


class Server:
    def __init__(self, project: str | None = None):
        self.default = project
        self.records: dict[str, Record] = {}

    def record(self, project: str | None) -> Record:
        try:
            root = str(home.resolve(project or self.default))
        except ValueError:
            if project or self.default or home.projects():
                raise
            # a person starting from nothing: the record that holds what they know is made for them, as `ros` does
            created = Record(home.init("me"))
            api.call("link", created, user_wide=True)
            created.close()
            root = str(home.resolve("me"))
        if root not in self.records:
            self.records[root] = Record(root)
        return self.records[root]

    def everything(self) -> list[Record]:
        """Every record of the home, opened once and kept: what the automation looks after, not only what the agent asked for."""
        for name in home.projects():
            root = str(home.home() / "projects" / name)
            if root not in self.records:
                try:
                    self.records[root] = Record(root)
                except Exception:  # a folder that is not (yet) a record is not the agent's problem
                    continue
        return list(self.records.values())

    def follow_up(self, rec: Record) -> None:
        """What follows from a change happens now, not when someone remembers to ask (see ``ros.automation``)."""
        try:
            api.call("reconcile", rec, mode="call")
        except Exception:  # the call that was asked for succeeded; trouble in the follow-up is the timer's to report
            pass

    def tools(self) -> list[dict]:
        out = []
        for t in api.TOOLS.values():
            if t.human:  # approvals, decisions and waivers are a person's, not an agent's
                continue
            schema = t.schema()
            select = {"record": {"type": "string", "description": "which record: a name or folder (default: the one "
                                                                    "this session was started for)"}}
            if "project" not in t.params:  # a tool with its own project argument (add_claim) is selected by `record`
                select["project"] = {"type": "string", "description": "same as record"}
            schema["properties"] = {**select, **schema["properties"]}
            out.append({"name": t.name, "description": t.help, "inputSchema": schema,
                        "annotations": {"readOnlyHint": not t.writes}})
        return out

    def handle(self, msg: dict) -> dict | None:
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:  # a notification
            return None
        try:
            if method == "initialize":
                asked = (msg.get("params") or {}).get("protocolVersion")
                result = {"protocolVersion": asked or PROTOCOL,
                          "capabilities": {"tools": {"listChanged": True}, "prompts": {"listChanged": False}},
                          "serverInfo": {"name": "research-os", "version": __version__}, "instructions": INSTRUCTIONS}
                try:
                    self.follow_up(self.record(None))
                except ValueError:
                    pass  # no default record yet: the first call that names one starts it
            elif method == "ping":
                # ROS_MCP_DEBUG names the worker (tests use it to see a restart); a client's ping gets {}
                result = {"pid": os.getpid(), "version": __version__} if os.environ.get("ROS_MCP_DEBUG") else {}
            elif method == "tools/list":
                result = {"tools": self.tools()}
            elif method == "prompts/list":
                result = {"prompts": [{"name": n, "description": p["description"], "arguments": p["arguments"]}
                                      for n, p in PROMPTS.items()]}
            elif method == "prompts/get":
                params = msg.get("params") or {}
                p = PROMPTS.get(params.get("name"))
                if p is None:
                    return _error(mid, -32602, f"unknown prompt {params.get('name')}")
                given = params.get("arguments") or {}
                missing = [a["name"] for a in p["arguments"] if a["required"] and not str(given.get(a["name"], "")).strip()]
                if missing:
                    return _error(mid, -32602, f"the prompt needs {', '.join(missing)}")
                text = p["text"].format(**{a["name"]: given.get(a["name"], "") for a in p["arguments"]})
                result = {"description": p["description"], "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}
            elif method == "tools/call":
                params = msg.get("params") or {}
                name, args = params.get("name"), dict(params.get("arguments") or {})
                if name not in api.TOOLS or api.TOOLS[name].human:
                    return _error(mid, -32602, f"unknown tool {name}" if name not in api.TOOLS
                                  else f"{name} is a person's decision: ask the researcher to make it in the portal")
                try:
                    selector = args.pop("record", None)
                    if "project" not in api.TOOLS[name].params:
                        selector = selector or args.pop("project", None)
                    rec = self.record(selector)
                    value = api.TOOLS[name].call(rec, args)
                    value = api.external_result(value)
                    if api.TOOLS[name].writes and name not in ("reconcile", "job_done"):
                        self.follow_up(rec)
                    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                    result = {"content": [{"type": "text", "text": text}], "isError": False}
                    if not isinstance(value, str):
                        result["structuredContent"] = value if isinstance(value, dict) else {"result": value}
                except (ValueError, KeyError) as exc:
                    result = {"content": [{"type": "text", "text": str(exc.args[0] if exc.args else exc)}],
                              "isError": True}
            else:
                return _error(mid, -32601, f"method not found: {method}")
        except Exception as exc:  # never let one bad call end the session
            return _error(mid, -32603, f"{type(exc).__name__}: {exc}")
        return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def serve(project: str | None = None, stdin=None, stdout=None, portal: int | None = None, automate: bool = True) -> int:
    """Answer requests until stdin closes. With ``portal``, the same process also serves the project's portal on that
    port, so the agent and the browser share one writer (calls are serialized by ``api.LOCK``)."""
    for stream in ((sys.stdin, sys.stdout) if stdin is None and stdout is None else ()):
        if hasattr(stream, "reconfigure"):  # MCP stdio is UTF-8; a Windows locale code page garbles or refuses non-ASCII
            stream.reconfigure(encoding="utf-8", errors="replace" if stream is sys.stdin else "strict")
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    server = Server(project)
    httpd, timer = None, None
    try:
        if automate:  # the timer and the worker live exactly as long as the agent session
            try:
                server.record(None)
            except ValueError:
                pass
            timer = runner.Runner(server.everything).start()
        if portal is not None:
            from . import serve as portal_server
            httpd = portal_server.start(server.record(None), portal)
            sys.stderr.write(f"research-os portal: http://127.0.0.1:{portal}/  (to approve or decide in it, open once: "
                             f"http://127.0.0.1:{portal}/workspace/#pair={httpd.pairing})\n")
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                reply = _error(None, -32700, "parse error")
            else:
                reply = server.handle(msg) if isinstance(msg, dict) else _error(None, -32600, "invalid request")
            if reply is not None:
                stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
                stdout.flush()
    finally:
        if timer is not None:
            timer.stop()
        if httpd is not None:  # the portal lives exactly as long as the agent session
            httpd.shutdown()
            httpd.server_close()
        for rec in server.records.values():
            rec.close()
        api.release()  # the user-wide records kept open for project records
    return 0


# ---- the supervisor -----------------------------------------------------------------------------------------------
VERSION_FILE_ENV = "ROS_MCP_VERSION_FILE"      # the file watched for a new release (tests point it elsewhere)
CHECK_SECONDS_ENV = "ROS_MCP_CHECK_SECONDS"    # how often the idle supervisor looks (default 10)
MAX_RESTARTS = 5                               # crashes tolerated within RESTART_WINDOW seconds, then requests get an error
RESTART_WINDOW = 60.0
LIST_CHANGED = b'{"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}\n'


def worker_command(project: str | None, portal: int | None) -> list[str]:
    """The server loop as a child process: this Python's ``ros mcp --worker``, or the frozen backend's ``--worker cli``."""
    cmd = [sys.executable, "--worker", "cli"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "ros"]
    if project:
        cmd += ["--project", project]
    cmd += ["mcp", "--worker"]
    return cmd + (["--portal", str(portal)] if portal is not None else [])


def _version_file() -> Path:
    return Path(os.environ.get(VERSION_FILE_ENV) or Path(__file__).resolve().parents[1] / "VERSION")


def _installed_version(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None  # unreadable (an update is replacing it): look again later


def _line(raw: bytes) -> bytes:
    return raw.rstrip(b"\r\n") + b"\n"


def _peek(raw: bytes) -> dict:
    try:
        msg = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return {}
    return msg if isinstance(msg, dict) else {}


class Supervisor:
    """Owns the client's pipes; forwards lines to a worker and restarts it when a release is installed or it dies."""

    def __init__(self, project=None, portal=None, stdin=None, stdout=None):
        self.cmd = worker_command(project, portal)
        self.stdin = stdin or sys.stdin.buffer
        self.stdout = stdout or sys.stdout.buffer
        self.lock = threading.RLock()
        self.out_lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.reader: threading.Thread | None = None
        self.gen = 0
        self.closing = False
        self.broken = False
        self.pending: dict[str, object] = {}     # request id (as JSON) -> id, for what the worker has not yet answered
        self.swallow: set[str] = set()           # replayed initialize ids whose replies are not the client's
        self.init_line: bytes | None = None
        self.inited_line: bytes | None = None
        self.crashes: list[float] = []
        self.version_file = _version_file()
        self.version = _installed_version(self.version_file)
        self.interval = float(os.environ.get(CHECK_SECONDS_ENV) or 10)

    def emit(self, raw: bytes) -> None:
        with self.out_lock:
            try:
                self.stdout.write(_line(raw))
                self.stdout.flush()
            except (OSError, ValueError):
                self.closing = True  # the client has gone

    def fail(self, mid, message: str) -> None:
        self.emit(json.dumps(_error(mid, -32603, message), ensure_ascii=False).encode("utf-8"))

    def spawn(self) -> None:
        with self.lock:
            self.gen += 1
            gen = self.gen
            self.version = _installed_version(self.version_file) or self.version
            self.proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            self.reader = threading.Thread(target=self.read_worker, args=(gen, self.proc), daemon=True)
            self.reader.start()
            if self.init_line is not None:  # the new worker meets the client as the old one did; its reply is ours
                msg = _peek(self.init_line)
                msg["id"] = f"ros-replay-{gen}"
                self.swallow.add(msg["id"])
                self.send(json.dumps(msg, ensure_ascii=False).encode("utf-8"))
                if self.inited_line is not None:
                    self.send(self.inited_line)

    def send(self, raw: bytes) -> bool:
        try:
            self.proc.stdin.write(_line(raw))
            self.proc.stdin.flush()
            return True
        except (OSError, ValueError, AttributeError):
            return False

    def read_worker(self, gen: int, proc: subprocess.Popen) -> None:
        for raw in proc.stdout:
            msg = _peek(raw)
            answer = "id" in msg and ("result" in msg or "error" in msg)
            with self.lock:
                if answer and isinstance(msg["id"], str) and msg["id"] in self.swallow:
                    self.swallow.discard(msg["id"])
                    continue
                if answer:
                    self.pending.pop(json.dumps(msg["id"]), None)
            self.emit(raw)
        proc.wait()
        self.worker_exited(gen)

    def worker_exited(self, gen: int) -> None:
        """The worker's output ended. If that was not asked for, answer what it left open and start another."""
        with self.lock:
            if gen != self.gen or self.closing:
                return
            lost, self.pending = list(self.pending.values()), {}
            self.swallow.clear()
            now = time.monotonic()
            self.crashes = [t for t in self.crashes if now - t < RESTART_WINDOW] + [now]
            tries = len(self.crashes)
            self.broken = tries > MAX_RESTARTS
        for mid in lost:
            self.fail(mid, "The Research OS server stopped while handling this request and is being restarted; ask again.")
        if self.broken:
            return
        time.sleep(min(0.25 * 2 ** (tries - 1), 4.0))
        with self.lock:
            if gen == self.gen and not self.closing:
                self.spawn()

    def retire(self) -> None:
        """Stop the current worker without the exit looking like a crash."""
        with self.lock:
            self.gen += 1
            proc = self.proc
        if proc is None:
            return
        try:
            proc.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    def check_update(self) -> None:
        """Restart the worker when a different release is installed and no request is in flight."""
        now = _installed_version(self.version_file)
        with self.lock:
            if now is None or now == self.version or self.pending or self.closing:
                return
        self.retire()
        with self.lock:
            self.crashes.clear()
            self.broken = False
            self.spawn()
            if self.init_line is not None:
                self.emit(LIST_CHANGED)

    def forward(self, raw: bytes) -> None:
        msg = _peek(raw)
        method, mid = msg.get("method"), msg.get("id")
        if method == "initialize" and mid is not None:
            self.init_line, self.inited_line = raw, None
        elif method == "notifications/initialized":
            self.inited_line = raw
        self.check_update()
        with self.lock:
            has_id = mid is not None and method is not None
            if self.broken or self.proc is None:
                if has_id:
                    self.fail(mid, "The Research OS server could not be started; restart the client.")
                return
            if has_id:
                self.pending[json.dumps(mid)] = mid
            if not self.send(raw) and has_id:
                self.pending.pop(json.dumps(mid), None)
                self.fail(mid, "The Research OS server is restarting; ask again.")

    def run(self) -> int:
        lines: queue.Queue = queue.Queue()

        def pump():
            for raw in self.stdin:
                lines.put(raw)
            lines.put(None)
        threading.Thread(target=pump, daemon=True).start()
        self.spawn()
        while True:
            try:
                raw = lines.get(timeout=self.interval)
            except queue.Empty:
                self.check_update()
                continue
            if raw is None or self.closing:
                break
            if raw.strip():
                self.forward(raw)
        with self.lock:
            self.closing = True
            proc, reader = self.proc, self.reader
        if proc is None:
            return 0
        try:
            proc.stdin.close()
        except (OSError, ValueError):
            pass
        code = proc.wait()
        if reader is not None:
            reader.join(timeout=10)
        return code


def supervise(project: str | None = None, portal: int | None = None) -> int:
    """``ros mcp``: the supervisor in front of the worker. ``ROS_MCP_NO_SUPERVISOR=1`` serves in this process instead."""
    if os.environ.get("ROS_MCP_NO_SUPERVISOR"):
        return serve(project, portal=portal)
    return Supervisor(project, portal).run()
