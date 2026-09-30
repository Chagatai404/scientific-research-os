# Connected research example (synthetic)

Everything here is a fictional fixture. It contains no real data, no real result,
and no evidence about any person's understanding. It demonstrates one project,
`connected-demo`, whose research graph, knowledge graph and visual registry are
linked by explicit references. The three graphs stay separate: research state
(`research/`), learner state (`learning/`), and the optional code reference
(`src/`).

```text
RQ-001                        research/RQ-001.md            active
├── H-001                     research/H-001.md             active
│   ├── EXP-001               completed, validated, adversarial review pending
│   │    ├── evidence         A-width  (EvidenceAtom, EXACT_SUPPORT)
│   │    ├── manifest         results/exp-001/manifest.json (valid)
│   │    └── visuals          VIS-014, VIS-027 (verified), VIS-031 (rendered only)
│   └── EXP-002               planned, human-approved, not yet run
└── H-002                     rejected — solely because DEC-001 is an accepted human decision
```

Learning dependencies (`learning/`), read as of `2026-09-30`:

```text
probability.density  ->  probability.gamma-distribution  ->  physics.shower-profile
retained (core)          demonstrated (working)               stale (working)
```

`physics.shower-profile` is stale (its review date passed): missing recent
evidence, not proven forgetting. It does **not** block the approved EXP-002.

Other pieces: `tutor-sessions/2026-09-25 gamma shape.md` (a closed session with an
inline `![[VIS-014-gamma-shape.svg]]` embed), `assets/visuals/*.visual.json` (the
visual registry), `evidence/`, `results/`, `src/`.

## Try it

From the repository root. `--as-of` fixes the date so output is reproducible.

```bash
python scripts/research.py validate --root examples/connected-research --as-of 2026-09-30
python scripts/research.py status   --root examples/connected-research --project connected-demo --as-of 2026-09-30
python scripts/research.py frontier --root examples/connected-research --as-of 2026-09-30
python scripts/research.py graph    --root examples/connected-research --experiment EXP-001 --as-of 2026-09-30
python scripts/research.py context  --root examples/connected-research --experiment EXP-001 --as-of 2026-09-30
python scripts/knowledge.py --root examples/connected-research --capability physics.shower-profile --dependencies --json --as-of 2026-09-30
python scripts/visuals.py --root examples/connected-research --reusable
python scripts/vault_health.py --root examples/connected-research --as-of 2026-09-30
python scripts/bootstrap.py --root examples/connected-research
```

What to expect:

- **validate** — `Tracked: 6`, no diagnostics.
- **frontier** (unranked, mechanical, not a recommendation):
  `EXP-001: adversarial-review-required`, `EXP-002: execution-available`.
- **status / context** — EXP-001 shows `manifest: valid`, `evidence: A-width —
  EXACT_SUPPORT`, its advisory learning states (retained / demonstrated / stale)
  and `code implemented-by: src/profile_fit.py`. Those evidence and manifest
  states are recorded facts, not scientific acceptance.
- **context** — lists the branch (RQ-001, H-001, EXP-001, DEC-001), the verified
  visuals VIS-014 and VIS-027, and reports what it omitted (sibling branch, and the
  unverified VIS-031).
- **knowledge** — the target's prerequisite closure with state, freshness,
  retention target and frontier flag.
- **visuals `--reusable`** — only VIS-014 and VIS-027; VIS-031 is a rendered
  schematic that has not been verified.
- **vault_health** — structural summary; no errors.
- **bootstrap** — a dry run: the session's one answered question is reported as
  *already recorded in a tracked learning record*, so nothing is proposed twice.

No command writes to this directory.

## What this example deliberately does not do

It does not mark H-001 accepted or rejected (no decision exists), does not rank
EXP-001 against EXP-002, and does not let a stale prerequisite block approved work.
An accepted decision, an experiment approval and a `verified` visual are each a
recorded human act.
