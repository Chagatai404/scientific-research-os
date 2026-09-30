---
name: visualize
description: Create scientific teaching diagrams, plots, interactive explorations, or physics/mathematical animations when relationships, geometry, scale, parameters, or evolution are clearer visually. Use for explanatory scientific visuals, not decorative imagery or general website design.
---

# Visualize

Read `references/VISUALIZATION_PROTOCOL.md` before creating the visual. Read
`references/SOURCE_POLICY.md` for scientific claims needing evidence, and
`references/LEARNING_PROTOCOL.md` when integrating with tutoring. In the source
tree, resolve these paths against the repository root; installed skills include
local copies of the shared references.

## Workflow

1. Identify one central teaching idea and the intended learner action: notice,
   predict, reconstruct, or explain. Reuse prepared lesson evidence when available.
2. Apply the protocol's source-first policy: would an authoritative existing
   visual (paper, official documentation, textbook, university material) serve
   better? If so use/link/embed it with provenance; otherwise generate only from
   verified equations/data/geometry, else label a schematic. Check
   `scripts/visuals.py --reusable --concept <id>` for an already verified asset.
   Then classify the visual as source, conceptual, model-driven, or
   simulation/data-driven and establish its inputs and assumptions.
3. Choose the simplest adequate form/backend from the protocol. Use the existing
   visualizer agent for a bounded production task when delegation adds value; the
   skill also works directly without an agent or a specific provider.
4. Create, render, inspect, and return the artifact with its provenance and limits
   under the protocol. If capabilities are missing, apply its fallback/draft rules.
5. For tutoring, follow with an explanation or transfer check; do not treat viewing
   as demonstrated understanding or automatically promote permanent knowledge.

For work that introduces a research model, simulation, or experiment, read
`references/RESEARCH_PROTOCOL.md` and preserve its explicit approval boundary.
Rendering an already authorized teaching artifact does not start another research
cycle. This skill does not install rendering dependencies automatically.

## Trigger and evaluation examples

- **Trigger:** “Show how the gamma density changes with shape, then help me explain
  the difference.” Choose a plot/interactive view with explicit parameter convention.
- **Trigger:** “Animate wave propagation from this specified solution.” Preserve
  the equation, scales, and physical-time mapping; inspect the rendered motion.
- **Non-trigger:** “Make a decorative particle background for my portfolio.” This
  is general visual design, not scientific teaching.
- **Failure mode:** Visually convincing shower branches with invented angles or
  energy sharing presented as simulated physics. Apply the protocol's schematic
  distinction or obtain supported quantitative inputs before producing that claim.
- **Evaluation task:** Given a neutral scientific question, a stated equation/data
  source, and an available renderer, produce one inspected visual and a prediction
  question. Check that units, model scope, provenance, and output agree. Repeat with
  an unavailable renderer: the response must provide an honest simpler alternative
  or unrendered draft, not claim successful rendering or install a backend silently.
