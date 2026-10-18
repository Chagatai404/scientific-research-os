# HTML-native session authoring (v0.8.5)

Every new substantive tutoring, course, research, literature, review, experiment
analysis, retention, methodology, planning or decision session must have sibling
HTML and structured state artifacts. Ordinary paper/concept/evidence/research
records and source files remain their existing formats; a record is not a session.
Use `scripts/html_sessions.py` as the centralized creation/update/migration API.
Run its `--help` for exact commands. Use the configured vault or an explicitly
chosen local workspace; do not invent a second untracked output convention.
Validate the session inventory before declaring a session complete. Missing HTML
is an error; archival exceptions must be machine-readable and appear in the report.

## Ownership and synchronization

Session JSON owns authored content and browser event history. HTML and the Markdown
bridge are projections. Keep original Markdown path, frontmatter, body, wikilinks
and heading anchors for search/backlinks/Excalidraw. Do not edit generated HTML.
Central updates verify bridge hashes and reject conflicting manual changes; import
reviewed bridge edits explicitly. Browser events are append-only raw progress.
Read unresolved questions and actual answers from state before resuming; preserve
the separate tutor checkpoint declaration and its diagnostic budget/return points.
Never overwrite user answers or silently regenerate state from HTML.

Canonical learning schemas 1/2/3 and retention.py still own capability evidence,
mastery, freshness, retention choices and scheduling. Browser recognition scores,
confidence or completed controls are not reviewed reconstruction/transfer evidence.
Review actual reasoning and assistance through the existing learning protocol before
adding ledger attempts. Never fabricate learning history or promote permanent notes.
EvidenceAtoms, exact citations, provenance and research decisions stay authoritative.

## Memory before the page

The HTML page is a view of the session, not the agent's memory. Before creating,
continuing or resuming any session, run
`python scripts/html_sessions.py --root <vault> context <session>` and read the
whole brief: learner activity awaiting you, the project note, the research graph
(validation errors, active questions and hypotheses, frontier, decisions and
validations awaiting the researcher, and the records this session refers to) and
the knowledge graph (capability states, frontier, stale/fragile/due capabilities).
Then run the workflow's own session-start steps: `research.py context` for the
chosen branch, `knowledge.py`/`tutor_plan.py` for the target capability,
`visuals.py --reusable`, retention checks and the project's Obsidian note. Never
teach or decide from chat memory alone. At block end update the canonical records
the workflow owns (learning ledger, research records, derived knowledge maps); the
session state never substitutes for them. Pass `--project-root`/`--learning-root`
when the project note does not resolve.

## Live tutoring loop

Open pages update in place when the session changes: no reload, the learner's
drafts, open panels and scroll position survive, and new content is marked as it
arrives. Write in increments as they are ready, so the learner sees the session
develop instead of waiting for a whole block.

1. Post one question at a time with `add-question <session> --source q.json`.
   It is placed at the current end of the session (an invisible
   `<!-- ros-question: <id> -->` marker), so the page reads in the order things
   happened: probe questions, then the teaching block, then the next questions.
   Append a teaching block with `append` before posting the question that follows it.
   Give every question a `solution` that explains the reasoning, not only the key.
2. Listen with `wait <session> --holder <name> --timeout 900` (run it in the background where the
   host supports it). It returns on an explicit Submit or Send, or on a timeout, which is **not** the end of the
   lesson. `--holder` renews a liveness lease so the page can say a tutor is connected (see below).
3. Read the actual response, confidence, hints and attempts it reports, then record
   your check: `review <session> <question-id> --verdict correct|partially-correct|incorrect|reviewed
   --feedback f.txt [--transcript t.md] [--next-question q.json]`. While your lease is live the learner sees
   "Checking…"; otherwise "Saved, waiting for the tutor". Your verdict, feedback and the prepared explanation then
   appear under their answer, followed by the transcript entry and next question. Every unreviewed submission is its
   own pending item. A review stands for the attempt it names and every attempt before it (it also lists them in `covers`); v0.8
   reviews recorded neither, and are read the same way, so a finished historical lesson does not come back as pending work. A
   review of an earlier attempt never settles a later one, and a retry after a review waits for the tutor again.
