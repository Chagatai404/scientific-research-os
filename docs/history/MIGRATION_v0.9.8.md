# Migrating to v0.9.8 — Adaptive Learning Core

VERSION is 0.9.8. This release contains the completed P0 implementation, with
legacy sessions and canonical knowledge records preserved. P1 teaching behaviors
(now implemented; see MIGRATION_P1.md), P2 ink and broader P3 evaluation are outstanding. Follow the exact test results
and remaining gates in [the adaptive plan](plans/v0.9.8-adaptive-learn-core-and-ink.md).
The companion retains its independent version 0.3.1; startup verifies actual
installed file contents rather than trusting the version label alone.

## P0a: free navigation and optional voice startup

The Quiz / Handout / Lecture / Video / Check order, dark player and blackboard
remain. Click any stage without completing earlier stages. Prepared content is
available immediately; an unprepared handout or check explains its status.
The selected stage is saved independently of completion. Switching away pauses
a playing lecture and retains its existing saved step and frozen path. Draft
answers survive stage switches; host-backed unsent recovery is described below. Submitted answers and review provenance retain their old format.

`html_sessions.py --root <vault> start <session> --holder <agent>` now defaults
to text preparation and connects the tutor without starting voice workers.
Automation/scripts that intentionally request narration should pass `--voice`
under the existing worker process consent. `--no-voice` remains compatible.
Read `ready` for core preparation and `voice_ready` for optional speech; failed
or warming voice does not make a prepared core unready. P0b1 below removes the
PDF-only readiness restriction. Board-independent text teaching and integrated
adaptive recommendations are included in this release.

There is no ledger migration or automatic change to retention targets, grades,
raw answers, research decisions or permanent notes. Old plans have no new required
fields. `view-stage:` uses the existing bounded checkpoint event contract and is
presentation progress only. Existing readers safely ignore those checkpoints.

## Deployment and rollback

The repository checkout and live vault are separate. Local installation was
explicitly authorized after P0 merged. For each reinstall, back up the deployed
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
native-only lesson. Local file installation does not establish actual Obsidian
UI acceptance.

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
is introduced by this release. Review-driven advice refresh is included;
automatic generation of revised teaching content remains later work.

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
plan change through existing stage-boundary guards. Review-driven advice, explicit
goal/time policy and learner-facing Study advice are included below. Automatic
lesson-content generation remains future work; the P1 teaching behaviors are described in `MIGRATION_P1.md`.
The packaged session helper set now includes `tutor_plan.py`; update complete
bundles rather than copying the changed context helper alone.

Real Obsidian acceptance remains pending: in an approved disposable session, run
startup/resume, compare the recommendation to the canonical scoped evidence, change
a target explicitly, and confirm the current lesson/raw answers stay intact. No
live-vault operation was executed for this slice.

## Study advice and review-driven refresh

Install the complete backed-up runtime, Python helper bundle and companion together
when local deployment is approved. The new `learning_advice.py` helper must travel
with `html_sessions.py`; `advice.js` is bundled into `session.js`. The companion
projects only validated advice and continues stripping agent-only context paths.
No listener, private upload or extra provider is required.

Old bindings remain readable without `context.advice`. New bindings may contain
this bounded optional presentation field. If rolling back to older Python tooling,
restore backed-up state or remove only `context.advice` from the backed-up working
copy first; older strict binding validators do not recognize it. Preserve all raw
events, reviews, source Markdown and plan content. No bulk migration is performed.

In an approved disposable Obsidian session, verify Study advice at the real pane
size; pending and partial-review advice; explicit navigation; refresh/adaptation
requests while disconnected and after reconnecting; latest-attempt feedback;
reload, draft preservation and a running lecture's frozen path. Check that actual
host updates expose advice without context paths. These local checks remain
PENDING; automated browser acceptance uses an offline scripted host. The styling
was inspected in dark desktop/phone screenshots; actual Obsidian UI acceptance
remains pending.

Explicit goal/time preferences are described below. Richer teaching behavior
selection is now the P1h selector (`MIGRATION_P1.md`); automatic guarded lesson-content revision remains a later slice; the advice does not pretend to have
generated or applied a new curriculum. Existing review/promotion gates still own
canonical evidence and human review of permanent knowledge.

## P0d: unsent draft recovery

The complete updated runtime and companion add a local `<session>.drafts.json`
sidecar (schema 1, session identity, bounded content-signature/value entries).
It contains unsent text only; do not import it as events or learning evidence.
The companion writes it under the existing session lock with atomic replacement.
Keep it private alongside the session and include it in any chosen session backup.
Older runtimes ignore the sidecar. Rollback can retain it safely; removal discards
unsent work, so first copy any text the learner still needs. Standalone exported
pages preserve edits only while open, with the existing download warning.

Local installation was authorized and installed-file parity checked. Actual
Obsidian reload/UI acceptance remains pending; repository checks use disposable
vaults and isolated browser fixtures.

## P0c3: explicit study preferences

Updated helpers accept optional `context.preferences` with objective
(`understand`, `exam`, `research`, `apply`, `review`), goal, time_minutes (1–480),
language tag and depth (`intuitive`, `intermediate`, `formal`). Save explicit
learner choices using `html_sessions.py --root <vault> preferences <session.md>
--source <preferences.json>`; `{}` clears the choices. Study advice displays them
and lets the learner request a change through the existing tutor conversation.
It does not silently apply new teaching content or reduce evidence requirements.

Install complete helper/runtime/companion bundles together after approval.
Older strict helper validators may reject this optional field; before rolling
back, back up the state and remove only `context.preferences`. Retain all raw
events, reviews, context bindings and canonical knowledge records.

## P0e: explicit staged Check proposals and historical fidelity

`plan_evidence.py --root <vault> --session <session.md> --question <id>
--mapping <reviewed-mapping.json> --learning-root <records>` prints an explicit
read-only proposal through the existing evidence gate. See the exact mapping
contract and manual review requirements in
[the P0 acceptance audit](plans/p0-remaining-acceptance-audit.md).
It never writes knowledge, grants retention or promotes permanent notes.

Plan updates now refuse changes to already answered question semantics, even
with `allow_reroute`. Add a new question ID for a changed assessment. Existing
records are preserved; this adds no bulk migration and does not reconstruct old
prompts. Generic plan writes also enforce current context and existing route/
frozen-segment guards. Deliberate route-only changes retain the existing explicit
review override. Rollback loses these safeguards, so retain state backups and
avoid editing historical assessment meaning with older helpers.

## P0f: changed teaching requires usable bound context

Current bound sessions now check essential context before changed prose,
questions, board content, teaching declarations, resources or new tutor answers
are published. Repair unavailable essential sources before retrying; rejected
writes preserve source/state/HTML. Historical and explicitly waived sessions
remain readable and writable under their existing limited-context status.
Metadata/navigation, raw learner submissions and idempotent saved answers are
available while context needs repair. Linking a request to existing published
explanation text introduces no teaching and remains available too.
