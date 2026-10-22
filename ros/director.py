"""The director's side of the system: how a person (or an agent working for them) starts, steers and judges without
knowing a single command. The person is the director: they say what they want to learn or find out, and later judge the
findings, informed. Everything in between is the system's and its agents' job.

* ``engage`` takes what the person said and starts the right **playbook**: for a course or a topic it makes the records,
  states the goal, opens the outline task and lets the automation prepare lessons, notes and handouts; for a research
  question it frames the question verbatim, opens neutral literature searches, and lets the automation verify what they
  find, write the brief and wait for the experiment plan the researcher will approve. Every step is idempotent.
* ``brief`` is the first call of every session: what needs the person's judgement (with the evidence to judge it),
  what is happening, what they learned, what is new, and one line on what to do next.
* ``work`` hands an agent its next task across every record, claimed, with the skill and the tool that finishes it.
* ``evidence`` is the packet behind one decision: the audit chain, the numbers, the citations, the plan and what approving
  it authorizes, the adversary's memo, the handout and the vault note.
* ``doctor`` says what is not set up (the vault, a PDF toolchain, an agent client) and the one command that fixes it.

Approving, deciding and waiving stay the person's own acts (``human`` tools); nothing here performs them.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import os
import re
import sys

from . import __version__, automation, context, graph, handouts, home, install, research, roadmap, tasks, vault
from .learn import schedule
from .store import Record, event_id

KINDS = ("auto", "course", "topic", "research", "review", "continue")
LEARN = re.compile(r"\b(teach|learn|study|tutor|explain|understand|lecture|course|revise|prepare for|exam|midterm|final)\b", re.I)
RESEARCH = re.compile(r"\b(investigate|research|find out|is it true|does|do|whether|compare|simulate|experiment|hypothes|"
                      r"literature|measure|why (?:does|do|is)|how (?:does|do|much))\b", re.I)
REVIEW = re.compile(r"\b(quiz me|what should i review|review(?: my)? (?:due|cards|material)|due (?:reviews|items))\b", re.I)
CONTINUE = re.compile(r"^\s*(continue|go on|carry on|next|what now|resume|keep going)\b[\s.!]*$", re.I)
COURSE = re.compile(r"\b([A-Za-z]{2,5})[\s-]?(\d{3}[A-Za-z]?)\b")
FILLER = re.compile(r"^(please\s+)?(can you\s+)?(teach|help)\s+me\s+(about\s+|to\s+|with\s+)?|^(i want to|i would like to|i need to)\s+"
                    r"(learn|study|understand)\s+(about\s+)?|^(learn|study)\s+(about\s+)?|^(investigate|research)\s+", re.I)
FACETS = (("competing", "competing models and explanations of the phenomenon, and the strongest criticisms of the "
                        "leading one"),
          ("null-results", "null results, failed replications and contradicting findings"),
          ("validity", "the regime in which each approach is valid, its assumptions and its known limits, and the "
                       "reviews that survey the field"))


def slug(text: str, limit: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].strip("-") or "untitled"


def parse_intent(text: str) -> dict:
    """What the person means, from their words alone: the fallback when an agent did not say. Deterministic and
    cautious: a course code means a course; asking whether or why something is so means research; the rest is a topic."""
    t = (text or "").strip()
    if not t:
        return {"kind": "continue", "target": None, "title": None}
    if CONTINUE.match(t):
        return {"kind": "continue", "target": None, "title": None}
    code = COURSE.search(t)
    topic = FILLER.sub("", t).strip(" .?!")
    if REVIEW.search(t) and not code:
        return {"kind": "review", "target": None, "title": None}
    if code and (LEARN.search(t) or not RESEARCH.search(t)):
        key = (code.group(1) + code.group(2)).lower()
        return {"kind": "course", "target": key, "title": (code.group(1) + " " + code.group(2)).upper()}
    if RESEARCH.search(t) and not (LEARN.search(t) and not t.endswith("?")):
        return {"kind": "research", "target": slug(topic), "title": topic[:120]}
    return {"kind": "topic", "target": slug(topic), "title": topic[:120]}


# ---- records ------------------------------------------------------------------------------------------------------
def _root(name: str):
    return home.home() / "projects" / name


@contextmanager
def linked(rec: Record):
    """The record and the ones it is joined to: a user-wide record with every project and course linked to it, a project
    with the user-wide record. Records opened here are closed; the cached user-wide record is left open."""
    opened: list[Record] = []
    out = [rec]
    cfg = home.config(rec.root)
    try:
        if cfg.get("role") == "user":
            for name in home.projects():
                c = home.config(_root(name))
                if c.get("role") == "project" and c.get("user") == rec.root.name and _root(name).resolve() != rec.root.resolve():
                    r = Record(_root(name))
                    opened.append(r)
                    out.append(r)
        elif cfg.get("user") and _root(cfg["user"]).is_dir():
            out.append(context.user_record(cfg))
        yield out
    finally:
        for r in opened:
            r.close()


def _user_record(rec: Record) -> tuple[Record, bool]:
    """The user-wide record for ``rec`` and whether it is a new one: ``rec`` itself, the one it is linked to, the only
    one that exists, or a new ``me`` (a person starting from nothing has no setup to do)."""
    cfg = home.config(rec.root)
    if cfg.get("role") == "user":
        return rec, False
    if cfg.get("user") and _root(cfg["user"]).is_dir():
        return context.user_record(cfg), False
    found = context.user_records(rec)
    if found:
        return context.user_record({"user": found[0]}), False
    root = home.init("me")
    new = Record(root)
    context.link(new, user_wide=True)
    return new, True


def _ensure_record(user: Record, name: str, hub: str, title: str) -> Record:
    """A course or project record named ``name``, created and joined to the user-wide record when it does not exist."""
    existed = _root(name).is_dir()
    root = home.init(name)
    rec = Record(root)
    if home.config(root).get("role") != "project" or not existed:
        context.link(rec, user=user.root.name, project=hub, title=title)
    return rec


def _sync_vault(rec: Record) -> None:
    """Give a new record its place in the vault now (its note and its Inbox), when a vault is set."""
    if vault.configured():
        try:
            vault.sync(rec)
        except (ValueError, OSError):
            pass  # the vault being unreachable is the doctor's to report, not a reason to refuse the person's request


def _hub(user: Record, hub: str, kind: str, title: str) -> None:
    if user.node(hub) is None:
        graph.add_node(user, hub, kind, {"title": title})


def _guide(task: dict, record: str) -> dict:
    g = tasks.GUIDE.get(task["kind"], {})
    return {"task": task["id"], "kind": task["kind"], "record": record, "skill": g.get("skill"), "role": g.get("role"),
            "finish_with": g.get("finish_with"), "brief": task.get("brief")}


def portal_url(path: str = "", record: str | None = None) -> str:
    port = home.settings()["portal_port"]
    return f"http://127.0.0.1:{port}/" + (f"#{path}" if path else "") + (f"?r={record}" if record and path else "")


# ---- engage: the playbooks ----------------------------------------------------------------------------------------
def engage(rec: Record, intent: str, kind: str = "auto", target: str | None = None, title: str | None = None,
           deadline: str | None = None, pace: int | None = None, materials: str | None = None) -> dict:
    """Start what the person asked for. Returns what was set up, what waits for an agent, what is the person's, and where
    to look. Saying the same thing again changes nothing."""
    if kind not in KINDS:
        raise ValueError(f"kind is one of {', '.join(KINDS)}")
    text = (intent or "").strip()
    if not text and kind in ("auto",):
        kind = "continue"
    parsed = parse_intent(text)
    kind = parsed["kind"] if kind == "auto" else kind
    target = target or parsed["target"]
    title = title or parsed["title"] or (target or "").replace("-", " ").title() or None
    if kind in ("course", "topic", "research") and not (target or title):
        raise ValueError(f"say what the {kind} is: pass target or write it in the intent")
    if deadline:
        date.fromisoformat(deadline)
    user, created = _user_record(rec)
    note = {"intent": text, "kind": kind, "target": target}
    user.append("intent", f"intent:{slug(target or kind)}", note, actor="person",
                id=event_id("intent", f"{user.root.name}|{kind}|{target}|{text}"))
    play = PLAYBOOKS[kind]
    out = play(user, text, target, title, deadline, pace, materials)
    out.update({"kind": kind, "created_user_record": created})
    if kind in ("course", "topic", "research"):
        out["agent_tasks"] = [_guide(t, r.root.name) for r, t in out.pop("_tasks")]
        out["for_you"] = out.get("for_you", [])
    else:
        out.pop("_tasks", None)
    return out


def _course(user: Record, text, target, title, deadline, pace, materials):
    key = slug(target or title)
    hub = f"course:{key}"
    _hub(user, hub, "course", title or key)
    course = _ensure_record(user, key, hub, title or key)
    try:
        roadmap.set_goal(user, f"goal:{key}", title, [hub], deadline, pace)
        tid = tasks.open_task(
            user, "outline", hub,
            f"Outline the course {title or key!r}: read what the person gave you"
            + (f" ({materials})" if materials else " (syllabus, slides, textbook, notes; if there is nothing yet, outline "
               "from the standard curriculum and say so)")
            + f", then add the capabilities of the course as capability:<key> nodes each part-of {hub}, with `requires` "
              "edges between them and a short title (add_node, add_edge). Group them in the order the lectures teach "
              "them. The record prepares lessons, notes and handouts from this on its own. Say what you could not source.",
            data={"hub": hub, "materials": materials, "title": title}, key="outline")
        tid_scout = tasks.open_task(
            user, "scout", hub, f"Map the authoritative sources a student of {title or key!r} should learn from "
            "(textbooks, lecture series, standard references) and return them with locators. Do not decide what to teach.",
            data={"hub": hub}, key="sources")
        _sync_vault(course)
        folder = _vault_folder(course)
        automation.reconcile(user, "tick")
        pending = [(user, tasks.get(user, i)) for i in (tid, tid_scout)]
        return {"playbook": "course", "record": course.root.name, "user_record": user.root.name, "hub": hub,
                "goal": f"goal:{key}", "vault": folder, "portal": portal_url(f"node/{hub}", user.root.name),
                "_tasks": pending,
                "for_you": ([f"Drop the syllabus, slides and papers into {folder['inbox']}: they are read in "
                             "automatically."] if folder.get("inbox") else
                            ["Choose your Obsidian vault with `ros vault_set` so notes and handouts have a home."])}
    finally:
        course.close()


def _topic(user: Record, text, target, title, deadline, pace, materials):
    key = slug(target or title)
    hub = f"subject:{key}"
    _hub(user, hub, "subject", title or key)
    roadmap.set_goal(user, f"goal:{key}", title, [hub], deadline, pace)
    scout = tasks.open_task(user, "scout", hub, f"Map the authoritative sources to learn {title or key!r} from, with locators; "
                            "do not decide what to teach.", data={"hub": hub}, key="sources")
    outline = tasks.open_task(
        user, "outline", hub, f"Outline {title or key!r} for someone learning it: the capabilities as capability:<key> "
        f"nodes each part-of {hub}, with `requires` edges, in the order to learn them (add_node, add_edge)."
        + (f" Materials: {materials}." if materials else ""), data={"hub": hub, "materials": materials}, key="outline")
    _sync_vault(user)
    automation.reconcile(user, "tick")
    return {"playbook": "topic", "user_record": user.root.name, "hub": hub, "goal": f"goal:{key}",
            "portal": portal_url(f"node/{hub}", user.root.name), "vault": _vault_folder(user),
            "_tasks": [(user, tasks.get(user, scout)), (user, tasks.get(user, outline))], "for_you": []}


def _research(user: Record, text, target, title, deadline, pace, materials):
    key = slug(target or title)
    hub = f"project:{key}"
    _hub(user, hub, "project", title or key)
    proj = _ensure_record(user, key, hub, title or key)
    try:
        qid = f"question:{key}"
        node = {"title": (title or key)[:120], "text": text or title, "status": "framed", "asked_by": "person"}
        if proj.node(qid) != {"id": qid, "type": "question", **node}:
            proj.put_nodes([{"id": qid, "type": "question", **node}])
        if not proj.edges(src=qid, type="part-of", dst=hub):
            proj.put_edge(qid, "part-of", hub)
        out = []
        for facet, what in FACETS:
            spec = {"question": text or title, "facet": facet, "hypothesis_sensitive": True,
                    "required_searches": ["primary", "review", "competing", "null-result", "validity-limits"]}
            tid = tasks.open_task(
                proj, "scout", qid, f"Search neutrally for {what}, on the question: {text or title}. Work from this brief "
                "alone (skill research, agent scout): return a scout report with the searches you ran, candidates with "
                "locators, and what you read of each. Do not decide what is true.",
                data={"question": qid, "facet": facet, "brief_spec": spec}, key=facet)
            out.append((proj, tasks.get(proj, tid)))
        _sync_vault(proj)
        automation.reconcile(proj, "tick")
        return {"playbook": "research", "record": proj.root.name, "user_record": user.root.name, "hub": hub,
                "question": qid, "vault": _vault_folder(proj), "portal": portal_url(f"node/{qid}", proj.root.name),
                "_tasks": out,
                "for_you": ["You will be asked to judge: the literature brief, the experiment plan to approve, and the "
                            "findings to decide on. Nothing else needs you."]}
    finally:
        proj.close()


def _review(user: Record, text, target, title, deadline, pace, materials):
    due = schedule.due(user, date.today())
    return {"playbook": "review", "user_record": user.root.name, "due": len(due),
            "start": {"tool": "start", "args": {"scope": "review:due"}} if due else None,
            "for_you": [f"{len(due)} item(s) are due: start the review lesson." if due else "Nothing is due today."],
            "portal": portal_url("learn", user.root.name), "_tasks": []}


def _continue(user: Record, text, target, title, deadline, pace, materials):
    with linked(user) as recs:
        for r in recs:
            automation.reconcile(r, "tick")
    return {"playbook": "continue", "user_record": user.root.name, "next": brief(user, compact=True)["next_action"],
            "portal": portal_url("director", user.root.name), "_tasks": []}


PLAYBOOKS = {"course": _course, "topic": _topic, "research": _research, "review": _review, "continue": _continue}


def _vault_folder(rec: Record) -> dict:
    """Where this record's notes go in the vault, once one is set (the Inbox is where the person drops material)."""
    if not vault.configured():
        return {"set": False}
    lay = vault.layout(rec)
    root = home.settings()["vault_root"]
    base = f"{root}/{lay['folder']}"
    return {"set": True, "folder": base, "inbox": f"{base}/Inbox" if not lay["is_user"] else f"{root}/Inbox"}