4. Answer open questions with `answer`; they appear in place the same way.

### Durable supervision

A bounded `wait` is not supervision, and a timeout never means the lesson is over. The page shows one of eight states, from
the saved session and an expiring lease, never from hope: *active*, *waiting for learner* (a tutor is connected and idle),
*response awaiting review*, *agent reviewing*, *paused*, *disconnected* (no live tutor: what the learner submits is saved
and waits), *completed* and *failed (recoverable)*.

- Liveness is a lease file beside the session (`<session>.supervision.json`) that an agent renews while it listens or
  reviews (`wait --holder`, or `python scripts/supervision.py --root <vault> heartbeat <session> --holder <name> --mode reviewing`)
  and that expires on its own. Two live agents never share a session (`--takeover` is a deliberate act). Nothing claims an
  agent is still there after its lease ran out, and no provider is claimed to keep running once its process ends.
- Pending work lives in the saved session, so it survives a timeout, a crash and a restart. A new agent starts with
  `python scripts/supervision.py --root <vault> resume <session> [--apply]` (it also completes an interrupted write, never
  overwriting later edits), then `wait --holder`.
- Decisions are recorded with a reason: `pause`, `fail` (needs a reason, recoverable), `complete` (refused while any
  submission still awaits review) and `reopen` (a completed session needs a reason). Free responses are never graded
  without a review.

An `answer` key gives MCQ/numeric questions an immediate local check; omit it when
the reasoning must be reviewed. Verdicts are pending tutor feedback, never ledger
evidence: canonical attempts still follow the learning protocol. Keep the
transcript chronological (append only). Questions created before markers existed
render after the content; place them by adding their markers through `update`.

## Teaching and interaction

Use this sequence: objectives/prerequisite recall → foundations → intuition →
mathematics → useful exploration → conceptual checkpoint → method/tool execution →
project application → transfer → retention/summary. Teach how the work is performed.
Ask one question at a time and preserve the existing diagnostic budget. Keep expected
answers and answer-position plans out of the learner-facing question. Solutions are
revealed only after a meaningful attempt or explicit learner request. Local scoring
is pedagogical feedback, not secure examination; offline answer keys are inspectable.
Learners can interrupt through open-question capture without spending probe budget.
No renderer-initiated external AI calls, background grading or paid-model dependency.

Use semantic components for definitions, derivations, evidence, code/output, warnings,
decisions and uncertainties. Include precise source locators. Match visual interaction
to learning value; mark schematic/model-driven demonstrations and assumptions. Do
not portray illustrative mathematics as experimentally validated simulation data.
Preserve literal LaTeX; report unsupported syntax instead of changing an expression.

## Where visuals go

A figure or interactive widget is part of the explanation it serves. Sessions created by v0.9 record
`placement: explicit`: put a figure with `![alt](resource:ID "caption")` and a widget with
`<!-- ros-widget: ID -->` where the lesson uses it (`html_sessions.py place` writes these for you), and declare it
in the session's `resources` / `widgets`. A declared visual that the lesson never places, a placeholder with no
declaration, and a visual placed twice are shown as visible diagnostics and reported by `validate`; nothing is
appended to the end of the page. Sessions without the `placement` field keep their earlier behaviour. How figures are
produced, labelled by evidence class and kept safe is in `references/VISUALIZATION_PROTOCOL.md`.

## The blackboard (v0.9.6)

