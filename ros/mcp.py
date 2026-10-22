"""The tools of ``ros.api`` over the Model Context Protocol (JSON-RPC 2.0, one message per line on stdio). Any MCP
client can attach: Claude Code, Codex, Gemini CLI, or a local model's harness. Calls run one at a time, so this
process is the single writer for as long as it runs.

Each tool takes an optional ``project``; without it the default project applies (see ``ros.home.resolve``).
"""
from __future__ import annotations

import json
import sys

from . import __version__, api, home
from .store import Record

PROTOCOL = "2025-06-18"


class Server:
    def __init__(self, project: str | None = None):
        self.default = project
        self.records: dict[str, Record] = {}

    def record(self, project: str | None) -> Record:
        root = str(home.resolve(project or self.default))
        if root not in self.records:
            self.records[root] = Record(root)
        return self.records[root]

    def tools(self) -> list[dict]:
        out = []
        for t in api.TOOLS.values():
            if t.human:  # approvals, decisions and waivers are a person's, not an agent's
                continue
            schema = t.schema()
            schema["properties"] = {"project": {"type": "string", "description": "project name or record folder"},
                                    **schema["properties"]}
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
                result = {"protocolVersion": asked or PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": "research-os", "version": __version__},
                          "instructions": "Research OS record tools. Start with status; run a lesson with start, "
                                          "answer and next; agents pick up work with tasks, claim and finish."}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.tools()}
            elif method == "tools/call":
                params = msg.get("params") or {}
                name, args = params.get("name"), dict(params.get("arguments") or {})
                if name not in api.TOOLS or api.TOOLS[name].human:
                    return _error(mid, -32602, f"unknown tool {name}" if name not in api.TOOLS
                                  else f"{name} is a person's decision: ask the researcher to make it in the portal")
                try:
                    value = api.TOOLS[name].call(self.record(args.pop("project", None)), args)
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


def serve(project: str | None = None, stdin=None, stdout=None, portal: int | None = None) -> int:
    """Answer requests until stdin closes. With ``portal``, the same process also serves the project's portal on that
    port, so the agent and the browser share one writer (calls are serialized by ``api.LOCK``)."""
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    server = Server(project)
    httpd = None
    try:
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
        if httpd is not None:  # the portal lives exactly as long as the agent session
            httpd.shutdown()
            httpd.server_close()
        for rec in server.records.values():
            rec.close()
        api.release()  # the user-wide records kept open for project records
    return 0
