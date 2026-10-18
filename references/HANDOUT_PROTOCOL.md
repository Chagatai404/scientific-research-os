# Handout protocol (v0.9.7)

The researcher's feedback was that text written on the page overlapped the live lecture and distracted from it. The page now carries only the board; everything a learner reads lives in one detailed, study-quality PDF, the **handout**, handed out after the initial probe and kept in the course or project library. It is modelled on good recitation notes: a title block, numbered sections, definition / rule / key-idea boxes, worked examples, a notation table, exercises with full solutions at the end, sources, and a wide margin for the learner's own notes.

A handout is teaching material, never learning evidence. What the learner can do without it is what the probe and the final check show.

## When

1. **At plan time** the plan's `handout` object names the title, the directory and the sections (`SESSION_PLAN.md`, status `planned`). Draft the body from the sources and the learner's recorded state, ideally in a subagent while the probe runs.
2. **Build a draft** (`--stage draft`) if the probe is still running. After the probe, add a short `gaps` section on what the probe found and build again with `--stage built`. The learner is handed the PDF at the Handout stage and reads it while the lecture's audio is prepared.
3. The handout is not a script of the lecture. It is what the learner studies from during and after it; the lecture does not repeat it line by line.

## How to build

```
python scripts/handout.py template                       # the environments, macros and packages a body may use
python scripts/handout.py check body.tex --plan plan.json  # lint without compiling
python scripts/handout.py build --root <vault> --session <session note> --body body.tex [--title T] [--library DIR] [--stage draft|built] [--figures DIR]
python scripts/handout.py locate --root <vault> --session <session note>
```

The body is the text between `\begin{document}` and `\end{document}`. The template (`assets/handout/template.tex`, `roshandout.sty`) owns the title block, header, fonts, margins and packages. `build` refuses a body that:

- uses a command that can read or write files, run a program, load code or change the template (`\input`, `\write`, `\usepackage`, `\catcode`, ...): the body is untrusted and is compiled with shell escape and the package installer off, in a scratch folder outside the vault;
- has unfilled slots, `TODO` markers, a missing section the plan declares, fewer than 300 words of prose, no sources, a citation without a `\bibitem`, a reference to a label that does not exist, an exercise with an empty solution, or a missing figure;
- compiles with errors, undefined references or citations, an overfull box beyond the limit, a missing glyph or a missing font.

Nothing is saved to the library unless the whole build passes. Problems are listed so you can fix the body and run it again; `--keep-build DIR` keeps the scratch `main.tex` and `main.log` for debugging.

## Where it goes

Default directories (an existing library convention wins; set `handout.directory` in the plan or pass `--library`):

- course: `<course folder>/Tutor Handouts/<date> <topic>/`
- project: `01 Projects/<Project>/Library/<topic>/`

The directory holds `<topic>.tex`, `<topic>.pdf`, `roshandout.sty`, `figures/`, a `handout.json` manifest and a vault note `<topic>.md` that links the PDF and the session. A rebuild by the same session replaces its own unchanged files; a file the learner edited, or one this tool did not write, is never overwritten: the new build is saved as `-v2`, `-v3`. The plan's `handout.status` moves forward only (`planned`, `draft`, `built`).

## What a good handout holds

- Numbered sections that build the idea from what the learner already knows (`TUTOR_PLANNING.md`), with every formula derived or cited, not asserted.
- `definition`, `rulebox`, `keyidea` and `commonmistake` boxes, used sparingly and only for what deserves one.
- Several worked examples with every step; a figure where one helps (verified under `VISUALIZATION_PROTOCOL.md` before it is included).
- A notation table, exercises that grow in difficulty, and a **full solution** to each (`\exercise{statement}{solution}` plus `\printsolutions`).
- Sources (`SOURCE_POLICY.md`): facts and formulas cite the course material or a textbook the agent has checked. A formula the agent cannot source is marked as unchecked in the text, not presented as fact.
- Turkish and other Latin-script text works (Latin Modern fonts).

## Environment

The build uses `xelatex` (MiKTeX or TeX Live; `ROS_MIKTEX_BIN` can point to its folder) and `latexmk` when perl is present. Packages: amsmath, amssymb, amsthm, mathtools, fontspec, unicode-math, geometry, xcolor, microtype, hyperref, fancyhdr, titlesec, booktabs, enumitem, tcolorbox (skins, breakable), longtable, array, graphicx, caption, tikz, pgfplots, etoolbox, and the Latin Modern fonts. If a package is missing, `build` says so; `--allow-package-install` lets MiKTeX download it (off by default).