# ---- brief ---------------------------------------------------------------------------------------------------------
def _age_hours(ts: str) -> float:
    return round((datetime.now(timezone.utc) - datetime.strptime(ts, tasks.FORMAT).replace(tzinfo=timezone.utc)).total_seconds() / 3600, 1)


def brief(rec: Record, as_of: date | None = None, compact: bool = False) -> dict:
    """The first thing to read: what needs the person's judgement, what is happening, what they learned, what is new."""
    as_of = as_of or date.today()
    needs, counts, oldest, jobs, recent = [], {}, None, {"open": 0, "claimed": 0}, []
    learned = {"due": 0, "next_due": None, "frontier": [], "lessons_this_week": 0, "unreviewed_handouts": []}
    new = {"inbox": 0, "my_notes_flowed_back": 0}
    week = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(tasks.FORMAT)
    records = []
    with linked(rec) as recs:
        for r in recs:
            try:
                automation.reconcile(r, "call")
            except Exception:
                pass
            cfg = home.config(r.root)
            role = cfg.get("role") or "unlinked"
            records.append({"name": r.root.name, "role": role, "hub": cfg.get("project")})
            for item in research.queue(r, as_of):
                needs.append({"record": r.root.name, **item, "evidence": _headline(r, item),
                              "portal": portal_url(f"node/{item['subject']}", r.root.name)})
            for kind, c in tasks.counts(r).items():
                if kind == "job":
                    jobs["open"] += c["open"]
                    jobs["claimed"] += c["claimed"]
                    continue
                row = counts.setdefault(kind, {"open": 0, "claimed": 0})
                row["open"] += c["open"]
                row["claimed"] += c["claimed"]
            for t in tasks.tasks(r):
                if t["kind"] != "job" and (oldest is None or t["opened"] < oldest):
                    oldest = t["opened"]
            recent += [{"record": r.root.name, **x} for x in automation.status(r, 3)["last"]]
            new["inbox"] += len(r.events(type="inbox.found", since=week))
            new["my_notes_flowed_back"] += len(r.events(type="note.annotate", since=week))
            if role == "user" or len(recs) == 1:
                due = schedule.due(r, as_of)
                learned["due"] += len(due)
                future = [c["due"] for c in schedule.schedule(r, as_of) if c["due"] > as_of.isoformat()]
                learned["next_due"] = min(future) if future else learned["next_due"]
                learned["frontier"] = [{"id": k, "title": (r.node(k) or {}).get("title")}
                                       for k in graph.Learning(r, as_of).frontier()[:5]]
                learned["lessons_this_week"] += len([e for e in r.events(type="lesson.close", since=week)
                                                     if not e["subject"].startswith("bundle:")])
            learned["unreviewed_handouts"] += [
                {"record": r.root.name, "id": n["id"], "title": n.get("title"), "status": n.get("status"), "pdf": n.get("pdf")}
                for n in r.nodes(type="handout") if n.get("status") in ("ready", "built")
                and not r.events(type="note.reviewed", subject=n["id"])]
    waiting = sum(c["open"] + c["claimed"] for c in counts.values())
    problems = _problems(rec)
    out = {"as_of": as_of.isoformat(), "record": rec.root.name, "records": records, "needs_you": needs,
           "happening": {"waiting_for_agent": waiting, "tasks": counts,
                         "oldest_waiting_hours": _age_hours(oldest) if oldest else None, "jobs": jobs,
                         "recent": sorted(recent, key=lambda x: x["at"], reverse=True)[:5], "problems": problems},
           "learned": learned, "new": new, "portal": portal_url("director", rec.root.name)}
    out["next_action"] = _next_action(out)
    if compact:
        out = {"next_action": out["next_action"], "needs_you": len(needs), "waiting_for_agent": waiting,
               "due": learned["due"], "problems": problems, "portal": out["portal"]}
    return out


