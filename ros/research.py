"""Research on the record: a claims ledger, the audit chain with six-state verdicts, human approvals and decisions, a
commitment ledger, and the defence bridge that turns each audited claim into things the researcher must be able to
defend, then tracks whether they can.

The researcher works at four points: frame, approve the plan, defend, decide. Everything between them is agent work
(tasks) that finishes in the decision queue. Three rules are enforced here, not left to good intentions:

* The executor never judges its own work: a verdict on a claim by the claim's author is refused.
* An auditor sees the claim and file paths only, never the author's reasoning: the audit task carries nothing else.
* Approvals, decisions, waivers and applying proposals are human acts: tools marked ``human`` are not offered over MCP,
  and the CLI asks for confirmation at a terminal.
"""
from __future__ import annotations

from datetime import date
import csv
import re
from pathlib import Path

from . import tasks, graph
from .store import Record

VERDICTS = ("PASS", "WARN", "FAIL", "BLOCKED", "ERROR", "NOT_APPLICABLE")
STEPS = ("integrity", "result-claim", "numbers", "citations", "kill-argument")
ASSURANCE = {"draft": ("numbers",),
             "internal": ("integrity", "result-claim", "numbers"),
             "presentation": ("integrity", "result-claim", "numbers", "citations", "kill-argument"),
             "submission": STEPS}
FAILURE_MODES = ("implementation-bug-passing-self-review", "hallucinated-citation", "hallucinated-result",
                 "shortcut-reliance", "bug-reframed-as-insight", "methodology-fabrication", "early-frame-lock")
DEFENCE = ("derivation", "baseline", "falsifier", "rejection", "code")
DEFENCE_BRIEF = {
    "derivation": "Derive the method behind the claim from what it rests on.",
    "baseline": "Why this baseline, and what a weaker or stronger one would change.",
    "falsifier": "What observation would falsify the claim.",
    "rejection": "The strongest argument for rejecting the claim (from the adversary) and its answer.",
    "code": "Where in the code the number comes from (file and function).",
}
OWNERSHIP_NEEDED = {"presentation", "submission"}


# ---- the ledger ---------------------------------------------------------------------------------------------------
def add_claim(rec: Record, key: str, text: str, project: str, author: str, assurance: str = "internal",
              numbers: list[dict] | None = None, artifacts: list[str] | None = None,
              citations: list[str] | None = None, experiment: str | None = None,
              question: str | None = None) -> dict:
    """A claim the project makes. ``numbers`` are ``{"value", "file", "column"|"key"}`` (paths relative to the project
    root) and are checked deterministically before any audit; ``artifacts`` are the files auditors read. ``experiment``
    (the experiment that produced it) or ``question`` (the question it answers) links the claim to that work, so only
    that work's stage reads it; a claim linked to neither counts for no question."""
    if assurance not in ASSURANCE:
        raise ValueError(f"assurance is one of {list(ASSURANCE)}")
    for link, kind in ((experiment, "experiment"), (question, "question")):
        if link and (rec.node(link) or {}).get("type") != kind:
            raise ValueError(f"{link} is not a recorded {kind}")
    cid = key if key.startswith("claim:") else f"claim:{key}"
    old = rec.node(cid) or {}
    node = {**old, "id": cid, "type": "claim", "text": text, "project": project, "author": author,
            "assurance": assurance, "numbers": numbers or [], "artifacts": artifacts or [],
            "citations": citations or []}
    rec.put_nodes([node])
    if not rec.edges(src=cid, type="part-of", dst=f"project:{project}"):
        rec.put_edge(cid, "part-of", f"project:{project}")
    for link, relation in ((experiment, "results"), (question, "answers")):
        if link and not any(e.get("relation") == relation for e in rec.edges(src=cid, type="relates", dst=link)):
            rec.put_edge(cid, "relates", link, relation=relation)
    return node


def claims(rec: Record, project: str | None = None, as_of: date | None = None) -> list[dict]:
    out, practice = [], Practice(rec, as_of)
    for n in rec.nodes(type="claim"):
        if project and n.get("project") != project:
            continue
        s = status(rec, n["id"], as_of, practice)
        out.append({"id": n["id"], "text": n.get("text"), "assurance": n.get("assurance"), "verdict": s["verdict"],
                    "owned": s["ownership"] in ("owned", "waived"), "ownership": s["ownership"],
                    "missing": s["missing"]})
    return out


# ---- the audit chain ----------------------------------------------------------------------------------------------
def precheck_numbers(rec: Record, claim: str, root: Path) -> dict:
    """Every cited number must be found in its named result file before a model is asked anything. Writes a
    ``numbers`` verdict by ``ros``: PASS, FAIL (with each missing number), or when nothing is cited NOT_APPLICABLE for a draft and WARN above it."""
    node = _claim(rec, claim)
    missing = []
    for n in node.get("numbers", []):
        path = (Path(root) / n.get("file", "")).resolve()
        if Path(root).resolve() not in path.parents or not path.is_file():
            missing.append(f"{n.get('file')}: no such result file")
            continue
        if not _number_in(path, n):
            missing.append(f"{n.get('value')} not found in {n.get('file')}"
                           + (f" ({n.get('column') or n.get('key')})" if n.get("column") or n.get("key") else ""))
    if not node.get("numbers"):
        # nothing to check is fine for a draft; above it, say so instead of passing silently
        verdict, missing = ("NOT_APPLICABLE", ["no numbers cited"]) if node.get("assurance") == "draft" else (
            "WARN", ["no numbers cited: the pre-check had nothing to verify"])
    else:
        verdict = "FAIL" if missing else "PASS"
    return record_verdict(rec, claim, "numbers", verdict, by="ros", notes="; ".join(missing),
                          _system=True)


