# Codex adapter

Codex discovers personal skills in:

```text
~/.agents/skills/<skill>/SKILL.md
```

and project skills in:

```text
.agents/skills/<skill>/SKILL.md
```

Custom agents use TOML files in:

```text
~/.codex/agents/
.codex/agents/
```

`scripts/install.py` converts canonical `agents/*.md` into Codex TOML agent definitions.

Recommended project `AGENTS.md` addition:

```markdown
## Scientific Research OS

Use the installed research skills for recurring learning/research workflows.
Read the project's RESEARCH_PROTOCOL.md when present.
Use specialist subagents only for isolated or independent work.
Do not promote AI-authored text into accepted research conclusions without human review.
For live tutoring, log substantive teaching turns to the active Obsidian session note when configured.
```
