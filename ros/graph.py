"""Queries over a record's graph and evidence: prerequisites, readiness, frontier, due reviews, claim support, code.

Conventions the importers and writers follow (see ``ros.store`` for the files themselves):

* A capability is a node ``capability:<learning_id>`` with ``title``, ``schema`` (1, 2 or 3), ``retention_target``,
  ``initial_state`` and, for schema 2 and 3, ``learning_scope`` and ``required_dimensions``.
* ``A --requires--> B`` means A cannot be ready before B is. Membership in a course, goal, project, subject, domain
  or block is ``capability --part-of--> <scope>``; the concept a capability is about is ``capability --about--> concept``.
* Evidence of retrieval is a ``retrieval`` event whose subject is the capability, with ``day``, ``period``, ``timing``,
  ``method``, ``outcome``, ``assistance``, ``evidence``, ``review`` and, for schema 2 and 3, ``scope``,
  ``dimension`` and ``context``. Answers to items are ``attempt`` events; they feed the tutor, not this file.
* Claim support is ``X --supports--> claim`` or ``X --invalidates--> claim``. Code is ``code-symbol:<path> --implements-->
  <node>``; symbols imported from Graphify are ``code-symbol:<path>#<label> --part-of--> code-symbol:<path>``.

The readiness rules are those of ``scripts/knowledge.py`` (schema 1 to 3), kept identical so the two agree on the
same history until the old runtime is retired. Everything here only reads; nothing writes except ``import_graphify``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path

from .store import Record

RECONSTRUCTION = {"explanation", "derivation", "transfer", "computation"}
SCOPES = ("conceptual", "project_application", "transfer")
DIMENSIONS = ("recognition", "explanation", "derivation", "transfer", "application")
LITERACY_DIMENSIONS = ("method_understanding", "tool_operation", "implementation_navigation")
STATE_ORDER = ("unknown", "learning", "fragile", "stale", "demonstrated", "retained")
SCOPE_TYPES = {"course", "goal", "project", "subject", "domain", "block"}


@dataclass
class Assessment:
    state: str
    first: date | None = None
    last: date | None = None
    review: date | None = None
    evidence: str = ""

    def as_dict(self, as_of: date) -> dict:
        return {"state": self.state, "first_learned": _iso(self.first), "last_retrieval": _iso(self.last),
                "next_review": _iso(self.review), "evidence": self.evidence,
                "freshness": ("unknown" if self.review is None else "overdue" if as_of > self.review
                              else "due" if as_of == self.review else "scheduled")}


# ---- evidence to state --------------------------------------------------------------------------------------------
def assess(rows: list[dict], initial: str, as_of: date, recognition: bool = False) -> Assessment:
    """Reduce retrieval rows (in time order) to a state. Same rules as ``knowledge.assess``."""
    result = Assessment("learning" if initial == "learning" else "unknown")
    periods: dict[str, date] = {}
    latest_reconstruction: date | None = None
    for row in rows:
        day = _day(row["day"])
        if day > as_of:
            break
        result.last = day
        qualifies = (recognition or row.get("method") in RECONSTRUCTION) and row.get("assistance") == "none"
        if row.get("outcome") == "pass" and qualifies:
            prior = periods.get(row.get("period"))
            delayed = (not recognition and row.get("timing") == "delayed" and prior is not None and prior < day
                       and latest_reconstruction is not None and latest_reconstruction < day)
            if (result.state == "retained" and row.get("timing") == "delayed"
                    and prior == day and latest_reconstruction == day):
                # Another check the same day keeps the delayed evidence but cannot extend its horizon.
                continue
            result.state = "retained" if delayed else "demonstrated"
            result.first = result.first or day
            periods[row.get("period")] = day
            latest_reconstruction = day
            result.review, result.evidence = _day(row.get("review")), row.get("evidence", "")
        elif row.get("outcome") != "pass" or row.get("assistance") != "none":
            result.state = "fragile" if result.first else "learning"
            periods.clear()
            result.review, result.evidence = _day(row.get("review")), row.get("evidence", "")
        # Recognition-only success neither promotes the state nor renews freshness.
    return result


def profile(states: dict[str, Assessment], required: list[str]) -> Assessment:
    """The weakest of the required dimensions: a conservative readiness summary, not total mastery."""
    parts = [states[d] for d in required]
    firsts = [a.first for a in parts if a.first]
    lasts = [a.last for a in parts if a.last]
    return Assessment(min((a.state for a in parts), key=STATE_ORDER.index),
                      max(firsts) if len(firsts) == len(parts) else None, max(lasts) if lasts else None,
                      min(a.review for a in parts) if all(a.review for a in parts) else None,
                      "; ".join(a.evidence for a in parts if a.evidence))


def dimensions(rows: list[dict], schema: int, as_of: date) -> dict[str, dict[str, Assessment]]:
    out: dict[str, dict[str, Assessment]] = {}
    for scope in SCOPES:
        out[scope] = {}
        for dim in DIMENSIONS + (LITERACY_DIMENSIONS if schema == 3 else ()):
            sel = [r for r in rows if r.get("scope") == scope and r.get("dimension") == dim]
            dated = [r for r in sel if _day(r["day"]) <= as_of]
            if schema == 3 and scope == "project_application" and dated:
                # Different contexts cannot form one delayed retention chain.
                by_context = {c: assess([r for r in dated if r.get("context", "") == c], "unknown", as_of,
                                        recognition=dim == "recognition")
                              for c in {r.get("context", "") for r in dated}}
                a = profile(by_context, sorted(by_context))
            else:
                a = assess(sel, "unknown", as_of, recognition=dim == "recognition")
            _stale(a, as_of)
            out[scope][dim] = a
    return out


# ---- the learning view --------------------------------------------------------------------------------------------
@dataclass
class Capability:
    id: str
    node: dict
    prerequisites: list[str]
    rows: list[dict]
    assessment: Assessment
    mastery: dict[str, dict[str, Assessment]]

    @property
    def ready(self) -> bool:
        if self.node.get("issues"):
            return False
        if self.mastery:
            required = self.node.get("required_dimensions") or []
            scope = self.mastery[self.node["learning_scope"]]
            return any(d != "recognition" for d in required) and all(
                scope[d].state in {"demonstrated", "retained"} and scope[d].review is not None for d in required)
        return self.assessment.state in {"demonstrated", "retained"} and self.assessment.review is not None


class Learning:
    """Every capability in a record, assessed as of one day. Build once per query; it reads the index once."""

    def __init__(self, rec: Record, as_of: date | None = None):
        self.as_of = as_of or date.today()
        retrievals: dict[str, list[dict]] = {}
        for ev in rec.events(type="retrieval"):
            retrievals.setdefault(ev["subject"], []).append(ev["data"])
        requires: dict[str, list[str]] = {}
        for e in rec.edges(type="requires"):
            requires.setdefault(e["src"], []).append(e["dst"])
        self.members: dict[str, set[str]] = {}
        for e in rec.edges(type="part-of") + rec.edges(type="about"):
            self.members.setdefault(e["dst"], set()).add(e["src"])
        self.caps: dict[str, Capability] = {}
        for n in rec.nodes(type="capability"):
            rows = sorted(retrievals.get(n["id"], []), key=lambda r: r["day"])  # stable: same-day rows keep log order
            schema = n.get("schema", 1)
            mastery = dimensions(rows, schema, self.as_of) if schema in (2, 3) else {}
            if mastery:
                a = profile(mastery[n["learning_scope"]], n.get("required_dimensions") or [])
            else:
                a = assess(rows, n.get("initial_state", "unknown"), self.as_of)
            _stale(a, self.as_of)
            self.caps[n["id"]] = Capability(n["id"], n, sorted(requires.get(n["id"], [])), rows, a, mastery)
        self.ready = self._ready()

    def _ready(self) -> set[str]:
        """Ready means valid evidence here and throughout the prerequisite ancestry."""
        ready: set[str] = set()
        while True:
            more = {k for k, c in self.caps.items() if k not in ready and c.ready and set(c.prerequisites) <= ready}
            if not more:
                return ready
            ready |= more

    def closure(self, ids) -> set[str]:
        """The given capabilities and everything they transitively require."""
        out, todo = set(ids), list(ids)
        while todo:
            cap = self.caps.get(todo.pop())
            for p in cap.prerequisites if cap else ():
                if p in self.caps and p not in out:
                    out.add(p)
                    todo.append(p)
        return out

    def select(self, scope: str) -> tuple[set[str], set[str]]:
        """(capabilities in scope, those plus their prerequisite closure). ``scope`` is any node id: a capability
        selects itself; a course, goal, project, subject, domain, block or concept selects its members."""
        primary = {scope} & self.caps.keys() if scope.startswith("capability:") else \
            self.members.get(scope, set()) & self.caps.keys()
        return primary, self.closure(primary)

    def is_frontier(self, key: str) -> bool:
        c = self.caps[key]
        return (not c.node.get("issues") and set(c.prerequisites) <= self.ready
                and not (c.assessment.state == "retained" and key in self.ready))

    def frontier(self, scope: str | None = None) -> list[str]:
        keys = self.select(scope)[1] if scope else self.caps.keys()
        return sorted(k for k in keys if self.is_frontier(k))

    def blocked_by(self, key: str) -> list[str]:
        return sorted(set(self.caps[key].prerequisites) - self.ready)

    def due(self, scope: str | None = None) -> list[dict]:
        """Capabilities whose recorded next review is today or past, oldest first. Reference targets are left out:
        they carry no routine review."""
        keys = self.select(scope)[1] if scope else self.caps.keys()
        out = []
        for k in keys:
            c = self.caps[k]
            if c.assessment.review and c.assessment.review <= self.as_of \
                    and c.node.get("retention_target") != "reference":
                out.append({"id": k, "next_review": _iso(c.assessment.review), "state": c.assessment.state})
        return sorted(out, key=lambda d: (d["next_review"], d["id"]))

    def view(self, key: str) -> dict:
        c = self.caps[key]
        out = {"id": key, "title": c.node.get("title", key), "prerequisites": c.prerequisites,
               "retention_target": c.node.get("retention_target", "unspecified"),
               **c.assessment.as_dict(self.as_of), "ready": key in self.ready, "frontier": self.is_frontier(key),
               "blocked_by": self.blocked_by(key), "diagnostics": sorted(c.node.get("issues") or [])}
        if c.mastery:
            out["mastery"] = {s: {d: a.as_dict(self.as_of) for d, a in dims.items()} for s, dims in c.mastery.items()}
        return out


# ---- research ----------------------------------------------------------------------------------------------------
def support(rec: Record, node: str) -> dict:
    """What supports or invalidates a node, with each source's current node data when it has one."""
    out = {}
    for rel in ("supports", "invalidates"):
        out[rel] = [{"id": e["src"], "node": rec.node(e["src"]), **{k: v for k, v in e.items()
                                                                   if k not in ("src", "type", "dst")}}
                    for e in rec.edges(type=rel, dst=node)]
    return out


