"""``ros``: the command line. With nothing after it, ``ros`` says what needs you and what to do next (and sets itself up
the first time). ``ros ask "teach me STAT303"`` (or ``go``) says what you want and stays until the work that can run
without an agent is done. Every tool in ``ros.api`` is a subcommand with the same arguments (``--json`` for machine
output), plus:

    ros ask "WORDS"               what you want to learn or find out; the records, lessons, notes and handouts follow
    ros go [WORDS]                the same, or with no words: carry on with what is waiting
    ros init NAME [--here]        create a record (in ~/ResearchOS/projects, or ./.ros with --here)
    ros projects                  list records
    ros tools                     list tools with their arguments, as JSON schemas with --json
    ros learn SCOPE               a lesson in the terminal; the log is written when it closes
    ros mcp                       serve the tools to an agent over stdio (Model Context Protocol)
    ros install --client C        install skills, agents and the MCP server for claude, codex, gemini or any agent
    ros migrate --vault PATH      import a whole vault (notes, sessions, research) and check every answer arrived
    ros serve [--port N]          the localhost portal
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__, api, home, runner
from .store import Record


ALIASES = {"b": ["brief"], "st": ["status"], "q": ["queue"], "w": ["work"], "d": ["doctor"], "v": ["vault_status"],
           "r": ["learn", "review:due"], "open": ["serve", "--open"]}
SPECIAL = ("init", "projects", "tools", "learn", "mcp", "install", "serve", "go")


def expand(argv: list[str]) -> list[str]:
    """A short name (``ros b``) becomes its command; global options before it stay where they are."""
    skip = False
    for i, a in enumerate(argv):
        if skip:
            skip = False
        elif a in ("--project", "-p"):
            skip = True
        elif not a.startswith("-"):
            if a == "ask" and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                return argv[:i] + ["go"] + argv[i + 1:]  # `ros ask "teach me STAT303"`; `ask --lesson ...` stays the tool
            return argv[:i] + ALIASES.get(a, [a]) + argv[i + 1:]
    return argv


def _value(p: api.Param):
    def parse(text: str):
        if p.type in ("array", "object") and text.startswith("@"):
            # @file.json: JSON read from a file, because a shell strips the backslashes of LaTeX written inline
            try:
                text = Path(text[1:]).expanduser().read_text(encoding="utf-8")
            except OSError as exc:
                raise argparse.ArgumentTypeError(f"cannot read {text[1:]}: {exc.strerror}") from exc
        try:
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
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{exc} (JSON, or @file.json)" if p.type in ("array", "object")
                                             else str(exc)) from exc
        return text
    return parse


def command_of(argv: list[str]) -> str | None:
    """The subcommand named in ``argv``, skipping global options, or None when it cannot be told."""
    skip = False
    for a in argv:
        if skip:
            skip = False
        elif a in ("--project", "-p"):
            skip = True
        elif not a.startswith("-"):
            return a
    return None


def _dest(name: str) -> str:
    """Where a tool argument is stored. A tool's ``project`` argument must not overwrite the global ``--project``."""
    return "tool_" + name if name in ("project", "json", "command") else name


