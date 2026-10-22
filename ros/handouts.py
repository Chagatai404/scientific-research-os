"""Study handouts, written by agents from what the record holds and delivered as an Obsidian note and a PDF.

A handout is a document you study from: for a course, a **lecture** note, a **recitation** and a textbook-style
**chapter**; for research, a **literature** brief and a **findings** handout. ``create`` composes what the record knows
(capabilities and their prerequisites, prepared narration, sources, claims and their audits) into the handout's
``context`` and opens one ``handout`` task; the agent that takes it writes each section with ``write`` (Markdown with
LaTeX math and boxes, see ``ros.lib.pdf``), and the gate says what is still missing. A handout is teaching or
reporting material, never learning evidence, and carries no answer key.

    handouts/<key>/source.json      the sections, sources and the context they were written from
    handouts/<key>/manifest.json    the gate's verdict for one version of the source
    handouts/<key>/figures/         images the sections refer to
    handouts/<key>/build/<hash>/    main.tex, index.html, out/<hash>.pdf and result.json for one version

The Markdown **note** in the vault is the primary artifact and is written as soon as there is text, marked as a draft by
its agents until you have read it. The **PDF** is built from the same source by whatever toolchain the computer has
(``ros.lib.pdf``); it is queued as a ``job`` and attached when it exists, and a missing toolchain is a reported fact,
never a failure. The gate (``ROWS``) decides whether a version is ready; a failing row opens a ``handout`` task.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Callable

from . import graph, home, prepare, research, tasks, vault
from .store import Record, canonical, event_id

SCHEMA = 1
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
UNFINISHED = re.compile(r"\bTODO\b|\bFIXME\b|\bXXX\b|\bTBD\b|lorem ipsum", re.I)
CITE = re.compile(r"\[@([A-Za-z0-9_:-]+(?:;\s*@[A-Za-z0-9_:-]+)*)\]")
MAX_CONTEXT = 24000  # characters of context kept in the source file


@dataclass(frozen=True)
class Kind:
    """One handout kind: its sections (role, heading, minimum words), the boxes it must contain, the roles whose claims
    need a source locator or a derivation, and what the agent is asked for."""
    name: str
    sections: tuple
    counts: dict
    factual: tuple
    brief: str


KINDS = {
    "lecture": Kind("lecture", (("gist", "L0 Gist", 8), ("recall", "L1 Core in 60 seconds", 15),
                                ("lecture", "L2 Lecture", 150), ("derivation", "L3 Derivation and sources", 60)),
                    {"question": 3}, ("lecture", "derivation"),
                    "A layered lecture note: a one-sentence gist; three or more :::question recall prompts with "
                    "answers after '=== answer' (the reader answers from memory first); the full lecture, words first, "
                    "then the picture, then the formula; then the derivation, its assumptions and where it can fail."),
    "recitation": Kind("recitation", (("intro", "What this recitation practises", 20), ("exercises", "Exercises", 40),
                                      ("mistakes", "Common mistakes", 20)),
                       {"exercise": 5}, ("mistakes",),
                       "A problem session: five or more :::exercise items that grow in difficulty, each with a full "
                       "solution after '=== solution' (printed in an appendix), and the mistakes students make. "
                       "Exercises here are for study; they never become assessment items."),
    "chapter": Kind("chapter", (("overview", "Overview", 40), ("definitions", "Definitions and results", 120),
                                ("examples", "Worked examples", 80), ("exercises", "Exercises", 40),
                                ("notation", "Notation", 8)),
                    {"definition": 1, "example": 1, "exercise": 3}, ("definitions", "examples"),
                    "A textbook-style chapter: definitions and results with proofs, worked examples with every step, "
                    "exercises with full solutions, and a notation table."),
    "literature": Kind("literature", (("question", "The question", 15), ("coverage", "What was searched", 30),
                                      ("evidence", "What the sources say", 100), ("synthesis", "Synthesis", 60),
                                      ("gaps", "Gaps and null results", 30), ("next", "What to read next", 8)),
                       {}, ("evidence", "synthesis"),
                       "A literature brief for the researcher's judgement: the question as asked, which searches were "
                       "run, what each verified source says with its locator, competing models and null results, the "
                       "gaps, and what to read next. Say plainly what was not found. If the evidence supports a test, end by proposing "
                       "the experiment: add_node experiment:<key> with a title, the plan, the scale ladder (smallest "
                       "rung first), a compute budget and authorization 'awaiting'. The researcher approves it; you "
                       "never do."),
    "findings": Kind("findings", (("plan", "Plan and approval", 20), ("results", "Results", 60),
                                  ("claims", "Claims and their audits", 40), ("interpretation", "Interpretation", 60),
                                  ("limitations", "Limitations", 30), ("decision", "Decision memo (a proposal)", 20)),
                     {}, ("results", "claims", "interpretation"),
                     "A findings handout for the researcher's decision: the approved plan, the results with the files "
                     "and numbers they come from, each claim with its audit chain, the interpretation, the limits, and "
                     "a decision memo that is labelled a proposal. The researcher decides."),
}


# ---- the source file ----------------------------------------------------------------------------------------------
def hid(key: str) -> str:
    return key if key.startswith("handout:") else f"handout:{key}"


def folder(rec: Record, handout: str) -> Path:
    key = hid(handout).split(":", 1)[1]
    if not KEY.fullmatch(key):
        raise ValueError("a handout key is letters, digits, dot, dash or underscore")
    return rec.root / "handouts" / key


def load(rec: Record, handout: str) -> dict:
    path = folder(rec, handout) / "source.json"
    if not path.exists():
        raise KeyError(f"no handout {handout}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save(rec: Record, src: dict) -> None:
    d = folder(rec, src["id"])
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "source.json.tmp"
    tmp.write_text(json.dumps(src, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(d / "source.json")
    (d / "manifest.json").unlink(missing_ok=True)  # any change voids the last verdict


def _lib():
    from .lib import pdf  # the engine is optional and loaded only when a handout is read or built
    return pdf


def meta(rec: Record, src: dict) -> dict:
    lay = vault.layout(rec)
    hub = src.get("hub")
    course = (rec.node(hub) or {}).get("title") if hub else None
    return {"title": src["title"], "course": course or (lay["title"] if not lay["is_user"] else ""), "date": date.today().isoformat(),
            "line": f"{src['kind'].capitalize()} handout", "subtitle": ""}


def current_hash(rec: Record, src: dict) -> str:
    return _lib().source_hash(meta(rec, src) | {"date": ""}, src["sections"], src.get("sources", []))


# ---- composing the context ----------------------------------------------------------------------------------------
def _scope_caps(rec: Record, scope: list[str]) -> list[str]:
    caps: list[str] = []
    for s in scope:
        node = rec.node(s)
        if node and node["type"] == "capability":
            caps.append(s)
        elif node:
            caps += [e["src"] for e in rec.edges(dst=s, type="part-of") + rec.edges(dst=s, type="about")
                     if e["src"].startswith("capability:")]
    return list(dict.fromkeys(caps))[:40]


def _clip(text, n=400) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


def compose(rec: Record, kind: str, scope: list[str]) -> dict:
    """What the record knows that the handout is about, bounded: the agent reads this, then writes."""
    ctx: dict = {"scope": scope}
    if kind in ("lecture", "recitation", "chapter"):
        caps = _scope_caps(rec, scope)
        if caps:
            learning = graph.Learning(rec, within=caps)
            rows = []
            for c in caps:
                if c in learning.caps:
                    v = learning.view(c)
                    rows.append({"id": c, "title": v["title"], "state": v["state"],
                                 "requires": [(rec.node(p) or {}).get("title", p) for p in v["prerequisites"]]})
            ctx["capabilities"] = rows
        narration = []
        for b in prepare.bundles(rec):
            plan = prepare.load_plan(rec, b["id"])
            if any(n["id"] in caps for n in plan["nodes"]):
                for n in plan["nodes"]:
                    for seg in n.get("segments", []):
                        narration.append({"node": n["id"], "text": _clip(seg.get("text"), 600),
                                          "claims": [c.get("text") for c in seg.get("claims", []) if isinstance(c, dict)]})
        ctx["narration"] = narration[:30]
        ctx["prompts"] = [{"capability": c, "prompt": _clip(i.get("prompt"), 200)}
                          for c in caps[:12] for i in [x for x in rec.items(c) if not x.get("defence")][:3]]
    elif kind == "literature":
        ctx["questions"] = [{"id": n["id"], "title": n.get("title") or n.get("text")}
                            for n in (rec.node(s) for s in scope) if n]
        srcs = rec.nodes(type="paper") + rec.nodes(type="source")
        ctx["sources"] = [{k: n.get(k) for k in ("id", "title", "authors", "year", "doi", "url", "path", "status",
                                                 "screening", "verified") if n.get(k) is not None}
                          for n in srcs[:60]]
        ctx["scouted"] = [{"task": t["id"], "kind": t["kind"], "result": _clip(json.dumps(t.get("result"), ensure_ascii=False), 500)}
                          for t in tasks.tasks(rec, state="done") if t["kind"] in ("scout", "verify", "ingest")][:30]
        ctx["hypotheses"] = [{"id": n["id"], "title": n.get("title") or n.get("text")} for n in rec.nodes(type="hypothesis")][:20]
    else:  # findings
        exps = [rec.node(s) for s in scope if (rec.node(s) or {}).get("type") == "experiment"]
        ctx["experiments"] = [{k: v for k, v in n.items() if isinstance(v, (str, int, float, bool))} for n in exps if n]
        ctx["approvals"] = [{"subject": e["subject"], "decision": e["data"].get("decision"), "by": e["actor"],
                             "note": _clip(e["data"].get("note"), 200)} for e in rec.events(type="approval")][-10:]
        claims = []
        for c in research.claims(rec)[:30]:
            st = research.status(rec, c["id"])
            claims.append({"id": c["id"], "text": c["text"], "verdict": st["verdict"], "ownership": st["ownership"],
                           "steps": {k: {"verdict": v["verdict"], "by": v["by"], "notes": _clip(v.get("notes"), 300)}
                                     for k, v in st["verdicts"].items()},
                           "artifacts": (rec.node(c["id"]) or {}).get("artifacts", [])})
        ctx["claims"] = claims
        ctx["decisions"] = [{"subject": e["subject"], "outcome": e["data"].get("outcome"), "by": e["actor"]}
                            for e in rec.events(type="decision")][-10:]
    text = json.dumps(ctx, ensure_ascii=False)
    if len(text) > MAX_CONTEXT:  # keep it readable: drop the longest lists first
        for k in sorted(ctx, key=lambda k: -len(json.dumps(ctx[k], ensure_ascii=False))):
            if isinstance(ctx[k], list):
                ctx[k] = ctx[k][:len(ctx[k]) // 2]
                if len(json.dumps(ctx, ensure_ascii=False)) <= MAX_CONTEXT:
                    break
    return ctx


# ---- tools' domain functions --------------------------------------------------------------------------------------
def create(rec: Record, kind: str, scope: list[str], title: str, key: str | None = None,
           hub: str | None = None) -> dict:
    """Start a handout: compose its context, lay out its sections and open the task that asks an agent to write it.
    Asking again for the same key changes nothing."""
    if kind not in KINDS:
        raise ValueError(f"kind is one of {', '.join(KINDS)}")
    if not title.strip():
        raise ValueError("a handout has a title")
    if not (isinstance(scope, list) and scope and all(isinstance(s, str) and ":" in s for s in scope)):
        raise ValueError("scope is a list of node ids: capabilities, a course or subject, a question, an experiment")
    key = key or re.sub(r"[^A-Za-z0-9]+", "-", f"{kind}-{title}").strip("-").lower()[:48]
    handout = hid(key)
    if (folder(rec, handout) / "source.json").exists():
        return {**describe(rec, handout), "existing": True}
    spec = KINDS[kind]
    src = {"schema": SCHEMA, "id": handout, "kind": kind, "title": title.strip(), "scope": scope,
           "hub": hub or vault.layout(rec)["hub_id"], "revision": 0, "created": date.today().isoformat(),
           "sections": [{"id": r, "role": r, "title": t, "text": "", "locators": [], "derivation": False, "by": ""}
                        for r, t, _ in spec.sections], "sources": [], "context": compose(rec, kind, scope)}
    _save(rec, src)
    _node(rec, src, "draft")
    task = tasks.open_task(rec, "handout", handout, brief(rec, src), data={"handout": handout, "kind": kind,
                                                                          "row": "all"}, key="create")
    return {**describe(rec, handout, with_context=True), "tasks": [task]}


def read(rec: Record, handout: str) -> dict:
    """The whole source: the sections as written, the sources, the context they are written from."""
    return load(rec, handout)


def brief(rec: Record, src: dict) -> str:
    spec = KINDS[src["kind"]]
    secs = "; ".join(f"{t} (at least {m} words)" for _, t, m in spec.sections)
    boxes = ", ".join(f"{n} {k}" for k, n in spec.counts.items())
    return (f"Write the {src['kind']} handout {src['title']!r} ({src['id']}). {spec.brief} Sections: {secs}."
            + (f" It needs at least {boxes} boxes." if boxes else "")
            + " Write each with handout_write (Markdown, LaTeX math in $...$, boxes as :::kind), give a source locator or "
              "mark a derivation for every factual section, add the sources with their keys and cite them as [@key], "
              "then run handout_check. Read the context in the source first. Never put an answer key from an "
              "assessment item into a handout.")


def describe(rec: Record, handout: str, with_context: bool = False) -> dict:
    src = load(rec, handout)
    spec = KINDS[src["kind"]]
    words = {s["id"]: len(s["text"].split()) for s in src["sections"]}
    return {"handout": src["id"], "kind": src["kind"], "title": src["title"], "revision": src["revision"],
            "sections": [{"id": s["id"], "title": s["title"], "words": words[s["id"]],
                          "min_words": next((m for r, _, m in spec.sections if r == s["role"]), 0),
                          "by": s["by"] or None} for s in src["sections"]],
            "boxes_needed": spec.counts, "sources": [x["key"] for x in src.get("sources", [])],
            "source_hash": current_hash(rec, src), **({"context": src["context"]} if with_context else {})}


def write(rec: Record, handout: str, section: str, text: str, by: str, title: str | None = None,
          locators: list | None = None, derivation: bool | None = None, sources: list | None = None) -> dict:
    """Write one section (replacing its text), the sources it cites and the locators that ground it."""
    if not (by or "").strip():
        raise ValueError("a section names who wrote it (by)")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("a section has text")
    src = load(rec, handout)
    sec = next((s for s in src["sections"] if s["id"] == section), None)
    if sec is None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", section) or not title:
            raise ValueError(f"{section!r} is not a section of this handout ({', '.join(s['id'] for s in src['sections'])}); "
                             "to add one, give a lowercase id and a title")
        sec = {"id": section, "role": section, "title": title, "text": "", "locators": [], "derivation": False, "by": ""}
        src["sections"].append(sec)
    if title:
        sec["title"] = title
    sec["text"], sec["by"] = text.strip() + "\n", by.strip()
    if locators is not None:
        sec["locators"] = [str(x) for x in locators]
    if derivation is not None:
        sec["derivation"] = bool(derivation)
    for s in sources or []:
        if not (isinstance(s, dict) and re.fullmatch(r"[A-Za-z0-9_:-]+", str(s.get("key", ""))) and str(s.get("text", "")).strip()):
            raise ValueError("a source is {key, text}: the key is letters, digits, dash or underscore")
        src["sources"] = [x for x in src["sources"] if x["key"] != s["key"]] + [{"key": s["key"], "text": str(s["text"]).strip()}]
    src["revision"] += 1
    _save(rec, src)
    sha = hashlib.sha256(sec["text"].encode()).hexdigest()[:16]
    rec.append("handout.revise", src["id"], {"section": section, "by": by, "sha": sha, "words": len(sec["text"].split()),
                                            "revision": src["revision"]}, actor=by)
    return {"handout": src["id"], "section": section, "words": len(sec["text"].split()), "revision": src["revision"],
            "source_hash": current_hash(rec, src)}


def add_file(rec: Record, handout: str, path: str, text: str | None = None, data: str | None = None) -> dict:
    """Put an image the sections refer to (``figures/x.png``) beside the source."""
    d = folder(rec, handout)
    load(rec, handout)
    target = (d / path).resolve()
    if (d / "figures").resolve() not in target.parents or target.suffix.lower() not in _lib().FIGURE_TYPES:
        raise ValueError("a figure is a pdf, png, jpg or svg file inside figures/")
    if (text is None) == (data is None):
        raise ValueError("give exactly one of text or base64")
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = text.encode("utf-8") if text is not None else base64.b64decode(data, validate=True)
    target.write_bytes(raw)
    (d / "manifest.json").unlink(missing_ok=True)
    return {"path": path, "bytes": len(raw)}


# ---- the gate -----------------------------------------------------------------------------------------------------
@dataclass
class Doc:
    rec: Record
    src: dict
    dir: Path
    kind: Kind


@dataclass(frozen=True)
class Row:
    """One gate row: ``check(doc)`` returns ``(problems, warnings)``. A failing row opens a ``handout`` task. To add a
    check, append a ``Row`` to ``ROWS``."""
    name: str
    check: Callable[[Doc], tuple[list[str], list[str]]]


def _texts(d: Doc):
    return [(s["title"], s.get("text") or "") for s in d.src["sections"] if (s.get("text") or "").strip()]


def _sources(d: Doc):
    problems, warnings = [], []
    keys = {s["key"] for s in d.src.get("sources", [])}
    if not keys:
        problems.append("no sources: add them with handout_write sources=[{key, text}] and cite them as [@key]")
    cited = set()
    for title, text in _texts(d):
        for m in CITE.finditer(text):
            cited |= {k.strip().lstrip("@") for k in m.group(1).split(";")}
    problems += [f"[@{k}] is cited but is not among the sources" for k in sorted(cited - keys)]
    warnings += [f"source {k} is never cited" for k in sorted(keys - cited)]
    for s in d.src["sections"]:
        if s["role"] in d.kind.factual and (s.get("text") or "").strip() and not (s.get("locators") or s.get("derivation")):
            problems.append(f"{s['title']}: give a source locator for what it states, or mark it a derivation "
                            "(locators=[...] or derivation=true)")
    return problems, warnings


def _hidden_strings(d: Doc) -> list[str]:
    """Text of answer keys of the items this handout's subject is tested by: it must not appear in the handout."""
    out: list[str] = []
    ids = set(d.src["scope"])
    ids |= {c["id"] for c in d.src.get("context", {}).get("capabilities", [])}
    ids |= {c["id"] for c in d.src.get("context", {}).get("claims", [])}
    for node in ids:
        for it in d.rec.items(node):
            for v in (it.get("explanation"), *(it.get("option_feedback") or []), it.get("feedback_wrong")):
                if isinstance(v, str) and len(v.strip()) >= 25:
                    out.append(v)
            out += [c for c in (it.get("rubric") or {}).get("criteria", []) if isinstance(c, str) and len(c) >= 25]
            if isinstance(it.get("answer"), str) and len(it["answer"]) >= 25:
                out.append(it["answer"])
    return out


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _no_keys(d: Doc):
    body = _norm(" ".join(t for _, t in _texts(d)))
    return [f"contains text from an assessment item's answer key ({_norm(h)[:50]}…): a handout teaches, "
            "it does not hand out the answers to the questions you are tested on"
            for h in _hidden_strings(d) if _norm(h) in body][:5], []