def request_audits(rec: Record, claim: str) -> list[str]:
    """Open one audit task per required step that has no verdict yet. The task carries the claim's text and its
    file paths, and nothing of the author's reasoning."""
    node = _claim(rec, claim)
    have = latest_verdicts(rec, claim)
    opened = []
    for step in ASSURANCE[node["assurance"]]:
        if step in have or step == "numbers":
            continue
        kind = "verify" if step == "citations" else "audit"
        brief = (f"{step} audit of a claim. Read the files cold and return one verdict of "
                 f"{', '.join(VERDICTS)} with notes. Claim: {node['text']}")
        if step == "integrity":
            brief += " Also mark each failure mode ok or concern: " + ", ".join(FAILURE_MODES) + "."
        if step == "kill-argument":
            brief += " Write the strongest rejection memo; the author answers it point by point."
        opened.append(tasks.open_task(rec, kind, claim, brief,
                                      data={"claim": claim, "step": step, "text": node["text"],
                                            "paths": node.get("artifacts", []), "citations": node.get("citations", [])},
                                      key=f"{step}|{node['text']}"))
    return opened


def record_verdict(rec: Record, claim: str, step: str, verdict: str, by: str, notes: str = "",
                   checklist: dict | None = None, evidence: list[str] | None = None, _system: bool = False) -> dict:
    node = _claim(rec, claim)
    if step not in STEPS:
        raise ValueError(f"step is one of {list(STEPS)}")
    if step not in ASSURANCE[node["assurance"]]:
        raise ValueError(f"a {node['assurance']} claim does not require the {step} step "
                         f"(it requires {', '.join(ASSURANCE[node['assurance']])}); raise the assurance first")
    if verdict not in VERDICTS:
        raise ValueError(f"verdict is one of {list(VERDICTS)}")
    by = (by or "").strip()
    if not by:
        raise ValueError("a verdict names who gives it")
    if not _system:
        if by.casefold() == "ros":
            raise ValueError("'ros' is the name of the mechanical pre-check; give your own name")
        if by.casefold() == str(node.get("author") or "").strip().casefold():
            raise ValueError("the claim's author cannot audit it: a fresh reviewer must")
        last = latest_verdicts(rec, claim).get(step)
        if step == "numbers" and last and last["by"] == "ros" and last["verdict"] == "FAIL":
            raise ValueError("the mechanical pre-check of the numbers failed (" + (last.get("notes") or "see claim_status")
                             + "): correct the claim or its files and run precheck again; a verdict cannot override it")
    if verdict in ("BLOCKED", "ERROR", "NOT_APPLICABLE") and not notes.strip():
        raise ValueError(f"a {verdict} verdict says why in its notes")
    if checklist:
        bad = {k: v for k, v in checklist.items() if k not in FAILURE_MODES or v not in ("ok", "concern")}
        if bad:
            raise ValueError(f"the checklist marks each of {', '.join(FAILURE_MODES)} as ok or concern; got {bad}")
    if step == "integrity" and verdict in ("PASS", "WARN"):
        missing = [m for m in FAILURE_MODES if (checklist or {}).get(m) not in ("ok", "concern")]
        if missing:
            raise ValueError("an integrity verdict marks every failure mode ok or concern; missing: " + ", ".join(missing))
        if verdict == "PASS" and any(v == "concern" for v in checklist.values()):
            raise ValueError("a failure-mode concern makes the integrity verdict WARN or FAIL, not PASS")
    data = {"step": step, "verdict": verdict, "notes": notes}
    if checklist:
        data["checklist"] = checklist
    if evidence:
        data["evidence"] = evidence
    rec.append("verdict", claim, data, actor=by)
    for t in tasks.tasks(rec, state=None):
        if t.get("claim") == claim and t.get("step") == step and t["state"] in ("open", "claimed", "paused"):
            tasks.finish(rec, t["id"], {"verdict": verdict}, by=by)
    if verdict in ("PASS", "WARN") and status(rec, claim)["verdict"] in ("PASS", "WARN"):
        open_defence(rec, claim)  # the queue asks for a defence of a WARN claim too, so the items must exist
    return {"claim": claim, "step": step, "verdict": verdict}


def latest_verdicts(rec: Record, claim: str) -> dict[str, dict]:
    out = {}
    for e in rec.events(type="verdict", subject=claim):
        out[e["data"]["step"]] = {**e["data"], "by": e["actor"], "ts": e["ts"]}
    return out


