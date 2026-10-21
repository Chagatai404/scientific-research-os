"""``ros``: the command line. Every tool in ``ros.api`` is a subcommand with the same arguments (``--json`` for machine
output), plus:

    ros init NAME [--here]        create a record (in ~/ResearchOS/projects, or ./.ros with --here)
    ros projects                  list records
    ros tools                     list tools with their arguments, as JSON schemas with --json
    ros learn SCOPE               a lesson in the terminal; the log is written when it closes
    ros mcp                       serve the tools to an agent over stdio (Model Context Protocol)
    ros install --client C        install skills, agents and the MCP server for claude, codex, gemini or any agent
    ros migrate VAULT             import a whole vault (notes, sessions, research) and check every answer arrived
    ros serve [--port N]          the localhost portal
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import api, home
from .store import Record


def _value(p: api.Param):
    def parse(text: str):
        if p.type == "integer":
            return int(text)
        if p.type == "number":
            return float(text)
        if p.type in ("array", "object"):
            return json.loads(text)
        if p.type == "any":
            try:
                return json.loads(text)
            except ValueError:
                return text
        return text
    return parse


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ros", description="Research OS: one record per course or project.")
    ap.add_argument("--project", "-p", help="project name or record folder (default: $ROS_PROJECT, ./.ros, the only one)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="machine-readable output")
    sub = ap.add_subparsers(dest="command", required=True, metavar="command")

    def add(name, **kw):
        return sub.add_parser(name, parents=[common], **kw)

    s = add("init", help="create a record")
    s.add_argument("name")
    s.add_argument("--here", action="store_true", help="in ./.ros (a research repository) instead of the home")
    add("projects", help="list records")
    add("tools", help="list tools")
    s = add("learn", help="a lesson in the terminal")
    s.add_argument("scope", nargs="?", help="capability:x, course:y, concept:z ... (default: the bundle's goal)")
    s.add_argument("--bundle", help="a prepared bundle; the lesson starts only when it is ready")
    s.add_argument("--title")
    add("mcp", help="serve tools over stdio (MCP)")
    s = add("migrate", help="import a whole vault into the record and check every answer arrived")
    s.add_argument("vault", help="the Obsidian vault (or any folder of old notes and sessions)")
    s.add_argument("--research-root", help="where research records live, if not in the vault")
    s.add_argument("--evidence", help="EvidenceAtom folder")
    s.add_argument("--graphify", help="a Graphify graph.json to import code symbols from")
    s = add("install", help="install skills, agents and the MCP server for an agent client")
    s.add_argument("--client", required=True, choices=("claude", "codex", "gemini", "agents"))
    s.add_argument("--target", help="project folder (default: here)")
    s.add_argument("--user", action="store_true", help="install for the user (home folder) instead of a project")
    s.add_argument("--force", action="store_true", help="overwrite installed files changed by hand")
    s.add_argument("--dry-run", action="store_true", help="say what would be written")
    s = add("serve", help="the localhost portal")
    s.add_argument("--port", type=int, default=8737)
    s.add_argument("--open", action="store_true", help="open it in the browser")
    for t in api.TOOLS.values():
        s = add(t.name, help=t.help, description=t.help)
        for name, p in t.params.items():
            flag = "--" + name.replace("_", "-")
            if p.type == "boolean":
                s.add_argument(flag, dest=name, action="store_true", help=p.help)
            else:
                s.add_argument(flag, dest=name, type=_value(p), required=p.required, help=p.help,
                               choices=list(p.enum) or None)
    return ap


def emit(value, as_json: bool) -> None:
    if isinstance(value, str) and not as_json:
        sys.stdout.write(value if value.endswith("\n") else value + "\n")
    else:
        sys.stdout.write(json.dumps(value, ensure_ascii=False, indent=None if as_json else 2) + "\n")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            emit({"record": str(home.init(args.name, Path.cwd() if args.here else None))}, args.json)
            return 0
        if args.command == "projects":
            emit({"home": str(home.home()), "projects": home.projects()}, args.json)
            return 0
        if args.command == "tools":
            emit([{"name": t.name, "help": t.help, "writes": t.writes, "input": t.schema()} for t in api.TOOLS.values()]
                 if args.json else "\n".join(f"{t.name:14} {t.help}" for t in api.TOOLS.values()), args.json)
            return 0
        if args.command == "install":
            from . import install
            out = install.install(args.client, Path(args.target) if args.target else None, args.user, args.force,
                                  args.dry_run)
            emit(out, args.json)
            return 0 if out.get("installed", True) else 4
        if args.command == "mcp":
            from . import mcp
            return mcp.serve(args.project)
        root = home.resolve(args.project)
        rec = Record(root)
        try:
            if args.command == "learn":
                return learn(rec, args.scope, args.title, bundle=args.bundle)
            if args.command == "migrate":
                from . import importers
                out = importers.migrate(rec, args.vault, args.research_root, args.evidence, args.graphify)
                emit(out if args.json else _migration_summary(out), args.json)
                return 0 if out["check"]["ok"] else 5
            if args.command == "serve":
                from . import serve
                return serve.run(rec, args.port, args.open)
            t = api.TOOLS[args.command]
            if t.human and not _confirm(t, args):
                sys.stderr.write(f"ros: {t.name} is a person's decision; it was not recorded\n")
                return 3
            emit(t.call(rec, {k: getattr(args, k) for k in t.params if getattr(args, k, None) not in (None, False)}),
                 args.json)
        finally:
            rec.close()
        return 0
    except (ValueError, KeyError) as exc:
        msg = exc.args[0] if exc.args else str(exc)
        if args.json:
            sys.stdout.write(json.dumps({"error": str(msg)}) + "\n")
        else:
            sys.stderr.write(f"ros: {msg}\n")
        return 2


def _migration_summary(out: dict) -> str:
    c, ln, se, rs = out["check"], out["learning"], out["sessions"], out["research"]
    lines = [f"Vault: {out['vault']}",
             f"Learning notes: {ln['capabilities']} capabilities, {ln['events_added']} new retrieval rows"
             + (f", {len(ln['diagnostics'])} diagnostics" if ln["diagnostics"] else ""),
             f"Sessions: {se['sessions']} imported, {se['items']} new items, {se['events_added']} new events"
             + (f", {len(se['problems'])} problems" if se["problems"] else ""),
             f"Research records: {rs['records']}",
             f"Check: {c['answers']} answers in {c['sessions']} session files, {c['missing']} missing from the history "
             f"({c['history_rows']} history rows): {'OK' if c['ok'] else 'NOT OK'}"]
    lines += [f"  {s['session']}: missing {', '.join(s['missing'])}" for s in c["per_session"] if s["missing"]]
    lines += [f"  problem: {p}" for p in se["problems"]] + [f"  diagnostic: {d}" for d in ln["diagnostics"][:20]]
    return "\n".join(lines) + "\nFull report: migration-report.json in the record."


def _confirm(t, args) -> bool:
    """A human act needs a person at a terminal who types yes."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    shown = ", ".join(f"{k}={getattr(args, k)}" for k in t.params if getattr(args, k, None))
    return input(f"Record {t.name} ({shown})? Type yes: ").strip().lower() == "yes"


