# FSRS scheduling (v0.9.5, S10)

`scripts/fsrs_schedule.py` estimates, for each thing the researcher has been checked on, how likely they are to recall it today and when that probability will have
fallen to a chosen level (default 90%). It uses the FSRS-6 memory model (Free Spaced Repetition Scheduler, Open Spaced Repetition), computed as the open-source
reference `py-fsrs` 6.3.2 (MIT) computes it. It is a **derived view**: it replays the retrieval history already written on each capability, writes nothing, and never changes
a human's `Next review`. `retention.py` still chooses what a session should probe; this says what the memory model expects about *when*.

## What the model is

Each item has a **stability** S (days until recall probability falls to 90%), a **difficulty** D (1 to 10) and a **retrievability** R(t) = (1 + F·t/S)^(−0.1542), the probability of
recalling it t days after the last review (F is chosen so that R(S) = 90%). A review updates S and D from the rating and from R at the moment of review: recalling something
that was nearly forgotten raises stability more than recalling something just seen; a lapse resets stability low; a second review the same day uses a separate short-term rule.
The next interval is the number of days until R falls to the desired retention, at least one and at most 36,500.

## How a checked attempt becomes a rating

Ratings come only from attempts recorded in a capability's `## Retrieval history`, by one written rule (`fsrs_schedule.py ratings` prints it):

| Attempt | Rating | Why |
|---|---|---|
| dimension `recognition` | not counted | the knowledge model: recognition never establishes retention |
| assistance `open-notes` | not counted | not recall from memory |
| outcome `fail` | Again | |
| outcome `partial` | Hard | |
| outcome `pass` with assistance `hinted` | Hard | a hint is assistance, never unaided mastery |
| outcome `pass` with assistance `none` | Good | |
| anything | **Easy is never produced** | nothing records that it was easy, and it is not inferred |

One card is kept per capability, scope and dimension, because each has its own evidence. Attempts after the `--as-of` day are ignored; a capability with issues is skipped; one with
no memory-review evidence has no card and creates no workload. What was left out is counted in the output (`attempts_left_out`), not hidden. Reviews are dated by day, so
two on one day use the same-day rule and the order of rows on that day matters.

## Using it

```bash
python scripts/fsrs_schedule.py ratings
python scripts/fsrs_schedule.py due --root <records> --as-of 2026-10-17 [--retention 0.9] [--concept <id>] [--all] [--limit 20]
```

Each item shows its estimated recall today, stability and difficulty, due date, days overdue, lapses and, beside it, the researcher's own `Next review` when one was written.
Cards are ordered by due date. A lower desired retention waits longer; a higher one asks for reviews sooner.

## What was verified, and what was not

**Verified by execution:** the implementation matches the reference library on **183 cases and 1,260 reviews** (first reviews at each rating, steady practice, lapses and recovery, same-day repeats, very long gaps,
Hard and Easy runs, and 150 random sequences with perturbed parameters and several retention targets): identical intervals and stability, difficulty and recall equal to the last digit. The golden file is
`tests/fixtures/fsrs-golden.json`, made by `tests/fixtures/make_fsrs_golden.py` with learning steps and fuzzing off. Run on the maintainer's real vault it produced 25 cards from 74 reviews.

**Not verified, stated plainly:**

- **The parameters are the defaults**, fitted to a large population of flashcard reviews, not to this researcher or to this kind of material (deriving, explaining, transferring rather than recalling a fact).
  FSRS can optimise them on a review history; this module does not, and 74 reviews is not enough to try. A due date is therefore an estimate, and the model's accuracy for this researcher is unmeasured.
- **The rating rule is a judgement.** FSRS ratings were designed for a learner's own report of how hard recall felt. Mapping an outcome and an assistance level to a rating is a reasonable reading, not something
  FSRS specifies. It is written down so it can be argued with and changed.
- **Whole days only.** The records carry dates, not times, so the sub-day learning steps of flashcard software are not modelled.
- **Older records** (`legacy` scope and dimension) form one card per capability, because they do not say which dimension they tested.
- The reference's fuzzing (random jitter on intervals) is deliberately off, so the same history always gives the same dates.
