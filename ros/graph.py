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

The readiness rules are those of ``ros.lib.knowledge`` (schema 1 to 3), kept identical so the two agree on the
same history until the old runtime is retired. Everything here only reads; nothing writes except ``import_graphify`` and
the agents' knowledge notes (``note_add``, ``note_revise``, ``note_retract``; see the end of this file).
"""
from __future__ import annotations

from array import array
from dataclasses import dataclass
from datetime import date
import json
import hashlib
import re
from pathlib import Path

from . import home
from .store import Record, event_id, make_event

RECONSTRUCTION = {"explanation", "derivation", "transfer", "computation"}
SCOPES = ("conceptual", "project_application", "transfer")
DIMENSIONS = ("recognition", "explanation", "derivation", "transfer", "application")
LITERACY_DIMENSIONS = ("method_understanding", "tool_operation", "implementation_navigation")
STATE_ORDER = ("unknown", "learning", "fragile", "stale", "demonstrated", "retained")


def capability_reference(rec: Record, capability: str) -> dict:
    """A real node-content revision, distinct from its human display alias."""
    node = rec.node(capability)
    if not node or node.get('type') != 'capability':
        raise KeyError('no such capability')
    revision = hashlib.sha256(json.dumps(node, sort_keys=True, separators=(',', ':'),
                                        ensure_ascii=False).encode()).hexdigest()
    return {'owner_record': rec.root.name, 'entity_id': capability, 'revision': revision}


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


def _assess(node: dict, rows: list[dict], as_of: date) -> tuple[Assessment, dict]:
    schema = node.get("schema", 1)
    mastery = dimensions(rows, schema, as_of) if schema in (2, 3) else {}
    if mastery:
        a = profile(mastery[node["learning_scope"]], node.get("required_dimensions") or [])
    else:
        a = assess(rows, node.get("initial_state", "unknown"), as_of)
    _stale(a, as_of)
    return a, mastery


class Structure:
    """The ``requires`` graph of a record as compact arrays: ids are interned to ints and each direction is a CSR (an
    offsets array and a flat array of neighbours), so a record with 10^5 capabilities and 10^6 edges costs megabytes,
    not hundreds of them, and a walk touches only the nodes it reaches."""
    __slots__ = ("names", "index", "_po", "_pe", "_do", "_de")

    def __init__(self, pairs):
        index: dict[str, int] = {}
        names: list[str] = []
        src, dst = array("i"), array("i")
        for a, b in pairs:
            for x in (a, b):
                if x not in index:
                    index[x] = len(names)
                    names.append(x)
            src.append(index[a])
            dst.append(index[b])
        self.names, self.index = names, index
        self._po, self._pe = _csr(len(names), src, dst)  # a requires b: b is among a's prerequisites
        self._do, self._de = _csr(len(names), dst, src)  # ... and a is among b's dependents

    def prerequisites(self, key: str) -> list[str]:
        i = self.index.get(key)
        return [] if i is None else sorted(self.names[j] for j in self._pe[self._po[i]:self._po[i + 1]])

    def dependents(self, key: str) -> list[str]:
        i = self.index.get(key)
        return [] if i is None else sorted(self.names[j] for j in self._de[self._do[i]:self._do[i + 1]])

    def ancestors(self, keys) -> set[str]:
        """The given ids and everything they transitively require, in time linear in what is reached."""
        seen = bytearray(len(self.names))
        todo = [self.index[k] for k in keys if k in self.index]
        for i in todo:
            seen[i] = 1
        out = set(keys)
        while todo:
            i = todo.pop()
            out.add(self.names[i])
            for j in self._pe[self._po[i]:self._po[i + 1]]:
                if not seen[j]:
                    seen[j] = 1
                    todo.append(j)
        return out


def _csr(n: int, src: array, dst: array) -> tuple[array, array]:
    offsets = [0] * (n + 1)
    for a in src:
        offsets[a + 1] += 1
    for i in range(n):
        offsets[i + 1] += offsets[i]
    fill, flat = list(offsets), array("i", bytes(4 * len(src)))
    for a, b in zip(src, dst):
        flat[fill[a]] = b
        fill[a] += 1
    return array("i", offsets), flat


_STRUCTURES: dict = {}


def structure(rec: Record) -> Structure:
    """The record's ``requires`` graph, built once per state of its edge log. It is keyed to ``rec.stamp("edges")``, not
    to the index generation, so answers and grades (events) never throw it away, and a write to the graph does."""
    key = rec.stamp("edges")
    root = str(rec.root.resolve())
    hit = _STRUCTURES.get(root)
    if hit and hit[0] == key:
        return hit[1]
    built = Structure((r["src"], r["dst"]) for r in rec.index().execute(
        "SELECT src, dst FROM edges WHERE type='requires'"))
    if len(_STRUCTURES) >= 16:
        _STRUCTURES.pop(next(iter(_STRUCTURES)))
    _STRUCTURES[root] = (key, built)
    return built


class Learning:
    """The capabilities of a record, assessed as of one day. Build once per query; it reads the index once.

    ``within`` limits it to those capabilities and everything they require (a downward-closed set, so readiness there
    is the same as in the whole record) and assesses only those: the cost follows the question, not the record."""

    def __init__(self, rec: Record, as_of: date | None = None, within=None):
        self.as_of = as_of or date.today()
        from .learn import evidence
        ev, kinds = evidence.of(rec), evidence.kinds(rec)
        self._rec, self._members = rec, None
        self.structure = structure(rec)
        if within is None:
            nodes = rec.nodes(type="capability")
        else:
            nodes = [n for n in rec.nodes_in(self.structure.ancestors(within)) if n["type"] == "capability"]
        self.caps: dict[str, Capability] = {}
        for n in nodes:
            rows = ev.rows(n["id"], kinds)
            a, mastery = ev.assessed(n["id"], self.as_of, n, lambda: _assess(n, rows, self.as_of))
            self.caps[n["id"]] = Capability(n["id"], n, self.structure.prerequisites(n["id"]), rows, a, mastery)
        self.ready = self._ready()

    @property
    def members(self) -> dict[str, set[str]]:
        """Hub (course, goal, project, subject, domain, block, concept) -> the capabilities that belong to it. Read
        from the edges when first asked for: most queries never need it."""
        if self._members is None:
            self._members = {}
            for e in self._rec.edges(type="part-of") + self._rec.edges(type="about"):
                self._members.setdefault(e["dst"], set()).add(e["src"])
        return self._members

    def _ready(self) -> set[str]:
        """Ready means valid evidence here and throughout the prerequisite ancestry. One pass over the edges: a
        capability becomes ready when its last prerequisite does; a cycle, or a prerequisite that is missing or not
        itself valid, leaves it waiting for good."""
        waiting: dict[str, int] = {}
        dependents: dict[str, list[str]] = {}
        for k, c in self.caps.items():
            if c.ready:
                waiting[k] = len(c.prerequisites)
                for p in c.prerequisites:
                    dependents.setdefault(p, []).append(k)
        ready: set[str] = set()
        todo = [k for k, w in waiting.items() if w == 0]
        while todo:
            k = todo.pop()
            ready.add(k)
            for d in dependents.get(k, ()):
                waiting[d] -= 1
                if waiting[d] == 0:
                    todo.append(d)
        return ready

    def order(self, keys) -> list[str]:
        """``keys`` with every capability after its prerequisites (roots first), ties by id. Capabilities in a cycle,
        and those that wait on one, come last in id order."""
        keys = set(keys)
        waiting = {k: 0 for k in keys}
        dependents: dict[str, list[str]] = {}
        for k in keys:
            for p in set(self.caps[k].prerequisites):
                if p in keys:
                    waiting[k] += 1
                    dependents.setdefault(p, []).append(k)
        level = dict.fromkeys(keys, 0)
        todo = [k for k, w in waiting.items() if w == 0]
        placed: list[str] = []
        while todo:
            k = todo.pop()
            placed.append(k)
            for d in dependents.get(k, ()):
                level[d] = max(level[d], level[k] + 1)
                waiting[d] -= 1
                if waiting[d] == 0:
                    todo.append(d)
        return sorted(placed, key=lambda k: (level[k], k)) + sorted(keys - set(placed))

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


# ---- editing the graph by hand -----------------------------------------------------------------------------------
def plan_revision(node):
    ignored={'authorization','approved_revision','authorized_by','authorized_at','status'}
    return hashlib.sha256(json.dumps({k:v for k,v in node.items() if k not in ignored},sort_keys=True).encode()).hexdigest()

def add_node(rec: Record, id: str, type: str, data: dict | None = None) -> dict:
    """Add or update a node; only human approval may authorize an experiment."""
    data = dict(data or {})
    existing = rec.node(id) or {}
    if type == 'experiment':
        proposed=data
        data={**{k:v for k,v in existing.items() if k not in ('id','type')},**proposed}
        if data.get('authorization') == 'approved' and existing.get('authorization') != 'approved':
            raise ValueError('Only the researcher can approve an experiment through approve')
        if existing.get('authorization') == 'approved' and any(existing.get(k) != v for k,v in data.items() if k not in ('authorization','status')):
            data['authorization'] = 'awaiting'
    prefix, _, key = id.partition(":")
    if not key.strip() or prefix != type:
        raise ValueError(f"a {type} node's id is '{type}:<key>', not {id!r}")
    rec.put_node(id, type, **(data or {}))
    return rec.node(id)


def add_edge(rec: Record, src: str, type: str, dst: str, data: dict | None = None) -> dict:
    """Add a typed edge. An edge from a node to itself, or a ``requires`` edge that closes a loop, would make
    a capability its own prerequisite and so never ready; both are refused."""
    if src == dst:
        raise ValueError(f"{src} cannot {type} itself")
    for end in (src, dst):
        if rec.node(end) is None:
            raise ValueError(f"no node {end}: add it (add_node) before linking it")
    if type == "requires":
        seen, todo = set(), [dst]
        while todo:
            cur = todo.pop()
            if cur == src:
                raise ValueError(f"{src} requires {dst} would make a loop: {dst} already requires {src}")
            if cur not in seen:
                seen.add(cur)
                todo += [e["dst"] for e in rec.edges(src=cur, type="requires")]
    rec.put_edge(src, type, dst, **(data or {}))
    return {"src": src, "type": type, "dst": dst}


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


def history(rec: Record, lesson: str | None = None, item: str | None = None, limit: int | None = None) -> list[dict]:
    """Answers, oldest first (the newest ``limit`` of them when given), each with the question it answered and the
    tutor's latest grade of it (``None`` while ungraded). A question later edited is shown as it was answered."""
    current = rec.current_items()
    if item:
        wanted = current.get(item, item)
        versions = [h for h, cur in current.items() if cur == wanted] or [item]
        attempts = [a for h in versions for a in rec.events(type="attempt", subject=h, lesson=lesson)]
        attempts.sort(key=lambda a: a["ts"])
        attempts = attempts[-limit:] if limit else attempts
    else:
        attempts = rec.events(type="attempt", lesson=lesson, limit=limit)
    if not attempts:
        return []
    wanted = {a["id"] for a in attempts}
    grades: dict[str, dict] = {}
    for g in rec.events(type="grade", since=min(a["ts"] for a in attempts)):  # a grade never precedes its answer
        if g["data"].get("attempt") in wanted:
            grades[g["data"]["attempt"]] = g
    items = rec.items_by_id()
    out = []
    for a in attempts:
        q = items.get(a["subject"], {})
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

    accepted = {k for k, n in nodes.items() if n["type"] == "decision" and n.get("status") == "accepted" and not bad(n)}
    decided = {d for s, d in rel.get("experiments", []) if s in accepted}
    out = []
    for key, n in sorted(nodes.items(), key=lambda kv: kv[0].split(":", 1)[-1]):
        t, status, todo = n["type"], n.get("status", "proposed"), []
        if bad(n):
            todo.append("repair-record")
        elif t == "question" and status in {"proposed", "active", "blocked"}:
            if status == "blocked":
                unresolved = [d for s, d in rel.get("parent_questions", []) if s == key and nodes[d].get("status") != "resolved"]
                if unresolved or any(e["relation"] == "learning_dependencies" for e in rec.edges(src=key, type="requires")):
                    todo.append("inspect-unresolved-dependencies")
            if not any(d == key and nodes[s]["type"] == "hypothesis" for s, d in rel.get("research_questions", [])):
                todo.append("hypothesis-missing")
        elif t == "hypothesis" and status in {"proposed", "active", "survives", "weakened", "inconclusive"}:
            if not any(d == key and nodes[s]["type"] == "experiment" for s, d in rel.get("hypotheses", [])):
                todo.append("experiment-missing")
        elif t == "experiment":
            if status in {"planned", "ready"}:
                authorization=n.get('authorization','awaiting')
                if n.get('approved_revision') and n['approved_revision'] != plan_revision(n): authorization='awaiting'
                todo += {"awaiting": ["approval-required"], "approved": ["execution-available"],
                         "modification-requested": ["plan-revision-required"], "rejected": []}.get(authorization, [])
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


