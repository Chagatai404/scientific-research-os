# Research

Frame → scout and verify → learn the evidence → plan (approval) → build and run (scale ladder) → audit chain →
defend → decide → persist. The researcher acts at Frame, Plan approval, Defend and Decide; the rest is agent work
that ends in the decision queue.

## Plans and runs

An experiment is planned before it is built: question, hypothesis, method lens (`skills/research/lenses/`), the
scale ladder (the smallest run that can fail first), the data and the acceptance criteria. Nothing is built or run
until the researcher approves it. Each run keeps a computational manifest (`python -m ros.lib.computational_manifest`):
code revision, environment, inputs, seeds, outputs with hashes.

## Claims and the audit chain

A claim records its text, author, assurance level and the numbers it cites (`{value, file, column|key}`). Before any
model is asked, `precheck` finds every cited number in its result file.

| Step | Asks |
|---|---|
| integrity | fake ground truth, self-normalized scores, phantom results; and the seven failure modes: implementation bug passing self-review, hallucinated citation, hallucinated result, shortcut reliance, bug reframed as insight, methodology fabrication, early frame-lock |
| result-claim | does the result say what the claim says, in its scope? |
| numbers | is every number traced to a run and a file? |
| citations | does each source say what it is cited for, at an exact locator? |
| kill-argument | the strongest case for rejection, answered point by point, adjudicated |

Required steps by assurance: draft — numbers; internal — integrity, result-claim, numbers; presentation — all but
none optional except as listed: integrity, result-claim, numbers, citations, kill-argument; submission — all five.

Verdicts: PASS, WARN, FAIL, BLOCKED, ERROR, NOT_APPLICABLE. A claim's verdict is the worst over its required steps;
a missing step keeps it pending. The author cannot audit their own claim (names are compared ignoring case and
spaces, and `ros` is the pre-check's name, not an auditor's); an integrity verdict marks every failure mode with a
known name as `ok` or `concern`; any concern rules out PASS. BLOCKED, ERROR and NOT_APPLICABLE give their reason in
the notes. A verdict is accepted only for a step the claim's assurance requires. A manual `numbers` verdict cannot
override a failed pre-check: fix the claim or its files and run `precheck` again. Auditors get claim text and file
paths only.

`precheck` finds each cited number in its file. For a CSV, `"where": {"particle": "proton"}` restricts the match to
rows with those column values, so another row cannot vouch for the number. A claim above `draft` that cites no numbers
gets a WARN from the pre-check, not a silent pass.

## Framing nodes

`question`, `hypothesis` and `experiment` nodes (`add_node --type <type>`, id `<type>:<key>`) carry a `status` and an
experiment an `authorization` (`awaiting`, then `approved`, `rejected` or `modification-requested` once the researcher
approves in the portal). They are linked with `add_edge --type relates --data '{"relation": "<name>"}'`: a hypothesis
to its question with `research_questions`, an experiment to its hypothesis with `hypotheses`, an accepted decision
to the experiment it decides with `experiments`. `research` lists the next step each one waits for.

## Defence: the bridge into learning

A claim that passes opens five defence items: the derivation of the method; why this baseline; what would falsify
it; the strongest rejection argument and its answer; where in the code the number comes from. Ownership:

| State | Meaning |
|---|---|
| unowned | no defence item answered |
| practising | some answered, or not all secure |
| owned | every kind answered correctly and unaided, none past its FSRS review |
| waived | the researcher accepted the risk, with a reason |

Presentation and submission claims are accepted only when owned or waived.

## Commitments and proposals

A reviewer's or supervisor's comment is split into atomic commitments, each naming the evidence that fulfils it.
Agents may propose changes to skills or the policy; the researcher decides.
