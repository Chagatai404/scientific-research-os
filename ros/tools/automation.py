"""Tools for what the system does by itself: looking at what changed and acting on it, and the local jobs (PDF builds,
voice renders) the process serving the portal or MCP runs.

Each tool is declared with ``@tool`` from ``ros.registry``; see ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

from .. import automation
from ..registry import P, tool


@tool("reconcile", "Look at what changed in this record and do what follows from it on its own: request audits for new "
      "claims, queue the run of an approved experiment, prepare the next lessons, check handouts, update the vault. "
      "Runs by itself after every change; call it to make it happen now.", writes=True,
      mode=P("string", "call (cheap, the default), tick, scan or daily", enum=automation.MODES))
def reconcile(rec, mode="call"):
    return automation.reconcile(rec, mode)


@tool("automation", "What the system has done on its own lately, and the jobs it has waiting.")
def automation_status(rec):
    return automation.status(rec)


@tool("jobs", "Local engine runs waiting to be done by the process serving this record: a PDF build, a voice render.")
def jobs(rec):
    return automation.jobs(rec)


@tool("job_done", "Finish a local job with what the run reported, and do what it said to do next (attach the PDF).",
      writes=True, task=P("string", "the job's task id", True), result=P("any", "what the run reported", True),
      by=P("string", "who ran it"))
def job_done(rec, task, result, by="runner"):
    return automation.job_done(rec, task, result, by)
