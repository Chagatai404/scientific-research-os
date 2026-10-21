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

Computer Use was resumed with the learner's permission. In Obsidian 1.14.4 the
prepared lecture started, the board advanced through real narration steps, and
saved progress survived a full application reload. The local Kokoro worker served
cached lecture audio without the page showing a fallback. These observations verify
the application playback path; speaker hardware was not independently recorded.
The PDF opened through the handout button in a separate Obsidian tab, showing all
five pages. The integrated MIT YouTube player subsequently played inside the Video tab; its
slide, captions and elapsed time advanced from five seconds to over one minute.
Microphone transcription and independently recorded speaker output remain untested.

### Desktop findings and corrections

- The PDF existed, but the companion treated a course-library-relative handout
  directory as a vault-root path. Resolve it against the session's project library,
  matching the Python builder; keep explicit requested PDFs confined to that folder.
- Measuring the entire shrinking lecture layout made a wrapped caption shrink the
  board again. Keep the caption column stable, measure the remaining viewport, and
  resize only the drawing frame. Desktop tools sit beside the larger board.
- A fixed-height layout can still overlap its footer. Compact cards and paginate
  long captions and saved-answer feedback; do not hide overflow. Browser acceptance
  checks assert page dimensions and control/footer separation, including question
  entry and feedback at 1440x800, 768x800 and 375x740.
- The actual full-width Obsidian lecture displayed the board, stage navigation,
  playback/caption controls, all four anticipated questions and status together
  without page scrolling. The handout stage also fitted the available pane.

### Checks performed on the recovery

- Session startup: 14 Python tests passed, including deployed recovery-helper drift.
- Speech worker behavior, stale-process replacement, windowless launch and cross-process startup locking: 62 Python tests passed.
- Installation and deployed-content drift: the earlier 15-test suite passed; the new companion recovery-helper installation check also passed.
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

## Course-player and voice-lifetime follow-up (19 October 2026)

The learner supplied a Coursera layout reference. The desktop now uses a left
lesson navigation, a central board/player and adjacent question tools. The visible
entry stage is **Quiz**; its internal `probe` identifiers remain unchanged so saved
answers and routing are preserved. Video is a supplementary tab, available without
changing quiz progress. It hosts only the vetted planned resource and interval.
The overlay is sized to a bounded central slot; navigation, status and return
controls remain outside it. The Electron guest supplies this application's own
referrer, uses an in-memory partition, and has Node integration and popups disabled.

Both original voice workers disappeared together while the session was open;
Whisper logged a window-CLOSE abort. The old Windows launcher combined
`DETACHED_PROCESS` with `CREATE_NO_WINDOW`, which makes the latter ineffective
according to [Microsoft's process-creation documentation](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags).
The corrected launcher uses windowless Python where present and no incompatible
flag combination. Short engine-discovery commands also suppress console windows.

The companion now owns recovery from the saved local environment setup, invoking
only its installed helper with argument arrays and no shell. Startup calls are
coalesced, missing setups are not installed automatically, and recovery never
launches over a live current worker. Requests wait for warm-up; the page can retry
the same interrupted step and retains a deliberate pause. The installed helper
closure is included in deployment and startup drift checks.

**Observed recovery:** a cooperative stop was requested only for this vault's TTS
worker (PID 39308). Without an agent startup command, Obsidian launched replacement
PID 6376, which reported ready after 15.55 seconds. The video kept playing during
this test. After recovery, the local worker served 13 cached requests with zero failures while
Obsidian advanced from `mse-split` through `mse-expand` to `mse-result`. The lecture
was paused at that checkpoint, with the original answers and closing check intact.
Worker readiness, in-app lecture progression and independent acoustic speaker
recording are distinct evidence; only the first two have been checked.


Agent startup and companion recovery share an OS-backed startup lock. Concurrent
launch attempts wait and re-check leases instead of spawning duplicate models;
process exit releases the lock. A two-process regression verifies contention and
release. Companion 0.3.1 packages its three-file recovery helper closure, and the
session preflight compares those files as well as renderer and host assets.


### Real-content viewport regression

Final desktop acceptance exposed another case the short synthetic credit missed:
the actual MIT source/licence paragraph occupied the lecture's tools area, reducing
the board to a thumbnail. The video offer, its failure/retry actions and its source
metadata now live in the Video environment. Metadata uses bounded detail pages;
the full attribution remains available. A failure lets the learner return to the
lecture and check, without putting a large error card over the board.

Browser regressions now use long licence and attribution records at 1440x800,
803x680 and 375x740, step through every details page, assert control/footer bounds,
and return through the explicit video-skip action. The underlying lesson answers
and progress identifiers are unchanged. Viewport acceptance must test real content
lengths as well as empty or concise example panels.
