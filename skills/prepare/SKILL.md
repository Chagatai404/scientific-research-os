---
name: prepare
description: Prepare a lesson bundle ahead of time (dependency map, narration, voice, visuals, animations, optional clips, items) and run the readiness gate, and write study handouts (lecture notes, recitations, chapters). Use when a topic has no ready lesson, when the learner asks to study something new, or when tasks of kind narration, visual, animation, video, item or handout are open.
---

# Prepare

A lesson starts only when its bundle is ready. Preparation runs unattended; the learner is not involved and nothing
is generated live except answers and grades. Contract: `references/PREPARATION.md`. `roadmap_tasks` opens one `item` task for each step of a roadmap that has no
questions and no prepared lesson, so preparation follows what the researcher needs next.

## Tasks you receive

`work --by <you>` gives you the next task across every record, with the skill and the tool that finishes it. Here:
`outline` (read the material, add the capabilities and `requires` edges of a course or topic), `bundle` (prepare one
lesson), `item`, `narration`, `visual`, `animation`, `video` (one piece of a bundle) and `handout` (a study document, below).
`ingest` (a file the researcher dropped into the vault) is for the `librarian`: classify it, link it to what it is
about. When a task is done, `finish` it with the record `work` named and call `work` again.

## 1. The dependency map

1. Ask a `scout` (agent) to check the field for the topic first; use its source map, not memory, for claims.
2. Draft the map: unconditional truths at the roots, the goal as the last node. Each node is a capability or concept
   id (`capability:<key>`). Add nodes and `requires` edges to the record (`add_node`, `add_edge`) when missing.
3. `bundle_create --bundle <id> --title <title> --goal <goal node>`, then write the whole plan with `bundle_plan`.

## 2. Content per node

- **Narration segments** (`motivate`, `establish`, `connect`): plain spoken prose, formulas in LaTeX. Every factual
  claim gets a `claims` entry with a source `locator`, or `derivation: true` if it is derived in the segment.
- **Visuals**: hand each to the `visual-maker` agent. It renders, looks at the result, fixes it, writes a RESULT note,
  and states the element count (at most 7). Attach `{path, result, elements}`.
- **Animation**: required when the idea is change over time, motion in geometry, a limit or a distribution building
  up (`dynamic: true`). Write the Manim scene and spec, then `bundle_animate`; the visual-maker looks at the key frames
  and sets `looked_at: true`. The basis (equation, model or data) is stated.
- **Clip** (optional, never the only path): the `video-scout` agent returns one segment of at most 3 minutes verified
  against its transcript, or `NONE`. Unverified clips are left out by the gate.
- **Items**: probe items at 3 or more difficulty levels per strand, a check item per node, one free-recall close item
  and one transfer item. Choice options mutate the correct claim and never justify themselves. Use `add_item` (pass
  the item with `--item @item.json` so LaTeX survives the shell). An item's `concepts` are node ids
  (`capability:var-sum`, never a bare strand name): a lesson finds its questions by them. A choice answer is the
  option's index. Items are immutable: to change one, add a new item with `supersedes` set to the old hash.

## 3. Voice and the gate

1. `bundle_voice` speaks every segment without audio (Kokoro for English by default). Segments that cannot be spoken
   are reported: rewrite the formula span and run it again.
2. `bundle_check`. Fix every row it lists. `bundle_tasks` opens one task per missing piece for other agents (and,
   with `clips`, video searches) — use it to split the work.
3. Ready means every row passes and nothing hashed has changed since. Tell the learner the lesson is ready.

A lapse found in review re-enters preparation for that node only: add a new explanation path, re-run the gate.

## Handouts

Lecture notes, recitations and textbook-style chapters are made the same way, from the record, for the Obsidian vault
and as PDFs (`references/HANDOUTS.md`, lens `lenses/handouts.md`):

1. `handout_create --kind lecture --scope '["capability:<key>"]' --title <title>` (kinds: lecture, recitation,
   chapter) composes the context and opens one `handout` task.
2. `handout_read --handout <id>`, then `handout_write` for each section with its sources, then `handout_check`.
3. `handout_build` writes the note into the vault now and queues the PDF; a missing toolchain is reported, never an error.
