# Learner model: terms, profile and the Student Brief (v0.9.5)

The capability graph records what a learner can **do**. The term ledger records which **words** they know, per language, so a
lesson never uses an unexplained term. Both are working records; neither is mastery by itself, and unknown stays unknown.

## Files

Under `<vault>/.research-os/learner/` (all optional; `scripts/terms.py` reads and appends them):

| File | Holds | Written by |
|---|---|---|
| `term-events.jsonl` | one event per line: `term`, `lang`, `kind`, `date`, plus `reviewed_by`, `session`, `confidence` (0..1), `hints` | `terms.py record`, after a review |
| `glossary.json` | `{"terms": {id: {"labels": {lang: text}, "concepts": [ids]}}}` linking a term to the concepts or capabilities it belongs to | `terms.py define` |
| `profile.json` | declared `languages` (`primary`, `secondary`, `by_domain`), `goals`, `time_budget_minutes` | the learner |

Term ids are ASCII slugs (`terms.term_id`): "olasılık yoğunluğu" becomes `olasilik-yogunlugu`. Link a Turkish and an English label to
one id in the glossary; they are then one term with a state per language.

## Term states

Derived by folding the events (dates order them; file order breaks ties). Nothing is stored as a state.

| State | Meaning |
|---|---|
| `unseen` | no event |
| `introduced` | the tutor presented it. **Not evidence.** |
| `defined` | the learner restated it and a reviewer recorded `restated` |
| `used` | the learner applied it correctly without prompting (`used`, reviewed) |
| `fluent` | `used` on two different dates with no `missed` since |
| `shaky` | a reviewed `missed` with no new evidence after it; re-teaching does not clear it |

`restated`, `used` and `missed` need `reviewed_by`: the event log is evidence, so a reviewer stands behind each line. Events are
appended, never edited; a bad line is reported and does not hide the good ones.

## What the profile may not hold

No learning-style fields (`learning_style`, `visual_learner`, `auditory` and the like) are accepted; `terms.py check` reports them.
Matching instruction to a self-declared style has no supporting evidence (Pashler, McDaniel, Rohrer & Bjork 2008,
*Psychological Science in the Public Interest* 9(3)). Visuals and narration are added for everyone because of how multimedia
learning works, not to match a style. What is personal is measured: `hint_rate` and `calibration_gap` (mean confidence minus
accuracy, positive = more confident than correct) are reported only after five relevant events.

## The Student Brief

`context_kernel.py preflight` adds `retrieval.learner.student` to the receipt: terms for the lesson's concepts sorted into
`known`, `shaky`, `introduced` and `unseen` (in the lesson language), `language_gaps` (known in one language, not the lesson's),
the declared languages, and the measured profile. It is bounded (40 terms; known terms are cut before weak ones).

`status` is `not-configured` (no vault), `empty` (no ledger yet: every term is unseen) or `ok`. A missing ledger never changes a
receipt's outcome. The brief is read when the receipt is built; the tutor appends events during a session, so re-run
`terms.py brief` when a decision depends on the latest state.

The tutor must read the brief before teaching: define `unseen` and `shaky` terms before the lesson uses them, in the lesson
language, and prefer the learner's stronger language for the first explanation of a term known only in the other.

## Commands

```
python scripts/terms.py --vault <vault> define --id probability-density --label en="probability density" --label tr="olasılık yoğunluğu" --concept gamma-density
python scripts/terms.py --vault <vault> record --term "probability density" --lang en --kind restated --reviewed-by tutor [--session S] [--confidence 0.7] [--hints 1]
python scripts/terms.py --vault <vault> brief --concept gamma-density --lang tr
python scripts/terms.py --vault <vault> check      # exit 1 on a malformed file or a learning-style field
```

Not in v0.9.5: a `confusable-with` concept relation, and a spaced-repetition estimator (see `docs/plans/v0.9.5-plan.md`).
