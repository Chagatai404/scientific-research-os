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

from . import tasks
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
              citations: list[str] | None = None) -> dict:
    """A claim the project makes. ``numbers`` are ``{"value", "file", "column"|"key"}`` (paths relative to the project
    root) and are checked deterministically before any audit; ``artifacts`` are the files auditors read."""
    if assurance not in ASSURANCE:
        raise ValueError(f"assurance is one of {list(ASSURANCE)}")
    cid = key if key.startswith("claim:") else f"claim:{key}"
    old = rec.node(cid) or {}
    node = {**old, "id": cid, "type": "claim", "text": text, "project": project, "author": author,
            "assurance": assurance, "numbers": numbers or [], "artifacts": artifacts or [],
            "citations": citations or []}
    rec.put_nodes([node])
    if not rec.edges(src=cid, type="part-of", dst=f"project:{project}"):
        rec.put_edge(cid, "part-of", f"project:{project}")
    return node


def claims(rec: Record, project: str | None = None, root: Path | None = None, as_of: date | None = None) -> list[dict]:
    out = []
    for n in rec.nodes(type="claim"):
        if project and n.get("project") != project:
            continue
        s = status(rec, n["id"], as_of)
        out.append({"id": n["id"], "text": n.get("text"), "assurance": n.get("assurance"), "verdict": s["verdict"],
                    "owned": s["ownership"] in ("owned", "waived"), "ownership": s["ownership"],
                    "missing": s["missing"]})
    return out


# ---- the audit chain ----------------------------------------------------------------------------------------------
def precheck_numbers(rec: Record, claim: str, root: Path) -> dict:
    """Every cited number must be found in its named result file before a model is asked anything. Writes a
    ``numbers`` verdict by ``ros``: PASS, FAIL (with each missing number) or NOT_APPLICABLE when nothing is cited."""
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
    verdict = "NOT_APPLICABLE" if not node.get("numbers") else "FAIL" if missing else "PASS"
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
    if verdict not in VERDICTS:
        raise ValueError(f"verdict is one of {list(VERDICTS)}")
    if not by or (by == node.get("author") and not _system):
        raise ValueError("the claim's author cannot audit it: a fresh reviewer must")
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
        if t.get("claim") == claim and t.get("step") == step and t["state"] in ("open", "claimed"):
            tasks.finish(rec, t["id"], {"verdict": verdict}, by=by)
    if verdict == "PASS" and status(rec, claim)["verdict"] == "PASS":
        open_defence(rec, claim)
    return {"claim": claim, "step": step, "verdict": verdict}


def latest_verdicts(rec: Record, claim: str) -> dict[str, dict]:
    out = {}
    for e in rec.events(type="verdict", subject=claim):
        out[e["data"]["step"]] = {**e["data"], "by": e["actor"], "ts": e["ts"]}
    return out


def status(rec: Record, claim: str, as_of: date | None = None) -> dict:
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
    own = ownership(rec, claim, as_of)
    met = overall in ("PASS", "WARN") and (node["assurance"] not in OWNERSHIP_NEEDED or own in ("owned", "waived"))
    return {"claim": claim, "assurance": node["assurance"], "required": list(required), "verdicts": have,
            "missing": missing, "verdict": overall, "ownership": own, "assurance_met": met}


def _number_in(path: Path, n: dict) -> bool:
    want = n.get("value")
    try:
        target = float(want)
    except (TypeError, ValueError):
        return str(want) in path.read_text(encoding="utf-8", errors="replace")
    tol = float(n.get("tolerance", 0)) or abs(target) * 1e-9
    if path.suffix.lower() == ".csv" and n.get("column"):
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if _close(row.get(n["column"]), target, tol):
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
    rec.append("approval", subject, {"decision": decision, "note": note}, actor=by)
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


def ownership(rec: Record, claim: str, as_of: date | None = None) -> str:
    """unowned: no defence item answered; practising: some answered or not yet secure; owned: every defence kind has a
    correct, unaided answer and none is past its FSRS review; waived: the owner accepted the risk."""
    if rec.events(type="waiver", subject=claim):
        return "waived"
    items = [i for i in rec.items(claim) if i.get("defence") in DEFENCE and rec.current_item(i["id"]) == i["id"]]
    if not items:
        return "unowned"
    from .learn import schedule
    as_of = as_of or date.today()
    cards = {c["id"]: c for c in schedule.schedule(rec, as_of)}
    grades = {}
    for g in rec.events(type="grade"):
        grades.setdefault(g["subject"], []).append(g["data"].get("verdict"))
    answered = [i for i in items if grades.get(i["id"])]
    if not answered:
        return "unowned"
    secure = {i["defence"] for i in items if (grades.get(i["id"]) or [None])[-1] == "correct"
              and not (cards.get(i["id"]) and cards[i["id"]]["due"] < as_of.isoformat())}
    return "owned" if secure >= set(DEFENCE) else "practising"


# ---- the queue ----------------------------------------------------------------------------------------------------
def queue(rec: Record, as_of: date | None = None) -> list[dict]:
    """Everything waiting for the researcher, oldest first: plans to approve, claims to decide or defend, open
    commitments, proposals, and the old research records' human transitions."""
    out = []
    approved = {e["subject"] for e in rec.events(type="approval")}
    for n in rec.nodes(type="experiment"):
        if n.get("authorization") == "awaiting" and n["id"] not in approved:
            out.append({"kind": "approve", "subject": n["id"], "text": n.get("title")})
    decided = {e["subject"] for e in rec.events(type="decision")}
    for c in claims(rec, as_of=as_of):
        if c["id"] in decided:
            continue
        if c["verdict"] in ("PASS", "WARN") and not c["owned"] and _claim(rec, c["id"])["assurance"] in OWNERSHIP_NEEDED:
            out.append({"kind": "defend", "subject": c["id"], "text": c["text"], "ownership": c["ownership"]})
        elif c["verdict"] in ("PASS", "WARN", "FAIL"):
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
