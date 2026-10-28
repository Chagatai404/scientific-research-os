---
name: defend
description: Help the researcher own their work — write and practise defence items for audited claims, walk through the code that produces a number, and report ownership (unowned, practising, owned, waived). Use for "defend my research", "walk me through this code", thesis or talk preparation.
---

# Defend

Notebook understanding is available in the desktop's Sources → Codebase view. The retained
`notebook_coverage.py` and `notebook_trace.py` engines are also installed under this skill's
`scripts/` directory. Coverage distinguishes imports from mentions; test-file presence never
proves execution. Trace and mutation require an explicit human notebook permission, use a
committed scratch copy and scrubbed environment, and preserve the original repository.
Scratch execution is data isolation, not an OS security sandbox; run trusted notebooks only.

A claim is owned when the researcher can defend it from memory, and still can at its review. Contract:
`references/RESEARCH.md` (defence bridge).

## Defence items

For each open `item` task on a claim (`work --by <you> --kinds '["item"]'`), write one free item with `add_item`:
`kind: free`, `concepts: ["claim:<id>"]`, `defence: <kind>`, a rubric with checkable criteria, and the explanation.
The five kinds:

- **derivation** of the method;
- **baseline**: why this one;
- **falsifier**: what would falsify the claim;
- **rejection**: the adversary's strongest argument and its answer;
- **code**: where the number comes from (file and function, from the claim's `implements` edges and `code`).

`finish` the task with the item hash.

## Practice

`start --scope claim:<id>` and run it like any lesson (skill `learn`): free recall, graded against the rubric.
`claim_status --claim claim:<id>` shows ownership. A lapse at review puts it back to practising.

## Code walkthrough

To show where a number comes from: `python -m ros.lib.code_walkthrough --repo <repo> map`, then `units`, `locate`
and `trace` (approved commands only). A walked unit's file and function go into the `code` defence item.

## Waiver

If the researcher accepts the risk of not owning a claim, they record it themselves (`waive`, a person's act).
Never suggest waiving to save time.
