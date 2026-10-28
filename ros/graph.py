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
same history until the old runtime is retired. Everything here only reads; nothing writes except ``import_graphify``.
"""
from __future__ import annotations

from array import array
from dataclasses import dataclass
from datetime import date
import json
import hashlib
from pathlib import Path

from .store import Record

RECONSTRUCTION = {"explanation", "derivation", "transfer", "computation"}
SCOPES = ("conceptual", "project_application", "transfer")
DIMENSIONS = ("recognition", "explanation", "derivation", "transfer", "application")
LITERACY_DIMENSIONS = ("method_understanding", "tool_operation", "implementation_navigation")
STATE_ORDER = ("unknown", "learning", "fragile", "stale", "demonstrated", "retained")


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
