# Obsidian Research + Learning Templates

These templates separate two activities:

1. **Learning loop:** probe → dependency map → learn → retrieve.
2. **Research loop:** question → evidence → hypothesis → experiment → decision.

The files are plain Markdown and are intentionally model-independent.

## Recommended vault layout

```text
Knowledge/
├── 00 Inbox/
├── 10 Concepts/
│   ├── Physics/
│   ├── Mathematics/
│   ├── Statistics/
│   ├── Machine Learning/
│   └── Quantum Computing/
├── 20 Learning Maps/
├── 30 Literature/
├── 40 Research/
│   └── AMS ECAL QML/
│       ├── Questions/
│       ├── Hypotheses/
│       ├── Experiments/
│       ├── Decisions/
│       └── Sessions/
├── 50 Quizbook/
├── 60 Derivations/
├── 70 MOCs/
└── 90 Templates/
```

## Install

Copy all `.md` files from this bundle into:

```text
Knowledge/90 Templates/
```

Then in Obsidian:

1. Open **Settings → Core plugins**.
2. Enable **Templates**.
3. Open **Settings → Templates**.
4. Set the template folder location to `90 Templates`.

The templates use only the core placeholders:

- `{{date}}`
- `{{time}}`
- `{{title}}`

No community plugin is required.

## First three templates to use

### For a live AI lesson

Use:

`00_Tutor_Session.md`

The AI should work directly inside/alongside this note. The note explicitly tells the tutor to use verified sources and separate facts from assumptions and speculation.

### When a concept finally clicks

Create a permanent note from:

`01_Concept.md`

Do not let the AI automatically promote its own explanation. Write or revise the permanent explanation yourself.

### When research begins

Create:

1. `07_Research_Question.md`
2. `08_Hypothesis.md`
3. `09_Experiment.md`

This turns an interesting idea into a falsifiable scientific workflow.

## Suggested source trust hierarchy

For scientific claims:

1. Primary peer-reviewed paper / official experiment publication.
2. Academic textbook or monograph.
3. High-quality review article.
4. Official scientific/institutional documentation.
5. University lecture/course material.
6. Reputable educational website.
7. YouTube/other video as a teaching aid.

A video can be excellent for intuition while still not being the evidentiary source for a research claim.

## Recommended next setup

After these templates are comfortable, add:

- Zotero + Better BibTeX for papers and citations.
- Obsidian Zotero Integration for literature notes.
- Spaced Repetition only for selected durable quiz cards.
- A shared `RESEARCH_PROTOCOL.md` in each research repo so Claude/Codex follow the same scientific rules.