# ---- the living knowledge graph ----------------------------------------------------------------------------------
# A view built on every read from what the record already says (work, assessed learning evidence, goals, sources, claims)
# plus the notes agents keep about what the person is learning. Nothing here is stored as a derived copy. The notes are
# events only (``graph.note.added``, ``.revised``, ``.retracted``): they are not nodes or edges of the record, so they
# can never change what the evidence says. A note may CITE a learning event; it can never create one, grade, decide or
# approve. The callers (``ros.tools.graph``) open the records and hand them in as ``recs``, a name -> Record mapping.
NOTE_KINDS = ("concept", "prerequisite", "misconception", "goal")
NOTE_LINKS = ("about", "requires", "prerequisite-for", "misconception-of", "aims-at", "relates")
NOTE_EVENTS = ("graph.note.added", "graph.note.revised", "graph.note.retracted")
NOT_AGENTS = {"person", "learner", "human", "user", "researcher", "system", "student", "me"}
WORK_KINDS = {"conversation", "lesson", "handout", "source", "paper", "material", "connection", "question", "hypothesis",
              "experiment", "claim", "decision", "change", "visual"}
MAX_NODES = 1000


def notes(rec: Record) -> dict:
    """Every note of a record as it stands now (retracted ones marked), folded incrementally from its events. The
    returned dict is the fold's own state: read it, copy what you keep, never change it."""
    def step(state, ev):
        d, t, n = ev["data"], ev["type"], ev["subject"]
        if t == "graph.note.added":
            state[n] = {"id": n, "kind": d["kind"], "title": d["title"], "text": d["text"], "links": d.get("links", []),
                        "workspace_id": d["workspace_id"], "revision": 1, "added_by": ev["actor"], "added_at": ev["ts"],
                        "updated_by": ev["actor"], "updated_at": ev["ts"], "retracted": None,
                        "cites": list(d["prompted_by"]["evidence"]), "work": list(d["prompted_by"]["work"]),
                        "events": [ev["id"]], "reason": d.get("reason", "")}
            return
        note = state.get(n)
        if note is None or note["retracted"]:
            return
        note["revision"] += 1
        note["updated_by"], note["updated_at"] = ev["actor"], ev["ts"]
        note["events"].append(ev["id"])
        for key, into in (("evidence", "cites"), ("work", "work")):
            note[into] += [x for x in d["prompted_by"][key] if x not in note[into]]
        if t == "graph.note.revised":
            for key in ("title", "text", "links"):
                if key in d:
                    note[key] = d[key]
        else:
            note["retracted"] = {"by": ev["actor"], "at": ev["ts"], "reason": d.get("reason", ""), "event": ev["id"]}
    return rec.fold("graph.notes.v1", NOTE_EVENTS, dict, step)


