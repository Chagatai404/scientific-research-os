"""Every operation on a record, declared once. The CLI, the MCP server and the portal's HTTP API are generated from
this table, so any agent (with a shell, with MCP, or with HTTP) sees the same tools with the same arguments.

A tool is a function ``fn(rec, **args) -> JSON``; its parameters are declared with a type, whether they are required,
and one line of help. Tools that write say so, and the server runs them one at a time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import threading
import uuid

import base64

from . import export, graph, importers, prepare, research as rsc, tasks
from .learn import policy, schedule, tutor
from .store import Record, validate_item

HIDDEN = {"answer", "rubric", "explanation", "option_feedback", "feedback_wrong", "meta", "supersedes", "tests",
          "assumes", "introduces"}
# One call at a time: the HTTP server's threads and the MCP loop share the record (and its SQLite connection).
LOCK = threading.RLock()
TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}


@dataclass
class Param:
    type: str
    help: str
    required: bool = False
    enum: tuple = ()


@dataclass
class Tool:
    name: str
    fn: object
    help: str
    params: dict[str, Param] = field(default_factory=dict)
    writes: bool = False
    human: bool = False  # a person's act (approve, decide, waive): never offered to agents over MCP

    def schema(self) -> dict:
        props = {}
        for k, p in self.params.items():
            props[k] = {"description": p.help} if p.type == "any" else {"type": p.type, "description": p.help}
            if p.enum:
                props[k]["enum"] = list(p.enum)
        return {"type": "object", "properties": props,
                "required": [k for k, p in self.params.items() if p.required], "additionalProperties": False}

    def call(self, rec: Record, args: dict):
        unknown = set(args) - set(self.params)
        if unknown:
            raise ValueError(f"{self.name}: unknown argument(s) {sorted(unknown)}")
        for k, p in self.params.items():
            if p.required and args.get(k) is None:
                raise ValueError(f"{self.name}: {k} is required ({p.help})")
            if args.get(k) is not None and p.type in TYPES and not isinstance(args[k], TYPES[p.type]):
                raise ValueError(f"{self.name}: {k} must be {p.type}")
            if p.enum and args.get(k) is not None and args[k] not in p.enum:
                raise ValueError(f"{self.name}: {k} must be one of {list(p.enum)}")
        with LOCK:
            return self.fn(rec, **{k: v for k, v in args.items() if v is not None})


TOOLS: dict[str, Tool] = {}


def tool(name: str, help: str, writes: bool = False, human: bool = False, **params: Param):
    def wrap(fn):
        if name in TOOLS:
            raise RuntimeError(f"tool {name} is declared twice")
        TOOLS[name] = Tool(name, fn, help, params, writes or human, human)
        return fn
    return wrap


def P(type: str, help: str, required: bool = False, enum: tuple = ()) -> Param:
    return Param(type, help, required, enum)


def present(item: dict | None) -> dict | None:
    """An item as the learner may see it before answering: no key, rubric or explanation."""
    if item is None:
        return None
    out = {k: v for k, v in item.items() if k not in HIDDEN}
    if item.get("hints"):
        out["hints"] = len(item["hints"])
    return out


def _day(as_of: str | None) -> date:
    return date.fromisoformat(as_of) if as_of else date.today()


# ---- reading ------------------------------------------------------------------------------------------------------
@tool("status", "What is in this record: capabilities and their states, due reviews, open tasks, lessons, problems.",
      as_of=P("string", "ISO date to assess on (default today)"))
def status(rec, as_of=None):
    day = _day(as_of)
    learning = graph.Learning(rec, day)
    states: dict[str, int] = {}
    for c in learning.caps.values():
        states[c.assessment.state] = states.get(c.assessment.state, 0) + 1
    open_tasks: dict[str, int] = {}
    for t in tasks.tasks(rec):
        open_tasks[t["kind"]] = open_tasks.get(t["kind"], 0) + 1
    return {"record": str(rec.root), "as_of": day.isoformat(), "capabilities": len(learning.caps), "states": states,
            "ready": len(learning.ready), "frontier": len(learning.frontier()), "due": len(schedule.due(rec, day)),
            "items": len(rec.items()), "lessons": len(rec.nodes(type="lesson")), "open_tasks": open_tasks,
            "research": len(graph.research_frontier(rec)), "problems": rec.problems}


@tool("capabilities", "Each capability in a scope with its state, readiness, frontier flag and what blocks it.",
      scope=P("string", "a node id such as course:stat303 or capability:x (default: all)"),
      as_of=P("string", "ISO date (default today)"))
def capabilities(rec, scope=None, as_of=None):
    learning = graph.Learning(rec, _day(as_of))
    keys = sorted(learning.select(scope)[1] if scope else learning.caps)
    return [learning.view(k) for k in keys]


@tool("frontier", "Capabilities ready to learn next: every prerequisite is ready and the capability is not yet retained.",
      scope=P("string", "a node id (default: all)"), as_of=P("string", "ISO date (default today)"))
def frontier(rec, scope=None, as_of=None):
    return graph.Learning(rec, _day(as_of)).frontier(scope)


@tool("due", "Reviews due by FSRS from graded answers and retrieval history, soonest first.",
      as_of=P("string", "ISO date (default today)"))
def due(rec, as_of=None):
    return schedule.due(rec, _day(as_of))


@tool("history", "Every answer with its question and grade, oldest first.",
      lesson=P("string", "only this lesson"), item=P("string", "only this item (any version)"))
def history(rec, lesson=None, item=None):
    return graph.history(rec, lesson, item)


@tool("item", "One item. Hidden fields (key, rubric, explanation) only with reveal=true, for tutors and authors.",
      id=P("string", "item hash", True), reveal=P("boolean", "include the key and explanation"))
def item(rec, id, reveal=False):
    it = rec.item(id)
    return it if reveal else present(it)


@tool("items", "Items testing a capability or concept, easiest first (learner view).",
      concept=P("string", "node id, e.g. capability:x or concept:y"))
def items(rec, concept=None):
    return [present(i) for i in rec.items(concept)]


@tool("tasks", "Work waiting for an agent: grade, answer, visual, narration, animation, video, audit, verify.",
      kind=P("string", "only this kind"), state=P("string", "open (default), claimed, done, cancelled or all"))
def list_tasks(rec, kind=None, state="open"):
    return tasks.tasks(rec, kind, None if state == "all" else state)


@tool("support", "What supports or invalidates a claim or other node.", node=P("string", "node id", True))
def support(rec, node):
    return graph.support(rec, node)


@tool("code", "Code that implements a node, with Graphify symbols.", node=P("string", "node id", True))
def code(rec, node):
    return graph.code_links(rec, node)


@tool("research", "The next mechanical transition of each research record (unranked).")
def research(rec):
    return graph.research_frontier(rec)


@tool("log", "The Markdown log of a lesson.", lesson=P("string", "lesson id", True))
def log(rec, lesson):
    return export.lesson_log(rec, lesson)


@tool("map", "The capability graph of a scope for drawing: nodes with state and position flags, requires edges.",
      scope=P("string", "a node id (default: all)"), as_of=P("string", "ISO date (default today)"))
def map_(rec, scope=None, as_of=None):
    learning = graph.Learning(rec, _day(as_of))
    keys = learning.select(scope)[1] if scope else set(learning.caps)
    nodes = [{k: v for k, v in learning.view(key).items() if k != "mastery"} for key in sorted(keys)]
    edges = [{"src": key, "dst": p} for key in sorted(keys) for p in learning.caps[key].prerequisites if p in keys]
    return {"nodes": nodes, "edges": edges}


@tool("bundles", "Prepared bundles with their goal and whether each is ready.")
def bundles(rec):
    out = []
    base = rec.root / "bundles"
    for d in sorted(base.iterdir()) if base.is_dir() else []:
        if (d / "plan.json").exists():
            plan = prepare.load_plan(rec, d.name)
            out.append({"id": d.name, "title": plan.get("title"), "goal": plan.get("goal"),
                        "nodes": len(plan.get("nodes", [])), "ready": prepare.is_ready(rec, d.name)})
    return out


@tool("library", "Lesson logs and lessons, newest first.")
def library(rec):
    lessons = {n["id"]: n for n in rec.nodes(type="lesson") if not n["id"].startswith("bundle:")}
    started = {e["subject"]: e["ts"] for e in rec.events(type="lesson.start")}
    closed = {e["subject"] for e in rec.events(type="lesson.close")}
    rows = []
    for lid, n in lessons.items():
        log = rec.root / "logs" / (lid.split(":", 1)[1] + ".md")
        rows.append({"id": lid, "title": n.get("title"), "started": started.get(lid), "closed": lid in closed,
                     "log": f"logs/{log.name}" if log.exists() else None, "legacy": n.get("legacy", False)})
    return sorted(rows, key=lambda r: r["started"] or "", reverse=True)


@tool("today", "The home page: reviews due, the next lesson (ready or what is missing), answers waiting for the tutor.",
      as_of=P("string", "ISO date (default today)"))
def today(rec, as_of=None):
    day = _day(as_of)
    ready = [b for b in bundles(rec) if b["ready"]]
    not_ready = [b for b in bundles(rec) if not b["ready"]]
    nxt = None
    if ready:
        nxt = {"bundle": ready[0]["id"], "title": ready[0]["title"], "ready": True}
    elif not_ready:
        m = prepare.check(rec, not_ready[0]["id"], record_ready=False)
        nxt = {"bundle": not_ready[0]["id"], "title": not_ready[0]["title"], "ready": False,
               "missing": m["missing"][:8], "missing_count": len(m["missing"])}
    waiting = tasks.tasks(rec, kind="grade") + tasks.tasks(rec, kind="grade", state="claimed")
    asks = tasks.tasks(rec, kind="answer") + tasks.tasks(rec, kind="answer", state="claimed")
    learning = graph.Learning(rec, day)
    return {"due": len(schedule.due(rec, day)), "next_lesson": nxt, "bundles": len(ready) + len(not_ready),
            "waiting_answers": len(waiting), "waiting_questions": len(asks), "frontier": learning.frontier()[:8],
            "agent_tasks": len(tasks.tasks(rec))}


# ---- the lesson loop ----------------------------------------------------------------------------------------------
def _next(rec, lesson, scope, as_of=None):
    d = policy.decide(rec, lesson, scope, _day(as_of))
    # The decision is logged (once per change) so the policy can be audited and tuned; the learner never sees it.
    logged = rec.events(type="policy", subject=lesson)
    entry = {k: d[k] for k in ("action", "reason", "item", "capability", "mode") if d.get(k) is not None}
    if not logged or {k: v for k, v in logged[-1]["data"].items() if k != "lesson"} != entry:
        rec.append("policy", lesson, {"lesson": lesson, **entry})
    if d.get("item"):
        d["question"] = present(rec.item(d["item"]))
    if d.get("capability"):
        node = rec.node(d["capability"]) or {}
        d["title"] = node.get("title", d["capability"].split(":", 1)[-1])
        bundle = (rec.node(lesson) or {}).get("bundle")
        if d["action"] == "teach":
            content = prepare.segments_for(rec, bundle, d["capability"]) if bundle else None
            # Without prepared content the tutor explains live, and the learner is told so.
            d["content"] = content or {"live": True, "note": "no prepared content for this part: live explanation"}
    return d


@tool("start", "Start a lesson and get the first step. On a bundle it starts only when the bundle is ready.",
      writes=True, scope=P("string", "what to learn: capability:x, course:y, concept:z ... (default: the bundle's goal)"),
      bundle=P("string", "a prepared bundle id"), title=P("string", "lesson title"),
      actor=P("string", "who is learning (default learner)"))
def start(rec, scope=None, bundle=None, title=None, actor="learner"):
    if bundle:
        if not prepare.is_ready(rec, bundle):
            missing = prepare.check(rec, bundle)["missing"]
            if missing:
                raise ValueError(f"bundle {bundle} is not ready: " + "; ".join(missing[:20])
                                 + (f" (and {len(missing) - 20} more)" if len(missing) > 20 else ""))
        plan = prepare.load_plan(rec, bundle)
        scope, title = scope or plan["goal"], title or plan["title"]
    if not scope:
        raise ValueError("start needs a scope or a bundle")
    lesson = f"lesson:{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    rec.put_node(lesson, "lesson", title=title or f"Lesson on {scope.split(':', 1)[-1]}", scope=scope,
                 **({"bundle": bundle} if bundle else {}))
    tutor.start(rec, lesson, title or "", scope, actor)
    return {"lesson": lesson, "next": _next(rec, lesson, scope)}


@tool("next", "The next step of a lesson, decided by the policy, with its reason.",
      lesson=P("string", "lesson id", True), scope=P("string", "scope (default: the lesson's)"),
      as_of=P("string", "ISO date (default today)"))
def next_step(rec, lesson, scope=None, as_of=None):
    return _next(rec, lesson, scope or (rec.node(lesson) or {}).get("scope", ""), as_of)


@tool("answer", "Answer an item. Choice and numeric answers are checked now; free answers wait for a grade. "
      "dont_know=true instead of a response says \"I don't know\" (a miss, never a guess).",
      writes=True, lesson=P("string", "lesson id", True), item=P("string", "item hash", True),
      response=P("any", "the answer: option index or text, a number, or free text"),
      dont_know=P("boolean", "the learner does not know"))
def answer(rec, lesson, item, response=None, dont_know=False):
    if response is None and not dont_know:
        raise ValueError("answer needs a response or dont_know=true")
    out = tutor.answer(rec, lesson, item, tutor.DONT_KNOW if dont_know else response)
    out["next"] = next_step(rec, lesson)
    return out


@tool("hint", "The next hint for an item, then its explanation.", writes=True,
      lesson=P("string", "lesson id", True), item=P("string", "item hash", True))
def hint(rec, lesson, item):
    return tutor.hint(rec, lesson, item)


@tool("ask", "The learner asks a question, or asks for another explanation (mode).", writes=True,
      lesson=P("string", "lesson id", True), text=P("string", "the question"),
      mode=P("string", "another explanation: simpler, more-rigorous, derivation, visual, analogy, worked-example, "
                       "physical-interpretation, implementation, prerequisites"))
def ask(rec, lesson, text=None, mode=None):
    if not text and not mode:
        raise ValueError("ask needs text or mode")
    if mode and not text:
        rec.append("ask", lesson, {"lesson": lesson, "mode": mode}, actor="learner")
        return {"mode": mode}
    out = tutor.ask(rec, lesson, text)
    if mode:
        rec.append("ask", lesson, {"lesson": lesson, "mode": mode}, actor="learner")
    return out


@tool("reply", "Answer a learner's question.", writes=True, ask=P("string", "the ask event id", True),
      text=P("string", "the answer", True), by=P("string", "who answers (default tutor)"))
def reply(rec, ask, text, by="tutor"):
    return tutor.reply(rec, ask, text, by)


@tool("grade", "Grade an answer: correct, partially-correct or incorrect.", writes=True,
      attempt=P("string", "the attempt event id", True),
      verdict=P("string", "the verdict", True, tutor.VERDICTS), feedback=P("string", "what to tell the learner"),
      criteria_met=P("array", "one true/false per rubric criterion"), by=P("string", "grader (default tutor)"))
def grade(rec, attempt, verdict, feedback="", criteria_met=None, by="tutor"):
    return tutor.grade(rec, attempt, verdict, feedback, by, criteria_met)


@tool("teach", "Record that a capability was taught, how, and with what content.", writes=True,
      lesson=P("string", "lesson id", True), capability=P("string", "capability id", True),
      mode=P("string", "explain, simpler, worked-example, visual ..."), content=P("string", "what was shown"))
def teach(rec, lesson, capability, mode="explain", content=None):
    return tutor.teach(rec, lesson, capability, mode, content)


@tool("close", "Close a lesson and write its log.", writes=True, lesson=P("string", "lesson id", True),
      summary=P("string", "one-line summary"))
def close(rec, lesson, summary=""):
    out = tutor.close(rec, lesson, summary)
    out["log"] = str(export.write_lesson_log(rec, lesson))
    return out


# ---- preparation --------------------------------------------------------------------------------------------------
@tool("bundle_create", "Create a lesson bundle with its goal as the only node.", writes=True,
      bundle=P("string", "bundle id", True), title=P("string", "title", True),
      goal=P("string", "the goal node, e.g. capability:x", True), lang=P("string", "narration language (en, tr)"))
def bundle_create(rec, bundle, title, goal, lang="en"):
    return prepare.create(rec, bundle, title, goal, lang)


@tool("bundle_plan", "Read a bundle's plan, or replace it with plan=... (validated; voids the last gate verdict).",
      writes=True, bundle=P("string", "bundle id", True), plan=P("object", "the whole new plan"))
def bundle_plan(rec, bundle, plan=None):
    if plan is not None:
        prepare.save_plan(rec, bundle, plan)
    return prepare.load_plan(rec, bundle)


@tool("bundle_file", "Write one file into a bundle (text, or base64 for binary), e.g. a visual or its RESULT note.",
      writes=True, bundle=P("string", "bundle id", True), path=P("string", "path inside the bundle", True),
      text=P("string", "text content"), base64=P("string", "binary content, base64"))
def bundle_file(rec, bundle, path, text=None, base64=None):
    d = prepare.bundle_dir(rec, bundle)
    target = (d / path).resolve()
    if d.resolve() not in target.parents:
        raise ValueError("the path must stay inside the bundle")
    if (text is None) == (base64 is None):
        raise ValueError("give exactly one of text or base64")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8") if text is not None else _b64(base64)
    target.write_bytes(data)
    (d / "manifest.json").unlink(missing_ok=True)
    return {"path": path, "bytes": len(data)}


def _b64(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


@tool("bundle_check", "Run the readiness gate: every row with what is missing, and ready true or false.", writes=True,
      bundle=P("string", "bundle id", True))
def bundle_check(rec, bundle):
    return prepare.check(rec, bundle)


@tool("bundle_tasks", "Open one task per missing piece of a bundle for agents to make (and clip searches).",
      writes=True, bundle=P("string", "bundle id", True), clips=P("boolean", "also ask video scouts for clips"))
def bundle_tasks(rec, bundle, clips=False):
    return {"tasks": prepare.open_tasks(rec, bundle, clips)}


@tool("bundle_voice", "Speak every narration segment without audio with a local engine.", writes=True,
      bundle=P("string", "bundle id", True), provider=P("string", "kokoro (default), piper or chatterbox"))
def bundle_voice(rec, bundle, provider="kokoro"):
    return prepare.render_voice(rec, bundle, provider)


@tool("bundle_animate", "Render a node's Manim animation from its spec and attach it.", writes=True,
      bundle=P("string", "bundle id", True), node=P("string", "node id", True),
      spec=P("string", "animation spec path inside the bundle", True))
def bundle_animate(rec, bundle, node, spec):
    return prepare.render_animation(rec, bundle, node, spec)


# ---- research -----------------------------------------------------------------------------------------------------
@tool("claims", "The claims ledger: each claim's verdict over its required audits, ownership, and what is missing.",
      project=P("string", "only this project"), as_of=P("string", "ISO date (default today)"))
def claims(rec, project=None, as_of=None):
    return rsc.claims(rec, project, as_of=_day(as_of))


@tool("claim_status", "One claim's audit status: verdict per step, missing steps, ownership, assurance met.",
      claim=P("string", "claim id", True))
def claim_status(rec, claim):
    return rsc.status(rec, claim)


@tool("add_claim", "Add or update a claim in the ledger.", writes=True, key=P("string", "claim key or id", True),
      text=P("string", "the claim, one sentence", True), project=P("string", "project", True),
      author=P("string", "who (or which agent) produced it", True),
      assurance=P("string", "required assurance", enum=tuple(rsc.ASSURANCE)),
      numbers=P("array", "cited numbers: {value, file, column|key, tolerance}"),
      artifacts=P("array", "files an auditor reads (paths)"), citations=P("array", "sources cited"))
def add_claim(rec, key, text, project, author, assurance="internal", numbers=None, artifacts=None, citations=None):
    return rsc.add_claim(rec, key, text, project, author, assurance, numbers, artifacts, citations)


@tool("precheck", "Check every number a claim cites against its result file, before any audit.", writes=True,
      claim=P("string", "claim id", True), root=P("string", "project root the file paths are relative to", True))
def precheck(rec, claim, root):
    return rsc.precheck_numbers(rec, claim, Path(root))


@tool("request_audits", "Open audit tasks for each required step without a verdict (claim text and paths only).",
      writes=True, claim=P("string", "claim id", True))
def request_audits(rec, claim):
    return {"tasks": rsc.request_audits(rec, claim)}


@tool("verdict", "Record an audit verdict. The claim's author cannot audit it.", writes=True,
      claim=P("string", "claim id", True), step=P("string", "audit step", True, rsc.STEPS),
      verdict=P("string", "six-state verdict", True, rsc.VERDICTS), by=P("string", "auditor", True),
      notes=P("string", "findings"), checklist=P("object", "integrity: each failure mode ok or concern"),
      evidence=P("array", "files the verdict rests on"))
def verdict(rec, claim, step, verdict, by, notes="", checklist=None, evidence=None):
    return rsc.record_verdict(rec, claim, step, verdict, by, notes, checklist, evidence)


@tool("commit", "Record one atomic commitment from a review comment, or resolve one (status=fulfilled|declined).",
      writes=True, text=P("string", "the commitment (new)"), source=P("string", "where it came from (new)"),
      evidence_required=P("string", "what fulfils it (new)"), commitment=P("string", "commitment id (resolve)"),
      status=P("string", "fulfilled or declined (resolve)"), evidence=P("string", "the evidence (resolve)"),
      by=P("string", "who"))
def commit(rec, text=None, source=None, evidence_required=None, commitment=None, status=None, evidence="", by="tutor"):
    if commitment:
        return rsc.resolve_commitment(rec, commitment, status or "", evidence, by)
    if not (text and source and evidence_required):
        raise ValueError("a new commitment needs text, source and evidence_required")
    return rsc.add_commitment(rec, source, text, evidence_required, by)


@tool("propose", "Propose a change to a skill or the policy; only a human decision applies it.", writes=True,
      change=P("string", "the change", True), rationale=P("string", "why", True), by=P("string", "agent", True))
def propose(rec, change, rationale, by):
    return rsc.propose(rec, change, rationale, by)


@tool("queue", "The decision queue: everything waiting for the researcher.")
def queue(rec):
    return rsc.queue(rec)


@tool("approve", "A person approves, rejects or asks for changes to a plan.", human=True,
      subject=P("string", "experiment or plan id", True),
      decision=P("string", "the decision", True, ("approved", "rejected", "changes-requested")),
      by=P("string", "your name", True), note=P("string", "note"))
def approve(rec, subject, decision, by, note=""):
    return rsc.approve(rec, subject, decision, by, note)


@tool("decide", "A person decides on a claim (accepted, revise, rejected, retracted), question or proposal.",
      human=True, subject=P("string", "id", True), outcome=P("string", "the outcome", True),
      by=P("string", "your name", True), rationale=P("string", "why", True))
def decide(rec, subject, outcome, by, rationale):
    return rsc.decide(rec, subject, outcome, by, rationale)


@tool("waive", "A person accepts the risk of not being able to defend a claim.", human=True,
      claim=P("string", "claim id", True), by=P("string", "your name", True), reason=P("string", "the risk", True))
def waive(rec, claim, by, reason):
    return rsc.waive(rec, claim, by, reason)


# ---- agents and authors -------------------------------------------------------------------------------------------
@tool("claim", "Claim a task so no other agent takes it (the claim lapses after 30 minutes).", writes=True,
      task=P("string", "task id", True), by=P("string", "agent name", True))
def claim(rec, task, by):
    return tasks.claim(rec, task, by)


@tool("finish", "Finish a task with its result.", writes=True, task=P("string", "task id", True),
      result=P("any", "the result", True), by=P("string", "agent name"))
def finish(rec, task, result, by="agent"):
    return tasks.finish(rec, task, result, by)


@tool("add_item", "Add an immutable item. Returns its hash; the same content is the same item.", writes=True,
      item=P("object", "kind (choice|numeric|free), prompt, options+answer | answer+tolerance | rubric, explanation, "
                       "hints, concepts, difficulty, supersedes", True))
def add_item(rec, item):
    problems = validate_item(item)
    if problems:
        raise ValueError("; ".join(problems))
    return {"id": rec.put_item(item)}


@tool("add_node", "Add or update a graph node.", writes=True, id=P("string", "<type>:<key>", True),
      type=P("string", "node type", True), data=P("object", "fields"))
def add_node(rec, id, type, data=None):
    rec.put_node(id, type, **(data or {}))
    return rec.node(id)


@tool("add_edge", "Add a typed edge between nodes.", writes=True, src=P("string", "source id", True),
      type=P("string", "edge type", True), dst=P("string", "target id", True), data=P("object", "fields"))
def add_edge(rec, src, type, dst, data=None):
    rec.put_edge(src, type, dst, **(data or {}))
    return {"src": src, "type": type, "dst": dst}


@tool("import", "Import old files into this record (idempotent).", writes=True,
      kind=P("string", "what to import", True, ("learning", "sessions", "research", "graphify")),
      path=P("string", "folder (or graph.json for graphify)", True),
      evidence=P("string", "EvidenceAtom folder for research"), repo=P("string", "repository root for graphify"))
def import_(rec, kind, path, evidence=None, repo=None):
    if kind == "learning":
        return importers.learning_records(rec, path)
    if kind == "sessions":
        return importers.sessions(rec, path)
    if kind == "research":
        return importers.research_records(rec, path, evidence)
    return {"symbols": graph.import_graphify(rec, path, repo)}


@tool("rebuild", "Drop and rebuild the index from the record's files.", writes=True)
def rebuild(rec):
    rec.rebuild()
    return {"rebuilt": True, "problems": rec.problems}
