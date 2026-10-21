# Teaching

How a lesson runs and why. The policy (`ros.learn.policy`) makes these decisions from the record; the tutor carries
them out and does what only a person or model can: explain, answer, grade.

## The cycle

Prepare (unattended) → probe → plan → teach each node (motivate, establish, connect, check) → close (free recall
and one transfer item) → review (FSRS, interleaved). A lapse at review reopens that node with a new explanation path.

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

## Items do not break

Items are immutable and named by the hash of their content. Editing one creates a new item that supersedes it; old
answers keep pointing at what was asked. Items are checked when a bundle is built, never during a lesson.

## Success

FSRS retrievability at the first review, and unaided free recall at close, per capability. Session length is not a
success measure.