def _problems(rec: Record) -> list[str]:
    """What stops the system doing its work on its own, said once: no vault, no PDF toolchain while handouts wait."""
    out = []
    if not vault.configured():
        out.append("No Obsidian vault is set: notes and PDFs have nowhere to go yet (`ros vault_set --path <vault>`).")
    jobs_waiting = [t for t in tasks.tasks(rec, "job") if t.get("handout")]
    if jobs_waiting and not handouts.toolchain()["engines"]:
        out.append(handouts.toolchain()["note"])
    return out


def _headline(rec: Record, item: dict) -> dict:
    """A few facts that let the person see at a glance what a queue item rests on; ``evidence`` has all of it."""
    s = item["subject"]
    if item["kind"] in ("decide", "defend") and s.startswith("claim:"):
        st = research.status(rec, s)
        return {"verdict": st["verdict"], "steps": {k: v["verdict"] for k, v in st["verdicts"].items()},
                "missing": st["missing"], "ownership": st["ownership"]}
    if item["kind"] == "approve":
        n = rec.node(s) or {}
        return {"plan": n.get("plan") or n.get("title"), "ladder": n.get("ladder"), "budget": n.get("budget")}
    return {}


def _next_action(b: dict) -> str:
    if b["needs_you"]:
        first = b["needs_you"][0]
        more = f" (and {len(b['needs_you']) - 1} more)" if len(b["needs_you"]) > 1 else ""
        return f"Judge: {first['kind']} {first['text'] or first['subject']}{more}. Open {b['portal']}"
    if b["learned"]["due"]:
        return f"Review {b['learned']['due']} due item(s): say \"quiz me\" to your agent, or `ros learn review:due`."
    h = b["happening"]
    if h["waiting_for_agent"]:
        age = f", the oldest {h['oldest_waiting_hours']} h" if h["oldest_waiting_hours"] is not None else ""
        return (f"{h['waiting_for_agent']} task(s) wait for an agent{age}: open your agent and say \"continue\".")
    if b["learned"]["frontier"]:
        return f"Ready to learn: {b['learned']['frontier'][0]['title']}. Say \"teach me {b['learned']['frontier'][0]['title']}\"."
    if b["happening"]["problems"]:
        return b["happening"]["problems"][0]
    return "Nothing waits. Tell your agent what to teach you, or what to investigate."


