# Ownership and defense acceptance fixture

Every source, answer, verdict, approval and decision here is fictional. This tests
structure and separation of axes; it supplies no scientific truth or actual human
learning evidence. Use a fresh disposable copy of this directory for generated files.

From the repository root (replace `<copy>` with that copy's absolute path):

```bash
python -S -B examples/defense/demo.py --root <copy> --output target.json
python -S -B scripts/defense.py project --root <copy> --input target.json --as-of 2026-10-08
python -S -B scripts/defense.py ownership --root <copy> --input ownership.json --as-of 2026-10-08
python -S -B scripts/defense.py viva --root <copy> --input target.json --claim T-2 --as-of 2026-10-08
```

The generator binds actual file bytes and canonical JSON fingerprints at run time,
so newline conversion does not leave stale committed hashes. Without `--output` it
prints target and ownership declarations without writing. Explicit output creates
two new files: `ownership.json` and the requested target. It never overwrites them.
These two publications are not a transaction; a failure after creating ownership
may leave that file for explicit inspection. Do not retry over existing outputs.

| Target | Scientific support | Personal defensibility | Why |
|---|---|---|---|
| T-1 | SUPPORTED | DEFENSIBLE | Scoped reviewed atom, current explanation and derivation |
| T-2 | SUPPORTED | INCOMPLETE | Same scoped science; partial, hinted explanation |
| T-3 | OVERSTATED | DEFENSIBLE | Broader wording explicitly rejected despite strong learning |
| T-4 | UNCERTAIN | DEFENSIBLE | Unresolved scientific claim, independent learning evidence |
| T-5 | UNCERTAIN | UNKNOWN | Agent implementation choice with unknown method, tool and navigation evidence |

G-1 is a selective ownership requirement for the agent choice. Its code and accepted
decision are bound references; its three canonical capabilities remain unknown.
The accepted decision and approved experiment stay unchanged by every projection.
No global readiness flag or score hides any of the five cases. The planned fixture
experiment and valid computational manifest are provenance, not observed success.

Viva emits one question and an explicit question contract, without its answer.
To continue, supply `--session viva.json` using the protocol's `viva_schema: 1`
wrapper, current declaration fingerprint, claim ID, the existing tutor lesson events,
and reviewed answer classifications. Record the actual probe/answer/criteria/verdict/
assistance before asking a follow-up. Vague answers request a concrete drill-down;
honest uncertainty requests targeted learning. Learner questions can interrupt and
resume without probe cost. Follow-up probes share the same budget when asked.
The tests demonstrate these sessions, including stale sessions, revealed answers,
budget exhaustion and separate canonical readiness. Transfer needs an explicitly
unfamiliar scenario rather than an inferred independence label.

`--export snapshot.json` explicitly creates a new read-only projection with an as-of
date and all input hashes. It does not change ledgers, accept claims, alter research
approval, run the workflow or access any source/account. Refresh snapshots from the
original files; missing/changed references stay visible and wording reviews must
bind the actual target, atom and literature manifest. Reviewers remain responsible
for semantic overstatement, assessment sufficiency and honest provenance.
