---
name: notes-to-latex
description: Convert visible handwritten technical or mathematical notes into faithful LaTeX, preserving meaning, apparent mistakes and meaningful ambiguity. Use for images or scanned notes, fragments or complete documents; offer clean or explicitly requested polished typesetting without silently correcting mathematics.
---

# Notes to LaTeX

Read `references/LATEX_TRANSCRIPTION_PROTOCOL.md`. In this repository shared
references live at `../../references/`; installation bundles them under
`references/` in each skill.

1. Inspect the available handwritten pages with the host's vision/document tools.
   Identify page order and readable scope; request missing input when necessary.
2. Respect the requested faithful, clean or polished mode. Default to
   faithful-clean transcription with original mathematical content intact.
3. Transcribe supported text/math structures and annotations, preserving apparent
   errors. Mark meaning-changing ambiguity with located `% UNCERTAIN` comments
   and an ambiguity report; use explicit placeholders when no reading is defensible.
4. Use minimal appropriate packages, returning a fragment or complete document as
   requested. Unclear figures get descriptive placeholders; do not invent geometry.
5. Compare every page with the output and check LaTeX structure. Disclose what was
   not readable or verified, including whether compilation was performed.
6. Return the LaTeX and concise ambiguities/omissions report. Keep transcription,
   formatting, interpretation and correction distinct. Never silently repair
   mathematics; report substantive corrections in explicitly requested polished work.

Do not build or require OCR, an AI API, or a LaTeX compiler. Use
`references/VISUALIZATION_PROTOCOL.md` separately if diagram recreation is requested.
Transcription alone does not invoke tutoring or the research cycle.
