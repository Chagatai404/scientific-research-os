---
name: research
description: Run a research project on the Research OS record from a framed question to a decided, defended claim — scouting, learning the evidence, planning with approval, building on a scale ladder, auditing, and the decision queue. Use for research sessions, hypotheses, experiment design, simulations (Geant4), ML and QML experiments.
---

# Research

The researcher works at four points: **Frame**, **Plan approval**, **Defend**, **Decide**. Everything between runs
as agent work and ends in the decision queue (`queue`). Contract: `references/RESEARCH.md`; evidence rules:
`references/EVIDENCE.md`.

## The cycle

1. **Frame.** The researcher states the question. Record it (`add_node --type question`). In the non-generation mode
   (when they ask for it) you only ask and mirror; you do not propose hypotheses until they say so.
2. **Scout and verify.** Send neutral briefs to `scout` agents in parallel (competing models, null results, validity
   limits, reviews, primary work). Send each candidate claim to a `verifier`. Record verified claims as EvidenceAtoms.
3. **Learn the evidence.** Gaps in what the researcher needs become lessons (skill `prepare`, then `learn`).
4. **Plan.** Write the experiment plan with its scale ladder (smallest run that can fail first). Record it as an
   `experiment` node with `authorization: awaiting`. Nothing runs until the researcher approves it in the portal or
   at the terminal (`approve` is a person's act; you cannot call it).
5. **Build and run.** Implement, run the ladder, keep a computational manifest per run.
6. **Claims.** Each result becomes a claim: `add_claim` with `author` = whoever produced it, the `assurance` level
   (draft, internal, presentation, submission), the numbers it cites (`{value, file, column|key}`), and the artifact
   paths. Then `precheck --root <repo>`: every cited number must be found in its result file.
7. **Audit.** `request_audits` opens one task per required step; give each to a fresh `auditor` (or `verifier` for
   citations, `adversary` for the kill-argument) with the task's text and paths only. Verdicts come back with
   `verdict`. You cannot audit a claim you authored.
8. **Defend.** A claim that passes opens five defence-item tasks; write the items (free, rubric, `defence` kind,
   concepts `[claim:<id>]`) and let the researcher practise them (skill `defend`).
9. **Decide.** The researcher decides in the portal. Presentation and submission claims need ownership or a waiver.

## Method lenses

Load the lens for the method before planning: `lenses/geant4.md`, `lenses/ml.md`, `lenses/qml.md`.

## Also

- Reviewer or supervisor comments: split them into atomic commitments (`commit`), each with the evidence that
  fulfils it.
- To change a skill or the policy, `propose` it; only the researcher applies it.
