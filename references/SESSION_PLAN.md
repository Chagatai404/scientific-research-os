# Session plan (v0.9.7)

## Adaptive core update (unreleased)

Quiz / Handout / Lecture / Video / Check retain their order and presentation.
Prepared stages are freely accessible, including Check before Quiz. The current
recommendation is independent of permission and completion. Navigation saves a
`view-stage:` checkpoint; it never supplies learning evidence. Leaving a playing
lecture pauses it and saves its existing step checkpoint. Unprepared stages say
so; no compulsory wizard is imposed. Draft answers survive stage switches (draft
reload persistence remains a tracked follow-up).

`html_sessions.py start` connects the tutor without launching speech workers.
`--voice` explicitly requests optional workers under the existing process consent;
`--no-voice` remains accepted. `ready` reports core readiness; `voice_ready`
separately reports optional voice availability. Warming, failed or unavailable
speech never disables stage navigation or lecture entry. A valid `handout.readable`
resource now satisfies preparation without PDF compilation; legacy PDF-only plans
retain their checked-export path. Native resource publication, bounds, revisions
and source requirements are specified in `HANDOUT_PROTOCOL.md`.

What a tutor decides before the learner sees anything, so the session moves without waiting for the agent between steps. It works with any agent that can write a JSON file and run a command. `TUTOR_PLANNING.md` still decides what is taught and in what order, `TUTORING_GATES.md` when a probe is due, `LIVE_LECTURE.md` how a lecture is given, and `RESOURCE_PROTOCOL.md` which outside material may be used. This file is the plan that ties them together.

## Why a plan

Every wait in a session used to be an agent turn: review a probe answer, choose the next question, write the next lecture step. A plan moves those decisions to before the session. The page follows the plan instantly; the agent is needed only at a stage boundary and for a question the plan did not anticipate.

## The plan

A plan is one JSON object (`plan_schema: 1`), checked by `python scripts/session_plan.py check plan.json` (exit 0 if valid, otherwise every problem with its location). `examples/session-plan-variance.json` is a worked plan.

| Part | What it is |
|---|---|
| `title`, `target`, `budget` | what is studied (a topic, never "Block 9" or an unfilled `[slot]`), the concept or capability, and the diagnostic budget (default 5, at most 8; the longest probe path must fit) |
| `probe` | a tree of questions: `start` and `questions`. Each question has an `id`, a `prompt`, the contract (`tests`, optionally `assumes`, `introduces`), a `solution` that explains the reasoning, and where it leads |
| `segments` | the lecture, in pieces. `core` always plays; `repair` plays before a named core segment when any listed probe question was answered wrong; `extension` plays when all listed questions were answered right. A segment has a `script` (a board script), a `video`, or both (the script plays first) |
| `anticipated` | questions the learner is likely to ask, each with `match` words and ready board `steps`, shown as buttons and answered at once |
| `handout` | `title`, library `directory`, declared `sections`, optional native `readable` resource; `status` (planned, draft, built) retains the PDF export lifecycle |
| `check` | the closing questions, a second tree with the same rules and its own budget |

**Questions.** `choice` (one right option; every wrong option carries feedback that names the mistake it stands for, and may route elsewhere with `next`), `numeric` (a value and a tolerance, plus feedback for a wrong number), and `short` (a free response with the criteria the agent will judge against; it never blocks: the learner goes straight on and the agent reviews in the background). `on_correct` and `on_wrong` name the next question or `end`. Questions only move forward, every one must be reachable, and the units on the longest path must fit the budget. Hidden answer-position balancing still applies: `session_plan.py check` warns when every right answer sits in the same place.

**Branching is a pacing decision, not a grade.** A branch taken records nothing as evidence of learning. Free-response answers still need the agent's honest review, and the canonical learning records are written only as `LEARNING_PROTOCOL.md` says.

`python scripts/session_plan.py path plan.json scale=wrong twopoint=correct` lists the segments that would play for those results, the same rule the page will run.

## Videos instead of drawing everything

