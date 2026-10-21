# Working on Research OS

Instructions for anyone, person or AI agent, changing this repository.

1. **Read `docs/ARCHITECTURE.md` first.** It defines the layers, the invariants and a recipe for every kind of
   addition (tool, event type, policy rule, gate row, importer, task kind, skill, portal view, engine). Follow the
   recipe instead of inventing a new path; if none fits, add the recipe to the document in the same change.
2. **Keep the layering.** Domain code never imports `api`, `registry`, `tools` or an interface; interfaces reach the
   domain only through `api.call`; `store` and `learn.fsrs` import nothing from `ros`. `tests/test_architecture.py`
   enforces this.
3. **Never scan the whole record per operation.** Use the indexed filters, `rec.derived`, `rec.fold` and
   `learn.evidence` (see "How a read stays fast").
4. **The record is append-only and the truth.** No edits to written lines, no stored derived values.
5. **Standard library only** in `ros/`. Engines live in `ros/lib/` and are optional.
6. **Test before you commit:** `python -m unittest discover -s tests -p "test_*.py"` and
   `node tests/ros-portal-browser.cjs` must pass. Add tests with every change.
7. **Docs move with code:** `references/` (protocols), `skills/`, `agents/`, `README.md` and `CHANGELOG.md` must
   describe what the code does; `tests/test_ros_m6.py` checks names, links and tool invocations.

Using Research OS (rather than changing it) is described in `README.md`; `ros install --client agents` adds a
managed block for that to a project's own `AGENTS.md`.