def format_brief(b: dict) -> str:
    """The brief as the few lines a terminal shows."""
    if "needs_you" in b and isinstance(b["needs_you"], int):  # the compact form
        return "\n".join([b["next_action"]] + [f"! {p}" for p in b["problems"]])
    lines = [f"{b['record']} · {b['as_of']}", ""]
    if b["needs_you"]:
        lines.append(f"Needs your judgement ({len(b['needs_you'])}):")
        lines += [f"  - {i['kind']}: {i['text'] or i['subject']}" for i in b["needs_you"][:6]]
    h, lrn = b["happening"], b["learned"]
    lines.append(f"Waiting for an agent: {h['waiting_for_agent']}" + (f" (oldest {h['oldest_waiting_hours']} h)"
                                                                      if h["oldest_waiting_hours"] is not None else "")
                 + (f"; {h['jobs']['open'] + h['jobs']['claimed']} job(s) running or queued" if h["jobs"]["open"] + h["jobs"]["claimed"] else ""))
    lines.append(f"Due for review: {lrn['due']}" + (f" · next {lrn['next_due']}" if lrn["next_due"] else "")
                 + f" · lessons this week: {lrn['lessons_this_week']}")
    if lrn["unreviewed_handouts"]:
        lines.append(f"Handouts to read: {len(lrn['unreviewed_handouts'])}")
    if b["new"]["inbox"]:
        lines.append(f"New in the vault this week: {b['new']['inbox']}")
    lines += [""] + [f"! {p}" for p in h["problems"]] + ["→ " + b["next_action"], f"  {b['portal']}"]
    return "\n".join(lines)


