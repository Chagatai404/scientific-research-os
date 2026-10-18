# STAT303 rollout and automatic session startup

On 18 October 2026, the installed skill bundles contained the v0.9.7 features,
but the actual STAT303 session did not use the planned flow. Installation and
operational readiness were being confused.

## What failed

- The vault runtime differed from the repository and lacked the standalone stage
  assets. The Obsidian companion had older code despite the same manifest version.
- All three course sessions had no plan. The tutor appended individual boards and
  questions, so automatic progression, anticipated answers and the handout were absent.
- The course-study skill did not explicitly require the new plan/handout workflow.
- Startup could report ready from voice-worker heartbeats alone. It did not check
  lesson preparation or the deployed display files. Its documented default omitted
  a tutor holder, and names with spaces caused lease argument failures.
- A warm Kokoro process was still running an older adapter: its fresh heartbeat
  said ready, but it did not consume v0.9.7 prefetch requests. Replacing files did
  not replace the code loaded by that process.
- Attaching the first plan to an already-open reading view did not mount the
  staged interface: it was only mounted on initial page load. Live updates now
  activate the plan, stop the old board, and keep local events and drafts.
- The installer status check compared skill text and references, but omitted
  helpers, runtime assets and the companion bundle.

## Required behavior for every supported agent

The learner says "continue STAT303" or "start a study session". A host that loads
these skills must do the preparation itself: inspect saved responses and context,
prepare a complete plan, build the handout, check deployment, warm current workers,
prefetch lecture audio, and maintain the answer loop during active tutoring. A
learner should not need to name commands or request each capability separately.

The shared `html_sessions.py start` now refuses readiness for tutor/course
sessions without a plan, a built handout or matching renderer files. Historical
sessions remain readable. The companion's actual files are compared, not merely
its version. Installed skills carry the canonical companion files for that check.
Names are normalized and a default holder is supplied; a different live tutor is
detected before warming workers. The startup result explicitly distinguishes
filesystem preflight from desktop verification (`desktop_verified: false`).

Speech-worker leases identify the adapter loaded at process startup. `voice.py up`
cooperatively stops obsolete workers through their existing folder-specific stop
signals before launching replacements. A worker that will not stop blocks startup;
no duplicate is launched. Known environment/model settings can be saved once and
reused by either host. A prepared session automatically queues its lecture audio.

## STAT303 recovery

The previous runtime, companion, three sessions and course navigation notes were
backed up outside the vault. Capability-record hashes were recorded. The current
session received a plan that reuses two existing reviewed answers with explicit
source event IDs and dates; no new learner answer or mastery was invented. The
original events, questions, reviews, Markdown and open questions are preserved.

The plan continues from sampling variation into estimator bias and MSE, with a
short standard-error bridge, complete derivation, worked examples, four anticipated
answers, and three closing checks. The five-page LaTeX handout was compiled with
the installed XeLaTeX, package installation and shell escape disabled, and visually
reviewed. An optional MIT OCW MSE video interval was independently checked against
its official timestamped transcript and course slides; this is transcript review,
not a claim that the footage was watched or that embedding played successfully.

## Verification boundary

Unit/host tests and file checks establish contracts and deployment, not visible
boards or audible playback on the learner's device. A successful voice synthesis
and a warm worker also do not establish speaker output or microphone operation.
Record real Obsidian display, PDF opening, video playback, audio playback and
reload persistence separately. Never call unperformed desktop checks passed.

Native Computer Use was interrupted with Escape; subsequent attempts still
reported stopped even after the learner authorized resuming. Desktop verification
therefore remained pending at this checkpoint. The session must not be described
as fully operational on that basis.

### Checks performed on the recovery

- Session startup: 13 Python tests passed.
- Speech worker behavior and stale-process replacement: 60 Python tests passed.
- Installation and deployed-content drift: 15 Python tests passed.
- Session plans: 58 Python tests passed; supervision: 25 passed.
- Handout tooling: 26 passed, 2 environment-dependent checks skipped.
- JavaScript stage logic, runtime/KaTeX checks, host bridge tests and the staged
  browser suite passed. The browser suite includes attaching a first plan to an
  open reading view while retaining saved progress, without duplicating stages.
- The actual local workers restarted with saved existing settings. All 76 queued
  audio chunks were rendered, with zero prefetch failures. A subsequent live
  request returned a 24 kHz non-silent WAV lasting 10.835 seconds. This verifies
  local synthesis, not the Obsidian speaker path.
- The five-page course PDF compiled successfully; all core and anticipated-answer
  boards passed the board layout checker. Bernoulli shrinkage-example arithmetic
  was checked with exact rational numbers.
- All original questions, reviews, events and Markdown in the three course
  sessions were compared with the backup. All 82 capability records retained
  their original hashes.
- The changed helpers, skills, companion verification files and rebuilt runtime
  were deployed and compared with source for both Claude and Codex. Obsidian's
  installed CLI was checked but is disabled; it could not provide desktop evidence.