def _math(d: Doc):
    pdf, problems = _lib(), []
    for title, text in _texts(d):
        problems += [f"{title}: {p}" for p in pdf.lint_math(pdf.math_spans(text))]
        problems += prepare._math_problems(text, title)
    return list(dict.fromkeys(problems)), []


def _structure(d: Doc):
    pdf, problems, warnings = _lib(), [], []
    counts: dict[str, int] = {}
    for s in d.src["sections"]:
        text = (s.get("text") or "").strip()
        want = next((m for r, _, m in d.kind.sections if r == s["role"]), 0)
        if not text:
            if any(r == s["role"] for r, _, _ in d.kind.sections):
                problems.append(f"{s['title']}: not written yet")
            continue
        if len(text.split()) < want:
            problems.append(f"{s['title']}: {len(text.split())} words; at least {want} are expected")
        bad = UNFINISHED.search(text)
        if bad:
            problems.append(f"{s['title']}: an unfinished marker ({bad.group(0)})")
        for b in pdf._walk(pdf.parse(text)):
            if b["t"] == "box":
                counts[b["kind"]] = counts.get(b["kind"], 0) + 1
                if b["kind"] in ("exercise", "question") and not b["extra"]:
                    problems.append(f"{s['title']}: a {b['kind']} has no solution (add '=== solution')")
    for kind, n in d.kind.counts.items():
        if counts.get(kind, 0) < n:
            problems.append(f"needs at least {n} :::{kind} box(es); has {counts.get(kind, 0)}")
    if d.src["kind"] in ("lecture", "chapter", "recitation") and not counts.get("example") and not counts.get("exercise"):
        warnings.append("no worked example or exercise: a handout teaches with at least one")
    return problems, warnings


