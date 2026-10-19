# Adaptive learning changes (unreleased, incremental)

VERSION remains 0.9.7. This document describes completed implementation slices,
not a released or installed v0.9.8. Follow the progress record in
[the adaptive plan](plans/v0.9.8-adaptive-learn-core-and-ink.md).

## P0a: free navigation and optional voice startup

The Quiz / Handout / Lecture / Video / Check order, dark player and blackboard
remain. Click any stage without completing earlier stages. Prepared content is
available immediately; an unprepared handout or check explains its status.
The selected stage is saved independently of completion. Switching away pauses
a playing lecture and retains its existing saved step and frozen path. Draft
answers survive stage switches; unsent draft recovery after a full reload is
still pending. Submitted answers and review provenance retain their old format.

`html_sessions.py --root <vault> start <session> --holder <agent>` now defaults
to text preparation and connects the tutor without starting voice workers.
Automation/scripts that intentionally request narration should pass `--voice`
under the existing worker process consent. `--no-voice` remains compatible.
Read `ready` for core preparation and `voice_ready` for optional speech; failed
or warming voice does not make a prepared core unready. P0b1 below removes the
PDF-only readiness restriction. Board-independent text teaching and integrated
adaptive refresh are still pending; this is not the complete personalized core.

There is no ledger migration or automatic change to retention targets, grades,
raw answers, research decisions or permanent notes. Old plans have no new required
fields. `view-stage:` uses the existing bounded checkpoint event contract and is
presentation progress only. Existing readers safely ignore those checkpoints.

## Deployment and rollback

The repository checkout and live vault are separate. No live installation is
performed by these slices. After explicit rollout approval, back up the deployed
runtime and installed skills, update through the existing installer/conflict
workflow, and reload the companion/session. Keep existing session JSON and
Markdown; never regenerate answers from HTML. Roll back runtime/skills from the
backup if needed; additional view checkpoints do not require data rollback.

## P0b1: native handouts before diagnostics

Publish source-grounded `readable.json` through the existing handout helper:

```
python scripts/handout.py publish-readable --root <vault> --session <note> --content readable.json
```

See `references/HANDOUT_PROTOCOL.md` for its additive, bounded plan contract. The
Handout stage now shows usable study content while the PDF status is still planned
or draft. Sources retain precise locators; solutions require explicit reveal.
Section/page position and reveal requests survive stage switching and reload.
Reading and reveal checkpoints never award mastery; assessed attempts still need
honest assistance attribution and review.

The publisher writes a revisioned Markdown resource inside the declared library,
adds a session backlink and a generated bridge link, and registers that specific
note through existing mediated navigation. It holds the central session lock;
human-edited copies are retained. Retrying after a projection failure reuses the
complete library artifact. Ordinary session journals still require the existing
recovery procedure before another write. PDF compilation is independent, and its
completion cannot overwrite a newer native resource or plan.

Old plans need no data migration and remain readable. New native plans require
the updated runtime bundle, including reader.js, and updated helper/skill bundles.
For rollback, restore the prior runtime and plan from an explicitly made backup;
keep the generated Markdown resource and all raw answer history. Old runtimes do
not display the new native content, so do not roll back the runtime alone for a
native-only lesson. No live installation has been performed here.

Native v1 supports structured prose, inline mathematics, source references and
solution appendices. Advanced figures/tables and designed page layout remain in
the existing optional PDF workflow; their native adapters are not claimed complete.

## Local acceptance still pending

With explicit approval, use a disposable session in the actual Obsidian host:

1. Open a prepared legacy plan. Before answering Quiz, visit Check and Handout;
   check that content and status are readable and the three columns remain.
2. Type an unsent answer, visit another stage and return; verify the draft stays.
   Submit it and reload: verify the raw answer and review remain unchanged.
3. Play a lecture, switch to Handout, return and resume, then fully reload;
   verify paused progress, selected stage, frozen path and captions.
4. With workers unavailable or warming, enter Lecture and use keyboard controls;
   verify no disabled core navigation. Run default `start` without starting workers.
5. Request voice explicitly under existing process approval and verify speech,
   failure feedback and recovery. Speaker/microphone behavior requires physical
   checks; synthetic browser tests cannot establish it.
6. In an approved disposable Obsidian session, publish a native handout while its
   PDF is absent. Open it before Quiz; check math, exact source locators, section
   changes, responsive paging and Library copy opening inside Obsidian. Reload
   and verify the page, solution reveal and any pending raw answers are retained.
   Compiler absence/failure must leave the native handout accessible. This local
   acceptance is still PENDING; the executed browser host is synthetic.

Real tablet stylus, LAN/TLS/pairing and handwriting assessment remain unimplemented
P2 work. No bridge, listener, firewall change, cloud upload or private-data transfer
is introduced by these slices. Integrated adaptive refresh remains a later slice.

Lecture now supports Text lesson / Blackboard using the same prepared steps and
checkpoint history. Test switching in both directions, backward step navigation,
page/reload recovery, typed questions, and video skip followed by Check in the
approved disposable Obsidian session. Verify a missing board runtime gives text
without changing raw answers. Drawing-only legacy steps require an authored text
alternative; the renderer reports that limitation. These new behaviors have only
synthetic-host browser acceptance until the local checks are performed.

## Canonical recommendation projection

No learning ledger or session-state migration is needed. Tutor/course receipts
add a digest-covered recommendation generated by the existing planner. Older
cached receipts are rebuilt when they lack the policy projection. Session startup
and resume preserve bound roots/targets/policy and evaluate today's evidence date.
Historical unbound/waived sessions keep compatibility with an explicit limited
status; bind current context before claiming personalized teaching.

`context --target concept:ID --bind` explicitly changes a session's context target
without rewriting prepared questions or lecture checkpoints. Review any subsequent
plan change through existing stage-boundary guards. Full review-driven dispatch,
goal/time policy and a learner-facing recommendation control are still pending.
The packaged session helper set now includes `tutor_plan.py`; update complete
bundles rather than copying the changed context helper alone.

Real Obsidian acceptance remains pending: in an approved disposable session, run
startup/resume, compare the recommendation to the canonical scoped evidence, change
a target explicitly, and confirm the current lesson/raw answers stay intact. No
live-vault operation was executed for this slice.
