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
or warming voice does not make a prepared core unready. PDF readiness is still
an outstanding restriction addressed by P0b; do not claim full dependency
isolation or a complete personalized core from P0a alone.

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

Real tablet stylus, LAN/TLS/pairing and handwriting assessment remain unimplemented
P2 work. No bridge, listener, firewall change, cloud upload or private-data transfer
is introduced by P0a. Native readable handouts, board-independent text teaching
and integrated adaptive refresh remain later slices in the plan.