def _figures(d: Doc):
    pdf, problems = _lib(), []
    for title, text in _texts(d):
        for b in pdf._walk(pdf.parse(text)):
            if b["t"] == "img":
                src = b["src"]
                if src.startswith(("http:", "https:", "/", "\\")) or ".." in src or ":" in src:
                    problems.append(f"{title}: figure {src!r} must be a file in figures/")
                elif not (d.dir / src).is_file():
                    problems.append(f"{title}: figure {src!r} is missing (add it with handout_file)")
    return problems, []


def _pdf(d: Doc):
    h = current_hash(d.rec, d.src)
    if d.rec.events(type="handout.built", subject=d.src["id"]) and any(
            e["data"].get("hash") == h for e in d.rec.events(type="handout.built", subject=d.src["id"])):
        return [], []
    return [], ["no PDF for this version yet (the Markdown note is the primary copy; the PDF is built by a job)"]


def _review(d: Doc):
    if d.rec.events(type="note.reviewed", subject=d.src["id"]):
        return [], []
    return [], ["agent-written and not yet read by you: it is marked a draft until you mark it reviewed"]


ROWS: list[Row] = [Row("sources", _sources), Row("no keys", _no_keys), Row("math", _math),
                   Row("structure", _structure), Row("figures", _figures), Row("pdf", _pdf), Row("review", _review)]