A lecture can be given on a blackboard in the page: a widget of kind `board` whose declaration carries a `script`, placed where the lecture belongs with
`<!-- ros-widget: ID -->` like any widget. The script is plain JSON any agent can write: `{"board_schema": 1, "hand": "kalam", "open": false, "steps": [...]}`.
Each step has an `id`, one spoken sentence `say`, and `do` actions that start while it is spoken (`delay` seconds after the sentence starts):
`write`, `math` (TeX, typeset by KaTeX), `draw` (an absolute SVG path), `arrow`, `circle`, `rect`, `axes`, `plot` (points the agent computed),
`dot`, `move` (a dot along a path), `highlight`, `erase`. Coordinates are board units, 160 wide and 90 high. Cues follow sentences, never clock time, so a
slow voice cannot desynchronise the board; a step ends when its sentence and its drawing are both done. `python scripts/board_script.py check|speech
script.json` validates a script and lists what would be spoken; `examples/board-lecture-gradient.json` is a worked lecture whose curve is computed from
its formula. A script is untrusted: text only becomes text, a path is parsed and rebuilt, colours and sizes are names from a fixed table, an unknown key
is an error, and the page re-checks with the same rules (`tests/fixtures/board-cases.json` pins both).

**Layout (v0.9.7).** Give text a place, not coordinates. `write` and `math` take either `at` (a point in board units, optionally with `w`, a width the text wraps to) or
`zone`, one of `title` (the strip across the top), `left` (a text column), `right` (the figure side), `body` (the full width under the title) and `caption` (the strip
along the bottom). Items in a zone stack from its top in the order the script gives them, wrap to the zone's width and push the next item down, so nothing needs a y.
Drawings (`axes`, `plot`, `draw`, `arrow`, `circle`, `rect`, `dot`) keep their board coordinates; the usual plan is text in `title`/`left`/`caption` and the figure in
the right 85 by 62 units (x 70 to 155, y 18 to 80). Text and drawing share one coordinate space, so they scale together at any width. A formula too wide for its zone
shrinks to at most 60% of its size; a longer one is reported as too wide. `board_schema` stays 1 and every script written with `at` stays valid.
The page measures each text box and drawn shape after it renders. In a live lecture a new text item that would land on something else moves to the next free slot, and a
line placed with `at` that would cross the right edge wraps there; the board reports what it moved and what it could not fix. `python scripts/board_script.py check
script.json` also estimates the extent of every text from the Kalam glyph widths and refuses a script whose items overlap or leave the board, naming the step and
the item (`--no-layout` checks the grammar alone). The estimate is for Kalam, the default hand, and good to roughly a tenth for the formulas a lecture writes; the page's
own measurement is the final word. `tests/html-board-browser.cjs` renders every `examples/board-lecture-*.json` in Chrome at 1280, 768 and 375 pixels, step by step, and
fails on any overlap, anything off the board, or a drawing that has drifted from its text.

**Live.** While `open` is true the page shows "Waiting for the tutor" at the end; adding steps to the widget (`html_sessions.update_session(root, session,
widgets=[...])`) makes the open board play them in place. Steps already started must not change: a changed earlier step shows "The tutor revised the
lecture" and waits for Replay. The learner can Pause, Skip a step, Replay, change speed and choose the voice. Open questions use the existing Send panel;
an answer is more steps on the board, not a separate channel, and is recorded as before (no evidence, no mastery).

**Recorded voice.** `python scripts/voice.py board --root <vault> --session <note.md> --widget <id> --env <kokoro env> --voice model_dir=<models>` speaks every
spoken step of a board with the chosen Kokoro delivery (`VOICE_PROTOCOL.md`; one model load for all the steps not yet recorded), registers one recording per step
in the narration registry (`Narration/<key>.wav`, the key the sentence would have if spoken alone) and stores
`audio: {step id: {file, seconds, pause, say_sha256}}` in the widget's declaration. The script is not touched: it stays plain JSON an agent writes and never carries
a path or an address. A sentence the voice cannot say (another language, a formula the speech rules refuse) is listed under `refused` and that step keeps the
page's other voices. The page is given addresses only by `html_sessions.py`: a path relative to the page in a vault page, an embedded copy in a standalone export
(3 MB a file, 12 MB across the page, shared with card narration; what does not fit stays out, and that step falls back). Only a step whose sentence still hashes to
`say_sha256` gets one, so editing a sentence drops its old recording instead of reading the old words under the new caption; run `voice.py board` again to
record the new one. The board plays the clip, then waits the pause the delivery puts after a sentence (0.5 s, 0.3 s after a colon), then starts the next step;
cues start with the clip and a step ends with it. A step with no recording, a recording that will not play and one that stalls are said by the device voice or
timed captions, and the recorded voice is the default only when every spoken step has one. The pause, resume, skip and speed controls act on the recording.