def note_recorded(recs: dict, key: str) -> bool:
    """Whether a note with this idempotency key was ever written (added, and maybe since revised or retracted) in any of these
    records: the same test the graph upkeep uses, so coverage and upkeep never disagree."""
    for name, rec in recs.items():
        if "note:" + hashlib.sha256(f"{name}|{key}".encode()).hexdigest()[:20] in notes(rec):
            return True
    return False


def dead_workspaces(recs: dict) -> tuple[set, set]:
    """(logical workspace ids, hub ids) of workspaces the person deleted that belonged to these records. A deleted workspace
    stays on disk and could be restored, so it is read from its folder's config, never from the lists it has left."""
    live_ids = {home.workspace_id(r.root) for r in recs.values()}
    live_hubs = {home.config(r.root).get("project") for r in recs.values()}
    users = {n for n, r in recs.items() if home.config(r.root).get("role") == "user"} | {
        home.config(r.root).get("user") for r in recs.values()}
    ids, hubs = set(), set()
    for name in home.projects(deleted=True):
        root = home.home() / "projects" / name
        cfg = home.config(root)
        wid = home.workspace_id(root)
        if wid in live_ids or (cfg.get("role") == "project" and cfg.get("user") not in users):
            continue
        ids.add(wid)
        if cfg.get("role") == "project" and cfg.get("project") and cfg["project"] not in live_hubs:
            hubs.add(cfg["project"])
    return ids, hubs