def code_links(rec: Record, node: str) -> list[dict]:
    """Code that implements a node, each with the Graphify symbols imported for that file."""
    out = []
    for e in rec.edges(type="implements", dst=node):
        path = e["src"].split(":", 1)[1].split("#", 1)[0]
        symbols = sorted(s["src"].split("#", 1)[1] for s in rec.edges(type="part-of", dst=e["src"]) if "#" in s["src"])
        out.append({"path": path, "exists": (rec.node(e["src"]) or {}).get("exists"), "symbols": symbols})
    return out


def import_graphify(rec: Record, graph_json: Path | str, repo_root: Path | str | None = None) -> int:
    """Add Graphify's symbols as ``code-symbol`` nodes, each part of its file's node. Paths are made relative to
    ``repo_root`` when they lie under it. Import edges and call edges are not imported: they say nothing about
    claims. Returns the number of symbols imported; an unreadable file imports nothing and raises ``ValueError``."""
    try:
        data = json.loads(Path(graph_json).read_text(encoding="utf-8"))
        raw = data.get("nodes", [])
    except (OSError, ValueError, AttributeError) as exc:
        raise ValueError(f"unreadable Graphify graph {graph_json}: {exc}") from exc
    base = str(Path(repo_root).resolve()).replace("\\", "/").rstrip("/") + "/" if repo_root else None
    nodes, edges = {}, set()
    for n in raw:
        if not (isinstance(n, dict) and isinstance(n.get("source_file"), str)):
            continue
        path = n["source_file"].replace("\\", "/")
        if base and path.startswith(base):
            path = path[len(base):]
        label = str(n.get("label", n.get("id", "")))
        file_id, sym_id = f"code-symbol:{path}", f"code-symbol:{path}#{label}"
        nodes.setdefault(file_id, {"id": file_id, "type": "code-symbol", "file": path})
        nodes[sym_id] = {"id": sym_id, "type": "code-symbol", "file": path, "graphify": str(n.get("id", ""))}
        edges.add((sym_id, file_id))
    rec.put_nodes(list(nodes.values()))
    rec.put_edges([{"src": s, "type": "part-of", "dst": d} for s, d in sorted(edges)])
    return len(edges)


