# Scientific Visualization Protocol

Visualization serves understanding, not decoration. Prefer **one visual carrying
one central idea**. This protocol owns scientific visual and animation decisions;
`LEARNING_PROTOCOL.md` owns teaching/retrieval, `SOURCE_POLICY.md` owns evidence,
and `RESEARCH_PROTOCOL.md` owns research plans and execution approval.

## Choose the teaching need

State what the learner should notice, predict, or explain after seeing the visual.
Use a visual when relationships, geometry, scale, variation, or temporal evolution
are materially clearer than prose. Skip it when a short explanation suffices.
Prepare visual candidates before live probing; do not start a long rendering job
between every answer. Ask for a prediction before revealing a change when useful,
then check explanation or transfer afterward. Watching an animation is not
retrieval evidence or permission to promote a permanent note.

Choose the presentation form before the backend:

- **Diagram:** relationships, coordinate conventions, or geometric structure.
- **Plot:** numerical relationships or comparisons with meaningful axes.
- **Interactive exploration:** the learner needs to vary a parameter or viewpoint;
  expose only controls that serve the question, with valid ranges and clear defaults.
- **Animation:** order, continuous change, or a mathematical transformation is the
  idea being taught. Prefer static panels when they communicate it as well.

## Source-first policy

Before generating a teaching visual, ask: **would an authoritative existing
visual better serve this concept?**

```text
visual need
   |
authoritative source visual exists?
   |- yes -> use / link / embed it with provenance
   |- no
       |
       can verified equations, data or geometry generate it?
       |- yes -> reproducible generated visual (record basis and parameters)
       |- no  -> schematic, explicitly labelled as a schematic
```

Preferred sources, in roughly descending authority for the claim being shown:
the primary paper, official experiment or software documentation, a textbook, and
reputable university material. Check licence/permission before copying a figure;
linking or citing with a locator is always acceptable. A source figure still needs
a citation and locator, and it does not become correct because it is published:
confirm it shows the regime and conventions the lesson needs.

Never treat a visually plausible generated image as scientific evidence, and never
let it stand in for a source figure the learner could have been shown. A generated
visual is not reusable merely because it rendered: record it in the visual registry
(`scripts/visuals.py`, `*.visual.json`) and let it advance only through
`candidate -> rendered -> inspected -> verified`. Only `verified` assets are
reused automatically as trusted teaching visuals; others are drafts to be
re-inspected. `verified` is a human/inspector attestation of the specific claim
the visual makes, not a rendering check.

Animations should normally be user-requested or clearly justified by temporal or
transformation pedagogy (order, continuous change, a mathematical transformation).
A static key-frame panel is the default when it teaches as well.

## Simplest suitable backend

These are optional capability recommendations, not Research OS runtime dependencies.
Use an available equivalent when it preserves the scientific and teaching contract.
Do not install a backend automatically. Research OS installation and validation
must work without any of them; no renderer framework or plugin registry is required.

| Backend | Appropriate capability |
|---|---|
| Mermaid | Dependency, flow, and relationship diagrams; learning graphs with explicit prerequisite edges. |
| Matplotlib | Scientific static plots, comparisons, and simple frame sequences. |
| Plotly | Interactive plots for parameter exploration, hover details, and selected viewpoints. |
| SVG | Custom static scientific diagrams with precise labels and geometry. |
| PyVista | Scientific 3D geometry, meshes, fields, and point clouds when depth matters. |
| Manim Community | Default Manim recommendation for explanatory mathematical/scientific animation. |
| Motion Canvas | Optional alternative for 2D explanatory animation. |

`3b1b/manim` is the original 3Blue1Brown implementation/reference, not the default
or a required backend. A requested backend can be used when available and suitable;
do not switch merely for stylistic preference. Consult its current official
documentation when implementing version-sensitive APIs.

If the preferred capability is unavailable, use a simpler available static view
when it still answers the teaching question. Otherwise return an explicitly
unrendered source/storyboard and the missing capability, not a claimed finished
animation. Do not silently substitute invented motion for unavailable simulation.

## Declare what the visual represents

| Kind | Meaning and provenance |
|---|---|
| Conceptual illustration | A schematic relationship or mechanism; no implied quantitative fidelity. Label schematic/not to scale where the distinction matters. |
| Model-driven visual/animation | Values follow stated equations with parameters, initial/boundary conditions, units, and domain of validity. Distinguish a toy model from a validated physical model. |
| Simulation/data-driven visual/animation | Values come from identified simulation outputs or datasets; preserve provenance, processing, sampling, and uncertainty. A simulation is not automatically experimentally validated. |

Mixed visuals must distinguish these components. For example, a measured profile
with schematic branching beside it must not suggest that the branches are measured
particle trajectories. A plot of a probability density is not a realized event.

**A scientific animation must not fabricate quantitative physics for visual effect.**
If a displayed trajectory, position, time, angle, field, energy, probability,
geometry, scale, distribution, or other quantity represents physical reality,
derive it from a stated equation, validated model, simulation, or dataset.
For approximate/toy models, explicitly limit the claim to that model and identify
unvalidated assumptions. Apply source-policy scope and provenance standards to
important physical claims; pause and verify unsupported claims before rendering.

