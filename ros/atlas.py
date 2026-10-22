"""Graphs a person can look at, laid out here so the page stays small: the knowledge graph (what you know, by course, subject
and capability), the research graph (question, hypothesis, experiment, claim, evidence, and what each needs you to
know), the chain of evidence behind one claim, and progress over time. Each returns nodes and edges with their positions;
the page only draws them.

The layout is layered and linear in the size of what is shown: layers by the longest path from a source (a cycle's back
edge is ignored), order inside a layer by the average position of its neighbours (two passes). What is drawn is bounded
(``limit``): the overview shows hubs and counts, a focus shows its neighbourhood, never twenty thousand boxes.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from . import context, graph, home, research, tasks, vault
from .learn import evidence, schedule
from .store import Record

W, H, GX, GY = 190, 38, 64, 12
HUBS = ("domain", "subject", "course", "goal", "project", "block")
RESEARCH_LANES = {"question": 0, "hypothesis": 1, "experiment": 2, "claim": 3, "handout": 4, "paper": 4, "source": 4,
                  "capability": 5}


# ---- the layout ---------------------------------------------------------------------------------------------------
def layout(nodes: list[dict], edges: list[tuple[str, str]], layers: dict[str, int] | None = None) -> dict:
    """Position ``nodes`` (dicts with ``id``) left to right along ``edges`` (from, to). With ``layers``, a node's column
    is given; otherwise it is the longest path from a source. Returns the nodes with ``x``, ``y``, ``w``, ``h``, the edges
    that were drawn, and the size of the drawing."""
    ids = [n["id"] for n in nodes]
    known = set(ids)
    succ: dict[str, list[str]] = {i: [] for i in ids}
    pred: dict[str, list[str]] = {i: [] for i in ids}
    drawn = []
    for a, b in dict.fromkeys(edges):
        if a in known and b in known and a != b:
            succ[a].append(b)
            pred[b].append(a)
            drawn.append((a, b))
    if layers is None:
        layer = _longest_path(ids, succ, pred)
    else:
        layer = {i: layers.get(i, 0) for i in ids}
    columns: dict[int, list[str]] = {}
    for i in ids:
        columns.setdefault(layer[i], []).append(i)
    order = {c: sorted(v) for c, v in columns.items()}
    index = {i: k for c in order.values() for k, i in enumerate(c)}
    for sweep in (0, 1):  # forward on predecessors, then backward on successors
        cols = sorted(order) if sweep == 0 else sorted(order, reverse=True)
        for c in cols:
            ref = pred if sweep == 0 else succ

            def key(i):
                near = [index[j] for j in ref[i] if layer[j] != c]
                return (sum(near) / len(near) if near else index[i], i)
            order[c] = sorted(order[c], key=key)
            for k, i in enumerate(order[c]):
                index[i] = k
    cols = sorted(order)
    place = {c: n for n, c in enumerate(cols)}
    out = []
    by_id = {n["id"]: n for n in nodes}
    for c in cols:
        for k, i in enumerate(order[c]):
            out.append({**by_id[i], "x": place[c] * (W + GX), "y": k * (H + GY), "w": W, "h": H})
    width = len(cols) * (W + GX) - GX if cols else 0
    height = (max(len(v) for v in order.values()) * (H + GY) - GY) if order else 0
    return {"nodes": out, "edges": [{"src": a, "dst": b} for a, b in drawn], "width": width, "height": height}


def _longest_path(ids, succ, pred) -> dict[str, int]:
    """Column of each node: the longest path from a source, with back edges of cycles ignored (found by a depth-first
    walk), in one pass over the nodes and edges."""
    state, back = {}, set()
    for root in ids:
        if root in state:
            continue
        stack = [(root, iter(succ[root]))]
        state[root] = 1
        while stack:
            node, it = stack[-1]
            for nxt in it:
                if state.get(nxt) == 1:
                    back.add((node, nxt))
                elif nxt not in state:
                    state[nxt] = 1
                    stack.append((nxt, iter(succ[nxt])))
                    break
            else:
                state[node] = 2
                stack.pop()
    waiting = {i: sum(1 for p in pred[i] if (p, i) not in back) for i in ids}
    layer = {i: 0 for i in ids}
    todo = [i for i in ids if waiting[i] == 0]
    while todo:
        i = todo.pop()
        for j in succ[i]:
            if (i, j) in back:
                continue
            layer[j] = max(layer[j], layer[i] + 1)
            waiting[j] -= 1
            if waiting[j] == 0:
                todo.append(j)
    return layer


def _tip(*parts) -> str:
    return " · ".join(str(p) for p in parts if p not in (None, ""))


# ---- the knowledge graph ------------------------------------------------------------------------------------------
def knowledge(rec: Record, focus: str | None = None, depth: int = 2, limit: int = 300, as_of: date | None = None) -> dict:
    """With no ``focus``: the hubs (courses, subjects, goals, projects) with how much of each you know. With a hub: its
    capabilities with their prerequisites. With a capability: its prerequisites and what depends on it, ``depth`` steps."""
    as_of = as_of or date.today()
    if focus is None:
        return _overview(rec, as_of, limit)
    node = rec.node(focus)
    if node is None:
        raise KeyError(f"no node {focus}")
    s = graph.structure(rec)
    if node["type"] == "capability":
        keep = {focus}
        near = {focus}
        for _ in range(max(1, min(depth, 4))):
            near = {p for k in near for p in s.prerequisites(k)} | {d for k in near for d in s.dependents(k)}
            keep |= near
            if len(keep) > limit:
                break
        everything = sorted(keep)
        caps = everything[:limit]
    else:
        probe = graph.Learning(rec, as_of)
        members = sorted(probe.members.get(focus, ()))
        everything = [m for m in probe.order(m for m in members if m in probe.caps)]
        caps = everything[:limit]
    learning = graph.Learning(rec, as_of, within=caps)
    shown = [c for c in caps if c in learning.caps]
    nodes, states = [], {}
    for c in shown:
        v = learning.view(c)
        states[v["state"]] = states.get(v["state"], 0) + 1
        nodes.append({"id": c, "label": v["title"], "cls": f"st-{v['state']}" + (" frontier" if v["frontier"] else "")
                      + (" focus" if c == focus else ""), "kind": "capability", "state": v["state"],
                      "tip": _tip(v["title"], v["state"], f"next review {v['next_review']}" if v["next_review"] else None,
                                  "ready to learn" if v["frontier"] else None)})
    edges = [(p, c) for c in shown for p in learning.caps[c].prerequisites]
    g = layout(nodes, edges)
    g.update(mode="knowledge", focus=focus, title=node["title"] if node and node.get("title") else focus,
             summary=states, truncated=max(0, len(everything) - len(shown)))
    return g


def _overview(rec: Record, as_of: date, limit: int) -> dict:
    learning = graph.Learning(rec, as_of)
    hubs = [n for t in HUBS for n in rec.nodes(type=t)][:limit]
    nodes, ids = [], {n["id"] for n in hubs}
    total = {}
    for h in hubs:
        caps = [c for c in learning.members.get(h["id"], ()) if c in learning.caps]
        counts: dict[str, int] = {}
        for c in caps:
            st = learning.caps[c].assessment.state
            counts[st] = counts.get(st, 0) + 1
            total[st] = total.get(st, 0) + 1
        known = counts.get("demonstrated", 0) + counts.get("retained", 0)
        share = (known / len(caps)) if caps else 0
        nodes.append({"id": h["id"], "label": h.get("title") or h["id"].split(":", 1)[-1],
                      "cls": f"hub hub-{h['type']} m{min(4, int(share * 5))}", "kind": h["type"],
                      "count": len(caps), "states": counts,
                      "tip": _tip(h.get("title") or h["id"], f"{len(caps)} capabilities", f"{known} known" if caps else None,
                                  f"due {h['deadline']}" if h.get("deadline") else None)})
    edges = [(e["dst"], e["src"]) for e in rec.edges(type="part-of") if e["src"] in ids and e["dst"] in ids]
    g = layout(nodes, edges)
    g.update(mode="knowledge", focus=None, title="Everything you know", summary=total, capabilities=len(learning.caps),
             truncated=0)
    return g


# ---- the research graph -------------------------------------------------------------------------------------------
def research_graph(rec: Record, focus: str | None = None, limit: int = 300, as_of: date | None = None) -> dict:
    """Question to hypothesis to experiment to claim to evidence, one column each, coloured by status, verdict and
    ownership; with what each step needs you to know on the right, in your own state."""
    as_of = as_of or date.today()
    types = ("question", "hypothesis", "experiment", "claim", "handout", "paper", "source")
    nodes_all = [n for t in types for n in rec.nodes(type=t)]
    if focus:
        near = {focus} | {e["dst"] for e in rec.edges(src=focus)} | {e["src"] for e in rec.edges(dst=focus)}
        nodes_all = [n for n in nodes_all if n["id"] in near or n["id"] == focus]
    nodes_all = nodes_all[:limit]
    ids = {n["id"] for n in nodes_all}
    practice = research.Practice(rec, as_of)
    nodes = []
    for n in nodes_all:
        t, cls, tip = n["type"], n["type"], n.get("title") or n.get("text") or n["id"]
        if t == "claim":
            st = research.status(rec, n["id"], as_of, practice)
            cls = f"claim v-{st['verdict'].lower()} own-{st['ownership']}"
            tip = _tip(tip, st["verdict"], st["ownership"])
        elif t == "experiment":
            cls = f"experiment auth-{n.get('authorization') or 'none'}"
            tip = _tip(tip, n.get("authorization"))
        elif t in ("question", "hypothesis"):
            cls = f"{t} status-{n.get('status') or 'none'}"
            tip = _tip(tip, n.get("status"))
        elif t == "handout":
            cls = f"handout hs-{n.get('status') or 'draft'}"
            tip = _tip(tip, n.get("kind"), n.get("status"))
        nodes.append({"id": n["id"], "label": str(n.get("title") or n.get("text") or n["id"].split(":", 1)[-1])[:60],
                      "cls": cls, "kind": t, "tip": str(tip)[:200]})
    edges = [(e["src"], e["dst"]) for e in rec.edges() if e["src"] in ids and e["dst"] in ids
             and e["type"] not in ("part-of", "requires")]
    # what the research needs the person to know, in the person's state
    needs: list[dict] = []
    try:
        if home.config(rec.root).get("role") == "project":
            needs = context.context(rec, as_of)["needs"]["capabilities"]
    except (ValueError, KeyError):
        pass
    lanes = dict(RESEARCH_LANES)
    layers = {n["id"]: lanes.get(n["kind"], 4) for n in nodes}
    for c in needs[:60]:
        nodes.append({"id": c["capability"], "label": c["title"] or c["capability"].split(":", 1)[-1],
                      "cls": f"st-{c['state']}", "kind": "capability", "state": c["state"],
                      "tip": _tip(c["title"] or c["capability"], c["state"], "ready" if c["ready"] else "not ready")})
        layers[c["capability"]] = 5
        for src in c["needed_by"]:
            if src in ids:
                edges.append((src, c["capability"]))
    g = layout(nodes, edges, layers)
    claims = [n for n in nodes_all if n["type"] == "claim"]
    g.update(mode="research", focus=focus, title=vault.layout(rec)["title"],
             summary={"claims": len(claims), "needs": len(needs)}, truncated=0)
    return g


def atlas(rec: Record, mode: str = "knowledge", focus: str | None = None, depth: int = 2, limit: int = 300,
          as_of: date | None = None) -> dict:
    if mode == "knowledge":
        return knowledge(rec, focus, depth, limit, as_of)
    if mode == "research":
        return research_graph(rec, focus, limit, as_of)
    raise ValueError("mode is knowledge or research")


# ---- the chain behind a claim -------------------------------------------------------------------------------------
def chain(rec: Record, claim: str, as_of: date | None = None) -> dict:
    """One claim and everything it rests on, left to right: the question and experiment it comes from, the claim, the audit
    steps with their verdicts, the files and sources behind them, the decision and the handouts about it."""
    node = rec.node(claim)
    if not node or node["type"] != "claim":
        raise KeyError(f"no claim {claim}")
    st = research.status(rec, claim, as_of)
    nodes = [{"id": claim, "label": (node.get("text") or claim)[:70], "kind": "claim",
              "cls": f"claim v-{st['verdict'].lower()} own-{st['ownership']}", "tip": _tip(st["verdict"], st["ownership"])}]
    edges, layers = [], {claim: 2}

    def add(i, label, kind, cls, layer, tip=""):
        if i not in layers:
            nodes.append({"id": i, "label": str(label)[:60], "kind": kind, "cls": cls, "tip": tip or str(label)})
            layers[i] = layer
        return i
    for step in st["required"]:
        v = st["verdicts"].get(step)
        sid = add(f"{claim}#{step}", f"{step}: {v['verdict'] if v else 'waiting'}", "verdict",
                  f"verdict v-{(v['verdict'] if v else 'pending').lower()}", 3,
                  _tip(step, v["verdict"] if v else "waiting", f"by {v['by']}" if v else None, (v or {}).get("notes")))
        edges.append((claim, sid))
    for a in node.get("artifacts", [])[:12]:
        edges.append((claim, add(f"file:{a}", a, "artifact", "artifact", 4)))
    for c in node.get("citations", [])[:12]:
        edges.append((claim, add(f"cite:{c}", c, "citation", "artifact", 4)))
    for e in rec.edges(dst=claim) + rec.edges(src=claim):
        other = e["src"] if e["dst"] == claim else e["dst"]
        n = rec.node(other) or {}
        t = n.get("type")
        if t in ("experiment", "hypothesis", "question"):
            edges.append((add(other, n.get("title") or other, t, t, 0 if t == "question" else 1 if t == "hypothesis" else 1), claim))
        elif t in ("paper", "source"):
            edges.append((claim, add(other, n.get("title") or other, t, t, 4)))
        elif t == "handout":
            edges.append((claim, add(other, n.get("title") or other, t, f"handout hs-{n.get('status') or 'draft'}", 5)))
    for d in rec.events(type="decision", subject=claim):
        did = add(f"decision:{d['id'][:12]}", f"decided: {d['data'].get('outcome')}", "decision", "decision", 5,
                  _tip(d["data"].get("outcome"), d["actor"], d["data"].get("rationale")))
        edges.append((claim, did))
    # a step's evidence files hang off the step that cites them
    for step in st["required"]:
        v = st["verdicts"].get(step) or {}
        for f in v.get("evidence") or []:
            edges.append((f"{claim}#{step}", add(f"file:{f}", f, "artifact", "artifact", 4)))
    g = layout(nodes, edges, layers)
    g.update(mode="chain", focus=claim, title=node.get("text") or claim, summary={"verdict": st["verdict"],
                                                                              "ownership": st["ownership"]}, truncated=0)
    return g


# ---- progress -----------------------------------------------------------------------------------------------------
def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def progress(rec: Record, weeks: int = 12, as_of: date | None = None) -> dict:
    """What you did and how it is going, by week: answers, correct unaided answers, reviews, lessons and newly known
    capabilities; and where you stand now (states, what is due, estimated recall). Read from indexed events in the window."""
    as_of = as_of or date.today()
    weeks = max(1, min(int(weeks), 52))
    start = _monday(as_of) - timedelta(weeks=weeks - 1)
    since = start.isoformat() + "T00:00:00Z"
    rows = {(start + timedelta(weeks=i)).isoformat(): {"week": (start + timedelta(weeks=i)).isoformat(), "answers": 0,
                                                       "correct": 0, "unaided_correct": 0, "reviews": 0, "lessons": 0,
                                                       "new": 0} for i in range(weeks)}

    def bucket(ts: str):
        return rows.get(_monday(date.fromisoformat(ts[:10])).isoformat())
    attempts = evidence.of(rec).attempts
    for e in rec.events(type="attempt", since=since):
        b = bucket(e["ts"])
        if b:
            b["answers"] += 1
    for e in rec.events(type="grade", since=since):
        b = bucket(e["ts"])
        if b and e["data"].get("verdict") == "correct":
            b["correct"] += 1
            if not (attempts.get(e["data"].get("attempt")) or (0, 0, False))[2]:
                b["unaided_correct"] += 1
    for e in rec.events(type="retrieval", since=since):
        b = bucket(e["ts"])
        if b:
            b["reviews"] += 1
    for e in rec.events(type="lesson.close", since=since):
        b = bucket(e["ts"])
        if b and not e["subject"].startswith("bundle:"):
            b["lessons"] += 1
    learning = graph.Learning(rec, as_of)
    states: dict[str, int] = {}
    for c in learning.caps.values():
        states[c.assessment.state] = states.get(c.assessment.state, 0) + 1
        first = c.assessment.first
        if first and first >= start:
            b = rows.get(_monday(first).isoformat())
            if b:
                b["new"] += 1
    cards = schedule.schedule(rec, as_of)
    recall = [c["retrievability"] for c in cards]
    days = {e["ts"][:10] for e in rec.events(type="attempt", since=(as_of - timedelta(days=60)).isoformat() + "T00:00:00Z")}
    streak, d = 0, as_of
    while d.isoformat() in days or (d == as_of and (as_of - timedelta(days=1)).isoformat() in days):
        if d.isoformat() in days:
            streak += 1
        d -= timedelta(days=1)
    return {"weeks": list(rows.values()), "states": states, "capabilities": len(learning.caps),
            "due": len([c for c in cards if c["due"] <= as_of.isoformat()]),
            "estimated_recall": round(sum(recall) / len(recall), 3) if recall else None, "reviewed_items": len(cards),
            "streak_days": streak}


# ---- finding things -----------------------------------------------------------------------------------------------
def find(rec: Record, q: str, limit: int = 20) -> list[dict]:
    """Nodes whose name or text contain ``q`` in this record and the ones it is joined to, and notes in the vault."""
    out: list[dict] = []
    limit = max(1, min(int(limit), 100))
    with context.linked(rec) as recs:
        for r in recs:
            for n in r.search_nodes(q, limit=limit):
                out.append({"record": r.root.name, "id": n["id"], "type": n["type"],
                            "title": n.get("title") or n.get("text") or n["id"].split(":", 1)[-1], "source": "record"})
            if vault.configured():
                for n in vault.find(r, q=q, limit=limit):
                    out.append({"record": r.root.name, "id": n["id"], "type": n["kind"], "title": n["title"],
                                "source": "vault", "obsidian": n["obsidian"]})
    seen, rows = set(), []
    for x in out:
        key = (x["record"], x["id"])
        if key not in seen:
            seen.add(key)
            rows.append(x)
    return rows[:limit]
