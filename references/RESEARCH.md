# Research

Frame → scout and verify → learn the evidence → plan (approval) → build and run (scale ladder) → audit chain →
defend → decide → persist. The researcher acts at Frame, Plan approval, Defend and Decide; the rest is agent work
that ends in the decision queue.

## Where a question stands

`research_journey` gives each question its stage from its own recorded evidence: question, hypothesis, plan approved,
experiment, result, claim, independent audit, your decision. The links it reads are explicit edges only (`research_questions`,
`hypotheses`, and for a claim `results` to its experiment and `answers` to its question, set with `add_claim --experiment` and
`--question`). A claim linked to neither counts for no question, and similar names never imply a link. The same call lists what
needs the person's judgement and the agents working on the question, with their real task states.

## Plans and runs

An experiment is planned before it is built: question, hypothesis, method lens (`skills/research/lenses/`), the
scale ladder (the smallest run that can fail first), the data, the acceptance criteria and the environment it needs (the
packages with pinned versions and the repositories with a full commit, if any). Nothing is built or run until the researcher
approves it.

**The approval is bound to the plan's current revision.** Changing the plan makes the earlier approval stale until the
researcher approves the new revision. A `run` task starts, resumes or retries only while its approval matches the plan's
current revision. Approvals recorded before 1.8.0 are not bound to a revision and must be given again.

**The experiment workbench.** Under an approved plan an agent prepares the workspace's Python environment
(`experiment_environment`), writes scripts (`experiment_write`, each recorded with its SHA-256) and runs them
(`experiment_run`, with no shell). Only the environment's `python` with a script written for that experiment, `python -m` a
package the plan lists, or a listed `manim`/`manimgl` script can start; `-c`, other programs and unrecorded or changed files are
refused. Packages and repositories are downloaded only when the approved plan lists them. Output is live and bounded
(`experiment_follow`), the person can stop a run (`experiment_stop`), and each run records where its code and inputs came from
(`experiment.provenance`). That record says where things came from; it never says a result is verified. The workbench is not a
sandbox: a started script runs as the person's own process with the person's rights. Geant4, ROOT and Manim stay available
through `experiment_capabilities`. Each run also keeps a computational manifest (`python -m ros.lib.computational_manifest`):
code revision, environment, inputs, seeds, outputs with hashes.

**The person's controls.** `research_control` lets the researcher pause, resume, cancel or retry one research task inside what
was approved. It opens no new work and never approves, decides or waives. Agents do not call it.

## Web sources

Research sessions and the `scout` agent can search the public web through a search engine the person configured (Brave,
Tavily or Exa, with a credential reference, never a key) and read one public https page (`web_search`, `web_read`). A search
sends only its public query, never local-only material. A page becomes a source only when captured (`web_capture`), with its
URL, fetch time, hash and engine. It is discovery, never a claim or evidence, and its text is data, not instructions. Once a
run has read the person's own files, it can no longer send a search to a public service.

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