# ---- work ----------------------------------------------------------------------------------------------------------
def work(rec: Record, by: str, kinds: list[str] | None = None) -> dict:
    """The next task for an agent across every record, claimed, with how to do it and the tool that finishes it."""
    if not (by or "").strip():
        raise ValueError("work names who is working (by)")
    for bad in kinds or []:
        if bad not in tasks.KINDS or bad == "job":
            raise ValueError(f"kinds are task kinds an agent takes: {', '.join(sorted(tasks.KINDS - {'job'}))}")
    skipped: set[str] = set()
    with linked(rec) as recs:
        for _ in range(8):
            best = None
            for r in recs:
                for t in tasks.tasks(r):
                    if t["kind"] == "job" or t["id"] in skipped or (kinds and t["kind"] not in kinds):
                        continue
                    if best is None or tasks.urgency(t) < tasks.urgency(best[1]):
                        best = (r, t)
            if best is None:
                return {"task": None, "message": "Nothing waits for an agent.", "needs_you": len(
                    [i for r in recs for i in research.queue(r)]), "portal": portal_url("director", rec.root.name)}
            r, t = best
            try:
                claimed = tasks.claim(r, t["id"], by.strip())
            except ValueError:
                skipped.add(t["id"])  # another agent took it in the same instant
                continue
            guide = tasks.GUIDE[t["kind"]]
            remaining = sum(1 for x in recs for y in tasks.tasks(x) if y["kind"] != "job" and y["id"] != t["id"])
            return {"record": r.root.name, "task": {k: v for k, v in claimed.items() if k not in ("state", "claimed")},
                    "skill": guide["skill"], "role": guide["role"], "how": guide["hint"],
                    "finish": {"tool": "finish", "task": t["id"], "record": r.root.name},
                    "finish_with": guide["finish_with"], "use_record": r.root.name, "remaining": remaining}
    return {"task": None, "message": "Everything is taken by other agents."}