**What it does not do yet.** A `board-append` command, hand-raising mid-sentence, a lint that every concept is explained on the board, and spoken questions
are the next slices (`docs/plans/v0.9.6-live-board-plan.md`). Recordings are not available inside Obsidian: the companion's frame has no media permission and
is given the session state without the page's addresses, so a board there uses the device voice or captions until the host can pass audio bytes over its
bridge (not built). Recordings are 24 kHz WAV, about 48 KB a second, so one exported page holds roughly four minutes of lecture; compressed audio is not made
here yet. A recording is added to a page when it is built, so steps appended to an open board later play with the other voices until the page is rebuilt. Cue
delays are seconds from the start of a sentence, not aligned to words. Tested in real Chrome with stand-in tones (not speech) and the captions fallback; the
recording path through the real engine was run once on the example lecture. Not tested inside Obsidian or Safari, with a real device voice, or by a learner:
nobody has listened to the board speak, and legibility is the researcher's judgement (Kalam was chosen over Patrick Hand, which read as too casual).

## Lecturing live on a board (v0.9.6)

`references/LIVE_LECTURE.md` is the agent's loop. The commands: `html_sessions.py board-append <session> <widget> --source steps.json [--after <step id>] [--open true|false]` adds steps to a lecture while it plays (at the end, or right after the step the learner has reached; the result is checked with the page's own rules before anything is written, and open views play it live); `html_sessions.py board-position <session>` says which step the learner is on, its state and how old that report is. The host writes that position (`<session>.board-position.json`, validated, kept out of the session state, a pacing hint and never evidence) as the page reports it. The board speaks with the **live voice** (`VOICE_PROTOCOL.md`) where the host offers it.

## Asking aloud (v0.9.6)

In the Obsidian view a **Hold to ask aloud** button sits under the open-question box. The sandboxed page never gets the microphone: it asks the host by action (`status`, `start`, `stop`, `cancel`) over the existing token-authenticated channel, the host records and hands the recording to a local voice worker (`VOICE_PROTOCOL.md`), and the transcript comes back as text in the question box. The learner reads and corrects it and presses Send; a spoken question is then an ordinary open question and `wait` / `answer` handle it unchanged. The lecture pauses while they ask and resumes when they send or cancel. The button is absent on a standalone page, where there is no host, and the host refuses to record when no worker has beaten recently, saying how to start one.

## The staged session (v0.9.7)

A session whose state carries a `plan` (`references/SESSION_PLAN.md`; set with `html_sessions.py plan <session> --source plan.json`, checked by `session_plan.py`) is
shown as four stages instead of one long page: **Probe**, **Handout**, **Lecture**, **Check**. The reading page, contents list, questions drawer and progress bar are not
built for it. Each stage is one environment: a probe question fills the view, with a strip of numbered buttons to move between answered questions and no page scrolling;
the lecture is the board, a way to ask and the questions the tutor expected, and nothing else. No element inside a stage has a scrollbar; the board is sized so the whole
stage fits the window, at desktop, tablet and phone widths.