def status(rec: Record, claim: str, as_of: date | None = None, practice: "Practice | None" = None) -> dict:
    """The claim's overall verdict over its required steps (worst wins; missing steps leave it PENDING), its
    ownership, and whether its assurance level is met."""
    node = _claim(rec, claim)
    required = ASSURANCE[node["assurance"]]
    have = latest_verdicts(rec, claim)
    order = ("ERROR", "BLOCKED", "FAIL", "WARN", "PASS", "NOT_APPLICABLE")
    missing = [s for s in required if s not in have]
    verdicts = [have[s]["verdict"] for s in required if s in have]
    worst = min(verdicts, key=order.index) if verdicts else None
    overall = worst if worst in ("ERROR", "BLOCKED", "FAIL") else "PENDING" if missing else (
        "WARN" if worst == "WARN" else "PASS")
    own = ownership(rec, claim, as_of, practice)
    met = overall in ("PASS", "WARN") and (node["assurance"] not in OWNERSHIP_NEEDED or own in ("owned", "waived"))
    events = rec.events(type="verdict", subject=claim)
    newest = {e["data"]["step"]: i for i, e in enumerate(events)}
    earlier = [{"step": e["data"]["step"], "verdict": e["data"]["verdict"], "by": e["actor"], "ts": e["ts"]}
               for i, e in enumerate(events) if newest[e["data"]["step"]] != i]  # replaced verdicts stay visible
    return {"claim": claim, "assurance": node["assurance"], "required": list(required), "verdicts": have,
            "superseded": earlier, "missing": missing, "verdict": overall, "ownership": own, "assurance_met": met}


def _number_in(path: Path, n: dict) -> bool:
    want = n.get("value")
    try:
        target = float(want)
    except (TypeError, ValueError):
        return str(want) in path.read_text(encoding="utf-8", errors="replace")
    tol = float(n.get("tolerance", 0)) or abs(target) * 1e-9
    if path.suffix.lower() == ".csv" and n.get("column"):
        where = n.get("where") or {}  # {"particle": "proton"}: only rows whose columns equal these values
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if all(str(row.get(c)) == str(v) for c, v in where.items()) and _close(row.get(n["column"]), target, tol):
                    return True
        return False
    if path.suffix.lower() == ".json" and n.get("key"):
        import json
        value = json.loads(path.read_text(encoding="utf-8"))
        for part in str(n["key"]).split("."):
            value = value.get(part) if isinstance(value, dict) else (
                value[int(part)] if isinstance(value, list) and part.isdigit() and int(part) < len(value) else None)
        return _close(value, target, tol)
    return any(_close(m, target, tol) for m in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?",
                                                          path.read_text(encoding="utf-8", errors="replace")))


def _close(value, target: float, tol: float) -> bool:
    try:
        return abs(float(value) - target) <= tol
    except (TypeError, ValueError):
        return False


# ---- human acts ---------------------------------------------------------------------------------------------------
def approve(rec: Record, subject: str, decision: str, by: str, note: str = "") -> dict:
    """A human approves, rejects or asks for changes to a plan (an experiment, a run)."""
    if decision not in ("approved", "rejected", "changes-requested"):
        raise ValueError("decision is approved, rejected or changes-requested")
    node = rec.node(subject)
    revision=graph.plan_revision(node) if node else None
    last = (rec.events(type="approval", subject=subject) or [None])[-1]
    if node and node.get("type") == "experiment" and last and last["data"].get("decision") == decision \
            and last["data"].get("revision") == revision:
        return {"subject": subject, "decision": decision, "repeat": True}  # the same answer for the same revision: no second effect
    rec.append("approval", subject, {"decision": decision, "note": note, 'revision':revision}, actor=by)
    if node and node.get("type") == "experiment":  # the research frontier reads the plan's own state
        authorization = {"approved": "approved", "rejected": "rejected",
                         "changes-requested": "modification-requested"}[decision]
        rec.put_node(subject, "experiment", **{**{k: v for k, v in node.items() if k not in ("id", "type")},
                                                "authorization": authorization, 'approved_revision':revision})
    return {"subject": subject, "decision": decision}


def decide(rec: Record, subject: str, outcome: str, by: str, rationale: str) -> dict:
    """A human decision on a claim, question or proposal, with its rationale. It is the only way a claim is accepted."""
    if not rationale.strip():
        raise ValueError("a decision states its rationale")
    if subject.startswith("claim:"):
        if outcome not in ("accepted", "revise", "rejected", "retracted"):
            raise ValueError("a claim is accepted, revise, rejected or retracted")
        s = status(rec, subject)
        if outcome == "accepted" and not s["assurance_met"]:
            raise ValueError(f"{subject} cannot be accepted yet: verdict {s['verdict']}, ownership {s['ownership']}"
                             + (f", missing {', '.join(s['missing'])}" if s["missing"] else ""))
    rec.append("decision", subject, {"outcome": outcome, "rationale": rationale}, actor=by)
    return {"subject": subject, "outcome": outcome}


def waive(rec: Record, claim: str, by: str, reason: str) -> dict:
    """The owner accepts the risk of not being able to defend a claim. Recorded, never silent."""
    if not reason.strip():
        raise ValueError("a waiver states the accepted risk")
    rec.append("waiver", claim, {"reason": reason}, actor=by)
    return {"claim": claim, "ownership": "waived"}