# ---- evidence ------------------------------------------------------------------------------------------------------
def evidence(rec: Record, subject: str) -> dict:
    """The packet behind one decision, so it can be made with everything in front of the person."""
    node = rec.node(subject)
    if subject.startswith("claim:"):
        return _claim_evidence(rec, subject)
    if node and node["type"] == "experiment":
        return _plan_evidence(rec, subject, node)
    ev = rec.event(subject)
    if ev and ev["type"] == "proposal":
        return {"subject": subject, "kind": "proposal", "text": ev["data"].get("change"), "why": ev["data"].get("rationale"),
                "by": ev["actor"], "decide": "accept or reject in the portal; an accepted proposal is applied by you"}
    if node:
        return {"subject": subject, "kind": node["type"], "node": node, "links": _links(rec, subject)}
    raise KeyError(f"no such subject {subject}")


def _links(rec: Record, subject: str) -> dict:
    out = {"portal": portal_url(f"node/{subject}", rec.root.name)}
    if vault.configured():
        loc = vault.locate(rec, subject)
        if loc:
            out["vault"] = loc
    about = [e["src"] for e in rec.edges(dst=subject, type="about") if e["src"].startswith("handout:")]
    out["handouts"] = [{"id": h, "title": (rec.node(h) or {}).get("title"), "status": (rec.node(h) or {}).get("status"),
                        "pdf": (rec.node(h) or {}).get("pdf")} for h in about]
    return out


