# Teaching

How a lesson runs and why. The policy (`ros.learn.policy`) makes these decisions from the record; the tutor carries
them out and does what only a person or model can: explain, answer, grade.

## The cycle

Prepare (unattended) → read what is already known → probe → plan → teach each node (motivate, establish, connect, check) → close (free recall
and one transfer item) → review (FSRS, interleaved). A lapse at review reopens that node with a new explanation path.

## Before the first question

A lesson does not start from zero. `start` reads the earlier evidence on the record (`prior_evidence`): per capability of the
scope, known, due, shaky or new, from graded answers and reviews only. Reading, asking, being told and stating a confidence
are never evidence. The plan is fixed from it when the lesson starts, so what is known is not probed again, and what is shaky
or due comes first. The tutor also reads the living graph with `graph_teaching` (what to teach next, the goals, the
misconceptions agents noted) to choose the first question. That read guides; it is never evidence and never a grade.

`medium_choose` picks, for each goal, text, a figure, an animation or code, with the reason and what is ready
(`learning_readiness` says which engines this computer has). Words always come first; a medium that is not ready falls back
to words and the lesson says so plainly. A missing engine never blocks a lesson.

## Decisions the learner never has to make

| Decision | Made from |
|---|---|
| What to probe, at which difficulty | bracketing: floor (hardest right, unaided) and ceiling (easiest missed), midpoint next |
| Teach mode (explain, simpler, worked example, the learner's requested mode) | probe result, repeated misses, the learner's last request |
| Retry with a hint, or show a worked example | a miss after teaching; a second miss on the same item |
| Practice item and tier | from the ceiling upward, fresh items first, interleaving another ready capability every third item |
| When to stop | three misses in a row, the answer budget, or every target secure |
| Review timing and mix | FSRS over all lessons |

Each decision is logged as a `policy` event with its reason. Learner controls in a lesson are at most six: the answer
field, I don't know, Ask, Continue, Replay, and voice speed in settings.

## Evidence of learning

- Only graded answers are evidence. Choice and numeric items grade themselves; free answers are graded by the tutor
  against the item's hidden rubric (`correct` needs every criterion).
- A choice answer is recognition: it never alone makes a capability demonstrated.
- A hint or revealed explanation before an answer makes it assisted (Hard in FSRS), never independent.
- "I don't know" is a miss, never a guess.
- Viewing, asking and being told are never evidence.

States per capability: unknown, learning, demonstrated, retained (a delayed, unaided reconstruction), fragile (a miss
after success), stale (a positive state past its review). Ready means demonstrated or retained with a review date,
throughout the prerequisite ancestry. Frontier means every prerequisite is ready and the capability is not retained.

## Answers, drafts and resuming

- Every question carries an `answer_key`. `answer` with that key writes one attempt however often it is sent, so a retry, a
  second window or another client records the answer once.
- An unsent answer is kept as a draft (`draft_save`, `draft_get`) on the record, so another client or a restarted app finds it.
  A draft is never an answer or evidence; the learner sends it.
- `lesson_state` gives everything needed to resume from any client: scope, prior evidence, answers so far, the draft, the next
  step and review dates.
- Confidence (guessing to certain, asked before feedback) is recorded with the attempt and is never learning evidence.

## Closing and the graph

Closing a lesson (`close`) writes the log and returns `graph_notes`: ready `graph_note_add` arguments for the tutor agent. It
also queues one `graph` task for agents (never in the learner's queue) that records what the lesson showed the learner needs
(a concept, a prerequisite, a misconception, a goal) with `graph_note_add`, `graph_note_revise` and `graph_note_retract`. The
learner never manages the graph, and a note is never evidence. The Knowledge view and the next lesson's `graph_teaching` read
these notes together with the evidence.

## Items do not break

Items are immutable and named by the hash of their content. Editing one creates a new item that supersedes it; old
answers keep pointing at what was asked. Items are checked when a bundle is built, never during a lesson.

## Success

FSRS retrievability at the first review, and unaided free recall at close, per capability. Session length is not a
success measure.
