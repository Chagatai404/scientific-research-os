# Claude Code adapter

Claude Code discovers personal skills in:

```text
~/.claude/skills/<skill>/SKILL.md
```

and project skills in:

```text
.claude/skills/<skill>/SKILL.md
```

Custom subagents live in:

```text
~/.claude/agents/
.claude/agents/
```

Use `scripts/install.py` to copy the canonical definitions.

Recommended project `CLAUDE.md` addition:

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