def _claim_evidence(rec: Record, claim: str) -> dict:
    st = research.status(rec, claim)
    n = rec.node(claim) or {}
    steps = {s: {"verdict": v["verdict"], "by": v["by"], "notes": v.get("notes"), "checklist": v.get("checklist"),
                 "evidence": v.get("evidence")} for s, v in st["verdicts"].items()}
    cite = []
    for c in n.get("citations", []):
        cite.append({"citation": c})
    memo = (st["verdicts"].get("kill-argument") or {}).get("notes")
    defence = [{"kind": i.get("defence"), "prompt": i.get("prompt")} for i in rec.items(claim) if i.get("defence")]
    sup = graph.support(rec, claim)
    return {"subject": claim, "kind": "claim", "text": n.get("text"), "author": n.get("author"), "assurance": st["assurance"],
            "verdict": st["verdict"], "required": st["required"], "missing": st["missing"], "steps": steps,
            "superseded": st["superseded"], "numbers": {"cited": n.get("numbers", []),
                                                        "precheck": steps.get("numbers")},
            "citations": cite, "artifacts": n.get("artifacts", []), "adversary_memo": memo,
            "ownership": st["ownership"], "defence_items": defence,
            "supports": [r["id"] for r in sup["supports"]], "invalidates": [r["id"] for r in sup["invalidates"]],
            "decided": [{"outcome": e["data"].get("outcome"), "by": e["actor"], "at": e["ts"]}
                        for e in rec.events(type="decision", subject=claim)],
            "can_accept": st["assurance_met"], "links": _links(rec, claim),
            "chain": _chain(rec, claim)}


def _chain(rec: Record, claim: str) -> list[dict]:
    """Claim to what it rests on: the experiments it comes from, the question they answer, the sources cited."""
    out, seen = [], {claim}
    frontier = [claim]
    for _ in range(3):
        nxt = []
        for node in frontier:
            for e in rec.edges(src=node) + rec.edges(dst=node):
                other = e["dst"] if e["src"] == node else e["src"]
                if other in seen or e["type"] == "part-of":
                    continue
                seen.add(other)
                n = rec.node(other) or {}
                if n.get("type") in ("experiment", "question", "hypothesis", "paper", "source", "claim", "capability"):
                    out.append({"id": other, "type": n.get("type"), "title": n.get("title") or n.get("text"), "edge": e["type"]})
                    nxt.append(other)
        frontier = nxt
    return out[:30]