# ---- commitments and proposals -------------------------------------------------------------------------------------
def add_commitment(rec: Record, source: str, text: str, evidence_required: str, by: str = "tutor") -> dict:
    """One atomic commitment split from a reviewer's or supervisor's comment, with the evidence that fulfils it."""
    ev = rec.append("commitment", source, {"text": text, "evidence_required": evidence_required}, actor=by)
    return {"commitment": ev["id"]}


def resolve_commitment(rec: Record, commitment: str, status: str, evidence: str = "", by: str = "tutor") -> dict:
    if status not in ("fulfilled", "declined"):
        raise ValueError("a commitment is fulfilled or declined")
    if status == "fulfilled" and not evidence.strip():
        raise ValueError("fulfilling a commitment names its evidence")
    rec.append("commitment.status", commitment, {"status": status, "evidence": evidence}, actor=by)
    return {"commitment": commitment, "status": status}


def commitments(rec: Record, state: str | None = "open") -> list[dict]:
    status_of = {e["subject"]: e["data"] for e in rec.events(type="commitment.status")}
    out = []
    for e in rec.events(type="commitment"):
        if e["type"] != "commitment":
            continue
        st = status_of.get(e["id"], {}).get("status", "open")
        if state is None or st == state:
            out.append({"id": e["id"], "source": e["subject"], "status": st, **e["data"]})
    return out


def propose(rec: Record, change: str, rationale: str, by: str) -> dict:
    """An agent proposes a change to a skill or the policy. Only a human decision applies it."""
    ev = rec.append("proposal", "proposals", {"change": change, "rationale": rationale}, actor=by)
    return {"proposal": ev["id"]}


# ---- the defence bridge -------------------------------------------------------------------------------------------
def open_defence(rec: Record, claim: str) -> list[str]:
    """When a claim passes its audits, ask for its five defence items (written by an agent as free items tagged with the
    claim). Idempotent."""
    node = _claim(rec, claim)
    code = [e["src"] for e in rec.edges(type="implements", dst=claim)]
    return [tasks.open_task(rec, "item", claim, f"Defence item ({kind}) for: {node['text']}. {DEFENCE_BRIEF[kind]}"
                            + (f" Code: {', '.join(code)}." if kind == "code" and code else "")
                            + " Write a free item with concepts [\"" + claim + "\"], defence \"" + kind + "\", a rubric.",
                            data={"claim": claim, "defence": kind}, key=f"defence|{kind}")
            for kind in DEFENCE]


def check_task_result(rec: Record, task: str, result) -> None:
    """A defence-item task is finished with the hash of an item of its own defence kind for its own claim."""
    t = next((x for x in tasks.tasks(rec, state=None) if x["id"] == task), None)
    if t is None:
        raise KeyError(f"no task {task}")
    if t["kind"] == "item" and t.get("defence"):
        item = rec.item(result) if isinstance(result, str) else None
        if item is None or item.get("defence") != t["defence"] or t["claim"] not in item.get("concepts", []):
            raise ValueError(f"finish this task with the hash of the {t['defence']} item you added for {t['claim']} "
                             "(add_item returns it)")


class Practice:
    """The review schedule and the grades of every item, read once and shared by every claim's ownership."""

    def __init__(self, rec: Record, as_of: date | None = None):
        self.rec, self.as_of = rec, as_of or date.today()
        self._cards: dict | None = None
        self._grades: dict | None = None

    @property
    def cards(self) -> dict:
        if self._cards is None:
            from .learn import schedule
            self._cards = {c["id"]: c for c in schedule.schedule(self.rec, self.as_of)}
        return self._cards

    @property
    def grades(self) -> dict:
        if self._grades is None:
            from .learn import evidence
            attempts = evidence.of(self.rec).attempts  # attempt -> (lesson, item, given a hint or the explanation)
            self._grades = {}
            for g in self.rec.events(type="grade"):
                verdict = g["data"].get("verdict")
                if verdict == "correct" and (attempts.get(g["data"].get("attempt")) or (0, 0, False))[2]:
                    verdict = "assisted"  # correct after a hint is practice, not ownership
                self._grades.setdefault(g["subject"], []).append(verdict)
        return self._grades


def ownership(rec: Record, claim: str, as_of: date | None = None, practice: Practice | None = None) -> str:
    """unowned: no defence item answered; practising: some answered or not yet secure; owned: every defence kind has a
    correct, unaided answer and none is past its FSRS review; waived: the owner accepted the risk."""
    if rec.events(type="waiver", subject=claim):
        return "waived"
    items = [i for i in rec.items(claim) if i.get("defence") in DEFENCE and rec.current_item(i["id"]) == i["id"]]
    if not items:
        return "unowned"
    practice = practice or Practice(rec, as_of)
    if not any(practice.grades.get(i["id"]) for i in items):
        return "unowned"
    today = practice.as_of.isoformat()
    secure = {i["defence"] for i in items if practice.grades.get(i["id"], [None])[-1] == "correct"
              and not (practice.cards.get(i["id"]) and practice.cards[i["id"]]["due"] < today)}
    return "owned" if secure >= set(DEFENCE) else "practising"


