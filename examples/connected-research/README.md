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
ros init connected-demo
ros -p connected-demo import --kind research --path examples/connected-research
ros -p connected-demo import --kind learning --path examples/connected-research
ros -p connected-demo research
ros -p connected-demo code --node experiment:EXP-001
ros -p connected-demo capabilities --scope capability:physics.shower-profile --as-of 2026-09-30
python -m ros.lib.knowledge --root examples/connected-research --capability physics.shower-profile --dependencies --json --as-of 2026-09-30
```

What to expect: `research` lists each record's next mechanical transition (unranked; not a recommendation), `code`
shows `src/profile_fit.py` implementing EXP-001, and `capabilities` shows the shower-profile capability blocked by its
prerequisites. These are the same answers the old `research.py` and `knowledge.py` gave (checked in
`tests/test_ros_importers.py` and `tests/test_ros_graph.py`).

## What this example deliberately does not do

It does not mark H-001 accepted or rejected (no decision exists), does not rank
EXP-001 against EXP-002, and does not let a stale prerequisite block approved work.
An accepted decision, an experiment approval and a `verified` visual are each a
recorded human act.
