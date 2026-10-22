"""The tools of ``ros.api`` over the Model Context Protocol (JSON-RPC 2.0, one message per line on stdio). Any MCP
client can attach: Claude Code, Codex, Gemini CLI, or a local model's harness. Calls run one at a time, so this
process is the single writer for as long as it runs.

Each tool takes an optional ``project``; without it the default project applies (see ``ros.home.resolve``).
"""
from __future__ import annotations

import json
import sys

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
                          "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
                          "serverInfo": {"name": "research-os", "version": __version__}, "instructions": INSTRUCTIONS}
                try:
                    self.follow_up(self.record(None))
                except ValueError:
                    pass  # no default record yet: the first call that names one starts it
            elif method == "ping":
                result = {}
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
            sys.stderr.write(f"research-os portal: http://127.0.0.1:{portal}/\n")
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
