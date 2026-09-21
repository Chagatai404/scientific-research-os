# Learning Protocol

The goal is understanding that can be reconstructed, not copied notes.

## Loop

1. **Probe** — find the edge of current understanding.
2. **Map** — build a small dependency graph from known foundations to the target.
3. **Teach** — one dependency node at a time.
4. **Connect** — state how each node follows from established knowledge.
5. **Retrieve** — quiz recall, explanation, derivation, transfer, and implementation.
6. **Promote** — the human rewrites durable understanding into permanent notes.

## Probing and retrieval formats

### Fast active probe

Before a probing block, establish internally the tested concepts, expected
understanding, acceptable variants, likely misconceptions, hint ladder, and
progression criteria. Verify uncertain facts and prepare sources before the block.

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
3. avoid making the correct answer obvious through wording or length;
4. avoid introducing information that gives away a later question;
5. ask for a brief reason when the reasoning matters;
6. optionally ask for confidence when distinguishing understanding from guessing.

A useful compact response format is:

```text
Answer: B
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
