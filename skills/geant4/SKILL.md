---
name: geant4
description: Coordinate scientifically valid Geant4 particle/detector simulation, including geometry, physics, generation, scoring and reproducibility. Use for planning or validating Geant4 work, with explicit research approval before implementation or execution.
---

# Geant4

Read `references/RESEARCH_PROTOCOL.md`, `references/COMPUTATIONAL_PROTOCOL.md`,
`references/GEANT4_PROTOCOL.md`, `references/SOURCE_POLICY.md` and
`references/AGENT_POLICY.md`. In the repository references live at
`../../references/`; installed skills receive local `references/` copies.

Identify the scientific question, approved scope and pinned project environment.
Follow the Geant4 protocol's geometry → physics → generation → scoring → execution
checks. Route physical assumptions to physics-audit, planning to design-experiment
and reproduction to the reproducibility-auditor when useful. Select a
simulation-reviewer for material simulation risks; reviews do not authorize runs.
Use the Geant4 tool pack for software semantics, not detector truth.

Record explicit configuration and observed environment separately. Follow the
canonical research plan/approval gate before build or experiments. Report the
actual artifacts, validation limits and A–D findings. Never invent a physics list,
cut, beam, geometry or event count from runtime discovery.

Installed helper: from this skill directory use
`python scripts/scientific_tools.py probe geant4` for capability discovery and
`python scripts/scientific_tools.py manifest --experiment <id> --repo <project> --tool geant4`
for observed provenance. Supply reviewed choices with `--declared <config.json>`.
Read `extensions/scientific-tools/geant4/GUIDE.md` for software semantics. Helpers
and packs are bundled locally; no source checkout or scientific package is required.


## Context preflight (required)

Before any planning or implementation, load context from the canonical records instead of relying on the chat:

```
python scripts/context_kernel.py preflight --workflow research-implement --target concept:<id>     --project "<project>" --vault "<vault>" [--session <path>] [--record <RQ-id>] [--expect-empty]
```

Read the receipt it prints. **BLOCKED** (exit 2) means an essential source is missing, invalid,
unreadable or unconfigured: stop, report which source and why, and do not continue from memory.
**DEGRADED** means continue only where the limitations do not reach, and say so. Empty is not
unavailable: declare a new learner or project with `--expect-empty`. An unresolved concept is
unknown, never demonstrated. Dependent actions check the receipt themselves (`html_sessions.py create`,
`tasks.py` stages 7/8/14/15), so skipping this step fails rather than passes silently.
See `references/CONTEXT_PROTOCOL.md`.

## Mandatory session artifacts

When this workflow creates or continues a substantive session, follow
`references/HTML_SESSION_PROTOCOL.md`: use the centralized
`scripts/html_sessions.py` API, preserve Markdown backlinks, produce HTML and
structured state, and validate the artifacts. Before creating or resuming, run
`scripts/html_sessions.py context <session>`: it lists unchecked answers and open
questions and loads the project's research and knowledge graphs, which remain the
memory; the page is only a view. Post questions, checks and teaching through the
live loop in that protocol so the session reads in order and updates without reload. Ordinary notes, evidence records and source files retain
their canonical formats. Browser feedback never automatically establishes mastery.