ADVISORY = {"pdf", "review"}  # warnings only: they never keep a handout from being ready


def verdict(rec: Record, handout: str) -> dict:
    src = load(rec, handout)
    d = Doc(rec, src, folder(rec, handout), KINDS[src["kind"]])
    rows = []
    for row in ROWS:
        problems, warnings = row.check(d)
        rows.append({"row": row.name, "ok": not problems, "problems": problems, "warnings": warnings})
    ready = all(r["ok"] for r in rows if r["row"] not in ADVISORY)
    return {"handout": src["id"], "source_hash": current_hash(rec, src), "rows": rows, "ready": ready,
            "missing": [f"{r['row']}: {x}" for r in rows for x in r["problems"]],
            "warnings": [f"{r['row']}: {x}" for r in rows for x in r["warnings"]]}


def check(rec: Record, handout: str, open_tasks: bool = True) -> dict:
    """Run the gate, store its verdict, update the handout's status and ask an agent for what is missing (once per
    distinct problem)."""
    v = verdict(rec, handout)
    d = folder(rec, handout)
    (d / "manifest.json").write_text(json.dumps(v, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    src = load(rec, handout)
    built = any(e["data"].get("hash") == v["source_hash"] for e in rec.events(type="handout.built", subject=src["id"]))
    _node(rec, src, "built" if built else "ready" if v["ready"] else "draft", v["source_hash"])
    v["tasks"] = []
    if open_tasks and not v["ready"] and any((s.get("text") or "").strip() for s in src["sections"]):
        for r in v["rows"]:
            if not r["ok"] and r["row"] not in ADVISORY:
                v["tasks"].append(tasks.open_task(
                    rec, "handout", src["id"], f"Handout {src['title']!r}: {r['row']}: " + "; ".join(r["problems"][:6]),
                    data={"handout": src["id"], "row": r["row"]}, key=f"{r['row']}|{'|'.join(r['problems'])}"))
    return v


# ---- the note, the build and the PDF ------------------------------------------------------------------------------
def markdown(rec: Record, src: dict) -> str:
    """The handout as Markdown for Obsidian: boxes as callouts, solutions and answers collapsed."""
    pdf = _lib()
    out = [f"# {src['title']}", ""]
    for s in src["sections"]:
        if (s.get("text") or "").strip():
            out += [f"## {s['title']}", "", pdf.to_obsidian(pdf.parse(s["text"])), ""]
    if src.get("sources"):
        out += ["## Sources", "", *[f"- **[{x['key']}]** {x['text']}" for x in src["sources"]], ""]
    return "\n".join(out)


def _node(rec: Record, src: dict, status: str, sha: str | None = None, pdf: str | None = None) -> None:
    old = rec.node(src["id"]) or {}
    node = {"id": src["id"], "type": "handout", "title": src["title"], "kind": src["kind"], "status": status,
            "dir": f"handouts/{src['id'].split(':', 1)[1]}", "revision": src["revision"]}
    for k, v in (("source_hash", sha or old.get("source_hash")), ("pdf", pdf or old.get("pdf"))):
        if v:
            node[k] = v
    if old != node:
        rec.put_nodes([node])
    wanted = [(t, "about") for t in src["scope"] if rec.node(t)]
    hub = src.get("hub")
    if hub and rec.node(hub):
        wanted.append((hub, "about"))
    have = {e["dst"] for e in rec.edges(src=src["id"], type="about")}
    new = [{"src": src["id"], "type": "about", "dst": t} for t, _ in wanted if t not in have]
    if new:
        rec.put_edges(new)


def _note_stub(rec: Record, src: dict, status: str, pdf_rel: str | None):
    body_md = markdown(rec, src)
    authors = sorted({s["by"] for s in src["sections"] if s["by"]})

    def build(ctx):
        head = []
        if pdf_rel:
            head += [f"![[{pdf_rel}]]", ""]
        head += [f"> [!warning] Draft by {', '.join(authors) or 'an agent'}",
                 "> Written from the record by an agent. Read it, then mark it reviewed with `ros vault_resolve "
                 f"--target {src['id']} --action reviewed` or set `ros_status: reviewed` above.", ""]
        extra = {"handout_kind": src["kind"], "status": status,
                 "capabilities": [ctx.link(c) for c in src["scope"] if c.startswith("capability:")][:20]}
        if pdf_rel:
            extra["pdf"] = vault.wikilink(pdf_rel)
        return extra, ["ros/handout", f"handout/{src['kind']}"], "\n".join(head) + body_md + (
            f"\n\n[Open in the portal]({ctx.portal(src['id'])})")
    return vault.custom_stub(rec, src["id"], "handout", "Handouts", src["title"], build, hub=src.get("hub"))


def publish_note(rec: Record, handout: str, pdf_rel: str | None = None) -> dict | None:
    """Write the handout's note into the vault (if one is set): the primary copy, as soon as there is text."""
    src = load(rec, handout)
    if not vault.configured() or not any((s.get("text") or "").strip() for s in src["sections"]):
        return None
    node = rec.node(src["id"]) or {}
    pdf_rel = pdf_rel or node.get("pdf")
    return vault.put_note(rec, _note_stub(rec, src, node.get("status", "draft"), pdf_rel))


def build(rec: Record, handout: str, wait: bool = False, engine: str | None = None) -> dict:
    """Deliver the handout: its note now, and its PDF as a queued job (or at once with ``wait``). The note is written
    whenever there is text; the PDF is built only for a version the gate passes."""
    v = check(rec, handout)
    src = load(rec, handout)
    note = publish_note(rec, handout)
    out = {"handout": src["id"], "ready": v["ready"], "source_hash": v["source_hash"], "missing": v["missing"],
           "warnings": v["warnings"], "note": note["path"] if note else None, "tasks": v["tasks"]}
    if not v["ready"]:
        out["pdf"] = None
        out["why"] = "the PDF is built when the gate passes: " + ("; ".join(v["missing"][:3]) or "nothing is written yet")
        return out
    sha = v["source_hash"]
    work = folder(rec, handout) / "build" / sha
    existing = work / "out" / f"{sha}.pdf"
    if existing.exists():  # one version is built once
        out["pdf"] = _attach(rec, src, sha)["pdf"]
        return out
    pdf = _lib()
    work.mkdir(parents=True, exist_ok=True)
    m = meta(rec, src)
    (work / "index.html").write_text(pdf.html_document(m, src["sections"], src["sources"]), encoding="utf-8", newline="\n")
    (work / "main.tex").write_text(pdf.tex_document(m, src["sections"], src["sources"]), encoding="utf-8", newline="\n")
    (work / "roshandout.sty").write_bytes((pdf.ASSETS / "roshandout.sty").read_bytes())
    figs = folder(rec, handout) / "figures"
    if figs.is_dir():
        import shutil
        shutil.copytree(figs, work / "figures", dirs_exist_ok=True)
    engine = engine or home.settings().get("pdf_engine") or "auto"
    argv = [sys.executable, "-m", "ros.lib.pdf", "build", "--dir", str(work), "--source", sha, "--engine", engine]
    job = tasks.open_task(rec, "job", src["id"], f"Build the PDF of {src['title']!r} ({engine})",
                          data={"argv": argv, "cwd": str(work), "timeout": 300, "handout": src["id"],
                                "source_hash": sha, "pythonpath": str(Path(__file__).resolve().parents[1]),
                                "then": {"tool": "handout_attach", "args": {"handout": src["id"], "source_hash": sha}}},
                          key=sha)
    out["job"] = job
    if wait:
        res = pdf.build(work, sha, engine)
        (work / "result.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
        out.update(attach(rec, handout, sha))
        if (j := tasks.get(rec, job))["state"] in ("open", "claimed"):
            tasks.finish(rec, job, {"ok": res["ok"], "engine": res.get("engine")}, by="ros")
    return out


def attach(rec: Record, handout: str, source_hash: str | None = None) -> dict:
    """Attach the PDF a job built for one version: verify it, record it once, place it in the vault, link it from the
    note. A build that failed or found no toolchain is reported and waits (it never fails the handout)."""
    src = load(rec, handout)
    sha = source_hash or current_hash(rec, src)
    work = folder(rec, handout) / "build" / sha
    try:
        res = json.loads((work / "result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"handout": src["id"], "pdf": None, "built": False, "why": "no build result yet for this version"}
    if not res.get("ok"):
        return {"handout": src["id"], "pdf": None, "built": False, "problems": res.get("problems", []),
                "missing_toolchain": bool(res.get("missing")), "tried": res.get("tried", [])}
    return {"handout": src["id"], "built": True, **_attach(rec, src, sha, res)}


def _attach(rec: Record, src: dict, sha: str, res: dict | None = None) -> dict:
    work = folder(rec, src["id"]) / "build" / sha
    pdf = work / "out" / f"{sha}.pdf"
    if res is None:
        res = json.loads((work / "result.json").read_text(encoding="utf-8")) if (work / "result.json").exists() else {}
    if not pdf.is_file() or (res.get("sha256") and hashlib.sha256(pdf.read_bytes()).hexdigest() != res["sha256"]):
        return {"pdf": None}
    rec.append("handout.built", src["id"], {"hash": sha, "engine": res.get("engine"), "pages": res.get("pages"),
                                           "bytes": pdf.stat().st_size, "path": str(pdf.relative_to(rec.root))},
               actor="ros", id=event_id("handout.built", f"{rec.root.name}|{src['id']}|{sha}"))
    rel = None
    if vault.configured():
        lay = vault.layout(rec)
        rel = vault.place(rec, pdf, src["id"], lay["title"], src["title"])
    _node(rec, src, "built", sha, rel)
    if rel:
        publish_note(rec, src["id"], rel)
    return {"pdf": str(pdf), "vault_pdf": rel, "engine": res.get("engine"), "pages": res.get("pages")}


def handouts(rec: Record) -> list[dict]:
    """Every handout of the record with its status, newest revision first."""
    return [{"id": n["id"], "title": n.get("title"), "kind": n.get("kind"), "status": n.get("status"),
             "revision": n.get("revision"), "pdf": n.get("pdf")} for n in rec.nodes(type="handout")]


def toolchain() -> dict:
    """What this computer can build a PDF with (``python -m ros.lib.pdf detect``)."""
    return _lib().detect()
