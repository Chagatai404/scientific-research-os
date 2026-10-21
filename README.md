# Scientific Research OS

Version **1.0.0**. One record per course or project, lessons prepared before you sit down, and research that is
audited by fresh reviewers and defended by you. It works with any AI agent: Claude, Codex, Gemini or a local
model.

The design and its reasons are in [the v1.0 architecture](docs/plans/v1.0-overhaul-architecture.md).

## What it does

- **Learn.** A lesson probes where you are, teaches just above that edge with prepared narration, visuals and
  animations, practises, and ends with recall. You never pick modes, levels or tiers; the policy does, and logs why.
  Reviews are scheduled with FSRS across all your lessons.
- **Prepare.** Agents build each lesson ahead of time: a dependency map, narration with sources, voice, visuals
  they have looked at, animations for ideas that move, optional verified video clips, and questions at several
  levels. A lesson starts only when its bundle passes the readiness gate.
- **Research.** You frame the question, approve the plan, defend the result and decide. Between those points agents
  scout neutrally, verify sources, build and run, and audit each claim in a fresh context with six-state verdicts.
  A claim you will present opens defence items, and you own it once you can answer them from memory.

## Start

Python 3.11 or newer, standard library only. From this folder:

```bash
pip install -e .                       # or use: python -m ros ...
ros init stat303                       # a record in ~/ResearchOS/projects/stat303
ros -p stat303 migrate ~/Vault         # bring in your old notes, sessions and research records
ros -p stat303 serve --open            # the portal, in a browser or Obsidian's Web Viewer
ros install --client claude            # or codex, gemini, agents: skills, agents and the MCP server
```

Then ask your agent to teach you something, or open **Today** in the portal.

## How the pieces fit

| Piece | Where |
|---|---|
| The record (append-only events, immutable questions, a typed graph, a rebuildable index) | `ros/store.py`, [DATA_MODEL](references/DATA_MODEL.md) |
| Queries: readiness, frontier, reviews, claim support, code links | `ros/graph.py` |
| The learning engine: FSRS, probing, the adaptation policy, the tutor's writes | `ros/learn/` |
| Prepared bundles and the readiness gate | `ros/prepare.py`, [PREPARATION](references/PREPARATION.md) |
| Claims, audits, approvals, decisions, ownership | `ros/research.py`, [RESEARCH](references/RESEARCH.md) |
| One tool table, served as the CLI, MCP and the portal's API | `ros/api.py`, `ros/cli.py`, `ros/mcp.py`, `ros/serve.py` |
| The portal | `ros/portal/`, [PORTAL](references/PORTAL.md) |
| Importers, exports, installation | `ros/importers.py`, `ros/export.py`, `ros/install.py` |
| Carried-over engines: speech, voice, Manim, paper library, scouting, evidence, manifests, code walkthrough | `ros/lib/` |
| Skills: learn, prepare, research, audit, defend, notes-to-latex | `skills/` |
| Agent roles: scout, verifier, auditor, adversary, visual-maker, video-scout | `agents/` |
| Protocols: teaching, preparation, research, evidence, data model, portal, voice, safety | `references/` |

## Any agent

Every operation is declared once in `ros/api.py` and exposed three ways: `ros <tool> --json` for agents with a
shell, the MCP server (`ros mcp`) for agents with MCP, and the portal's local HTTP API. `ros tools --json` lists
them with their JSON schemas. Skills and agent roles are plain Markdown; `ros install` writes them where each client
looks. Work only a model can do (grading a written answer, making a visual, auditing a claim) waits as a task
that any attached agent can claim; with none attached, prepared lessons still play and written answers wait.

## You decide

Approving a plan, accepting a claim and waiving ownership are your acts. Agents cannot do them over MCP, the CLI asks
you to confirm at a terminal, and the portal's research view is where you make them. The rules agents follow are in
[SAFETY](references/SAFETY.md).

## Where things live

Records, questions, audio and video live in `~/ResearchOS/projects/<name>/` (set `ROS_HOME` to move it) or in a
research repository's `.ros/`. Only curated notes go into your vault, with `ros export --kind obsidian`; a note
you have edited is never overwritten. `ros export --kind static` writes a read-only single-file snapshot.

## Tests

```bash
python -m unittest discover -s tests -p "test_*.py"     # about 10 seconds
node tests/ros-portal-browser.cjs                        # a whole lesson in Chromium, layout at 320-1920 px
```

The history of earlier versions is in `docs/history/` and the changelog.