If a good video already exists for the exact topic, play it instead of animating the idea yourself. A video is faster for the learner and for you, and the lecture still has to teach everything: introduce it on the board, say what to watch for, play the part that teaches (`video.start`–`video.end`, at most 30 minutes, usually two to six), then ask the question that checks it.

1. **Look first, per segment.** `python scripts/resources.py --vault <vault> list --concept <id> --status vetted` for a record that already exists; otherwise search for the exact topic and level. A near miss is a different topic.
2. **Add a candidate, never an address in the plan.** `resources.py add ... --embed youtube --start S --end E`; the plan holds only the record id (`RES-...`) and the part to play.
3. **Someone else vets it.** The finder never vets their own find (`RESOURCE_PROTOCOL.md`). Ask a separate agent (the `source-verifier` agent, or any subagent that did not find it) to watch or read the part against the course source and record `vet ... --by "reviewer: <name>"` with what it checked. An `agent:` vetting covers routine use; a video that a claim the work depends on rests on needs a reviewer or the human.
4. **Choose by:** exact topic and level; correct against the course source; clear and in the learner's language (English first); a creator with authority for the claim; captions available; the part is short. Prefer a primary lecture or an established educator over a re-upload.
5. **Self-made visuals remain for what no video covers**, for what must match the course's own notation or numbers, and for anything a video gets wrong.

**Where it plays.** The Obsidian view's frame forbids embedded players (`RESOURCE_PROTOCOL.md`: `frame-src 'none'`), and "Open" would hand the address to the system browser, which is exactly what the session must not do. So a video plays in the integrated Video tab through a player the Obsidian companion owns, which the page requests by record id and start and end (the researcher approved this widening on 2026-10-18; `RESOURCE_PROTOCOL.md`, "The video pane in Obsidian", has what it permits and why it is safe). `html_sessions.py plan` copies the vetted registry records the plan names into the session as `video_records` (a record that is missing, not vetted, stale or not embeddable is left out), and the host looks the video up there, takes the times from the plan, and builds the address itself.

On the page: the segment's script plays first and should introduce the video (a segment with no script gets its `notice` spoken). The board then waits and the video card appears with what to watch for and a "Play the video" button; nothing outside loads before the learner presses it. The lecture goes on when the video ends or its tab is closed, when the learner says they have finished, or when the video cannot be played (embedding refused, offline, no answer in ten seconds): the page says so, the lecture goes on from the board and the handout, and the video stays on offer ("Try the video again"). So **a segment with a video must still teach what matters on the board or in the handout**; the video adds to it and may fail. The check question follows the lecture as usual.

The integrated Video tab was observed playing the vetted MIT MSE lesson in
Obsidian 1.14.4 on 19 October 2026, with advancing slides, captions and elapsed time.
The host uses an isolated Electron guest with this application's own HTTP referrer;
see `RESOURCE_PROTOCOL.md`. Browser tests separately cover completion, closing,
errors and timeout behavior. Do not extend these observations to another video,
a physical mobile device, or independently recorded speaker output.

## Layout acceptance

The complete active stage must fit the available Obsidian pane without vertical or
horizontal scrolling. Use a course-player layout: Quiz, Handout, Lecture, Video and Check navigation on the left of a desktop teaching surface, with supporting question tools alongside it. Keep the stage navigation, playback and question actions,
caption controls, and tutor status visible together. Use the wide lecture layout
with the board beside its tools on desktop; stack compact tools on smaller panes.
Size the drawing frame from the remaining height while keeping captions at a stable
column width. Long captions use Previous/Next caption pages. When a saved answer
and its feedback cannot fit together, use Your answer/Feedback/Explanation pages; preserve both
in full. Never conceal an overflowing control with clipping or tiny text.

Video offers and video failures belong to the Video environment, alongside paged source/licence details; they must never consume the board's height. Test realistic long attribution text.

Verify Quiz, Handout, Lecture, Video, question entry, feedback and Check at the actual
pane size, plus desktop, tablet and narrow viewport regressions. A scrollbar-style
check alone is insufficient: assert document dimensions and that interactive
controls stay above the footer and can actually be clicked.

