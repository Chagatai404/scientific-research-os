# Handwritten notes to LaTeX

Preserve what the learner wrote. Do not silently replace it with what the model
thinks the mathematics should have been. This protocol governs transcription after
the host can see the notes; it is not an OCR engine or an automatic tutoring pass.

## Input and mode

Inspect the supplied pages/images using available host vision or document tools.
Keep page order, reading order and source locations. If pages are unavailable or
unreadable, ask for the missing page or clearer crop; do not invent its content.
Proceed with readable portions and identify any omissions.

- **faithful:** transcribe as written as closely as practical, including apparent
  mathematical mistakes. Preserve meaningful notation, annotations and ordering.
- **clean:** preserve mathematical meaning/content while improving spacing,
  alignment, equation formatting, headings, lists and LaTeX structure. No
  substantive mathematical correction without disclosure.
- **polished:** only when explicitly requested, repair obvious notation/formatting
  issues and improve presentation; report substantive corrections separately.
  If a correction depends on an uncertain interpretation, seek clarification or
  retain the original with a proposed alternative rather than silently choosing.

Default for "convert these notes to LaTeX" is **faithful-clean**: readable LaTeX
with the original content and mathematics intact, not editorial rewriting.
Distinguish transcription, formatting, interpretation and correction. Do not
silently turn transcription into tutoring or proofreading.

## Meaningful ambiguity

Use `% UNCERTAIN [page/line or equation]: ...` immediately before an uncertain
transcription, plus a concise ambiguity report with the same locator. Show likely
alternatives; a tentative reading is not a confident resolution. For example:

```latex
% UNCERTAIN [p1, eq2]: symbol may be \nu or v; tentative reading below.
\nu = 1
```

If no reading is defensible, use an explicit visible placeholder rather than a
guessed symbol: `\text{[illegible]}` in math (with amsmath), or `[illegible]` in
prose, with a locator/comment. Preserve readable surrounding content.
Mark ambiguities that could change meaning: u/v/nu, 1/l, minus/dash, exponents,
matrix entries, subscripts and unreadable words. Do not flood the output with
comments for trivial high-confidence readings. Never resolve handwriting solely
because one reading would make the mathematics correct.

## Structures and figures

Preserve plain text, headings, bullet and numbered lists, inline/display math,
multi-line derivations, aligned equations, cases, matrices, tables, definitions,
theorems, equation labels/numbers and simple handwritten annotations. Use suitable
LaTeX environments such as `align`, `cases`, `pmatrix` and `tabular` as needed.
Keep explicit source equation numbers (for example with `\tag{...}`) and do not
invent labels, steps, theorem hypotheses or missing derivation lines. Distinguish
margin annotations from the main text and mark uncertain insertion locations.

For a simple, clear mathematical diagram, TikZ may be appropriate. Do not infer
precise geometry from an unclear drawing. For complex or uncertain figures use:

```latex
% Figure placeholder [p2]: diagram description; unclear labels/geometry listed in report.
```

Include a concise description of visible content and missing details. If the user
explicitly requests recreation, the separate visualization workflow may be used;
that does not authorize inventing scientific geometry or changing the transcription.

## Output and verification

Provide a fragment when requested, without forcing a document wrapper. For a
complete compile-ready document include a minimal `\documentclass`, preamble and
document environment. Use common packages only as needed (`amsmath`, `amssymb`,
`mathtools`); specialized packages such as TikZ or theorem support require relevant
content. Escape prose characters and check braces, environments and commands.
Avoid enormous preambles and unsupported custom macros.

Compare the output against every supplied page: signs, indices, exponents, matrix
dimensions/entries, equation numbers, annotations, ordering and omissions. Check
syntax without claiming a compilation that was not performed. If an available
compiler is used, report its result; an OCR engine or LaTeX installation is never
required by Research OS or its test suite. Do not automatically install one.

Return the LaTeX and a compact report of meaningful ambiguities, figure placeholders,
omissions and any disclosed corrections. When none exist, say so briefly. Preserve
apparent mathematical errors in faithful/clean modes and optionally flag separately:
"Transcribed as written. Possible issue: line 4 appears to use ...; I did not modify
it." In polished mode identify original reading, changed form and reason for any
substantive correction. Uncertainty about a symbol and suspicion of a mathematical
error are different findings. Human review resolves them.
