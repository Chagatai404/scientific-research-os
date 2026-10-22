# The Obsidian vault

The vault is where your knowledge and decisions live when you want to read, search or link them yourself. The record
stays the truth; the vault is written from it automatically and read back from it, and you never have to run a command
for either. Everything Research OS writes goes under one folder of the vault (`Research OS/` by default); nothing
outside it is touched.

Choose the vault once: `ros vault_set --path ~/Vault` (with no path it uses the only vault Obsidian knows about). After
that every session, the portal and the MCP server keep it in step.

## Layout

```
Research OS/
  Home.md                          map of content: courses, projects, knowledge, reviews, bases
  Inbox/                           drop anything here
  Courses/<Course>/                <Course>.md (map of content), Capabilities/, Lessons/, Handouts/, Decisions/, Inbox/
  Projects/<Project>/              <Project>.md, Questions/, Hypotheses/, Experiments/, Claims/, Papers/, Handouts/,
                                   Decisions/, Decision Log.md, Inbox/, <Project>.canvas
  Knowledge/                       Knowledge.md, Capabilities/<domain>/, Lessons/, Decisions/ (the user-wide record)
  Reviews/YYYY-MM-DD.md            the daily review note
  Bases/*.base                     Obsidian Bases tables over the properties below
  Attachments/<hub>/*.pdf          handout PDFs
```

Every course and project has its own `Inbox/`: a file you drop there is attributed to that course or project.

## A note

```
---
ros_id: "capability:variance"      the record id: every lookup goes through it
ros_record: stat303                the record that holds it
ros_kind: capability
ros_portal: "http://127.0.0.1:8737/#node/capability:variance?r=stat303"
ros_hash: 3f9a…                    a hash of what Research OS wrote
ros_status: generated              generated | reviewed | draft-unreviewed
title: Variance
aliases: [variance]
state: demonstrated
next_review: 2026-11-02
up: "[[Research OS/Courses/STAT303/STAT303|STAT303]]"
prerequisites: ["[[Research OS/Courses/STAT303/Capabilities/Mean|Mean]]"]
tags: [ros/capability, state/demonstrated, course/stat303]
---
<!-- ros:begin (generated from the record; edits here pause updates) -->
… generated from the record …
<!-- ros:end -->

## My notes
(yours: never touched)
```

Properties are flat strings and lists, so they work with Properties, Bases and Dataview. Links are path-qualified
wikilinks, so two notes with the same title never resolve to each other. File names are safe on Windows and in Obsidian;
a short suffix is added only on a collision. Notes carry slow-changing values only (state, next review date), never the
daily numbers, so Obsidian Sync and iCloud see little churn.

## Who owns what

| You did | Research OS does | The record gets |
|---|---|---|
| Nothing | Updates the note whenever the record changes | nothing |
| Wrote under "My notes" | Never touches it | a `note.annotate` event (path, text, hash); never learning evidence |
| Edited inside the generated region, or an owned property | Keeps your note as it is and stops updating it (`user-edited`) | `note.annotate` (kind `region-edit`) |
| Chose "update" for a pinned note (`vault_resolve --action update`) | Rewrites it; your edit is kept under "My notes" as "Kept from your edit" | `note.release` |
| Set `ros_status: reviewed` on an agent-written note, or `vault_resolve --action reviewed` | Accepts it as read | `note.reviewed` (this is not one of the three human acts: approve, decide and waive stay in the portal) |
| Deleted a generated note | Does not recreate it; maps of content, Home, bases and PDFs are regenerated | `note.dismiss`; `vault_resolve --action restore` brings it back |
| Moved or renamed a note | Follows it by `ros_id` | nothing |
| Dropped a file in an `Inbox/` (or anywhere under the folder) | Never moves or edits it | `inbox.found`; a Markdown file becomes a `source` node, a PDF or image also opens an `ingest` task |
| Left a version 1.1 export note unedited | Replaces it with the new layout | nothing |

The only deletion rule: Research OS deletes a file only when it generated it and its hash is still what it wrote.
Broken wikilinks, notes missing from the vault and attachments nothing links to are reported by `vault_status` and never
repaired by deleting anything.

## Cost and robustness

The manifest (`$ROS_HOME/vault/<id>.sqlite`) is outside the vault and derived: lose it and the next scan rebuilds it from
the `ros_id` in each note. A scan stats the files under the folder and reads only those whose size or time changed. A
sync after the first renders only the notes the record's new log lines touch (`Record.since`), their neighbours and the
maps of content. Lookups by id, title, kind or tag (`vault_find`, `vault_note`) are indexed queries. A write is a
temporary file renamed over the old one, and a note is rewritten only when its hash changed.

## Tools

| Tool | Does |
|---|---|
| `vault_set` | Choose the vault and the folder; says which vaults Obsidian knows |
| `vault_sync` | Read what you changed, then write what the record changed; `--dry-run` says what would be written |
| `vault_status` | What is out of step: edited, deleted, added, broken links, orphaned attachments |
| `vault_find` | Find notes by title, kind, id or tag |
| `vault_note` | Path, Obsidian link and portal link of one note |
| `vault_resolve` | `update`, `restore` or `reviewed` |
| `vault_review` | Write today's review note |