## Parallel work

The researcher allows subagents and subprocesses where they save time: a subagent writes and compiles the handout and its figures while the probe runs, another produces a verified figure or animation, the voice worker renders the lecture's audio. The lecturer owns the plan and what the learner sees. A subagent returns files and a short report, its facts and figures are verified before they are shown, and it never edits the learner's session state.

## Written answers and the agent

A written answer is `pending`: the page records it, the learner goes on, and `html_sessions.py wait` hands it to the agent with the question's prompt, criteria and the answer. The agent
records `plan-review` (verdict, feedback, optional `--criteria-met`, optional `--revise-plan`). The verdict only picks segments: `correct` is right, `partially-correct` and
`incorrect` are wrong, `reviewed` changes nothing. A revision applies at a stage boundary: a lecture that has not started follows the reviewed results; a started lecture keeps its
frozen path, and a revised plan may not change how answered questions were judged or routed, nor drop started segments, unless `--allow-reroute`. Nothing here awards mastery.

## Honest limits

A plan makes the common path instant. A question it did not anticipate still waits for the agent. A plan that has not been run by a learner is untested teaching; the check below only proves the plan is well-formed.

- `session_plan.py check` verifies structure: references, reachability, the budget, board scripts, paths. It does not judge whether the questions test what they claim, whether the feedback is right, or whether the lecture is good.
- The handout builder is a later slice (`docs/plans/v0.9.7-focused-session-plan.md`). The handout button was verified against the recovered STAT303 session in Obsidian on 2026-10-18; the integrated Video tab also has real Obsidian playback evidence; failure and completion paths remain separately tested by scripted hosts.

## Native text lecture

Lecture keeps its existing central surface and question rail. **Text lesson**
uses prepared step narration plus written prose/formula actions, paginated by the
native reader; **Blackboard** keeps the drawing presentation. Missing, rejected or
throwing board mounts fall back to text. Optional voice is not a prerequisite.
Both modes use the same `lecture-path:` and `lecture-step:` checkpoints; text
Previous step saves a backward move too. `lecture-mode:` saves presentation only,
and `lecture-read:<step-id>:` checkpoints save text pages, never evidence.
Anticipated answers are inserted into the same script; typed questions keep the
existing pending tutor workflow. Reading completion merely offers Check.

Drawing-only actions cannot be translated into a scientific explanation by the
renderer. If no narration or writing is prepared, disclose the missing text
alternative and direct the learner to Handout/the tutor. Authors must prepare a
useful source-grounded textual explanation; this fallback is not automatic image
interpretation or proof that every legacy lesson is accessible.

## Review-driven session pacing

A review can influence current instruction only when its `response_event_id`
matches the latest actual attempt at that question. Historical and late reviews
remain stored; they cannot approve, reject or supply feedback for a newer attempt.
The stage renderer and Python planner use the same attempt-specific rule.
`reviewed` alone leaves reasoning pending, and contradictory criterion data cannot
produce a correct pacing result. Existing criteria and raw-answer contracts apply.

`plan-review` returns an `adaptation` projection, also present in startup/resume
advice. It distinguishes a prepared repair, a focused repair request when none is
available on the current path, pending review, and ordinary continuation. This
advice is not canonical evidence. A newly needed repair affects an unstarted
lecture through existing segment rules; a started lecture retains its frozen path.
Revised teaching in a review transaction requires current essential context and
must still pass the existing answered-question/started-path revision guards.

## Learner-facing Study advice

The existing five stages remain unchanged. **Study advice** beside their controls
opens a keyboard-accessible, paged view with two sources: **This session** (latest
attempt-specific reviews) and **Recorded knowledge** (the bounded canonical
recommendation, labeled with its context-check date). Reading advice awards no
evidence. Stage selection is always an explicit learner click; a request to adapt
a lesson or repair/refresh context uses the ordinary open-question queue.