# ---- the queue ----------------------------------------------------------------------------------------------------
def queue(rec: Record, as_of: date | None = None) -> list[dict]:
    """Everything waiting for the researcher, oldest first: plans to approve, claims to decide or defend, open
    commitments, proposals, and the old research records' human transitions."""
    out = []
    # an approval counts only for the plan revision it was given for: a plan revised since is waiting again
    approved = {e["subject"] for e in rec.events(type="approval")
                if tasks.plan_approval(rec, e["subject"])["state"] in ("approved", "rejected", "changes-requested")} \
        | {e["subject"] for e in rec.events(type="approval") if not (rec.node(e["subject"]) or {}).get("type") == "experiment"}
    for n in rec.nodes(type="experiment"):
        if n.get("authorization") == "awaiting" and n["id"] not in approved:
            out.append({"kind": "approve", "subject": n["id"], "text": n.get("title") or n.get("text") or n["id"]})
    decided = {e["subject"] for e in rec.events(type="decision")}
    for c in claims(rec, as_of=as_of):
        if c["id"] in decided:
            continue
        if c["verdict"] in ("PASS", "WARN") and not c["owned"] and _claim(rec, c["id"])["assurance"] in OWNERSHIP_NEEDED:
            out.append({"kind": "defend", "subject": c["id"], "text": c["text"], "ownership": c["ownership"]})
        elif c["verdict"] in ("PASS", "WARN", "FAIL", "BLOCKED", "ERROR"):  # a blocked audit is the researcher's to see
            out.append({"kind": "decide", "subject": c["id"], "text": c["text"], "verdict": c["verdict"]})
    for cm in commitments(rec):
        out.append({"kind": "commitment", "subject": cm["id"], "text": cm["text"]})
    for p in rec.events(type="proposal"):
        if p["id"] not in decided:
            out.append({"kind": "proposal", "subject": p["id"], "text": p["data"]["change"]})
    from .graph import research_frontier
    listed = {x["subject"] for x in out}
    for f in research_frontier(rec):
        if f["transition"] in ("human-decision-required", "approval-required") and f["id"] not in listed \
                and f["id"] not in decided and f["id"] not in approved:
            out.append({"kind": f["transition"], "subject": f["id"], "text": (rec.node(f["id"]) or {}).get("title")})
    return out


def _claim(rec: Record, claim: str) -> dict:
    node = rec.node(claim)
    if not node or node.get("type") != "claim":
        raise KeyError(f"no claim {claim}")
    node.setdefault("assurance", "internal")
    return node


# ---- the journey: where each question stands, from its own recorded evidence ---------------------------------------
JOURNEY = (("question", "Question"), ("hypothesis", "Hypothesis"), ("plan", "Plan approved"), ("experiment", "Experiment"),
           ("result", "Result"), ("claim", "Claim"), ("audit", "Independent audit"), ("decision", "Your decision"))
CONTROLS = ("pause", "resume", "cancel", "retry")
SERVES_RESEARCH = ("scout", "verify", "audit", "run", "review", "item", "ingest")


def _related(rec: Record, dst: str, relation: str, node_type: str) -> list[str]:
    """Nodes of a type with an explicit ``relates`` edge of this relation into ``dst`` (never inferred from names)."""
    return sorted(e["src"] for e in rec.edges(dst=dst, type="relates")
                  if e.get("relation") == relation and (rec.node(e["src"]) or {}).get("type") == node_type)


def _decision(rec: Record, subject: str) -> str | None:
    events = rec.events(type="decision", subject=subject)
    return events[-1]["data"].get("outcome") if events else None


def _claim_row(rec: Record, cid: str, practice: "Practice") -> dict:
    node, st = _claim(rec, cid), status(rec, cid, None, practice)
    auditors = sorted({v["by"] for v in st["verdicts"].values() if v.get("by") and v["by"] != "ros"})
    author = str(node.get("author") or "")
    cites = [c for c in node.get("citations", []) if isinstance(c, str)]
    recorded = [c for c in cites if rec.node(c)]
    return {"id": cid, "text": node.get("text"), "author": author, "assurance": node["assurance"], "verdict": st["verdict"],
            "missing": st["missing"], "ownership": st["ownership"], "auditors": auditors,
            "independent": bool(auditors) and author.casefold() not in {a.casefold() for a in auditors},
            "decision": _decision(rec, cid),
            "citations": {"recorded": recorded, "unverified": [c for c in cites if c not in recorded]}}


def _provider(model: str | None, by: str | None) -> str | None:
    name = (model or by or "").removeprefix("agent:")
    return name.split(":", 1)[0] if ":" in name else None