def history(rec: Record, lesson: str | None = None, item: str | None = None) -> list[dict]:
    """Every answer, oldest first, with the question it answered and the tutor's latest grade of it (or ``None``
    while ungraded). A question that was later edited is shown as it was when answered."""
    grades: dict[str, dict] = {}
    for g in rec.events(type="grade"):
        if g["data"].get("attempt"):
            grades[g["data"]["attempt"]] = g
    out = []
    for a in rec.events(type="attempt"):
        if lesson and a["data"].get("lesson") != lesson:
            continue
        if item and rec.current_item(a["subject"]) != rec.current_item(item):
            continue
        q = rec.item(a["subject"]) or {}
        g = grades.get(a["id"])
        out.append({"id": a["id"], "ts": a["ts"], "lesson": a["data"].get("lesson"), "item": a["subject"],
                    "prompt": q.get("prompt"), "kind": q.get("kind"), "response": a["data"].get("response"),
                    "grade": g["data"].get("verdict") if g else None,
                    "feedback": g["data"].get("feedback") if g else None})
    return out


def research_frontier(rec: Record) -> list[dict]:
    """The next mechanical transition of each research record: what a person or agent must do next, unranked. Same
    rules as ``research.frontier``. A record with an error diagnostic needs repair before anything else."""
    nodes = {n["id"]: n for t in ("question", "hypothesis", "experiment", "decision") for n in rec.nodes(type=t)}
    rel: dict[str, list[tuple[str, str]]] = {}
    for e in rec.edges():
        if e["src"] in nodes and e["dst"] in nodes and e.get("relation"):
            rel.setdefault(e["relation"], []).append((e["src"], e["dst"]))

    def bad(n):
        return any(d["severity"] == "ERROR" for d in n.get("diagnostics", []))

    accepted = {k for k, n in nodes.items() if n["type"] == "decision" and n["status"] == "accepted" and not bad(n)}
    decided = {d for s, d in rel.get("experiments", []) if s in accepted}
    out = []
    for key, n in sorted(nodes.items(), key=lambda kv: kv[0].split(":", 1)[1]):
        t, status, todo = n["type"], n["status"], []
        if bad(n):
            todo.append("repair-record")
        elif t == "question" and status in {"proposed", "active", "blocked"}:
            if status == "blocked":
                unresolved = [d for s, d in rel.get("parent_questions", []) if s == key and nodes[d]["status"] != "resolved"]
                if unresolved or any(e["relation"] == "learning_dependencies" for e in rec.edges(src=key, type="requires")):
                    todo.append("inspect-unresolved-dependencies")
            if not any(d == key and nodes[s]["type"] == "hypothesis" for s, d in rel.get("research_questions", [])):
                todo.append("hypothesis-missing")
        elif t == "hypothesis" and status in {"proposed", "active", "survives", "weakened", "inconclusive"}:
            if not any(d == key and nodes[s]["type"] == "experiment" for s, d in rel.get("hypotheses", [])):
                todo.append("experiment-missing")
        elif t == "experiment":
            if status in {"planned", "ready"}:
                todo += {"awaiting": ["approval-required"], "approved": ["execution-available"],
                         "modification-requested": ["plan-revision-required"], "rejected": []}[n["authorization"]]
            elif status == "completed":
                validation, review = n.get("result_validation", "pending"), n.get("adversarial_review", "pending")
                todo.append("validation-required" if validation == "pending" else
                            "validation-revision-required" if validation == "failed" else
                            "adversarial-review-required" if review == "pending" else
                            "review-revision-required" if review == "failed" else
                            "human-decision-required" if key not in decided else "")
        elif t == "decision" and status in {"proposed", "revisit"}:
            todo.append("human-decision-required")
        out += [{"id": key, "transition": x} for x in sorted(todo) if x]
    return out


# ---- helpers ------------------------------------------------------------------------------------------------------
def _stale(a: Assessment, as_of: date) -> None:
    # Stale is a dated view of a positive state, never its replacement in the record.
    if a.state in {"demonstrated", "retained"} and a.review and as_of > a.review:
        a.state = "stale"


def _day(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None
