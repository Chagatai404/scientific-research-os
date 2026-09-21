# Scientific Research OS

A model-independent research and learning workflow for human-led scientific work with AI assistance.

The system separates two loops:

- **Learning:** probe → dependency map → teach → retrieve → promote.
- **Research:** question → learn → independent discovery → separate verification → reconcile → synthesize → specialist validation → adversarial review → triage → plan → explicit human approval → build → experiment → validate/attack results → decision → learn again → persist.

The human researcher is always the final authority. AI agents may search, explain, implement, critique, reproduce, verify, and propose changes, but they do not silently promote claims into permanent knowledge or accepted research conclusions.

## Core design

```text
Obsidian vault                 Git research repo
(understanding)                (evidence)
      │                              │
      ├─ concepts                    ├─ src/
      ├─ derivations                 ├─ tests/
      ├─ quizbook                    ├─ notebooks/
      ├─ literature notes            ├─ configs/
      └─ learning maps               └─ results/
              \                      /
               \                    /
                human researcher
                       │
              assigns the task/role
                       │
        ┌──────────────┼──────────────┐
        │              │              │
      Claude         Codex          other AI
        │              │              │
        └─────── interchangeable tools ┘
                       │
          tutoring / literature / coding
          experiments / review / audit
          verification / reproducibility
```

The user decides which tool performs which task. A project may choose conventions—for example, using one tool more often for tutoring and another for implementation—but those conventions belong to the project or user workflow, not to Scientific Research OS itself.

For substantial work, prefer **one coordinating primary agent at a time**, with separate literature discovery and source-verification agents and relevant independent reviewers. Follow the canonical [research protocol](references/RESEARCH_PROTOCOL.md); the summaries here do not replace its gates.

Cross-validation means independent reconstruction or verification, not asking a second agent whether it agrees with the first.

## Repository layout

```text
skills/                 Canonical model-independent skills
agents/                 Canonical specialist/subagent role definitions
references/             Shared scientific policies
assets/obsidian/        Obsidian templates
scripts/                Portable local tooling
extensions/             Capability contracts and optional integrations
adapters/                Notes for Claude Code and Codex
examples/                Example project integration
tests/                   Lightweight self-checks
```

## Initial skills

- `tutor` — source-grounded live tutoring with prerequisite probing and retrieval checks.
- `study-source` — deeply study a paper, book chapter, website, lecture, or video.
- `derive` — reconstruct mathematics/physics from assumptions and sanity checks.
- `form-hypothesis` — turn ideas into falsifiable scientific hypotheses.
- `design-experiment` — design reproducible experiments before running them.
- `stats-audit` — audit statistical validity and leakage.
- `physics-audit` — audit physical assumptions, units, geometry, and limiting behavior.
- `research-review` — adversarial review of claims and evidence.
- `research-session` — orchestrate a complete human-led research session.

Skills describe workflows and capabilities. They are not tied to a particular model or provider.

## Initial specialist agents

- literature-scout
- source-verifier
- physics-reviewer
- statistics-reviewer
- reproducibility-auditor
- adversarial-reviewer
- visualizer

These are **task roles**, not provider identities. Any compatible AI system may perform them if it has the required capabilities.

Use specialist agents when work benefits from isolated context, independent verification, or parallelizable evidence gathering. Do not spawn them for trivial tasks.

## Research independence and bias control

For hypothesis-sensitive, model-selection, or implementation-defining questions, separate:

```text
neutral research question
        ↓
independent literature discovery
        ↓
independent source verification
        ↓
reconciliation → synthesis → relevant specialist validation
        ↓
adversarial review → blocker/relevance triage
        ↓
plan → explicit human approval → build/experiment
        ↓
result validation/attack → human decision → learning → persist
```

The initial literature search should not be shaped by the project's preferred implementation, equations, existing citations, or desired conclusion unless those details are genuinely necessary to define the system or regime.

