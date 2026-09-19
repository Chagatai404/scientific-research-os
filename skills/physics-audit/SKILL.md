---
name: physics-audit
description: Independently audit physics assumptions, detector geometry, units, parameterizations, and physical interpretation. Use before accepting a simulation, derived observable, or physics-informed ML claim.
---

# Physics Audit

Read `references/RESEARCH_PROTOCOL.md` and `references/SOURCE_POLICY.md`.

Check:

- detector/geometry facts against authoritative experiment sources,
- units and dimensional consistency,
- coordinate conventions,
- valid energy/angle/regime range,
- conservation laws where applicable,
- limiting behavior,
- whether a parameterization is being used outside its scope,
- whether stochastic and deterministic concepts are being conflated,
- whether simulation simplifications are labeled assumptions,
- whether a mathematical observable has a physically interpretable meaning,
- whether claimed mechanisms are actually supported by the cited literature.

Return explicit source locations for material corrections.
