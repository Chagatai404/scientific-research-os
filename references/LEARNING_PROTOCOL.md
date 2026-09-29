# Learning Protocol

The goal is understanding that can be reconstructed, not copied notes.

## Loop

1. **Prepare** — define the target capability, map likely dependencies, and verify
   the facts needed for the lesson before live questioning.
2. **Check prior retention** — inspect relevant retrieval evidence and check due
   or uncertain prerequisites before reteaching them.
3. **Probe and map** — use a bounded diagnostic block to locate the learner's
   boundary, then refine the dependency map from the answers.
4. **Teach and connect** — one dependency node at a time, connected to established
   foundations; use a visual when it materially helps understanding.
5. **Retrieve** — test reconstruction, explanation, derivation, transfer, or use.
6. **Record and revisit** — preserve retrieval evidence, summarize learning state,
   and choose follow-up according to retention target; reinforce weak areas when needed.
7. **Promote by choice** — the human chooses whether to rewrite demonstrated
   understanding into permanent notes. Promotion does not establish retention.

This is the learning loop, not a replacement for research stage order or approval
gates in `RESEARCH_PROTOCOL.md`. An isolated lesson does not require a full
research cycle. Use verified material already available when sufficient.

## Learning state and retention

Track evidence for a specific capability, not mastery of an entire subject.

| State | Meaning |
|---|---|
| `unknown` | The capability has not yet been demonstrated. |
| `learning` | The capability is currently being developed. |
| `demonstrated` | The learner successfully reconstructed or used it during the current learning period. |
| `retained` | The learner passed a delayed retrieval check after the original learning period. |
| `fragile` | Previously demonstrated understanding recently failed or only partly survived retrieval. |
| `stale` | Previously demonstrated or retained understanding lacks sufficiently recent retention evidence. |

These labels summarize evidence, not certainty. `stale` means missing recent
evidence, **not proven forgetting**. A note's existence, confidence rating,
creation date, or reading/review timestamp is not evidence of retrieval. With no
retrieval history, do not infer either mastery or forgetting from an old label.

Keep the retrieval history rather than replacing it with only the latest state.
At block end, record the capability, date/learning period, prompt or attempt
reference, method, outcome, assistance used, and suggested next review with its
rationale. Distinguish same-period reconstruction from delayed retrieval. Preserve
earlier failures and successes; record corrections explicitly. Use working
learning/session records within the authorized note workflow, without silently
creating or rewriting permanent concept notes.

### Delayed retrieval

Check recall or reconstruction before showing the explanation or solution.
Successful unassisted explanation, derivation, transfer, or application can support
`demonstrated`; a qualifying delayed check can support `retained`. Delayed means
retrieval after time away from instruction, not merely opening a new chat or
repeating a just-revealed answer. Multiple-choice
recognition alone is normally insufficient for `retained`; follow it with meaningful
reconstruction or transfer. Record hints and open-note assistance rather than
treating assisted success as equivalent to unassisted retrieval.

A simple starting schedule is same-session reconstruction, then about one day,
one week, one month, and a longer interval. These are adaptable defaults, not an
optimal spacing algorithm or scientific laws. Choose the next interval according
to the capability, learner, evidence, and upcoming use. Strong delayed retrieval
can lengthen it; partial retrieval shortens it; failure calls for reinforcement
and an earlier check. A successful retry immediately after reteaching establishes
current demonstration, not a new delayed retention success.

For previously demonstrated knowledge, partial or failed retrieval supports
`fragile`; failure on a never-demonstrated concept leaves it `unknown` or
`learning`. When a previously agreed review horizon passes without a new check,
mark freshness as `stale` while preserving the last evidenced state and history.
An overdue date must not erase a recorded failure or replace `fragile` with a
mere absence-of-evidence label.
If no review horizon was recorded, report freshness as unknown; propose a check when justified by the target and actual use;
do not invent an expiry date. Retention checks are learner/session driven, not a
requirement for a background scheduler.

## Probing and retrieval formats

### Fast active probe

Before a probing block, prepare internally the target capability, likely
dependency map, relevant retention evidence, verified scientific facts and sources,
question bank, expected answers and acceptable variants, likely misconceptions,
hint ladder, progression/stopping criteria, and useful visual candidates. Keep
answers and diagnostic plans out of the learner-facing question. Prepare enough
to run the block without repeated expensive research; do not exhaustively research
unrelated prerequisite branches.

Default to **3–5 diagnostic questions**, asked **one at a time**. Stop earlier when
there is enough evidence to choose the next teaching step. Normally do not exceed
roughly **8 questions** unless the learner requests deeper testing, genuinely
independent prerequisite branches need resolution, or answers reveal a contradiction
that materially changes the learning path. Explain the reason for extending the
block. Count prior-retention questions used diagnostically toward this budget;
do not evade it through multipart questions or consecutive renamed blocks.

During an active probe, optimize for rapid question → answer → lightweight
verdict/hint → next question. Use responses such as `Correct.`, `Correct — next
question: ...`, `Partially correct. Hint: ...`, or `Not quite. Think about ...`.
Do not perform extensive analysis, re-teaching, literature/source retrieval,
repository inspection, or long commentary after every answer. Keep only compact
internal observations; if using a note UI, write only the verdict/hint and next
question. Defer detailed assessment, source tables, maps, and durable logging.

Expensive pedagogical synthesis happens after the probe unless a misconception
prevents meaningful continuation. In that case give the minimum correction, or
explicitly pause the block to teach/verify an uncertain point before resuming.
If an answer exposes a genuine inconsistency or insufficient prepared evidence,
pause, verify the disputed scientific point, and correct the preparation before
continuing. Fresh research is an exception, not a routine step between answers.
Never guess a verdict to save time. A request for deeper explanation can pause
the probe too. Multiple choice is encouraged for cumbersome answers, intuition,
competing interpretations, and fast diagnostics; a correct guess is not mastery.