# ---- the terminal lesson --------------------------------------------------------------------------------------------
HELP = ("Type your answer. ? for a hint, - for I don't know, !text to ask the tutor, ~mode for another explanation, "
        "q to stop.")


def learn(rec: Record, scope: str | None, title: str | None = None, read=input, write=print,
          bundle: str | None = None) -> int:
    started = api.start(rec, scope=scope, bundle=bundle, title=title)
    lesson, step = started["lesson"], started["next"]
    write(f"Lesson {lesson} on {scope or bundle}. {HELP}")
    while True:
        action = step["action"]
        write(f"\n[{action}] {step.get('reason', '')}")
        if action in ("close", "wait"):
            if action == "wait":
                write("Your written answers are waiting for the tutor. Close for now? [Y/n]")
                if read("> ").strip().lower().startswith("n"):
                    step = api.next_step(rec, lesson)
                    continue
            out = api.close(rec, lesson, step.get("reason", ""))
            write(f"Lesson closed. Log: {out['log']}")
            return 0
        if action == "teach":
            write(f"Now: {step.get('title')} ({step.get('mode')}). Your tutor teaches this part; "
                  "press Enter when done.")
            read("> ")
            api.teach(rec, lesson, step["capability"] or scope, step.get("mode", "explain"))
            step = api.next_step(rec, lesson)
            continue
        q = step["question"]
        write(q["prompt"])
        for i, o in enumerate(q.get("options") or []):
            write(f"  {chr(97 + i)}. {o}")
        while True:
            text = read("> ").strip()
            if text == "q":
                api.close(rec, lesson, "stopped by the learner")
                write("Stopped. The log is written.")
                return 0
            if text == "?":
                h = api.hint(rec, lesson, step["item"])
                write(h.get("hint") or h.get("explanation") or "No more hints.")
                continue
            if text.startswith("!"):
                api.ask(rec, lesson, text=text[1:].strip())
                write("Asked. Your tutor will answer.")
                continue
            if text.startswith("~"):
                api.ask(rec, lesson, mode=text[1:].strip() or "simpler")
                write("Noted: the next explanation will be like that.")
                continue
            if text:
                break
        if text == "-":
            out = api.answer(rec, lesson, step["item"], dont_know=True)
        else:
            response = text
            if q.get("kind") == "choice" and len(text) == 1 and text.isalpha():
                response = ord(text.lower()) - 97
            out = api.answer(rec, lesson, step["item"], response)
        verdict = out["verdict"]
        write({"correct": "Correct.", "incorrect": "Not yet.", "pending": "Saved; your tutor will grade it."}
              .get(verdict, verdict))
        if out.get("feedback"):
            write(out["feedback"])
        if verdict == "incorrect" and out.get("explanation") and out["next"]["action"] != "retry":
            write(out["explanation"])
        step = out["next"]


if __name__ == "__main__":
    raise SystemExit(main())
