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
