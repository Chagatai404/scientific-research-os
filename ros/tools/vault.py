"""Tools for the Obsidian vault: choosing it, keeping it in step with the record, finding notes, and acting on drift.

Each tool is declared with ``@tool`` from ``ros.registry``; see ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

from datetime import date

from .. import vault
from ..registry import P, tool


@tool("vault_set", "Choose the Obsidian vault (and the folder inside it, default 'Research OS') that holds the notes, "
      "PDFs and decisions; with no arguments it finds Obsidian's vaults and uses the only one.", writes=True,
      path=P("string", "the vault folder"), root=P("string", "the folder inside the vault (default Research OS)"))
def vault_set(rec, path=None, root=None):
    return vault.set_vault(path, root)


@tool("vault_sync", "Bring the vault in step with this record: read what you changed there, then write the notes the "
      "record changed. Incremental; dry_run says what would be written.", writes=True,
      dry_run=P("boolean", "write nothing, say what would be written"),
      full=P("boolean", "look at every note, not only what changed"))
def vault_sync(rec, dry_run=False, full=False):
    return vault.sync(rec, dry_run, full)


@tool("vault_status", "What is out of step in the vault: notes you edited, deleted or added, links that do not resolve, "
      "attachments nothing links to. Changes nothing.",
      deep=P("boolean", "also count every file under the folder"))
def vault_status(rec, deep=False):
    return vault.status(rec, deep)


@tool("vault_find", "Find notes of this record by title text, kind, record id or tag (an indexed lookup, not a scan).",
      q=P("string", "text in the title"), kind=P("string", "capability, claim, lesson, decision, handout, ..."),
      id=P("string", "the record id, e.g. capability:variance"), tag=P("string", "a tag, e.g. ros/claim"),
      limit=P("integer", "at most this many (default 20)"))
def vault_find(rec, q=None, kind=None, id=None, tag=None, limit=20):
    return vault.find(rec, q, kind, id, tag, limit)


@tool("vault_note", "Where one note (and its PDF) is: path, Obsidian link, portal link.",
      id=P("string", "the record id of the note", True))
def vault_note(rec, id):
    out = vault.locate(rec, id)
    if out is None:
        raise KeyError(f"no note for {id}: it has not been written to the vault yet")
    return out


@tool("vault_resolve", "Act on drift: update lets the record rewrite a note you edited (your edit is kept under My "
      "notes), restore brings back a note you deleted, reviewed marks an agent-written note as read and accepted.",
      writes=True, target=P("string", "the note's record id or its path in the vault", True),
      action=P("string", "what to do", True, ("update", "restore", "reviewed")))
def vault_resolve(rec, target, action):
    return vault.resolve(rec, target, action)


@tool("vault_review", "Write today's review note in the vault: what is due, learned, decided and added.", writes=True,
      day=P("string", "ISO date (default today)"))
def vault_review(rec, day=None):
    return vault.review_note(rec, date.fromisoformat(day) if day else None)