def _plan_evidence(rec: Record, subject: str, node: dict) -> dict:
    plan = {k: v for k, v in node.items() if k not in ("id", "type")}
    budget = node.get("budget") or node.get("compute_budget")
    return {"subject": subject, "kind": "approve", "title": node.get("title"), "plan": plan,
            "authorizes": ("Approving lets the agent run every rung of the scale ladder, smallest first, within "
                           + (f"the stated budget ({budget})" if budget else "a budget the plan does not state: ask for one")
                           + " and nothing beyond; it asks you before anything the plan does not cover."),
            "has_ladder": bool(node.get("ladder")), "has_budget": bool(budget),
            "authorization": node.get("authorization"),
            "approvals": [{"decision": e["data"].get("decision"), "by": e["actor"], "note": e["data"].get("note")}
                          for e in rec.events(type="approval", subject=subject)],
            "questions": [{"id": e["dst"], "title": (rec.node(e["dst"]) or {}).get("title")}
                          for e in rec.edges(src=subject) if e["dst"].startswith(("question:", "hypothesis:"))],
            "links": _links(rec, subject)}


# ---- doctor --------------------------------------------------------------------------------------------------------
def doctor(rec: Record) -> dict:
    """What is set up and what is not, each with the one thing that fixes it."""
    checks = []

    def add(name: str, ok: bool, detail: str, fix: str | None = None, level: str = "needed"):
        checks.append({"check": name, "ok": ok, "detail": detail, **({"fix": fix} if fix and not ok else {}),
                       "level": level})

    add("python", sys.version_info >= (3, 11), f"Python {sys.version.split()[0]}, ros {__version__}")
    add("record", not rec.problems, f"{rec.root.name}: " + ("healthy" if not rec.problems else f"{len(rec.problems)} problem(s): {rec.problems[0]}"),
        "ros rebuild")
    cfg = home.config(rec.root)
    add("linked", cfg.get("role") in ("user", "project"), f"role: {cfg.get('role') or 'unlinked'}",
        "ros init me --user-wide, then link this record to it", "advice")
    st = home.settings()
    found = home.detect_vaults()
    if vault.configured():
        writable = os.access(vault.vault_path(), os.W_OK)
        add("vault", writable, f"{vault.vault_path()} / {st['vault_root']}" if writable
            else f"the vault {vault.vault_path()} is not writable", "check the folder's permissions")
    else:
        add("vault", False, "no vault is set" + (f"; Obsidian knows {len(found)}: {found[0]['path']}" if found else ""),
            "ros vault_set" + (f" --path {found[0]['path']}" if found else " --path <your vault>"))
    tool = handouts.toolchain()
    add("pdf", bool(tool["engines"]), "PDF engines: " + (", ".join(tool["engines"]) or "none") + (
        " (LaTeX preferred)" if "latex" in tool["engines"] else ""), "install MiKTeX/TeX Live, or Edge/Chrome; "
        "the Markdown notes work without one", "advice")
    jobs = tasks.tasks(rec, "job", state=None)
    add("jobs", not [t for t in jobs if t["state"] == "open"], f"{sum(1 for t in jobs if t['state'] == 'open')} job(s) queued; "
        "they run while `ros serve`, `ros mcp` or `ros go` is running", "ros go", "advice")
    runs = rec.events(type="automation.run", limit=1)
    add("automation", True, "last automatic action " + (_age_text(runs[0]["ts"]) if runs else "none yet"), level="info")
    for client in install.CLIENTS[:3]:
        try:
            out = install.install(client, None, False, False, True)
            ok = not out.get("would_write")
            add(f"agent:{client}", ok, "skills, agents and the MCP server are installed here" if ok
                else "not installed in this folder", f"ros install --client {client}", "advice")
        except Exception as exc:
            add(f"agent:{client}", False, str(exc)[:80], f"ros install --client {client}", "advice")
    return {"ok": all(c["ok"] for c in checks if c["level"] == "needed"), "checks": checks,
            "fix": [c["fix"] for c in checks if not c["ok"] and c.get("fix")]}


def _age_text(ts: str) -> str:
    h = _age_hours(ts)
    return f"{h} h ago" if h >= 1 else "within the hour"
