# Contributing

Research OS stays small on purpose: six skills, six agent roles, eight protocols, one record format, one tool table.

## Before adding something

- **A tool** goes in `ros/api.py` with typed parameters and one line of help. It then exists in the CLI, MCP and
  the portal at once. A person's act (approving, deciding, waiving) is declared `human=True`.
- **A skill or agent role** needs a workflow that has repeated, a trigger that can be described, a stable procedure,
  no overlap with an existing one, and explicit points where the researcher decides. Prefer a lens (a Markdown file
  a skill loads on demand) over a new skill.
- **A dependency**: the core is standard library only. Engines (TTS, Whisper, Manim) run in their own environments
  through `ros/lib/`; nothing imports them.

## Checks

```bash
python -m unittest discover -s tests -p "test_*.py"
node tests/ros-portal-browser.cjs
```

The suite must stay under five minutes. `tests/test_ros_m6.py` checks that skills, agents and protocols refer only to
files and tools that exist. Portal code stays under 60 KB of JS and 20 KB of CSS.

Release notes go in `CHANGELOG.md`; there are no per-slice gate records.