def parser(only: str | None = None) -> argparse.ArgumentParser:
    """The argument parser. With ``only`` naming a tool, just that tool's subparser is built: constructing all sixty
    costs about 0.15 s, paid on every call for nothing."""
    ap = argparse.ArgumentParser(prog="ros", description="Research OS: one record per course or project.")
    ap.add_argument("--project", "-p", help="project name or record folder (default: $ROS_PROJECT, ./.ros, the only one)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--version", action="version", version=f"ros {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="machine-readable output")
    sub = ap.add_subparsers(dest="command", required=True, metavar="command")

    def add(name, **kw):
        return sub.add_parser(name, parents=[common], **kw)

    s = add("init", help="create a record")
    s.add_argument("name")
    s.add_argument("--here", action="store_true", help="in ./.ros (a research repository) instead of the home")
    s.add_argument("--kind", choices=("project", "course"), default="project",
                   help="what this record is for: a project's research or a course (default project)")
    s.add_argument("--title", help="its name in the knowledge graph (default: the record name)")
    s.add_argument("--user", help="the user-wide record to join (default: the only one)")
    s.add_argument("--user-wide", action="store_true", help="this is the user-wide knowledge record")
    s.add_argument("--no-link", action="store_true", help="do not join the user-wide knowledge graph")
    add("projects", help="list records")
    add("tools", help="list tools")
    for name, what in (("go", "say what you want to learn or find out, or carry on (ros ask \"words\" is the same)"),):
        s = add(name, help=what, description=what)
        s.add_argument("intent", nargs="*", help="your words (for go: none means carry on)")
        s.add_argument("--kind", choices=("course", "topic", "research", "review", "continue"),
                       help="what it is (default: worked out from your words)")
        s.add_argument("--deadline", help="ISO date to finish by")
        s.add_argument("--pace", type=int, help="minutes a week")
        s.add_argument("--materials", help="where the course material is, or what it is")
        s.add_argument("--timeout", type=float, default=600, help="seconds to wait for local jobs (default 600)")
        s.add_argument("--watch", action="store_true", help="keep running, keeping the record in step, until Ctrl+C")
    s = add("learn", help="a lesson in the terminal")
    s.add_argument("scope", nargs="?", help="capability:x, course:y, concept:z ... (default: the bundle's goal)")
    s.add_argument("--bundle", help="a prepared bundle; the lesson starts only when it is ready")
    s.add_argument("--title")
    s = add("mcp", help="serve tools over stdio (MCP)")
    s.add_argument("--portal", type=int, metavar="PORT", help="also serve the portal for this project on PORT")
    s = add("install", help="install skills, agents and the MCP server for an agent client")
    s.add_argument("--client", required=True, choices=("claude", "codex", "gemini", "agents"))
    s.add_argument("--target", help="project folder (default: here)")
    s.add_argument("--user", action="store_true", help="install for the user (home folder) instead of a project")
    s.add_argument("--force", action="store_true", help="overwrite installed files changed by hand")
    s.add_argument("--dry-run", action="store_true", help="say what would be written")
    s.add_argument("--hooks", action="store_true", help="claude: also add a SessionStart hook that shows `ros brief`")
    s = add("serve", help="the localhost portal")
    s.add_argument("--port", type=int, default=8737)
    s.add_argument("--open", action="store_true", help="open it in the browser")
    for t in api.TOOLS.values():
        if only in api.TOOLS and t.name != only:
            continue
        s = add(t.name, help=t.help, description=t.help)
        for name, p in t.params.items():
            flag = "--" + name.replace("_", "-")
            if p.type == "boolean":
                s.add_argument(flag, dest=_dest(name), action="store_true", help=p.help)
            else:
                s.add_argument(flag, dest=_dest(name), type=_value(p), required=p.required, help=p.help,
                               choices=list(p.enum) or None)
    return ap


def emit(value, as_json: bool) -> None:
    value = api.external_result(value)
    if isinstance(value, str) and not as_json:
        sys.stdout.write(value if value.endswith("\n") else value + "\n")
    else:
        sys.stdout.write(json.dumps(value, ensure_ascii=False, indent=None if as_json else 2) + "\n")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = expand(sys.argv[1:] if argv is None else argv)
    if not any(not a.startswith("-") for a in argv) and not {"--help", "-h", "--version"} & set(argv):
        return _bare(argv)
    cmd = command_of(argv)
    if cmd and cmd not in SPECIAL and cmd not in api.TOOLS:
        close = home.suggest(cmd, [*SPECIAL, *api.TOOLS, *ALIASES])
        sys.stderr.write(f"ros: unknown command {cmd!r}" + (f" (did you mean {', '.join(close)}?)" if close else "")
                         + ". `ros tools` lists them, `ros` says what to do next.\n")
        return 2
    args = parser(cmd).parse_args(argv)
    try:
        if args.command == "init":
            root = home.init(args.name, Path.cwd() if args.here else None)
            out = {"record": str(root)}
            if not args.no_link:  # a new record joins the two graphs now, not "later, by hand"
                rec = Record(root)
                try:
                    out["setup"] = api.call("link", rec, user=args.user, project=None if args.user_wide else
                                            f"{args.kind}:{args.name}", title=args.title, user_wide=args.user_wide)
                except ValueError as exc:  # e.g. no user-wide record yet: the record exists, and the way on is said
                    out["setup"] = {"role": "unlinked", "note": str(exc)}
                finally:
                    rec.close()
                    api.release()
            emit(out, args.json)
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
                                  args.dry_run, args.hooks)
            if not args.json and len(out.get("written", [])) > 10:  # a person wants the count, not 75 file names
                out = {**out, "written": f"{len(out['written'])} files (--json lists them)"}
            emit(out, args.json)
            return 0 if out.get("installed", True) else 4
        if args.command == "mcp":
            from . import mcp
            return mcp.serve(args.project, portal=args.portal)
        if args.command == "go":
            return _ask(args)
        try:
            root = home.resolve(args.project)
        except ValueError as exc:
            if not home.projects() and not args.project:
                raise ValueError("no records yet: run `ros` to set yourself up (or `ros init <name>`)") from exc
            raise
        rec = Record(root)
        try:
            if args.command == "learn":
                return learn(rec, args.scope, args.title, bundle=args.bundle)
            if args.command == "serve":
                from . import serve
                return serve.run(rec, args.port, args.open)
            t = api.TOOLS[args.command]
            if t.name == "brief" and not args.json and not getattr(args, "as_of", None) and not getattr(args, "compact", False):
                args.text = True  # people read a few lines; `--json` is for programs
            if t.human and not _confirm(t, args):
                sys.stderr.write(f"ros: {t.name} is a person's decision and was not recorded: run it at a terminal and "
                                 "type yes, or make it in the portal (ros serve)\n")
                return 3
            # `0 in (None, False)` is true in Python: compare by identity so an answer of 0 is not dropped
            out = t.call(rec, {k: getattr(args, _dest(k)) for k in t.params
                               if getattr(args, _dest(k), None) is not None and getattr(args, _dest(k)) is not False})
            if t.writes and t.name not in ("reconcile", "job_done"):
                try:  # what follows from the change happens now (see ros.automation)
                    api.call("reconcile", rec, mode="call")
                except Exception:
                    pass
            if t.name == "migrate":
                emit(out if args.json else _migration_summary(out), args.json)
                return 0 if out["check"]["ok"] else 5
            if t.name == "doctor" and not args.json:
                emit(_doctor_text(out), False)
                return 0 if out["ok"] else 1
            emit(out, args.json)
        finally:
            rec.close()
        return 0
    except (ValueError, KeyError) as exc:
        msg = exc.args[0] if exc.args else str(exc)
        if isinstance(exc, KeyError):  # str(KeyError('status')) is just "status"; say what it means
            msg = f"not found: {msg}" + _nearest(args, str(msg))
        if args.json:
            sys.stdout.write(json.dumps({"error": str(msg)}) + "\n")
        else:
            sys.stderr.write(f"ros: {msg}\n")
        return 2