def agent_row(rec: Record, t: dict, ctx: dict | None = None) -> dict:
    """One agent task as the person needs it: identity, who holds it, its real status, why it is stuck, the next action
    and the controls open to the person. ``ctx`` carries the dispatch ledger's view (``attempts``, ``parked``,
    ``allowance``, ``auto`` kinds, ``why`` a kind waits); without it only the task's own record is used."""
    ctx = ctx or {}
    attempt = (ctx.get("attempts") or {}).get(t["id"]) or {}
    parked = (ctx.get("parked") or {}).get(t["id"], "")
    allowance, state = ctx.get("allowance") or {"ok": True, "reason": ""}, t["state"]
    plan = tasks.plan_approval(rec, t["experiment"]) if t["kind"] == "run" and t.get("experiment") else None
    gate = tasks.run_gate(rec, t) if state in ("open", "claimed", "paused") else ""
    ended = attempt.get("ended") or {}
    retried = attempt.get("retried") or ""
    lapsed = bool(t.get("lapsed")) and not (retried and retried >= (t.get("claimed") or ""))
    stopped_after_start = ended.get("at", "") >= (attempt.get("started") or "")
    reason, nxt = "", {"actor": "agent", "label": "An agent takes this task"}
    if state == "done":
        base, nxt = "completed", {"actor": None, "label": "Finished"}
    elif state == "cancelled":
        base, reason = "cancelled", t.get("reason") or ""
        nxt = {"actor": None, "label": "Cancelled; a new approval or question opens new work"}
    elif state == "paused":
        base, reason = "paused", f"Paused by {t.get('paused_by')}" + (f": {t['paused_note']}" if t.get("paused_note") else "")
        nxt = {"actor": "person", "label": "Resume when you want the work to continue"}
    elif state == "claimed" and ended.get("outcome") in ("interrupted", "unfinished") and stopped_after_start:
        base, reason = "interrupted", ended.get("detail") or "The agent's run stopped before it finished the task"
        nxt = {"actor": "person", "label": "Retry the task"}
    elif state == "claimed" and ended.get("outcome") in ("failed", "refused") and stopped_after_start:
        base, reason = "failed", ended.get("detail") or "The agent's run failed"
        nxt = {"actor": "person", "label": "Retry the task"}
    elif state == "claimed":
        base, nxt = "running", {"actor": "agent", "label": "The agent is working; its result is checked before it counts"}
    elif lapsed:
        base, reason = "interrupted", "The agent stopped reporting and its claim lapsed"
        nxt = {"actor": "person", "label": "Retry the task, or leave it for another agent"}
    elif parked or ended.get("outcome") in ("failed", "refused"):
        base, reason = "failed", parked or ended.get("detail") or "The last run failed"
        nxt = {"actor": "person", "label": "Retry the task"} if parked else {"actor": "agent", "label": "It is taken again automatically"}
    elif ended.get("outcome") == "interrupted":
        base, reason = "interrupted", ended.get("detail") or "The last run was stopped"
        nxt = {"actor": "person", "label": "Retry the task"}
    elif t["kind"] in (ctx.get("auto") or ()) and not allowance.get("ok"):
        base, reason = "blocked", allowance.get("reason") or "Agents are not available"
        nxt = {"actor": "person", "label": "Choose an agent model or lift the pause in Settings"}
    else:
        base = "queued"
        why = (ctx.get("why") or {}).get(t["kind"]) if t["kind"] not in (ctx.get("auto") or ()) else ""
        nxt = {"actor": "agent", "label": "An agent client takes this task" + (f" ({why})" if why else "")}
    shown = base
    if gate and base in ("queued", "blocked", "failed", "interrupted"):
        if plan and plan["state"] in ("awaiting", "stale"):
            shown, reason = "waiting-human", gate
            nxt = {"actor": "person", "label": "Approve the plan's current revision", "kind": "approve", "subject": t["experiment"]}
        else:
            shown, reason = "blocked", gate
            nxt = {"actor": "agent" if plan and plan["state"] == "changes-requested" else "person",
                   "label": "The plan must change before this runs"}
    controls = []
    for action in CONTROLS:
        if action == "pause":
            ok, why_not = base in ("queued", "running", "blocked"), (
                "already paused" if base == "paused" else f"a {base} task cannot be paused")
        elif action == "resume":
            ok, why_not = base == "paused" and not gate, gate if base == "paused" else "only a paused task is resumed"
        elif action == "cancel":
            ok, why_not = base not in ("completed", "cancelled"), f"already {base}"
        else:
            ok = base in ("failed", "interrupted") and not gate
            why_not = gate if base in ("failed", "interrupted") else "only a failed or interrupted task is retried"
        controls.append({"action": action, "allowed": bool(ok), "reason": "" if ok else why_not})
    by = t.get("by") if state in ("claimed", "done") else None
    return {"task": t["id"], "kind": t["kind"], "label": (t.get("brief") or "")[:160], "question": t.get("question"),
            "role": (tasks.GUIDE.get(t["kind"]) or {}).get("role"), "agent": by, "model": attempt.get("model"),
            "provider": _provider(attempt.get("model"), by), "status": shown, "state": state, "blocked_reason": reason,
            "warning": gate if gate and base == "running" else "", "next_action": nxt, "controls": controls,
            "runs": attempt.get("runs", 0),
            "scope": ({"experiment": t["experiment"], "revision": plan["revision"], "plan": plan["state"]}
                      if plan else {k: t[k] for k in ("question", "claim", "step") if t.get(k)}),
            "updated": t.get("done") or t.get("paused_at") or t.get("claimed") or t.get("opened")}