def _clip(value, what: str, low: int, high: int) -> str:
    if not isinstance(value, str) or not low <= len(value.strip()) <= high or any(
            ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError(f"{what} must be text of {low} to {high} characters")
    return value.strip()


def _ids(values, what: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list) or len(values) > 20 or not all(isinstance(v, str) and 0 < len(v) <= 500 for v in values):
        raise ValueError(f"{what} is a list of at most 20 ids")
    return list(dict.fromkeys(values))


def _agent(by) -> str:
    if not isinstance(by, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}", by.strip()) \
            or by.strip().casefold() in NOT_AGENTS:
        raise ValueError("by names the agent that maintains the graph (letters, digits, dot, dash); a person, learner or "
                         "system cannot be named: this is an agent's note, not a human act")
    return "agent:" + by.strip()


def find_node(recs: dict, ident: str, hidden=None, dead_hubs=(), prefer: str | None = None):
    """(owner record name, node) for an id or ``owner::id``; none for what is missing, hidden or a deleted workspace's hub."""
    owner, _, entity = ident.rpartition("::") if "::" in ident else (None, "", ident)
    if entity in dead_hubs:
        return None
    for name in ([owner] if owner else sorted(recs, key=lambda n: (n != prefer, n))):
        rec = recs.get(name)
        node = rec.node(entity) if rec else None
        if node and not (hidden and hidden(name, entity)):
            return name, node
    return None


def _prompted(recs: dict, work, evidence, hidden, dead_hubs) -> dict:
    work, evidence = _ids(work, "work"), _ids(evidence, "evidence")
    if not work and not evidence:
        raise ValueError("say what prompted this: the work (work) or the learning evidence (evidence) it came from")
    from .learn import evidence as ev_types
    out_work, out_evidence = [], []
    for ident in work:
        found = find_node(recs, ident, hidden, dead_hubs)
        if not found:
            raise ValueError(f"work {ident!r} is not in this knowledge")
        out_work.append({"owner_record": found[0], "entity_id": ident.rpartition("::")[2] or ident})
    for ident in evidence:
        for name, rec in sorted(recs.items()):
            event = rec.event(ident)
            if event:
                break
        else:
            raise ValueError(f"evidence {ident!r} is not a recorded learning event")
        if event["type"] not in ev_types.TYPES:
            raise ValueError(f"evidence {ident!r} is a {event['type']} event, not learning evidence a note may cite")
        out_evidence.append({"owner_record": name, "event": ident, "type": event["type"]})
    return {"work": out_work, "evidence": out_evidence}


def _links(recs: dict, links, owner: str, visible: set, hidden, dead_hubs) -> list[dict]:
    if links is None:
        return []
    if not isinstance(links, list) or len(links) > 20:
        raise ValueError("links is a list of at most 20 {type, target}")
    out = []
    for link in links:
        if not isinstance(link, dict) or set(link) != {"type", "target"} or link["type"] not in NOTE_LINKS \
                or not isinstance(link["target"], str):
            raise ValueError(f"a link is {{type: one of {list(NOTE_LINKS)}, target: a node or note id}}")
        target = link["target"]
        if target.startswith("note:"):
            if target not in visible:
                raise ValueError(f"no such note {target}")
            out.append({"type": link["type"], "target": target, "owner_record": None})
            continue
        found = find_node(recs, target, hidden, dead_hubs, prefer=owner)
        if not found:
            raise ValueError(f"no such node {target}: a note links only to what is in the knowledge")
        out.append({"type": link["type"], "target": target.rpartition("::")[2] or target, "owner_record": found[0]})
    return out


def _find_note(recs: dict, note: str, live_ids=None):
    for name, rec in sorted(recs.items()):
        state = notes(rec).get(note)
        if state:
            if live_ids is not None and state["workspace_id"] not in live_ids:
                break
            return name, state
    raise KeyError(f"no such note {note}")


def _digest(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def _write(owner: Record, op: str, note: str, key: str, by: str, data: dict, request: str) -> bool:
    """Append one note event under its idempotency key; returns whether it was a replay. A replay (same operation, note
    and key) writes nothing and is only allowed with the same request; the same key with another request is refused."""
    eid = event_id(f"graph.note.{op}", f"{owner.root.name}|{note}|{key}")
    prior = owner.event(eid)
    if prior:
        if prior["data"].get("request") != request:
            raise ValueError("this key was already used for a different write; use a new key")
        return True
    event = make_event(f"graph.note.{op}", note, {**data, "request": request}, actor=by, id=eid)
    if owner.append_many([event]) == 0:   # another writer won the race: it must have written the same request
        if owner.event(eid)["data"].get("request") != request:
            raise ValueError("this key was already used for a different write; use a new key")
        return True
    return False


def _seen(rec: Record, op: str, owner: str, note: str, key: str) -> bool:
    return rec.event(event_id(f"graph.note.{op}", f"{owner}|{note}|{key}")) is not None


def _note_view(owner: str, state: dict, replayed: bool) -> dict:
    return {"note": state["id"], "owner_record": owner, "workspace_id": state["workspace_id"], "revision": state["revision"],
            "kind": state["kind"], "retracted": bool(state["retracted"]), "replayed": replayed,
            "ref": {"owner_record": owner, "entity_id": state["id"]}}


def note_add(recs: dict, owner: str, workspace_id: str, kind: str, title: str, text: str, key: str, by: str,
             work=None, evidence=None, links=None, hidden=None, dead_hubs=()) -> dict:
    """Add a knowledge note to the record ``owner``. Idempotent per ``key``: the note's id comes from the owner and key."""
    if kind not in NOTE_KINDS:
        raise ValueError(f"kind is one of {list(NOTE_KINDS)}")
    actor = _agent(by)
    title, text, key = _clip(title, "title", 1, 200), _clip(text, "text", 1, 2000), _clip(key, "key", 1, 200)
    note = "note:" + hashlib.sha256(f"{owner}|{key}".encode()).hexdigest()[:20]
    request = _digest("add", workspace_id, kind, title, text, work, evidence, links, actor)
    rec = recs[owner]
    data = {}
    if not _seen(rec, "added", owner, note, key):
        visible = {n for r in recs.values() for n, s in notes(r).items() if not s["retracted"]}
        data = {"kind": kind, "title": title, "text": text, "workspace_id": workspace_id,
                "links": _links(recs, links, owner, visible, hidden, dead_hubs),
                "prompted_by": _prompted(recs, work, evidence, hidden, dead_hubs)}
    replayed = _write(rec, "added", note, key, actor, data, request)
    return _note_view(owner, notes(rec)[note], replayed)


def note_revise(recs: dict, note: str, key: str, by: str, work=None, evidence=None, title=None, text=None, links=None,
                reason="", base=None, live_ids=None, hidden=None, dead_hubs=()) -> dict:
    """Revise a note (its title, text or links) keeping its identity. ``base`` is the revision the agent read; a newer one refuses."""
    actor, key = _agent(by), _clip(key, "key", 1, 200)
    owner, state = _find_note(recs, note, live_ids)
    rec = recs[owner]
    request = _digest("revise", note, title, text, links, work, evidence, reason, actor)
    data = {}
    if not _seen(rec, "revised", owner, note, key):
        if state["retracted"]:
            raise ValueError(f"{note} is retracted; add a new note instead")
        if base is not None and base != state["revision"]:
            raise ValueError(f"stale: {note} is at revision {state['revision']}, not {base}; read it again")
        if title is not None:
            data["title"] = _clip(title, "title", 1, 200)
        if text is not None:
            data["text"] = _clip(text, "text", 1, 2000)
        if links is not None:
            visible = {n for r in recs.values() for n, s in notes(r).items() if not s["retracted"] and n != note}
            data["links"] = _links(recs, links, owner, visible, hidden, dead_hubs)
        if not data:
            raise ValueError("revise something: title, text or links")
        data["prompted_by"] = _prompted(recs, work, evidence, hidden, dead_hubs)
        data["reason"] = _clip(reason, "reason", 1, 500) if reason else ""
    replayed = _write(rec, "revised", note, key, actor, data, request)
    return _note_view(owner, notes(rec)[note], replayed)


def note_retract(recs: dict, note: str, key: str, by: str, reason: str, work=None, evidence=None, live_ids=None,
                 hidden=None, dead_hubs=()) -> dict:
    """Retract a note: it leaves the graph and the tutor's read; its history stays in the record."""
    actor, key = _agent(by), _clip(key, "key", 1, 200)
    owner, state = _find_note(recs, note, live_ids)
    rec = recs[owner]
    request = _digest("retract", note, reason, work, evidence, actor)
    data = {}
    if not _seen(rec, "retracted", owner, note, key):
        if state["retracted"]:
            raise ValueError(f"{note} is already retracted")
        data = {"reason": _clip(reason, "reason", 1, 500), "prompted_by": _prompted(recs, work, evidence, hidden, dead_hubs)}
    replayed = _write(rec, "retracted", note, key, actor, data, request)
    return _note_view(owner, notes(rec)[note], replayed)


# ---- reading the living graph ------------------------------------------------------------------------------------
def _members(rec: Record, hub: str) -> list[str]:
    """The capabilities part of (or about) a hub: one query on the destination index."""
    rec.stamp("edges")
    return [r[0] for r in rec.index().execute(
        "SELECT src FROM edges WHERE dst=? AND type IN ('part-of','about') AND src LIKE 'capability:%' "
        "ORDER BY src LIMIT 5000", (hub,))]


def _goal_caps(rec: Record, goal: dict) -> list[str]:
    named = goal.get("targets") or []
    out: list[str] = []
    for x in named:
        out += [x] if x.startswith("capability:") else _members(rec, x)
    return out if named else _members(rec, goal["id"])


def _touched(rec: Record) -> list[str]:
    """Capabilities with learning evidence, from the evidence fold (no scan of the record)."""
    from .learn import evidence
    keys = [k for k in evidence.of(rec).versions if k.startswith("capability:") and "|" not in k]
    return sorted(k for k in keys if rec.node(k))


def _orphans(rec: Record, dead_hubs) -> set:
    """Capabilities filed only under deleted workspaces: they leave the graph with them (the evidence stays in the record)."""
    out = set()
    for hub in dead_hubs:
        for cap in _members(rec, hub):
            anchors = [e["dst"] for t in ("part-of", "about") for e in rec.edges(src=cap, type=t)]
            if not [a for a in anchors if a not in dead_hubs]:
                out.add(cap)
    return out


def living(recs: dict, entries: list, rows: dict, as_of: date, scope: str, workspace_id: str | None, hidden=None,
           limit: int | None = 200, omitted: int = 0) -> dict:
    """The knowledge graph of a workspace (or of the whole person) as of a day, derived from the records given.

    ``entries`` are the workspace identities in scope, ``rows`` their work (``{workspace_id: [overview row + group]}``).
    A workspace, a work item, a note or a hub that is gone (deleted, hidden, retracted) is simply not built, and a last pass
    keeps only the edges whose two ends are in the view, so nothing dangles. ``limit`` caps the nodes shown (None: all, for a
    reader that bounds its own answer); ``omitted`` is how many workspaces the caller left out of ``entries``."""
    limit = None if limit is None else max(1, min(int(limit), MAX_NODES))
    recs = {n: r for n, r in recs.items() if not home.config(r.root).get("deleted")}   # a deleted record is no client of it
    dead_ids, dead_hubs = dead_workspaces(recs)
    entries = [e for e in entries if e["workspace_id"] not in dead_ids
               and (e.get("hub") or {}).get("entity_id") not in dead_hubs]
    live_ids = {e["workspace_id"] for e in entries}
    nodes: dict[str, dict] = {}
    edges: dict[tuple, dict] = {}

    def edge(src, dst, type, origin="record"):
        edges[(src, dst, type, origin)] = {"src": src, "dst": dst, "type": type, "origin": origin}

    work_ids: dict[str, dict] = {}
    for e in entries:
        wid, hub = e["workspace_id"], e.get("hub")
        nodes[wid] = {"id": wid, "kind": "workspace", "workspace_kind": e["kind"], "title": e["title"],
                      "ref": {"owner_record": e["owner_record"], "entity_id": hub["entity_id"] if hub else wid}}
        for row in rows.get(wid, []):
            owner, entity = row["ref"]["owner_record"], row["ref"]["entity_id"]
            if row["kind"] not in WORK_KINDS or owner not in recs or (hidden and hidden(owner, entity)):
                continue
            nid = f"{owner}::{entity}"
            node = nodes.setdefault(nid, {"id": nid, "kind": row["kind"], "title": row["title"], "group": row["group"],
                                          "ref": {"owner_record": owner, "entity_id": entity}})
            work_ids[nid] = node
            for field in ("state", "status"):
                if row.get(field) is not None:
                    node[field] = row[field]
            edge(wid, nid, "contains")
    # claim support is read from the claim's own record, indexed by the claim
    for nid, node in sorted(work_ids.items()):
        if node["kind"] == "claim":
            owner = node["ref"]["owner_record"]
            for rel in ("supports", "invalidates"):
                for e in recs[owner].edges(type=rel, dst=node["ref"]["entity_id"]):
                    edge(f"{owner}::{e['src']}", nid, rel)

    # which record holds each workspace's capabilities, and which capabilities are in scope
    members: dict[str, dict] = {}
    cap_owner: dict[str, str] = {}
    orphans: dict[str, set] = {}
    for e in entries:
        hub = e.get("hub")
        owner = e["owner_record"] if hub else e["record"]
        if owner not in recs:
            continue
        cap_owner[e["workspace_id"]] = owner
        if owner not in orphans:
            orphans[owner] = _orphans(recs[owner], dead_hubs)
        found = _members(recs[owner], hub["entity_id"]) if hub else _touched(recs[owner])
        members[e["workspace_id"]] = {c: owner for c in found if c not in orphans[owner]}
        if hub and e["record"] != owner and e["record"] in recs:   # what the project's own research needs
            r = recs[e["record"]]
            r.stamp("edges")
            for src, dst in r.index().execute(
                    "SELECT src, dst FROM edges WHERE type='requires' AND dst LIKE 'capability:%' "
                    "AND src NOT LIKE 'capability:%' ORDER BY src, dst LIMIT 5000"):
                if f"{e['record']}::{src}" in work_ids and recs[owner].node(dst):
                    members[e["workspace_id"]].setdefault(dst, owner)
                    edge(f"{e['record']}::{src}", dst, "requires")
    caps: dict[str, set] = {}      # owner record -> capability ids to assess
    for found in members.values():
        for cap, owner in found.items():
            caps.setdefault(owner, set()).add(cap)

    # goals the person (or an agent) set, that touch what is in scope
    goals: dict[str, dict] = {}
    for owner in sorted(set(cap_owner.values())):
        rec = recs[owner]
        hubs = {(e.get("hub") or {}).get("entity_id") for e in entries if cap_owner.get(e["workspace_id"]) == owner}
        for goal in rec.nodes(type="goal"):
            targets = goal.get("targets") or []
            if targets and not [t for t in targets if t not in dead_hubs]:
                continue
            gcaps = [c for c in _goal_caps(rec, goal) if c not in orphans.get(owner, ())]
            if scope == "personal" or hubs & set(targets) or set(gcaps) & caps.get(owner, set()):
                goals[goal["id"]] = {"owner": owner, "node": goal, "caps": gcaps, "targets": targets}
    for g in goals.values():
        caps.setdefault(g["owner"], set()).update(g["caps"])

    # the notes agents keep, then the capabilities they point at
    visible: dict[str, dict] = {}
    for name, rec in sorted(recs.items()):
        for nid, st in notes(rec).items():
            if st["retracted"] or (scope == "workspace" and st["workspace_id"] != workspace_id) \
                    or st["workspace_id"] not in live_ids:
                continue
            visible[nid] = dict(st, owner_record=name)
            for link in st["links"]:
                if link["target"].startswith("capability:") and link["owner_record"] in recs:
                    caps.setdefault(link["owner_record"], set()).add(link["target"])

    learned: dict[str, Learning] = {}
    cap_by_id: dict[str, tuple] = {}
    for owner, ids in sorted(caps.items()):
        learned[owner] = Learning(recs[owner], as_of, within=sorted(ids))
        for cid, cap in learned[owner].caps.items():
            cap_by_id.setdefault(cid, (owner, cap, learned[owner]))
    for cid, (owner, cap, learning) in cap_by_id.items():
        a = cap.assessment
        due = bool(a.review and a.review <= as_of and cap.node.get("retention_target") != "reference")
        signal = ("known" if a.state in ("demonstrated", "retained") and not cap.node.get("issues") else
                  "shaky" if a.state in ("fragile", "stale", "learning") else "new")
        nodes[cid] = {"id": cid, "kind": "capability", "title": cap.node.get("title", cid), "state": a.state,
                      "signal": signal, "due": due, "ready": cid in learning.ready, "frontier": learning.is_frontier(cid),
                      "blocked_by": learning.blocked_by(cid), "next_review": a.review.isoformat() if a.review else None,
                      "last_retrieval": a.last.isoformat() if a.last else None, "evidence": a.evidence,
                      "ref": {"owner_record": owner, "entity_id": cid}}
        for p in cap.prerequisites:
            if p in cap_by_id:
                edge(cid, p, "requires")
    for e in entries:
        if e.get("hub"):
            for cap in members.get(e["workspace_id"], ()):
                if cap in cap_by_id:
                    edge(cap, e["workspace_id"], "part-of")
    for gid, g in sorted(goals.items()):
        nodes[gid] = {"id": gid, "kind": "goal", "title": g["node"].get("title", gid), "source": "record",
                      "ref": {"owner_record": g["owner"], "entity_id": gid}}
        for cap in g["caps"]:
            if cap in cap_by_id:
                edge(gid, cap, "aims-at")
        for e in entries:
            if (e.get("hub") or {}).get("entity_id") in g["targets"]:
                edge(gid, e["workspace_id"], "aims-at")

    for nid, st in sorted(visible.items()):
        nodes[nid] = {"id": nid, "kind": "note", "note_kind": st["kind"], "title": st["title"], "text": st["text"],
                      "revision": st["revision"], "added_by": st["added_by"], "updated_by": st["updated_by"],
                      "updated_at": st["updated_at"], "workspace_id": st["workspace_id"],
                      "cites": [dict(c) for c in st["cites"]], "work": [dict(w) for w in st["work"]],
                      "ref": {"owner_record": st["owner_record"], "entity_id": nid}}
        edge(nid, st["workspace_id"], "part-of", "note")
    for nid, st in sorted(visible.items()):
        for link in st["links"]:
            target = link["target"]
            if not target.startswith("note:") and target not in nodes:
                found = find_node(recs, target, hidden, dead_hubs, prefer=link["owner_record"])
                if found:
                    nodes[target] = {"id": target, "kind": found[1]["type"], "title": found[1].get("title", target),
                                     "reference": True, "ref": {"owner_record": found[0], "entity_id": target}}
            edge(nid, target, link["type"], "note")

    # bounded: keep the most useful nodes, then only the edges whose two ends remain
    total = len(nodes)
    if limit is not None and total > limit:
        def weight(n):
            kind = n["kind"]
            return (0 if kind == "workspace" else 1 if kind == "goal" else 2 if kind == "note" else
                    3 if kind == "capability" and (n["signal"] == "shaky" or n["due"]) else
                    4 if kind == "capability" else 6 if n.get("reference") else 5, n["id"])
        keep = {n["id"] for n in sorted(nodes.values(), key=weight)[:limit]}
        nodes = {k: v for k, v in nodes.items() if k in keep}
    out_edges = sorted((e for e in edges.values() if e["src"] in nodes and e["dst"] in nodes),
                       key=lambda e: (e["src"], e["dst"], e["type"], e["origin"]))
    out_nodes = [nodes[k] for k in sorted(nodes)]
    counts: dict[str, int] = {}
    for n in out_nodes:
        counts[n["kind"]] = counts.get(n["kind"], 0) + 1
    return {"schema": "ros.living-graph.v1", "scope": scope, "workspace_id": workspace_id, "as_of": as_of.isoformat(),
            "nodes": out_nodes, "edges": out_edges, "counts": counts,
            "truncated": ({"nodes": total, "shown": len(out_nodes), **({"workspaces_omitted": omitted} if omitted else {})}
                          if len(out_nodes) < total else {"workspaces_omitted": omitted} if omitted else None),
            "digest": _digest(out_nodes, out_edges)}


def teaching(view: dict, limit: int = 10) -> dict:
    """What a tutor needs to decide what to teach next, read from a living graph: what is known, shaky and due, the gaps
    towards each goal, and the misconceptions agents recorded. Each list is bounded; each entry carries its reference."""
    limit = max(1, min(int(limit), 50))
    nodes = {n["id"]: n for n in view["nodes"]}
    on: dict[str, list] = {}
    for e in view["edges"]:
        if e["origin"] == "note" and e["src"].startswith("note:") and e["dst"] in nodes:
            on.setdefault(e["dst"], []).append(e["src"])

    def note_row(nid):
        n = nodes[nid]
        return {"note": nid, "kind": n["note_kind"], "title": n["title"], "revision": n["revision"], "ref": n["ref"]}

    def cap_row(n):
        row = {"id": n["id"], "title": n["title"], "state": n["state"], "next_review": n["next_review"], "ref": n["ref"]}
        if n["blocked_by"]:
            row["blocked_by"] = n["blocked_by"]
        if n["evidence"]:
            row["evidence"] = n["evidence"]
        hints = sorted(set(on.get(n["id"], ())))
        if hints:
            row["notes"] = [note_row(s) for s in hints]
        return row

    caps = [n for n in view["nodes"] if n["kind"] == "capability"]
    order = {"fragile": 0, "stale": 1, "learning": 2}
    known = [cap_row(n) for n in caps if n["signal"] == "known"]
    shaky = [cap_row(n) for n in sorted((n for n in caps if n["signal"] == "shaky"),
                                        key=lambda n: (order.get(n["state"], 3), n["id"]))]
    due = [cap_row(n) for n in sorted((n for n in caps if n["due"]), key=lambda n: (n["next_review"] or "", n["id"]))]
    aims: dict[str, set] = {}
    for e in view["edges"]:
        if e["type"] == "aims-at" and nodes.get(e["src"], {}).get("kind") in ("goal", "note") \
                and nodes.get(e["dst"], {}).get("kind") == "capability":
            aims.setdefault(e["src"], set()).add(e["dst"])
    gaps = []
    for gid in sorted(aims):
        missing = [cap_row(nodes[c]) for c in sorted(aims[gid]) if not nodes[c]["ready"]]
        if missing:
            gaps.append({"goal": gid, "title": nodes[gid]["title"], "source": "note" if gid.startswith("note:") else "record",
                         "ref": nodes[gid]["ref"], "targets": len(aims[gid]), "missing": missing})
    miscons = []
    for n in view["nodes"]:
        if n["kind"] == "note" and n["note_kind"] == "misconception":
            about = sorted({e["dst"] for e in view["edges"] if e["src"] == n["id"] and e["origin"] == "note"
                            and e["type"] in ("misconception-of", "about")})
            miscons.append({"note": n["id"], "title": n["title"], "text": n["text"], "revision": n["revision"],
                            "about": about, "cites": n["cites"], "updated_at": n["updated_at"], "ref": n["ref"]})
    queue = [{"id": r["id"], "why": "due", "ref": r["ref"]} for r in due]
    queue += [{"id": r["id"], "why": "shaky", "ref": r["ref"]} for r in shaky]
    queue += [{"id": m["id"], "why": "goal-gap", "ref": m["ref"]} for g in gaps for m in g["missing"]
              if nodes[m["id"]]["frontier"]]
    seen, nxt = set(), []
    for item in queue:
        if item["id"] not in seen:
            seen.add(item["id"])
            nxt.append(item)
    totals = {"known": len(known), "shaky": len(shaky), "due": len(due), "goal_gaps": len(gaps),
              "misconceptions": len(miscons), "next": len(nxt)}
    return {"schema": "ros.teaching-signals.v1", "workspace_id": view["workspace_id"], "as_of": view["as_of"],
            "known": known[:limit], "shaky": shaky[:limit], "due": due[:limit], "goal_gaps": gaps[:limit],
            "misconceptions": miscons[:limit], "next": nxt[:limit], "totals": totals,
            "limits": {"per_list": limit, "graph_truncated": bool(view.get("truncated"))}, "digest": view["digest"]}
