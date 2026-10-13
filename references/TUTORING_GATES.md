# Concept-first tutoring gates (v0.9)

The learning protocol says to teach the general idea before the project application, to address prerequisites
deliberately, to probe for reasoning rather than recognition, and to keep evidence honest. These gates make those
rules executable. They live in `scripts/tutor_gate.py`; none of them grades an answer, edits a learner ledger or infers
mastery. Canonical capability ledgers stay human-approved, and unknown mastery stays unknown.

A session opts in by declaring teaching blocks and/or giving its questions a contract. A session that declares neither is
left alone.

## 1. Declare what each section teaches

`html_sessions.py declare-block <session> --source block.json`, with

```json
{"id": "density", "heading": "From the exponential to the gamma density", "kind": "derivation",
 "target": "gamma-density", "assumes": ["gamma-function", "exponential-distribution"],
 "introduces": {"shape parameter": "The number of waiting stages."}}
```

`kind` is `concept`, `intuition`, `derivation`, `review`, `application` or `implementation`. The heading must match
exactly one heading of the lesson, so a declaration cannot drift from what the learner reads. `assumes` lists the
concepts the section relies on; `introduces` defines each new term where it first appears.

## 2. Run the gate before posting

```
python scripts/tutor_gate.py --root <vault> check <session> --receipt <context receipt>
```

The learner view comes from the context receipt (`html_sessions.py context --json`), or from `--learner file.json`
(`{concept-id: state}`). `--no-learner` checks structure only and says that the prerequisite gate was **not** run.

* **A dependency is satisfied** when the learner's record shows it demonstrated or retained and still fresh, or when an
  earlier block in this lesson teaches it. The second is *deliberate explanation*, reported as `explained-earlier`,
  and the concept stays unknown in the learner's record until a reviewed answer says otherwise.
* **Otherwise the block is blocked** (`UNSUPPORTED_PREREQUISITE`). Teach the dependency in an earlier block, probe it with
  a contract question, or branch to a prerequisite lesson, then check again. Weak, stale or in-progress is not established.
* **An application block** needs its concept taught earlier in the lesson or established (`APPLICATION_BEFORE_CONCEPT`).
  Project explanations never substitute for the foundation.
* **A question** may assume only what is established, explained *before it in the lesson*, or defined in its own
  `INTRODUCES`.

## 3. Every probe carries a contract

On the question: `contract` (`TESTS`, `ASSUMES`, `INTRODUCES`), `scope` (conceptual, transfer, project_application),
`dimension`, `method`, `units`, `probe` and, for any answer someone must review, explicit `criteria`.

* One separately assessed capability per probe. The knowledge model's rules apply: recognition may use a choice;
  explanation, derivation, transfer and application need the learner to produce the reasoning. Transfer needs an
  explicitly independent example.
* `probe` is one of conceptual-choice, short-explanation, derivation, prediction, error-identification, transfer,
  calculation, tool-exercise, code-comprehension, implementation-task.
* Every assessed unit counts against the diagnostic budget (default 5). Only the learner can extend it, with a recorded
  request.
* Multiple-choice options are checked for cues a guesser could use (few options, duplicates, "all of the above", the
  correct option much longer, absolute words only in distractors). These are warnings: whether the distractors are
  scientifically plausible needs a human.

`add-question` refuses a malformed contract when the question is posted; `html_sessions.py validate` holds the whole session
to its declarations.

## 4. When the learner asks for another explanation

The Questions panel offers: more simply, more rigorously, show the derivation, visually, an analogy, a worked example,
physical meaning, how to implement it, review prerequisites. A request is recorded with the section it was asked in and
appears in pending activity. Add the explanation to the lesson under a new heading (`append`), then
`html_sessions.py answer-explanation <session> <request-id> --heading "<exact heading>"`. The learner is offered a link to it
and a way back to where they asked. A request is never a response, never evidence and never changes the learner's record.

## 5. Evidence is proposed, never granted

Review free responses against every declared criterion:
`html_sessions.py review <session> <question> --verdict correct --criteria-met true,true --reviewed-by "<who>"`. A `correct`
verdict needs every criterion met.

`python scripts/tutor_gate.py --root <vault> evidence <session> <question>` prints what the reviewed answer could contribute: the
actual response, criteria and which were met, scope and dimension, hints used, whether the solution was shown first,
the reviewed outcome, whether it counts as an independent demonstration, and retention as `not-assessed` (retention is
recorded by later retrieval). It writes nothing. A click, an auto-checked option or an unreviewed answer is never
evidence; hints or a revealed solution make an attempt assisted; recognition cannot stand in for reconstruction.

## 6. Implementation literacy

A section that explains research code or methodology is an `implementation` block and must carry, in `literacy`: why this
method was chosen, what it assumes, how it works, how to run it, how to verify its output, where to find and change it
(`code_locations`: path and what to change), how it fails, and the alternatives. The gate refuses a block missing any of
the eight, and the items are shown on the page under the section's heading, so declaring them means teaching them.
