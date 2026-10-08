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

The research graph skill bundles include the read-only literature_check.py and
its canonical manifest protocol. They use the same scientific contracts as Codex;
the helper does not authenticate, launch agents or execute experiments.
The same bundles include paper_access.py for sanitized single-document handoffs,
reviewed public fallback and manual inbox outcomes. Provider sessions stay external.
`tasks.py` provides the same durable DAG and manual fallback as Codex. Host adapters
may register nonblocking launch/status/cancel hooks; live background integration is
not installed. Canonical job IDs, approval/context bindings and writer reservations
survive restart. Do not pass full-history forks as independent verifier context.

The same graph skill bundles include `tutor_session.py` for nested lesson checkpoint
replay and explicit local persistence. Learner questions cost no diagnostic units;
tutor assessments share their budget across branches. Schema 3 keeps method/tool/
navigation evidence separate. Canonical ledgers remain authoritative and unchanged
by session replay. Ownership/defense runtime remains pending Slice 5.

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
