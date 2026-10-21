"""Tools for research: the old records' frontier, claim support and code links, the claims ledger, audits and verdicts,
commitments, proposals, the decision queue, and the researcher's own acts.

Each tool is declared with ``@tool`` from ``ros.registry``; see ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

from pathlib import Path

from .. import graph, research as rsc
from ..registry import P, iso_day, tool


@tool("support", "What supports or invalidates a claim or other node.", node=P("string", "node id", True))
def support(rec, node):
    return graph.support(rec, node)


@tool("code", "Code that implements a node, with Graphify symbols.", node=P("string", "node id", True))
def code(rec, node):
    return graph.code_links(rec, node)


@tool("research", "The next mechanical transition of each research record (unranked).")
def research(rec):
    return graph.research_frontier(rec)


@tool("claims", "The claims ledger: each claim's verdict over its required audits, ownership, and what is missing.",
      project=P("string", "only this project"), as_of=P("string", "ISO date (default today)"))
def claims(rec, project=None, as_of=None):
    return rsc.claims(rec, project, as_of=iso_day(as_of))


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