A disagreement between external evidence and the current codebase is a research finding, not something to smooth over.

When practical, an independent reviewer should receive the claim, source, artifact, experiment, or acceptance criteria without being given the authoring agent's full reasoning first.

## Quick start

### 1. Configure your vault

Copy:

```text
research-os.example.toml -> research-os.toml
```

Edit the vault path.

### 2. Validate the repo

```bash
python scripts/validate.py
python -m unittest discover -s tests -v
```

### 3. Install skills and agents globally

Dry run first:

```bash
python scripts/install.py --target all --dry-run
```

Then:

```bash
python scripts/install.py --target all
```

This installs:

- skills to `~/.claude/skills/` and `~/.agents/skills/`
- Claude-compatible subagents to `~/.claude/agents/`
- Codex custom agents to `~/.codex/agents/`

Each installed skill receives copies of the canonical `references/` documents. In the source tree, resolve skill `references/` paths against the repository root. Installed standalone agents receive the shared agent policy, triage, and approval boundary in their generated instructions; edit canonical sources and reinstall, rather than editing generated copies.

The installed definitions are the same scientific roles expressed through provider-specific adapter formats. Installing them does **not** assign Claude or Codex permanent responsibilities.

### 4. Install Obsidian templates

```bash
python scripts/install.py --obsidian
```

The destination is read from `research-os.toml`.

### 5. Start a live tutor session

```bash
python scripts/vault.py new \
  --template 00_Tutor_Session.md \
  --title "Generalized Fractal Dimensions" \
  --dest "00 Tutor Sessions"
```

Append a logged teaching turn:

```bash
python scripts/vault.py append \
  --note "00 Tutor Sessions/2026-09-20 Generalized Fractal Dimensions.md" \
  --speaker "Tutor" \
  --text "Today we will first establish the scaling-law foundation."
```

Open the note:

```bash
python scripts/vault.py open \
  --note "00 Tutor Sessions/2026-09-20 Generalized Fractal Dimensions.md"
```

## Tool independence

Scientific Research OS is model- and provider-independent.

The framework defines:

- scientific workflows,
- evidence standards,
- specialist task roles,
- review boundaries,
- human authority points.

It does **not** prescribe that a particular provider must perform a particular type of work.

For example, `literature-scout` requires capabilities such as:

- scholarly/web search,
- source retrieval,
- citation metadata,
- optional citation-context search.

Claude, Codex, ChatGPT, MCP servers, connectors, or future tools may satisfy those capabilities differently.

Likewise, `tutor`, `physics-reviewer`, `reproducibility-auditor`, and other roles can be assigned to whichever tool the user chooses.

A project may define its own preferred tool conventions in project-local instructions such as `CLAUDE.md`, `AGENTS.md`, or equivalent files.

## Suggested coordination pattern

A simple default for substantial work is:

```text
human defines question
        ↓
primary agent coordinates the canonical research cycle
        ↓
human inspects result
        ↓
independent result reviewers verify/reproduce as warranted
        ↓
human accepts, rejects, or revises
```

Use simultaneous agents only when true parallelism adds value and their contexts can remain independent.

Git is the coordination layer for reproducible artifacts. Obsidian is the learning/understanding layer. The human researcher is the convergence point.

## Security

- Do not store API keys, tokens, passwords, `.env` contents, or private credentials in this repo.
- Skills and agents must not read secrets unless the user explicitly requests a task that requires them.
- Treat skill repositories as executable instructions: review external skills before installing them.
- Prefer read-only subagents for literature and review work.
- Never let an AI agent silently rewrite accepted research conclusions.

## Status

v0.1 focuses on:

1. source-grounded learning,
2. scientific reasoning,
3. reproducible research,
4. Obsidian live logging,
5. provider-independent AI collaboration,
6. independent literature discovery and review.

Future extensions should be added only after a recurring workflow proves it is needed.