The canonical advice is a small optional `context.advice` snapshot, not another
knowledge store. It is initialized from a real context receipt, refreshed at
startup and plan-review boundaries, and can be refreshed with
`html_sessions.py --root VAULT refresh-advice SESSION`. Refresh preserves raw
answers, prior reviews, prepared questions, handout content and frozen paths.
Unchanged receipts reuse the canonical retrieval; opening or paging advice does
not scan the vault. Canonical evidence remains owned by existing reviewed writers.

When essential context becomes unavailable, plain feedback can still be saved
with a blocked advice notice, while revised teaching remains refused. A blocked
snapshot never replaces the last usable context binding. Once records return,
explicit refresh can recover. Older unbound/waived sessions show an honest missing
context message, with a request to the tutor rather than fabricated knowledge.

## Optional P1 pedagogy contract (schema 1)

`plan.pedagogy` is optional; legacy plans need no migration. It has exactly
`schema: 1` plus optional `socratic` and `explanations` arrays (at most 40 each,
120 KiB UTF-8 in total). `pedagogy_contract.validate` checks these after the base
plan validates. Structural acceptance does not verify scientific content.

Every entry requires `id` (safe 1..64 characters), exact plan `target`, positive
integer `version`, and 1..12 `sources: [{id, locator}]`. These source declarations
need independent content verification; a string locator is no proof of access.

Socratic entries additionally require `tree` (`probe` or `check`), `question_id`,
`question_sha256` and `hints: [{kind, text}]`. The digest is SHA-256 of sorted,
compact, UTF-8 JSON of the complete existing question. Hints progress through
`cue`, `structure`, `partial-step`, without duplicates (1..3 hints, 2000 chars
each). The original question owns the solution, key, criteria and routing.

Explanation entries require `segment_id`, `segment_sha256` (same digest rule)
and `levels`. One or more `intuitive`, `intermediate`, `formal` variants each
contains exactly `text` (1..12000 characters), `assumptions` (1..12 explicit
strings of at most 500 characters) and `bridge` (1..2000 characters explaining
simplification/connection). A missing level must be reported, never invented.
Metadata cannot override canonical scopes, dimensions, criteria or evidence.

Wave 0 freezes the following interaction interfaces for P1 integration:

- Shared issuance: checkpoint response `pedagogy-probe:<qid>:<units>`, units 1..4.
  `pedagogy_budget.project(state, lesson=None)` counts each issued assessment once
  across both trees, including off-route historical answers and legacy contracted
  reservations. `assert_can_issue` rejects only a new assessment; pending answers
  and revisions remain savable. Tutoring extensions retain the existing explicit
  learner request/reason requirement. The optional same-session `lesson` is an
  explicitly supplied, independently replayed tutor_session declaration; no saved
  state mapping or automatic equivalence between formats is presumed.
- Staged assistance uses `pedagogy-help`, with question_id and response exactly
  `{entry_id, version, tree, question_sha256, level, prior_response_event_id}`.
  Level is an integer hint index starting at 1, or `solution`. Prior response
  identifies the actual latest attempt (null before the first). Persist and
  acknowledge before presenting content; rejected persistence reveals nothing.
- Explanation selection uses checkpoint `pedagogy-level:<entry-id>:<version>:<level>`.
  It records presentation only, retains the lecture path/step and never grades.
- New UI modules receive `persist(type, questionId, response): Promise<event>`,
  committed `events()`, `doc`, `rich(tag,text)` and the unchanged prepared entry.
  The host owns validation and persistence; offline persistence is explicitly
  page-local. The existing five stages and three-column layout are preserved.

P1a now enforces locked shared issuance and acknowledged help attribution.
P1b level controls are a separate integration. Never infer scientific validation
or evidence from metadata, reading or a presentation selection.

Unpresented entry edits must increase their version. Once a help/level checkpoint
presents an entry, retain it unchanged and add a new ID for new content. The first
opening of prepared levels is acknowledged before display, including a preferred
or restored level. Requests retain entry/version and segment in their origin so
later tutor responses can identify the exact explanation even after navigation.