The page runs the plan itself. A choice or number is judged against the plan's own key at once, with the feedback written for that very option, and the next question
appears with no agent turn; a written answer never blocks (the learner goes on, the agent reads it in the background). Answers can be typed, chosen, or spoken with the
same hold-to-speak control as an open question (the words wait in the box to be read and sent). Answers are saved as `plan-answer` events (`question_id` is a plan
question; the response is `{answer, verdict, tree}`) and stage changes as `checkpoint` events (`stage:lecture`, `stage:check`); the page rebuilds where the learner is from
those events alone, so a reload resumes. These are pacing decisions: a `plan-answer` is never evidence of learning. The lecture
plays the segments `lecture_path` chooses from the probe results. The Start button of the lecture waits while the live voice reports `warming` and says so when the voice is
not running; asking during the lecture sends an ordinary open question.

**The agent reads written answers in the background.** A written answer is recorded with verdict `pending` and the learner goes straight on. Until a plan review covers it, it is
pending work: `pending_activity` (Python) and `pendingOf` (runtime.js) count it by the same rule, pinned by `tests/fixtures/supervision-cases.json`, and `html_sessions.py wait`
returns it as `{kind: "plan-answer", question_id, tree, prompt, criteria, response, attempt, attempts}`. Judge it against the question's criteria, then record the verdict:

`python scripts/html_sessions.py --root <vault> plan-review <session> <question_id> --verdict correct|partially-correct|incorrect|reviewed --feedback f.txt [--criteria-met true,false] [--reviewed-by NAME] [--revise-plan plan.json [--allow-reroute]]`

The review is appended to `plan_reviews` (append-only, validated); it names the learner's answer event, never replaces it, and awards no mastery or evidence. A review stands
for the answer it names and every earlier answer to that question. Only a `pending` answer can be reviewed (choices and numbers were judged on the page). The verdict is a
pacing decision: `correct` counts as right, `partially-correct` and `incorrect` as wrong, `reviewed` changes nothing. It changes the lecture only at a stage boundary: before the
lecture starts, the path is chosen from the probe results with reviews applied; once it starts, the page has frozen its path in a `lecture-path:` checkpoint and keeps it. A
`--revise-plan` is refused, with the review, if it would send answered questions elsewhere or drop a segment the lecture started with, unless `--allow-reroute`.

**The lecture position survives a reload.** The page records `lecture-path:` and `lecture-step:` checkpoints and resumes from them. It also reports its position to the host
under the reserved widget id `plan-lecture`, so `board-position` returns the step and the segment it belongs to.

**Not built yet:** opening the handout PDF, playing a video segment, and the board's own layout fixes (slices S4 to S8 and S2b of
`docs/plans/v0.9.7-focused-session-plan.md`). Tested in real Chrome with a scripted host, not in Obsidian.

## Titles, navigation and the questions panel

**Titles say what is being studied.** Keep stable internal IDs in state; never put workflow positions or identifiers in
a heading a learner reads ("Block 9 - Content 3", "Q3", "RQ-004", "Section 1"), and never leave a template slot such as
`[Name the concept this part teaches]` unfilled. Write "Understanding multiscale dimensions".
`html_sessions.py validate` reports both in sessions created by v0.9, and a session with no explicit title is named by
its shallowest meaningful heading rather than its file name.

**The page has three areas.** Navigation on the left (the section list with hierarchy, the current section, per-section
progress, previous/next, "Where am I?", related lessons and notes), the lesson in the middle, and a questions panel on
the right (ask a question, history with Open/Answered status, responses waiting for the tutor, and "Back to ..." which
returns to the section a question was asked in). From 1600px wide all three are visible; on smaller windows the
contents bar stays pinned and the questions panel is a drawer opened from a button (Escape closes it and returns
focus). A question answered while the drawer is closed is signalled on its button.

**The learner can ask for the same idea another way.** The panel offers nine styles (more simply, more rigorously, show the
derivation, visually, an analogy, a worked example, physical meaning, how to implement it, review prerequisites). A request
is recorded with the section it came from and listed in pending activity; the agent adds the explanation to the lesson under
a new heading and links it with `html_sessions.py answer-explanation`. A request is never a response and never evidence. Concept-first gates,
probe contracts, evidence proposals and implementation literacy are in `references/TUTORING_GATES.md`.

