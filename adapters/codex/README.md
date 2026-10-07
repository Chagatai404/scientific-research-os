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

The research graph skill bundles include the read-only literature_check.py and
its canonical manifest protocol. They use the same scientific contracts as Claude;
the helper does not authenticate, launch agents or execute experiments.

Recommended project `AGENTS.md` addition:

```markdown
## Scientific Research OS

Use the installed research skills for recurring learning/research workflows.
Follow the installed skill's canonical references/RESEARCH_PROTOCOL.md and read project-specific additions when present.
Require explicit approval of the presented plan before implementation or experiments.
Use fast verdict/hint feedback during probes and synthesize at block end.
Use specialist subagents only for isolated or independent work.
Do not promote AI-authored text into accepted research conclusions without human review.
For live tutoring, log substantive teaching turns to the active Obsidian session note when configured.
```
