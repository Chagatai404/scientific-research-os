# Handouts

A handout is a document you study from, written by an agent from what the record holds and delivered as a note in your
Obsidian vault and, when the computer can make one, a PDF. It is teaching or reporting material: it is never evidence that
you learned anything, and it never carries an assessment item's answer key.

| Kind | For | Sections | Needs |
|---|---|---|---|
| `lecture` | a lecture unit of a course | L0 Gist, L1 Core in 60 seconds, L2 Lecture, L3 Derivation and sources | 3 `:::question` recall prompts |
| `recitation` | a problem session | What it practises, Exercises, Common mistakes | 5 `:::exercise` with full solutions |
| `chapter` | a course part or subject, textbook style | Overview, Definitions and results, Worked examples, Exercises, Notation | a definition, an example, 3 exercises |
| `literature` | a research question | The question, What was searched, What the sources say, Synthesis, Gaps and null results, What to read next | sources with locators |
| `findings` | an experiment or claims | Plan and approval, Results, Claims and their audits, Interpretation, Limitations, Decision memo | every claim with its audit chain |

## How one is made

1. `handout_create` composes the **context** from the record (capabilities and their prerequisites, prepared narration, the
   questions that test them without their answers, the sources, claims and audit verdicts) and opens one `handout` task.
2. The agent that takes the task reads the context (`handout_read`) and writes each section with `handout_write`:
   Markdown with LaTeX math (`$x$`, `$$x$$`), lists, pipe tables, an image line (`![caption]` with the path `figures/name.png` in round brackets) and boxes
   (`:::definition Name`, `rule`, `keyidea`, `mistake`, `remark`, `example`, `exercise`, `question`; a `=== solution` or
   `=== answer` line splits a box from its solution). Sources are added with their keys and cited as `[@key]`.
3. `handout_check` runs the gate and opens a task for what is missing. `handout_build` writes the note and queues the PDF.

## The gate

| Row | Fails when |
|---|---|
| `sources` | no sources; a `[@key]` with no source; a factual section with neither a locator nor `derivation` |
| `no keys` | the text contains an item's explanation, rubric criterion, option feedback or answer (checked against the items that test the handout's capabilities and claims) |
| `math` | an unbalanced delimiter or brace, a command that could read files or run a program, or an expression KaTeX rejects (when Node and KaTeX are present) |
| `structure` | a section is missing or too short, a box kind is under its minimum, an exercise or recall prompt has no solution, an unfinished marker (`TODO`, `TBD`) |
| `figures` | a figure is missing or is not a file in `figures/` |
| `pdf` | (a warning) no PDF of this version yet |
| `review` | (a warning) you have not read it yet |

A failing row opens a `handout` task with the row and its problems, once. To add a row, append a `Row` to `ros.handouts.ROWS`.

## Where it goes

- The **note** (`Research OS/<Courses|Projects>/<Name>/Handouts/<Title>.md`) is written as soon as there is text. Its
  properties carry `handout_kind`, `status` and `pdf`; its body uses Obsidian callouts, with solutions and answers
  collapsed. It is marked `ros_status: draft-unreviewed` and says which agent wrote it, until you read it and mark it
  reviewed (`vault_resolve --action reviewed`, or `ros_status: reviewed` in its properties).
- The **PDF** is built from the same source: `main.tex` on the restored study-handout style (`roshandout.sty`), or
  `index.html` printed by a headless browser. It is placed in `Research OS/Attachments/<Name>/<Title>.pdf` and embedded
  in the note. A PDF you annotated is never overwritten: the next version is saved as `<Title> v2.pdf`.
- A version (the hash of the source) is built once; an edit is a new version.

## The toolchain ladder

`python -m ros.lib.pdf detect` says what this computer has. A build tries, in order: `xelatex` (MiKTeX or TeX Live; set
`ROS_MIKTEX_BIN` if it is not on the path), then a headless Chromium-family browser (Chrome, Edge, Chromium, or
`ROS_BROWSER`) with the vendored KaTeX. With neither, the job reports `PDF needs a toolchain`, the doctor shows it once,
and the note is still delivered. Nothing is installed for you. Set `pdf_engine` (`ros` settings) to `latex` or
`chromium` to fix the choice.

LaTeX is compiled with shell escape off and the package installer off, in a scratch folder, with a timeout; the body is
generated from the Markdown with text escaped, and math (which passes through) is linted for `\input`, `\write`,
`\catcode`, `\def` and the like before any compiler sees it.