**Related lessons come from recorded context, never invention.** `html_sessions.py navigation <session> [--apply]`
derives prerequisites, the first and recent earlier lessons on the concept, and research applications from the context
kernel's receipt and stores them as `navigation` (validated note references, at most 64). A source that is missing
contributes nothing.

**Links to other notes are requests, not hrefs.** A `[[Note]]` in a lesson (or an entry in `navigation`) asks the host to
open it. The host re-validates the reference itself (relative path, optional `#heading`/`#^block`; no scheme, drive,
absolute path, traversal or hidden folder), refuses anything the session does not itself link to, resolves it the way
Obsidian resolves a wikilink, and opens it in a **new tab** so the lesson stays exactly where the learner left it. A
standalone page cannot open notes and says so next to the link. Malformed targets stay visible but are not links. The
host also remembers the reading position in memory so a rebuilt page (theme change, reload) returns to it.

## Listening

Each page offers a **Listen** control in the navigation: it reads the section in view (with its subsections, and a section that is
only a title together with the one after it) using the browser's own speech synthesis. Nothing is installed or sent anywhere: voices
on the device come first and are chosen by default; an online voice appears in its own group, is labelled as sending the text to a
speech service, and is never selected for the learner. Pause remembers the place, Stop ends it, speed is adjustable, and the part
being read is marked. What is read is the lesson text: question prompts, hints and solutions, interactive widgets, code (announced
as a code block) and anything hidden are skipped. Equations are read from their TeX in words only where the spoken form is
unambiguous (powers, fractions, roots, sums, Greek letters, common relations); any other expression is announced as an equation to
read on the page rather than half-spoken. With no speech engine or no voice the control says so and the page is unaffected. The
audio is a rendering of the page and adds no content; it is tested with a recording fake engine, not on a real device.

Other optional Obsidian integrations (search, retention cards, Canvas, suggestions) and how they degrade are in
`OBSIDIAN_INTEGRATIONS.md`.

## Obsidian and fallback

The session lives in Obsidian. An agent must never open a browser (Chrome, a `file://` page, a local server or a browser pane) to show or check a session unless
the researcher asks for it in that message; `vault.py open` passes an `obsidian://` address to the system's Obsidian handler and never uses a web browser. Start
the voices with `html_sessions.py start <session> --holder <name>` (it waits until the live voice and the speech worker report ready).

Install the companion plugin and shared runtime using the documented installer.
Markdown bridges use a `ros-session` code block to embed their HTML. Sessions run
inside opaque-origin sandboxed iframes; the renderer receives no Obsidian, filesystem,
Node or Electron APIs. Only narrowly validated progress events cross the host bridge.
Missing plugin/runtime must produce actionable setup instructions, not fake success.
Desktop verification and mobile verification are separate gates. Mobile stays gated
until tested on an actual device. Standalone export is offline and announces the
absence of vault persistence; exported progress requires an explicit user export.

Legacy Markdown checkbox submission remains a compatibility fallback. Explicit
submission is required; never infer completion from idle timers or modification
timestamps. Update projections through the central API and retain chronology.

## Migration

Inventory and dry-run before applying. Back up exact bytes with a versioned manifest.
Convert only discovered session records. Preserve original content, links, equations,
answers, confidence prose and decisions without inferring missing relationships.
Uncertain structures remain legacy components and conversion warnings. Retry safely;
rollback must refuse to discard subsequent edits. A fixture migration is not proof
that the user's actual vault has been migrated.

Open questions use an inline **Send** button and chronological question/answer history below the composer. Send records for the session agent; it does not call an AI service. Read `open_questions`, answer the actual prompt, then use `answer_open_question(root, session, question_id, answer)` or `html_sessions.py --root VAULT answer SESSION QUESTION_ID --source answer.txt`. This preserves earlier answers and pending questions without awarding learning evidence. Reopening restores the recorded conversation.