def _nearest(args, missing: str) -> str:
    """For a node id that does not exist, the ones that do and look like it."""
    try:
        rec = Record(home.resolve(args.project))
        try:
            word = missing.split(":", 1)[-1].replace("-", " ")
            found = [n["id"] for n in rec.search_nodes(word, limit=3)] or [
                n["id"] for n in rec.search_nodes(word[: max(3, len(word) // 2)], limit=3)]
        finally:
            rec.close()
        return f" (did you mean {', '.join(found)}?)" if found else ""
    except Exception:
        return ""


def _doctor_text(out: dict) -> str:
    lines = []
    for c in out["checks"]:
        mark = "ok " if c["ok"] else ("!! " if c["level"] == "needed" else ".. ")
        lines.append(f"{mark}{c['check']}: {c['detail']}" + (f"\n     fix: {c['fix']}" if c.get("fix") else ""))
    return "\n".join(lines + ["", "Everything needed is set up." if out["ok"] else "Something needed is not set up (the lines marked !!)."])


# ---- zero configuration: ros, ros ask, ros go ---------------------------------------------------------------------
def _zero_config(project: str | None, quiet: bool = False) -> Record:
    """The record to work on. On a first run, with no record anywhere, make the user-wide one (``me``), and tell the person
    what was done and the one thing left to choose (their Obsidian vault)."""
    try:
        return Record(home.resolve(project))
    except ValueError:
        if project or home.projects():
            raise
    root = home.init("me")
    rec = Record(root)
    api.call("link", rec, user_wide=True)
    if not quiet:
        found = api.call("vault_set", rec)
        lines = [f"Welcome. Your records live in {home.home()}; the one that holds everything you know is 'me'."]
        if found.get("vault"):
            lines.append(f"Your notes and PDFs go to the Obsidian vault {found['vault']}.")
        elif found.get("detected"):
            lines.append("Obsidian knows these vaults: " + "; ".join(v["path"] for v in found["detected"][:3])
                         + ". Choose one with `ros vault_set --path <vault>`.")
        else:
            lines.append("Choose your Obsidian vault with `ros vault_set --path <vault>` so notes and PDFs have a home.")
        sys.stdout.write("\n".join(lines) + "\n\n")
    return rec


def _bare(argv: list[str]) -> int:
    """``ros`` alone: what needs you, what is happening, one line on what to do next."""
    project, as_json = None, "--json" in argv
    for i, a in enumerate(argv):
        if a in ("--project", "-p") and i + 1 < len(argv):
            project = argv[i + 1]
    try:
        rec = _zero_config(project)
    except (ValueError, KeyError) as exc:
        sys.stderr.write(f"ros: {exc.args[0] if exc.args else exc}\n")
        return 2
    try:
        out = api.call("brief", rec, text=not as_json)
        emit(out, as_json)
        return 0
    finally:
        rec.close()
        api.release()


def _open_all(rec: Record) -> list[Record]:
    out = [rec]
    for r in api.call("records", rec):
        if not r["current"]:
            out.append(Record(home.home() / "projects" / r["name"]))
    return out


def _ask(args) -> int:
    """``ros ask "..."``: say it, then stay until what can run without an agent has run, and show where things stand."""
    from . import runner
    rec = _zero_config(args.project)
    opened: list[Record] = []
    say = (lambda *a: None) if args.json else (lambda *a: print(*a, flush=True))
    try:
        text = " ".join(args.intent).strip()
        out = api.call("engage", rec, intent=text, kind=args.kind or ("continue" if not text else None),
                       deadline=args.deadline, pace=args.pace, materials=args.materials)
        say(_engaged_text(out))
        opened = _open_all(rec)
        timer = runner.Runner(lambda: opened)

        def progress(r: dict) -> None:
            say(f"  {'ok' if r['ok'] else 'failed'}: {r.get('brief') or r['job']} ({r['seconds']} s)" + (
                f" — {r['output'].strip().splitlines()[-1][:100]}" if not r["ok"] and r.get("output", "").strip() else ""))
        total = timer.until_idle(args.timeout, progress)
        if args.watch:
            say("Keeping everything in step; Ctrl+C to stop.")
            try:
                import time
                while True:
                    timer.tick_once(scan=True)
                    for r in timer.run_jobs_once(limit=3):
                        progress(r)
                    time.sleep(5)
            except KeyboardInterrupt:
                pass
        brief = api.call("brief", rec, text=not args.json)
        if args.json:
            emit({"engaged": out, "ran": total, "brief": brief}, True)
        else:
            say("\n" + brief)
        return 0
    finally:
        for r in opened:
            if r is not rec:
                r.close()
        rec.close()
        api.release()


def _engaged_text(out: dict) -> str:
    lines = {"course": "Set up the course", "topic": "Set up the topic", "research": "Set up the question",
             "review": "Review", "continue": "Carrying on"}
    head = lines.get(out["kind"], out["kind"]) + (f" ({out['hub']})" if out.get("hub") else "")
    rows = [head + "."]
    tasks_ = out.get("agent_tasks") or []
    if tasks_:
        kinds: dict[str, int] = {}
        for t in tasks_:
            kinds[t["kind"]] = kinds.get(t["kind"], 0) + 1
        rows.append("For your agent: " + ", ".join(f"{n} {k}" for k, n in kinds.items()) + ". Open it and say \"continue\".")
    rows += [f"For you: {x}" for x in out.get("for_you", [])]
    if out.get("vault", {}).get("inbox"):
        rows.append(f"Drop material into the vault at {out['vault']['inbox']}.")
    return "\n".join(rows)


def _migration_summary(out: dict) -> str:
    c, ln, se, rs, cov = out["check"], out["learning"], out["sessions"], out["research"], out["coverage"]
    lines = [f"Vault: {out['vault']}",
             f"Learning notes: {ln['capabilities']} capabilities, {ln['events_added']} new retrieval rows"
             + (f", {len(ln['diagnostics'])} diagnostics" if ln["diagnostics"] else ""),
             f"Sessions: {se['sessions']} imported, {se['items']} new items, {se['events_added']} new events"
             + (f", {len(se['problems'])} problems" if se["problems"] else ""),
             f"Research records: {rs['records']}"
             + (f", {rs['unreferenced_atoms']} uncited claims kept" if rs.get("unreferenced_atoms") else "")]
    more = [("notes", "notes", "notes"), ("session_notes", "session_notes", "session pages"), ("projects", "projects", "projects"),
            ("papers", "papers", "papers"), ("legacy_tasks", "tasks", "research tasks"), ("visuals", "visuals", "visuals"),
            ("resources", "resources", "resources"), ("handouts", "handouts", "handouts")]
    lines.append("Also: " + ", ".join(f"{out[k][f]} {label}" for k, f, label in more if out.get(k, {}).get(f)) + ".")
    lines.append(f"Check: {c['answers']} answers in {c['sessions']} session files, {c['missing']} missing from the history "
                 f"({c['history_rows']} history rows).")
    lines.append(f"Coverage: {cov['files']} files: {cov['imported']} read in, {cov['derived']} derived, {cov['retired']} retired "
                 f"(each with its reason), {cov['unknown']} unknown"
                 + (f", {cov['not_imported']} not found in the record" if cov["not_imported"] else "") + f": {'OK' if c['ok'] else 'NOT OK'}")
    lines += [f"  unknown: {f}" for f in cov["unknown_files"][:20]] + [f"  not in the record: {f}" for f in cov["not_imported_files"][:20]]
    lines += [f"  {s['session']}: missing {', '.join(s['missing'])}" for s in c["per_session"] if s["missing"]]
    lines += [f"  problem: {p}" for p in se["problems"]] + [f"  diagnostic: {d}" for d in ln["diagnostics"][:20]]
    lines += [f"  warning: {w}" for w in out.get("warnings", [])]
    return "\n".join(lines) + "\nFull report: migration-report.json in the record; `ros migrate_check` re-checks without writing."


def _confirm(t, args) -> bool:
    """A human act needs a person at a terminal who types yes."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    shown = ", ".join(f"{k}={getattr(args, _dest(k))}" for k in t.params if getattr(args, _dest(k), None))
    return input(f"Record {t.name} ({shown})? Type yes: ").strip().lower() == "yes"


# ---- the terminal lesson --------------------------------------------------------------------------------------------
HELP = ("Type your answer. ? for a hint, - for I don't know, !text to ask the tutor, ~mode for another explanation, "
        "q to stop.")


def learn(rec: Record, scope: str | None, title: str | None = None, read=input, write=print,
          bundle: str | None = None) -> int:
    started = api.call("start", rec, scope=scope, bundle=bundle, title=title)
    lesson = started["lesson"]
    try:
        return _converse(rec, lesson, started["next"], scope or bundle, scope, read, write)
    except (EOFError, KeyboardInterrupt):  # Ctrl-D, Ctrl-C or a closed pipe: leave like "q", never a traceback
        api.call("close", rec, lesson=lesson, summary="stopped by the learner")
        write("\nStopped. The log is written.")
        return 0


def _converse(rec: Record, lesson: str, step: dict, topic: str | None, scope: str | None, read, write) -> int:
    write(f"Lesson {lesson} on {topic}. {HELP}")
    while True:
        action = step["action"]
        write(f"\n[{action}] {step.get('reason', '')}")
        if action in ("close", "wait"):
            if action == "wait":
                write("Your written answers are waiting for the tutor. Close for now? [Y/n]")
                if read("> ").strip().lower().startswith("n"):
                    step = api.call("next", rec, lesson=lesson)
                    continue
            out = api.call("close", rec, lesson=lesson, summary=step.get("reason", ""))
            write(f"Lesson closed. Log: {out['log']}")
            return 0
        if action == "teach":
            write(f"Now: {step.get('title')} ({step.get('mode')}).")
            content = step.get("content") or {}
            if content.get("segments"):  # prepared: the narration is the lesson, media are files on disk
                base = rec.root / content.get("base", "")
                for seg in content["segments"]:
                    write(f"\n{seg['text']}")
                    if seg.get("audio"):
                        write(f"  (audio: {base / seg['audio']})")
                for v in content.get("visuals", []):
                    write(f"  (visual: {base / v['path']})")
                for key, label in (("animation", "video"), ("clip", "path")):
                    media = content.get(key) or {}
                    if media.get(label):
                        write(f"  ({key}: {base / media[label]})")
                write("\nPress Enter to go on, or ask with !text.")
            else:
                write("Your tutor teaches this part live; press Enter when done.")
            read("> ")
            api.call("teach", rec, lesson=lesson, capability=step["capability"] or scope, mode=step.get("mode", "explain"))
            step = api.call("next", rec, lesson=lesson)
            continue
        q = step["question"]
        write(q["prompt"])
        for i, o in enumerate(q.get("options") or []):
            write(f"  {chr(97 + i)}. {o}")
        while True:
            text = read("> ").strip()
            if text == "q":
                api.call("close", rec, lesson=lesson, summary="stopped by the learner")
                write("Stopped. The log is written.")
                return 0
            if text == "?":
                h = api.call("hint", rec, lesson=lesson, item=step["item"])
                write(h.get("hint") or h.get("explanation") or "No more hints.")
                continue
            if text.startswith("!"):
                api.call("ask", rec, lesson=lesson, text=text[1:].strip())
                write("Asked. Your tutor will answer.")
                continue
            if text.startswith("~"):
                api.call("ask", rec, lesson=lesson, mode=text[1:].strip() or "simpler")
                write("Noted: the next explanation will be like that.")
                continue
            if text and q.get("kind") == "choice" and text != "-":
                letters = [chr(97 + i) for i in range(len(q.get("options") or []))]
                if text.lower() not in letters:  # not an answer: do not count a typo as a miss
                    write(f"Choose one of {', '.join(letters)} (- for I don't know).")
                    continue
            if text:
                break
        if text == "-":
            out = api.call("answer", rec, lesson=lesson, item=step["item"], dont_know=True)
        else:
            response = text
            if q.get("kind") == "choice" and len(text) == 1 and text.isalpha():
                response = ord(text.lower()) - 97
            out = api.call("answer", rec, lesson=lesson, item=step["item"], response=response)
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
