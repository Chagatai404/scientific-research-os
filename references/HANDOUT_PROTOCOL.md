# Handout protocol (v0.9.7)

The handout is a reusable, self-contained study resource, available in its own
Handout stage before the diagnostic. It never overlaps the lecture surface.
The unreleased adaptive core supports native readable content independently of
the optional designed LaTeX PDF. Existing PDF-only plans remain compatible.
Prepare definitions, intuition, justified formal steps, examples, common mistakes,
exercises and a solution appendix, with precise sources and explicit assumptions.
Native content uses headings, short paragraphs and safe inline math; figures,
tables and advanced page design remain available through the existing PDF export.

A handout is teaching material, never learning evidence. What the learner can do without it is what the probe and the final check show.

## When

1. **At plan time** inspect available sources and recorded knowledge, and draft
   useful native content without waiting for diagnostics or speech workers.
   Source inventory and drafting can overlap safely; unavailable material must
   be disclosed, never fabricated. Prefer assigned course material where available.
2. Publish the native resource immediately. After diagnostics, increment its
   revision for focus recommendations or a gaps supplement; retain the complete
   underlying resource. Export a PDF independently if desired. Compiler failure
   must never make the native handout inaccessible.
3. The handout is not a script of the lecture. It is what the learner studies from during and after it; the lecture does not repeat it line by line.

## Native resource (unreleased)

```
python scripts/handout.py publish-readable --root <vault> --session <note> --content readable.json [--library DIR]
```

`handout.readable` is an additive plan-schema-1 field:

```json
{
  "revision": 1,
  "focus": ["Review the prerequisite only if needed; focus today on the derivation."],
  "sections": [{"title": "Objective", "paragraphs": ["A complete, source-grounded explanation."]}],
  "sources": [{"title": "Assigned text", "reference": "Reviewed source identity", "locator": "Exact section, page or equation"}]
}
```

Bounded at 120 KiB: 1–40 sections, 1–40 paragraphs per section (up to 2000
characters each), 1–40 precise source records, up to 12 focus recommendations.
Titles are one line; paragraphs use the existing scientific inline grammar.
Mark an appendix section `"solution": true` to require explicit reveal in the
reader. Sources and assumptions must be scientifically checked under SOURCE_POLICY;
schema validity is not verification of content or educational effectiveness.

The publisher manages the vault-relative `note` link. Its content-addressed,
revisioned Markdown resource lives in the existing declared library directory,
links back to the session and is linked from the generated Markdown bridge.
Publication holds the central session lock and a library lock; repeated identical
publication reuses its artifact, while learner-edited notes are preserved in place
and a fresh copy is versioned. A failed session projection leaves the complete
library resource recoverable; retry publication or use ordinary session recovery
if a projection journal exists. Never remove another writer's lock.

The page offers section selection and responsive pages, preserving inline math
and saved position on stage switches/reload. Revealing a solution records a
presentation checkpoint, not a grade. Actual assistance must still be attributed
when an assessed attempt uses that solution. Native publication never changes a
capability, retention choice, research decision or permanent concept note.

Legacy `handout.status` continues to describe PDF preparation (`planned`, `draft`,
`built`). A valid native resource satisfies core readiness independently of that
status; an existing PDF-only plan still uses its checked PDF. PDF status updates
retain native content or replanning published while compilation was running.

## How to build

The commands below build the optional PDF export; they do not gate native reading.

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
