# Preparation

A lesson plays only prepared content; the gate (`bundle_check`) decides when it is ready.

| Piece | Made by | Gate |
|---|---|---|
| Narration per node (motivate, establish, connect) | the tutor agent from the dependency map and a scout's source map | Every segment has text that can be spoken (formula spans pass `speech_text`); every factual claim has a source locator or is marked as a derivation; math renders in KaTeX |
| Voice | `bundle_voice` (Kokoro English by default; Chatterbox for Turkish) | 100% of segments have audio |
| Static visuals | `visual-maker` | Rendered file, a RESULT note from the maker who looked at it, at most 7 elements |
| Animation | `visual-maker` with Manim through `bundle_animate` | For every dynamic node (change over time, motion, a limit, a distribution building up): MP4, poster and key-frame strip, a stated basis, key frames looked at |
| Clip (optional) | `video-scout` | One segment of at most 3 minutes, verified against its transcript; otherwise left out |
| Items | the tutor agent | Probe items at 3 or more difficulty levels per strand; a check item per node; a free-recall close item; a transfer item. Valid, distinct options that never justify themselves, math that renders |
| Manifest | `prepare` | Hashes of the plan and every file; ready only when every row passes |

A changed file or plan voids readiness until the gate passes again. Missing pieces become tasks for agents
(`bundle_tasks`). A lapse in review re-enters preparation for that node only.

## Writing narration

Short sentences, spoken order ("x squared", not "x^2" read aloud: the speech layer verbalizes LaTeX). One idea per
segment. Motivate first: why this is needed now. Establish by letting the learner discover it when they plausibly
can; otherwise show how one could have discovered it. Connect to what they already hold.

## Visuals

One central idea per visual, at most 7 elements, labels legible at lesson width, nothing cut off. Quantitative
visuals are drawn from data or equations and say which; schematic ones say they are schematic. The maker renders,
looks, fixes, and only then writes the RESULT note.

## Animations

Motion must have a basis (an equation, a model or data), stated in the spec. Scenes are linted before rendering and
run in a subprocess; key frames are looked at before the animation is attached.