At the end, synthesize clearly understood and partly understood concepts,
misconceptions, important corrections, connections, and reinforcement needed
before progression. Verify reconstruction/transfer at the depth needed for the
active research task. Repair necessary prerequisites before advancing; do not
demand mastery of unrelated topics. Repeat this loop after meaningful builds and
experiments so the researcher understands their code and evidence.

Use the response format that best diagnoses understanding with the least unnecessary friction.

Possible formats include:

- short free-response questions;
- explain-in-your-own-words prompts;
- derivations;
- numerical exercises;
- coding/computation tasks;
- transfer questions;
- multiple-choice questions;
- ranking or comparison questions;
- prediction-before-calculation questions.

### Multiple-choice questions

Multiple-choice questions are appropriate when:

- the correct free-response answer would be unnecessarily long to type;
- keyboard entry would distract from the concept being tested;
- the goal is to test physical or mathematical intuition;
- several plausible interpretations need to be distinguished;
- the learner is being probed before formal teaching;
- a quick retrieval check is useful between deeper questions.

Good multiple-choice questions should:

1. test a concept rather than trivia;
2. use plausible distractors that correspond to real misconceptions;
3. inspect option symmetry: length, detail, grammatical form, precision, qualifiers,
   terminology, and tone must not identify the correct answer;
4. avoid introducing information that gives away a later question;
5. ask for a brief reason when the reasoning matters;
6. optionally ask for confidence when distinguishing understanding from guessing.

Before an MCQ block, prepare a **hidden answer-position plan**. For four-option
questions, allocate A/B/C/D counts differing by at most one across the planned
block, then shuffle or deliberately permute those positions without an obvious
cycle. For example, `C A D B B C A D` is balanced for eight questions;
`A B C D A B C D` is predictably cyclic. Do not always assign the remainder to
the same letters in shorter blocks. Reorder options to fit the plan and recheck
the answer key and scientific meaning. For an extended block, balance the total
planned counts; do not add questions merely to complete a quota after an early stop.
Do not reveal the position plan or reuse a fixed sequence across sessions.

Inspect each question before presenting it: the correct option should not
routinely be the longest or most scientifically detailed. Repair weak distractors
or use free response when plausible symmetric alternatives are unavailable. The
position plan never takes priority over an unambiguous, scientifically valid question.

A useful compact response format is:

```text
Answer: <letter>
Reason: ...
Confidence: low / medium / high
```

Do not use multiple choice exclusively. Free reconstruction, derivation, transfer, and explanation are still necessary to establish durable understanding.

When a learner selects the correct option for the wrong reason, treat the underlying concept as unresolved.

## Mathematical teaching

For a new formula:

1. State the problem that makes the quantity necessary.
2. Define objects and assumptions.
3. Motivate each transformation.
4. Derive rather than merely present when practical.
5. Check units/dimensions.
6. Check simple or limiting cases.
7. Explain physical/statistical/computational meaning.
8. Apply it to a concrete example.

## Permanent-note gate

AI output is temporary working material until the learner:

- explains the idea in their own words;
- answers a retrieval question;
- and chooses to promote it.

## Selective long-term retention

Understanding and permanent memorization are different questions. `learning_state`
summarizes retrieval evidence; optional `retention_target` records the learner's
long-term unaided-availability choice. A demonstrated reference capability is valid.
Reference does not mean unimportant: scientifically critical details can be looked up.

- **core:** maintain enough unaided understanding to reconstruct, explain, derive,
  or apply fluently. Learn → reconstruct → delayed retrieval → progressively
  longer retrieval → maintain when justified.
- **working:** understand deeply and recover practical fluency with a modest
  refresh. Learn → demonstrate → some delayed retrieval when useful → refresh
  around actual future use, without continual spaced review by default.
- **reference:** understand what it is, why it exists, when it matters, and how to
  recover exact details. Learn/understand → demonstrate enough understanding →
  record retrieval path/source/context → no routine spaced-retention burden.

Missing target means **unspecified**, not core. Respect existing choices. A tutor
may recommend a target with a short rationale, but the learner decides consequential
choices; never silently assign or reassign targets. Do not turn every block into
a questionnaire. Note promotion is still separate from both evidence and targets.

Recommend using qualitative questions: Is this a prerequisite for many later
capabilities? Will the learner reason with it repeatedly? Would lookup interrupt
reasoning? Is reconstruction expensive? Does fluent understanding need immediate
availability? Is it central to a stated long-term goal? Conversely, can the exact
detail be recovered almost instantly? Is knowing it exists the useful knowledge?
Is it an implementation/API detail rather than a conceptual dependency? Is its
exact value rarely needed? Foundational probability or physical reasoning may be
core; rarely used constants, identities, syntax or API spelling may be reference.
These are examples, never domain rules or a numeric score. Retention priority must
not be inferred solely from graph centrality, AI confidence, note frequency, or
arbitrary numeric scoring.

Targets do not alter historical attempts, evidence-derived state, recorded review
horizons, or conservative prerequisite readiness. An overdue reference horizon is
historical evidence context, not an automatic high-priority review warning. Show
its policy explicitly: no routine spaced review. Frontier means eligible for
learning/checking, not a recommendation to drill every node. When a dependency
requires fluent recall rather than lookup, handle that explicitly in learning
design and the capability definition; never claim false mastery from its target.
Missing/failed evidence can warrant a contextual check for actual use, regardless
of target. Do not destroy old evidence or invent an expiry date.
