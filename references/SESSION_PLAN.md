# Session plan (v0.9.7)

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
| `handout` | the detailed LaTeX document: `title`, `directory` inside the course or project library, `status` (planned, draft, built), `sections` |
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

**Where it plays (open item).** The Obsidian view's frame forbids embedded players (`RESOURCE_PROTOCOL.md`: `frame-src 'none'`), and "Open" would hand the address to the system browser, which is exactly what the session must not do. Playing a vetted video inside Obsidian therefore needs a host-owned video pane that the page requests by record id (the host looks the address up itself and accepts only a vetted YouTube record). That widens the security model, is built and tested in a later slice, and is **not verified in Obsidian**, nor whether the player loads there. Until it is, a plan with a video segment must still teach the idea on the board or in the handout, and the video is offered as supplementary material.

## Parallel work

The researcher allows subagents and subprocesses where they save time: a subagent writes and compiles the handout and its figures while the probe runs, another produces a verified figure or animation, the voice worker renders the lecture's audio. The lecturer owns the plan and what the learner sees. A subagent returns files and a short report, its facts and figures are verified before they are shown, and it never edits the learner's session state.

## Honest limits

A plan makes the common path instant. A question it did not anticipate still waits for the agent. A plan that has not been run by a learner is untested teaching; the check below only proves the plan is well-formed.

- `session_plan.py check` verifies structure: references, reachability, the budget, board scripts, paths. It does not judge whether the questions test what they claim, whether the feedback is right, or whether the lecture is good.
- The page that runs a plan, the handout builder and the video pane are later slices (`docs/plans/v0.9.7-focused-session-plan.md`).