def control(rec: Record, task: str, action: str, by: str, note: str = "", ctx: dict | None = None, retry=None) -> dict:
    """A person's pause, resume, cancel or retry of one research task. It stays inside what was approved: resume and
    retry of a run re-check the current plan approval, nothing opens a new task, and no approval, decision or waiver is
    written. A repeated pause or cancel is a no-op."""
    if action not in CONTROLS:
        raise ValueError(f"a control is one of {', '.join(CONTROLS)}")
    if not (by or "").strip():
        raise ValueError("a control names who gives it")
    t = tasks.get(rec, task)
    if t["kind"] not in SERVES_RESEARCH:
        raise ValueError(f"{task} is not research work")
    row = agent_row(rec, t, ctx)
    if (action == "pause" and t["state"] == "paused") or (action == "cancel" and t["state"] == "cancelled"):
        return {"task": task, "action": action, "changed": False, "status": row["status"]}
    entry = next(c for c in row["controls"] if c["action"] == action)
    if not entry["allowed"]:
        raise ValueError(entry["reason"] or f"{action} is not possible while the task is {row['status']}")
    by = by.strip()
    if action == "pause":
        tasks.pause(rec, task, by, note)
    elif action == "resume":
        tasks.resume(rec, task, by)
    elif action == "cancel":
        tasks.cancel(rec, task, ("Cancelled by " + by + (": " + note if note else ""))[:300], by=by)
    else:
        if retry is None:
            raise ValueError("retry needs the dispatcher's ledger")
        retry(rec, task)
    return {"task": task, "action": action, "changed": True, "status": agent_row(rec, tasks.get(rec, task), ctx)["status"]}


def _question_view(rec: Record, q: str, practice: "Practice", ctx: dict | None) -> dict:
    node = rec.node(q) or {}
    hyps = _related(rec, q, "research_questions", "hypothesis")
    exps = sorted({x for h in hyps for x in _related(rec, h, "hypotheses", "experiment")})
    claim_ids = sorted({c for x in exps for c in _related(rec, x, "results", "claim")} | set(_related(rec, q, "answers", "claim")))
    scope = {q, *hyps, *exps, *claim_ids}
    rows = [t for t in tasks.tasks(rec, state=None) if t["kind"] in SERVES_RESEARCH and (
        t.get("question") == q or t.get("experiment") in exps or t.get("claim") in claim_ids or t.get("ref") in scope)]
    plans = {x: tasks.plan_approval(rec, x) for x in exps}
    claims_ = [_claim_row(rec, c, practice) for c in claim_ids]
    run_done = [t for t in rows if t["kind"] == "run" and t["state"] == "done" and t.get("experiment") in exps]
    exp_nodes = {x: rec.node(x) or {} for x in exps}
    flags = {
        "question": True, "hypothesis": bool(hyps),
        "plan": any(p["state"] == "approved" for p in plans.values()),
        "experiment": bool(run_done) or any(n.get("status") == "completed" for n in exp_nodes.values()),
        "result": any(t.get("result") not in (None, "", [], {}) for t in run_done)
                  or any(n.get("result_validation") not in (None, "pending") for n in exp_nodes.values()),
        "claim": bool(claims_), "audit": bool(claims_) and all(c["verdict"] != "PENDING" for c in claims_),
        "decision": bool(claims_) and all(c["decision"] for c in claims_)}
    states, earlier, anomalies, current = [], True, [], None
    for key, label in JOURNEY:
        if flags[key] and earlier:
            state = "done"
        else:
            state = "current" if earlier else "todo"
            if flags[key]:
                anomalies.append(f"{label} evidence is recorded while an earlier step is not complete for its current revision")
            if earlier:
                current = key
            earlier = False
        states.append({"key": key, "label": label, "state": state})
    revise = [c for c in claims_ if c["decision"] == "revise"]
    stage = current or "decision"
    blocked, nxt = "", {"actor": "agent", "label": "An agent continues this question"}
    if stage == "hypothesis":
        nxt = {"actor": "agent", "label": "An agent frames a hypothesis for this question"}
    elif stage == "plan":
        awaiting = next((x for x in exps if plans[x]["state"] in ("awaiting", "stale")), None)
        changes = next((x for x in exps if plans[x]["state"] in ("changes-requested", "rejected")), None)
        if awaiting:
            stale = plans[awaiting]["state"] == "stale"
            nxt = {"actor": "person", "kind": "approve", "subject": awaiting,
                   "label": "Approve the revised plan" if stale else "Approve the plan, ask for changes or reject it"}
            if stale:
                blocked = "The plan changed after you approved it; nothing runs until you approve its current revision."
        elif changes:
            nxt = {"actor": "agent", "label": "An agent revises the plan as you asked", "subject": changes}
            blocked = "You " + ("rejected" if plans[changes]["state"] == "rejected" else "asked for changes to") + " the current plan."
        else:
            nxt = {"actor": "agent", "label": "An agent writes the experiment plan with its scale ladder and compute budget"}
    elif stage == "experiment":
        nxt = {"actor": "agent", "label": "An agent runs the approved plan at its stated scale"}
    elif stage == "result":
        nxt = {"actor": "agent", "label": "An agent records the result with its files and parameters"}
    elif stage == "claim":
        nxt = {"actor": "agent", "label": "An agent records the claim with the numbers it cites"}
    elif stage == "audit":
        nxt = {"actor": "agent", "label": "A fresh agent audits the claim independently of its author"}
    else:
        waiting = next((c for c in claims_ if not c["decision"]), None)
        bad = next((c for c in claims_ if c["verdict"] in ("FAIL", "BLOCKED", "ERROR") and not c["decision"]), None)
        if bad:
            blocked = f"The audit of {bad['id']} is {bad['verdict']}; it cannot be accepted until the checks pass."
        if waiting:
            defend = (waiting["verdict"] in ("PASS", "WARN") and waiting["assurance"] in OWNERSHIP_NEEDED
                      and waiting["ownership"] not in ("owned", "waived"))
            nxt = {"actor": "person", "kind": "defend" if defend else "decide", "subject": waiting["id"],
                   "label": "Show you can defend the claim, or waive it" if defend else "Decide on the claim: accept, revise or reject"}
        elif revise:
            nxt = {"actor": "agent", "label": "An agent revises the claim as you asked", "subject": revise[0]["id"]}
        else:
            nxt = {"actor": None, "label": "Decided"}
    if stage != "plan" and not blocked and any(p["state"] == "stale" for p in plans.values()):
        blocked = "A plan changed after its approval; it needs your approval again."
    focus = next((x for x in exps if plans[x]["state"] != "approved"), exps[0] if exps else None)
    return {"question": q, "title": node.get("title") or q, "text": node.get("text"), "status": node.get("status"),
            "stage": stage, "stage_label": dict(JOURNEY)[stage], "stages": states,
            "complete": current is None and not revise,
            "plan": {"experiment": focus, "state": plans[focus]["state"], "revision": plans[focus]["revision"]} if focus else None,
            "plans": [{"experiment": x, **plans[x]} for x in exps],
            "evidence": {"hypotheses": hyps, "experiments": exps, "claims": claim_ids},
            "claims": claims_, "next_action": nxt, "blocked_reason": blocked, "anomalies": anomalies,
            "agents": [agent_row(rec, t, ctx) for t in rows]}


