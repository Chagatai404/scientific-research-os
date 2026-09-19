# Scientific Research OS

A model-independent research and learning workflow for human-led scientific work with AI assistance.

The system separates two loops:

- **Learning:** probe → dependency map → teach → retrieve → promote.
- **Research:** question → evidence → hypothesis → experiment → audit → decision.

The human researcher is always the final authority. AI agents may search, explain, implement, critique, and propose changes, but they do not silently promote claims into permanent knowledge or accepted research conclusions.

## Core design

```text
Obsidian vault          Git research repo
(understanding)         (evidence)
      │                       │
      ├─ concepts             ├─ src/
      ├─ derivations          ├─ tests/
      ├─ quizbook             ├─ notebooks/
      ├─ literature notes     ├─ configs/
      └─ learning maps        └─ results/
              \               /
               \             /
                human researcher
                      │
          ┌───────────┴───────────┐
          │                       │
       Claude                   Codex
     explanation              implementation
     literature               experiments
     derivation               reproducibility
```

## Repository layout

```text
skills/                 Canonical model-independent skills
agents/                 Canonical subagent role definitions
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

## Initial specialist agents

- literature-scout
- source-verifier
- physics-reviewer
- statistics-reviewer
- reproducibility-auditor
- adversarial-reviewer
- visualizer

Use subagents when work can be isolated or parallelized. Do not spawn them for trivial tasks.

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
- Claude subagents to `~/.claude/agents/`
- Codex custom agents to `~/.codex/agents/`

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

The skills describe capabilities rather than hard-coding a provider.

For example, `literature-scout` requires:

- scholarly/web search,
- source retrieval,
- citation metadata,
- optional citation-context search.

Claude, Codex, ChatGPT, MCP servers, or connectors may satisfy those capabilities differently.

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
5. Claude/Codex portability.

Future extensions should be added only after a recurring workflow proves it is needed.
