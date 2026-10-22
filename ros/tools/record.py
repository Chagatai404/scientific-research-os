"""Tools for the record itself: what it holds, single items and tasks, adding and removing graph entries, imports, exports
and the index.

Each tool is declared with ``@tool`` from ``ros.registry``; see ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

from pathlib import Path

from .. import export, graph, importers, research, tasks, vault
from ..learn import schedule
from ..store import validate_item
from ..registry import P, iso_day, present, tool


@tool("status", "What is in this record: capabilities and their states, due reviews, open tasks, lessons, problems.",
      as_of=P("string", "ISO date to assess on (default today)"))
def status(rec, as_of=None):
    day = iso_day(as_of)
    learning = graph.Learning(rec, day)
    states: dict[str, int] = {}
    for c in learning.caps.values():
        states[c.assessment.state] = states.get(c.assessment.state, 0) + 1
    open_tasks = {k: v["open"] for k, v in tasks.counts(rec).items() if v["open"]}
    return {"record": str(rec.root), "as_of": day.isoformat(), "capabilities": len(learning.caps), "states": states,
            "ready": len(learning.ready), "frontier": len(learning.frontier()), "due": len(schedule.due(rec, day)),
            "items": len(rec.items()), "lessons": sum(1 for n in rec.nodes(type="lesson") if not n["id"].startswith("bundle:")), "open_tasks": open_tasks,
            "research": len(graph.research_frontier(rec)), "problems": rec.problems}


@tool("history", "Answers with their question and grade, oldest first: the newest 200 unless limit says otherwise.",
      lesson=P("string", "only this lesson"), item=P("string", "only this item (any version)"),
      limit=P("integer", "how many of the newest answers (default 200; 0 for all)"))
def history(rec, lesson=None, item=None, limit=200):
    return graph.history(rec, lesson, item, limit or None)


@tool("item", "One item. Hidden fields (key, rubric, explanation) only with reveal=true, for tutors and authors.",
      id=P("string", "item hash", True), reveal=P("boolean", "include the key and explanation"))
def item(rec, id, reveal=False):
    it = rec.item(id)
    if it is None:
        raise KeyError(f"no item {id}")
    return it if reveal else present(it)


@tool("items", "Items testing a capability or concept, easiest first (learner view).",
      concept=P("string", "node id, e.g. capability:x or concept:y"))
def items(rec, concept=None):
    return [present(i) for i in rec.items(concept)]


@tool("tasks", "Work waiting for an agent: grade, answer, visual, narration, animation, video, audit, verify, scout, "
      "ingest, outline, bundle, handout, run (job tasks are for the portal or MCP process).",
      kind=P("string", "only this kind"), state=P("string", "open (default), claimed, done, cancelled or all"))
def list_tasks(rec, kind=None, state="open"):
    return tasks.tasks(rec, kind, None if state == "all" else state)


@tool("log", "The Markdown log of a lesson.", lesson=P("string", "lesson id", True))
def log(rec, lesson):
    if rec.node(lesson) is None:
        raise KeyError(f"no lesson {lesson}")
    return export.lesson_log(rec, lesson)


@tool("library", "Lesson logs and lessons, newest first.")
def library(rec):
    lessons = {n["id"]: n for n in rec.nodes(type="lesson") if not n["id"].startswith("bundle:")}
    started = {e["subject"]: e["ts"] for e in rec.events(type="lesson.start")}
    closed = {e["subject"] for e in rec.events(type="lesson.close")}
    rows = []
    for lid, n in lessons.items():
        log = rec.root / "logs" / (lid.split(":", 1)[-1] + ".md")
        rows.append({"id": lid, "title": n.get("title"), "started": started.get(lid), "closed": lid in closed,
                     "log": f"logs/{log.name}" if log.exists() else None, "legacy": n.get("legacy", False)})
    return sorted(rows, key=lambda r: r["started"] or "", reverse=True)


@tool("claim", "Claim a task so no other agent takes it (the claim lapses after 30 minutes).", writes=True,
      task=P("string", "task id", True), by=P("string", "agent name", True))
def claim(rec, task, by):
    return tasks.claim(rec, task, by)


@tool("finish", "Finish a task with its result.", writes=True, task=P("string", "task id", True),
      result=P("any", "the result", True), by=P("string", "agent name"))
def finish(rec, task, result, by=None):
    research.check_task_result(rec, task, result)
    return tasks.finish(rec, task, result, by, owner_only=True)


@tool("cancel", "Withdraw an open task that is no longer needed, with the reason.", writes=True,
      task=P("string", "task id", True), reason=P("string", "why", True))
def cancel(rec, task, reason):
    tasks.cancel(rec, task, reason)
    return {"task": task, "state": "cancelled"}


@tool("remove", "Remove a graph node (id) or an edge (src, type, dst). The removal is recorded; history is kept.",
      writes=True, id=P("string", "node id"), src=P("string", "edge source"), type=P("string", "edge type"),
      dst=P("string", "edge target"))
def remove(rec, id=None, src=None, type=None, dst=None):
    if id and not (src or type or dst):
        rec.delete_node(id)
        return {"removed": id}
    if src and type and dst and not id:
        rec.delete_edge(src, type, dst)
        return {"removed": {"src": src, "type": type, "dst": dst}}
    raise ValueError("give a node id, or an edge's src, type and dst")


@tool("add_item", "Add an immutable item. Returns its hash; the same content is the same item.", writes=True,
      item=P("object", "kind (choice|numeric|free), prompt, options+answer | answer+tolerance | rubric, explanation, "
                       "hints, concepts, difficulty, supersedes", True))
def add_item(rec, item):
    problems = validate_item(item)
    for c in item.get("concepts", []):
        if isinstance(c, str) and ":" not in c:  # a lesson finds an item by the node id it tests
            problems.append(f"concept {c!r} is not a node id; use <type>:<key>, e.g. capability:{c}")
    if "defence" in item:  # an item that defends a claim: the kind is fixed, and it names the claim and a rubric
        if item["defence"] not in research.DEFENCE:
            problems.append(f"defence is one of {', '.join(research.DEFENCE)}")
        if item.get("kind") != "free" or not (item.get("rubric") or {}).get("criteria"):
            problems.append("a defence item is a free item with a rubric of criteria")
        if not any(str(c).startswith("claim:") for c in item.get("concepts", [])):
            problems.append('a defence item lists its claim in concepts, e.g. ["claim:width"]')
    if problems:
        raise ValueError("; ".join(problems))
    return {"id": rec.put_item(item)}


@tool("add_node", "Add or update a graph node.", writes=True, id=P("string", "<type>:<key>", True),
      type=P("string", "node type", True), data=P("object", "fields"))
def add_node(rec, id, type, data=None):
    return graph.add_node(rec, id, type, data)


@tool("add_edge", "Add a typed edge between nodes.", writes=True, src=P("string", "source id", True),
      type=P("string", "edge type", True), dst=P("string", "target id", True), data=P("object", "fields"))
def add_edge(rec, src, type, dst, data=None):
    return graph.add_edge(rec, src, type, dst, data)


@tool("import", "Import old files into this record (idempotent).", writes=True,
      kind=P("string", "what to import", True, tuple(importers.IMPORTERS)),
      path=P("string", "folder (or graph.json for graphify)", True),
      evidence=P("string", "EvidenceAtom folder for research"), repo=P("string", "repository root for graphify"),
      project=P("string", "documents: the project id, project:<key>, they are about"))
def import_(rec, kind, path, evidence=None, repo=None, project=None):
    if not Path(path).expanduser().exists():
        raise ValueError(f"no such path: {path}")
    return importers.IMPORTERS[kind](rec, path, evidence=evidence, repo=repo, project=project)


@tool("export", "Write this record's notes into an Obsidian vault (the same as vault_set + vault_sync), or a "
      "read-only single-file HTML snapshot.",
      writes=True, kind=P("string", "what to write", True, ("obsidian", "static")),
      path=P("string", "the vault folder (obsidian) or the HTML file (static)", True),
      folder=P("string", "folder inside the vault (default Research OS)"))
def export_(rec, kind, path, folder=None):
    if kind == "obsidian":
        vault.set_vault(path, folder)
        return vault.sync(rec)
    return {"written": str(export.static(rec, path))}


@tool("migrate", "Import a whole vault (notes, sessions, research records) and check every answer arrived.",
      writes=True, vault=P("string", "the vault folder", True),
      research_root=P("string", "where research records live, if not in the vault"),
      evidence=P("string", "EvidenceAtom folder"), graphify=P("string", "a Graphify graph.json"))
def migrate(rec, vault, research_root=None, evidence=None, graphify=None):
    return importers.migrate(rec, vault, research_root, evidence, graphify)


@tool("rebuild", "Drop and rebuild the index from the record's files.", writes=True)
def rebuild(rec):
    rec.rebuild()
    return {"rebuilt": True, "problems": rec.problems}
