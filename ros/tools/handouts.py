"""Tools for study handouts: lecture notes, recitations and chapters for a course, literature briefs and findings for
research. An agent writes the sections; the gate says what is missing; the note goes to the vault and the PDF is built
by whatever toolchain the computer has.

Each tool is declared with ``@tool`` from ``ros.registry``; see ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

from .. import handouts as h
from ..registry import P, tool

HANDOUT = P("string", "the handout id (handout:<key>) or its key", True)


@tool("handout_create", "Start a handout (lecture, recitation, chapter, literature, findings) for a scope in this "
      "record: composes what the record knows and opens the task that asks an agent to write it.", writes=True,
      kind=P("string", "what kind of handout", True, tuple(h.KINDS)),
      scope=P("array", "node ids it is about: capabilities, a course or subject, a question, an experiment", True),
      title=P("string", "its title", True), key=P("string", "a short key (default from the title)"))
def handout_create(rec, kind, scope, title, key=None):
    return h.create(rec, kind, scope, title, key)


@tool("handout_read", "A handout's whole source: its sections as written, its sources and the context it is written from.",
      handout=HANDOUT)
def handout_read(rec, handout):
    return h.read(rec, handout)


@tool("handout_write", "Write one section of a handout (Markdown, LaTeX math in $...$, boxes as :::definition, :::example, "
      ":::exercise ... === solution ... :::), with the sources it cites and the locators that ground it.", writes=True,
      handout=HANDOUT, section=P("string", "the section id (its role, e.g. gist, lecture, evidence)", True),
      text=P("string", "the section's Markdown", True), by=P("string", "who wrote it", True),
      title=P("string", "heading (to rename a section or add a new one)"),
      locators=P("array", "where what it states comes from: a page, section or source key"),
      derivation=P("boolean", "the section derives its results instead of citing them"),
      sources=P("array", "sources to add: {key, text}, cited in text as [@key]"))
def handout_write(rec, handout, section, text, by, title=None, locators=None, derivation=None, sources=None):
    return h.write(rec, handout, section, text, by, title, locators, derivation, sources)


@tool("handout_file", "Put an image a handout's sections refer to (figures/name.png) beside its source.", writes=True,
      handout=HANDOUT, path=P("string", "figures/<name>.png (or pdf, jpg, svg)", True),
      text=P("string", "text content (svg)"), base64=P("string", "binary content, base64"))
def handout_file(rec, handout, path, text=None, base64=None):
    return h.add_file(rec, handout, path, text, base64)


@tool("handout_check", "Run a handout's readiness gate: sources, no answer keys, math, structure, figures; a failing row "
      "opens a task.", writes=True, handout=HANDOUT)
def handout_check(rec, handout):
    return h.check(rec, handout)


@tool("handout_build", "Deliver a handout: write its note into the vault now and build its PDF (queued as a job, or "
      "now with wait) when the gate passes.", writes=True, handout=HANDOUT,
      wait=P("boolean", "build the PDF now instead of queueing it"),
      engine=P("string", "auto (default), latex or chromium", enum=("auto", "latex", "chromium")))
def handout_build(rec, handout, wait=False, engine=None):
    return h.build(rec, handout, wait, engine)


@tool("handout_attach", "Attach the PDF a build job made for one version of a handout: verify it, place it in the vault "
      "and link it from the note.", writes=True, handout=HANDOUT,
      source_hash=P("string", "the version (default: the current one)"))
def handout_attach(rec, handout, source_hash=None):
    return h.attach(rec, handout, source_hash)


@tool("handouts", "Every handout of this record with its status (draft, ready, built) and where its PDF is.")
def handouts(rec):
    return h.handouts(rec)
