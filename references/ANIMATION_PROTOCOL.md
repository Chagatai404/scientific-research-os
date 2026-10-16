# Animation protocol (v0.9.5)

How a teaching animation is made and registered. `VISUALIZATION_PROTOCOL.md` still owns whether a visual is needed, the rule that motion needs a stated
basis, and the inspection steps. This protocol adds the tooling: one scene file, one spec, detected backends, a recorded render. Nothing here installs
a renderer, and rendering is never verification.

## The shape of a teaching animation

**Predict, play, pause, explain.** The spec carries the prediction question; the learner answers it before the video is shown; the scene pauses where the
spec says (`pauses`), and the explanation follows from what they saw. Watching is not understanding: the check afterwards is the evidence.

## The spec (`animation_schema: 1`)

```json
{"animation_schema": 1, "id": "VIS-complete-square", "title": "Completing the square", "scene": "derivation.py", "scene_class": "Derivation",
 "concepts": ["quadratic-formula"], "basis": "Each line follows from the previous by adding b^2/4 to both sides and factoring.",
 "predict": "What must be added to both sides so the left side becomes a perfect square?", "resolution": "1280x720", "fps": 30}
```

| Field | Meaning |
|---|---|
| `basis` | **Required unless `"schematic": true`.** The equation, data or source that justifies the motion. No basis, no quantitative animation. |
| `schematic` | Not to scale or not physical; registered as a conceptual schematic and never as quantitative. |
| `predict`, `pauses`, `time_mapping` | The prediction prompt, `{at, note}` stops, and how scene time maps to physical time (compression, looping, integration step versus frame rate). |
| `seed` | For any random draw; one realisation is not an ensemble. The linter warns about unseeded randomness. |
| `backend` | `auto` (ManimGX, else Manim Community), `manimgx` or `manim`. `slides: true` selects Manim Community. |
| `scene`, `scene_class` | The scene file, relative to the spec and inside its folder, and the class to render. |

## Writing the scene

Write against the Manim Community API once. This import line lets one file run on either backend: `try: import manimgx as m` / `except ImportError: import manim as m`.
Values on screen come from the stated equations, never from visual convenience. `python scripts/animate.py lint scene.py --spec spec.json` refuses a scene that
imports network, process or file-operation modules, calls `eval`/`exec`, or defines no class named `scene_class`. **It is a screen, not a sandbox:** a scene is
code that runs in the chosen environment, so render only scenes you or the researcher wrote or read, in an environment that holds nothing else.

## Backends and selection

`python scripts/animate.py capabilities [--env DIR ...]` reports ManimGX, Manim Community and their versions, whether `manim-slides` sits beside them, and ffmpeg.
Environments come from `--env` or `RESEARCH_OS_ANIMATION_ENVS`; the PATH is always checked. Install a backend in its own virtual environment, never globally.
ManimGX needs Python 3.13 or newer; Manim Community builds on Python 3.11 here. With no backend, `render` exits 3 and returns a note: give an
unrendered storyboard or key-frame panels and say that nothing was rendered.

## Rendering and what is kept

`python scripts/animate.py render spec.json --root <vault>` lints, renders, takes a poster frame and a six-frame strip, and writes into `Visuals/<id>/`: the video,
`.poster.png`, `.keyframes.png`, the scene (`.scene.py`), the spec, `.render.json` (backend, version, commands, timings, video hash, layout report) and a
`*.visual.json` at **`rendered`** with `kind: animation`. It never overwrites; the same spec and scene return the existing record. Sessions embed the poster and
strip (they take static images only); the video opens from the vault.

**Layout check.** ManimGX `inspect` checks 2D scenes for clipping, overlapping text, lines over text and small labels. Problems stop the render (exit 4) unless
`--allow-layout-problems` records them. **3D scenes are not layout-checked, and Manim Community has no equivalent:** inspect the key frames yourself.

## Measured here (2026-10-16)

Windows 11, RTX 4050 Laptop 6 GB, idle machine, 1280x720 at 30 fps, ManimGX 0.1.1 (Python 3.14) against Manim Community 0.22.0 (Python 3.11, caching disabled,
TeX cache warm). The same three scene files ran on both without edits. Seconds per render, runs in order:

| Scene | ManimGX | Manim Community | Ratio |
|---|---|---|---|
| 2D derivation (5 equation steps) | 3.6, 3.6, 3.5 | 9.1, 8.7 (first run, TeX compiling: 17.4) | about 2.5x |
| 3D surface, orbiting camera | 3.8, 3.8, 3.7 | 79.6, 81.3 | about 21x |
| LaTeX-heavy equations (matrix, Maxwell, integral, sum) | 3.4, 3.2, 3.2 | 8.4, 7.9 (first run: 13.6) | about 2.5x |

This does not test the vendor's 90.6x claim (that was an Apple M4 Pro with the vendor's scenes). Not tested: 1080p60, longer scenes, whether ManimGX used the GPU,
and output equivalence beyond viewing the frames. Only the ManimGX frames were inspected in full (the derivation's five steps are correct; the surface and equations look right apart from the points below); the Manim Community output was timed, not compared frame by frame, and no pixel comparison was made.

**What went wrong, kept on the record.** (1) A first test appeared to show ManimGX flattening `pmatrix` and `aligned`; the cause was my own shell collapsing `\\` to
`\` in the scene file, and Manim Community drew the same broken source the same way. With the correct source ManimGX drew matrices and aligned lines properly. Check the
generated source before blaming a backend. (2) The 3D surface is cropped at the top of the frame at one point of the camera orbit, and no tool reported it. (3) The LaTeX
overflow in the first equations scene was caught by `inspect`, which is what it is for. (4) Importing `mitex` from `Typst(...)` as the docs suggest failed
(`unknown variable: mitex`); native `MathTypst("mat(a, b; c, d)")` works. Not pursued.

## Slides (predict-first pauses)

ManimGX treats a scene's sections as slides (`manimgx present`, interactive). Manim Community uses `manim-slides` (MIT): a `Slide` subclass with `self.next_slide()`;
`render` then runs `manim-slides convert --to html --one-file --offline`, which wrote one self-contained HTML file (about 870 KB) with no external src or href, checked by
reading the file. **`manim-slides` 5.7.0 fails under Manim Community 0.22.0** (`AttributeError: write_to_movie`) and works under 0.19.0 here: keep a separate environment pinned to
`manim==0.19.0` for slides. `animate.py present spec.json` prints the presenting command and does not run it. The interactive presenters were not driven in this session.

## Licensing

ManimGX's package metadata lists GPL-3.0-or-later among its licences (the native wheels bundle GPL components; the project's own code is MIT). That matters only if Research OS
is ever distributed with it. `manim-slides` is MIT. Not checked: Manim Community's dependency licences.

## Not done

Narration and audio (S8: `self.say()`, `manim-voiceover`), the physics, chemistry and ML plugins, Motion Canvas and Remotion, browser (Pyodide/WebGPU) rendering, and playing the video inside a session.