def journey(rec: Record, hubs: set[str] | None = None, question: str | None = None, title: str = "",
            workspace_id: str | None = None, ctx: dict | None = None, own_record: bool = False) -> dict:
    """The research of one scope for the person: each question's stage from its own explicitly linked evidence, what needs
    their judgement, the agents working or stuck with real status and scoped controls, and recent outputs.
    ``hubs`` limits the questions to those part of these hubs; None keeps every question of the record. In a record that
    belongs to this one workspace (``own_record``) a decision waiting on work that no question links to is still listed,
    with ``question`` None: a plan or claim waiting for the person is never hidden because its links are missing (it
    changes no question's stage)."""
    import json
    practice = Practice(rec)
    qs = [n["id"] for n in rec.nodes(type="question")
          if (not hubs or any(e["dst"] in hubs for e in rec.edges(src=n["id"], type="part-of"))) and (not question or n["id"] == question)]
    views = [_question_view(rec, q, practice, ctx) for q in qs]
    owner = {}
    for v in views:
        owner[v["question"]] = v["question"]
        for k in ("hypotheses", "experiments", "claims"):
            owner.update({x: v["question"] for x in v["evidence"][k]})
    waiting = queue(rec)
    pending = [{**item, "question": owner[item["subject"]]} for item in waiting if item["subject"] in owner]
    if own_record and not question:
        pending += [{**item, "question": None} for item in waiting if item["subject"] not in owner]
    seen, agents = set(), []
    for v in views:
        for a in v["agents"]:
            if a["task"] not in seen:
                seen.add(a["task"])
                agents.append({**a, "question": a["question"] or v["question"]})
    live = [a for a in agents if a["state"] not in ("done", "cancelled")]
    ended = sorted((a for a in agents if a["state"] in ("done", "cancelled")), key=lambda a: a["updated"] or "", reverse=True)
    outputs = []
    for a in [x for x in ended if x["state"] == "done"][:6]:
        done = tasks.get(rec, a["task"])
        result = done.get("result")
        outputs.append({"task": a["task"], "kind": a["kind"], "question": a["question"], "by": done.get("by"), "at": done.get("done"),
                        "summary": (result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str))[:240]})
    person = pending[0] if pending else None
    own = next((v["next_action"] for v in views if v["next_action"].get("actor") == "person"), None)
    if person:
        top = {"actor": "person", "kind": person.get("kind"), "subject": person.get("subject"),
               "label": own["label"] if own and own.get("subject") == person["subject"] else (person.get("text") or "A decision is waiting for you")}
    else:
        top = own or next((v["next_action"] for v in views if v["next_action"].get("actor") == "agent"), None) or {
            "actor": None, "label": "Ask a research question to begin" if not views else "Nothing is waiting for you"}
    return {"schema": "ros.research-journey.v1", "workspace_id": workspace_id, "record": rec.root.name, "goal": title or rec.root.name,
            "questions": views, "pending_decisions": pending, "agents": live + ended[:8], "outputs": outputs, "next_action": top}
