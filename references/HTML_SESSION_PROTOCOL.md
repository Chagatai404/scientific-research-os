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
   own pending item; a review of a later answer records which earlier attempts it supersedes (`covers`).
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