Keep editorial transitions separate from scientific evolution. Moving a label or
camera for explanation is allowed; interpolating a particle path or changing an
energy to make a scene attractive changes the scientific content. Label any
illustrative motion accordingly. Do not use easing functions as physical time
integration, or imply measured dynamics through presentation timing.

## Quantitative and animation checks

Before constructing the visual, establish the applicable equation/model/data,
quantity definitions, units, coordinate origin and orientation, scale, and valid
parameter range. Keep this proportional: a prerequisite diagram needs edge meanings,
not a physics simulation specification.

For scientific plots, geometry, and animation:

- Label axes, units, legends, normalization, and reference frames. Identify log
  scales, truncated ranges, arbitrary units, exaggerated dimensions, and projections.
- Preserve aspect ratio where angles or geometry are being interpreted. Explain
  occlusion or camera perspective when it could change the apparent result.
- Distinguish physical time, integration step, sampling interval, frame rate, and
  playback speed. State time compression, looping/reset, and interpolation when used.
- For numerical evolution, check relevant initial/boundary conditions, limiting
  cases, resolution/time-step sensitivity, and applicable conservation or
  normalization constraints. Use only checks that bear on the displayed claim.
- Do not imply conservation in a projected/open subsystem where it does not apply;
  identify unshown components when interpreting a balance.
- For stochastic visuals, record the seed and sampling/model assumptions; one
  realization is not an ensemble result. Never turn arbitrary random branching
  into claimed physical probabilities or energy sharing.
- Keep comparison scales stable, or visibly announce scale changes. Preserve
  uncertainty and distinguish observations, model predictions, and extrapolation.
- For interactive controls, test endpoints and invalid combinations. For animation,
  make the central change legible with pause/replay or a static key-frame companion
  when practical. Avoid decorative motion that competes with the explanation.

## Render, inspect, and return

Render the actual deliverable and inspect it before presenting it as complete.
Check clipping, labels, contrast, axes, units, orientation, and whether the central
idea is readable at the intended size. Do not rely on color alone to encode state.

For animation, inspect initial/final frames, intermediate frames, and all important
transitions, then play the result to check timing and continuity. For interactive
output, exercise the meaningful controls and inspect the resulting views. Compare
representative displayed values against their equations or source data; successful
rendering alone does not establish scientific correctness. Repair and rerender when
inspection reveals a problem. If rendering/playback is unavailable, disclose exactly
what remains unverified and label the artifact as a draft.

Keep reproducible source, parameters, data references, and outputs in the research
repository's existing figure/assets/results location when they support research
claims. Record the rendering command and relevant backend version; include seeds
and input provenance when applicable. Do not copy private datasets into a vault.

For teaching-only exports, use the configured Obsidian assets location and link from
the authorized working session/learning note. Use existing conventions; no fixed
vault migration is required. Prefer linking to reproducible research artifacts
instead of maintaining divergent copies. Do not overwrite unrelated assets or
silently add visuals to permanent concept notes.

Return the artifact path/preview, one sentence stating the central idea, its kind
(schematic/model/data), and essential assumptions or limitations. Keep reproducibility
details beside the artifact rather than crowding the teaching view.

Creating a requested teaching diagram or rendering existing approved data does not
require a new full research cycle. A new research simulation, model implementation,
or experiment still follows the research protocol's concrete plan → explicit human
approval → execution gate. Visualization never bypasses that gate. Specialist
validation is selected by scientific risk; a visualizer's self-check is not an
independent physics review.

## Example teaching choices

These are possible tasks, not assumptions about any particular research project:

| Central idea | Suitable view and scientific boundary |
|---|---|
| Prerequisite readiness | Mermaid with state labels and prerequisite arrows; note existence does not imply mastery. |
| Changing gamma-distribution parameters | Static curves or interactive plot with declared shape/scale convention, support, and normalization. Parameter sweep is not physical time. |
| Longitudinal shower profile | Plot a stated profile model or identified data, with depth/energy conventions and regime limits. |
| Electromagnetic shower branching | Label a conceptual tree schematic; quantitative branching positions, probabilities, or energy sharing require a supported model or simulation. |
| Fractal box counting | Show grid scales and counts from the same object/data; identify finite-scale and grid-offset effects. |
| Lorenz evolution / Lyapunov divergence | Use declared equations, parameters, initial conditions, and numerical solution; camera motion or hand-drawn separation is not dynamical evidence. |
| Wave propagation | Animate a specified wave equation/solution with boundary conditions and time/space scales. |
| Detector geometry / vector field | SVG or PyVista as needed; specify coordinates and distinguish documented geometry from a schematic or sampled field. |
| Quantum/Bloch-state evolution | State the system, representation, and evolution law; the sphere depicts state coordinates, not a particle's physical orbit. |
