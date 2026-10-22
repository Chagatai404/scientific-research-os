# Architecture

How Research OS is built, the rules that keep it robust and fast, and how to add to it. `tests/test_architecture.py`
checks the rules marked **(checked)**; a change that breaks one fails the suite. If a rule must change, change this
document and that test in the same commit.

## The shape

```
 interfaces    cli · mcp · serve (portal) · runner   how people and agents reach the system; the runner is the
     │                                       background that ticks automation and runs jobs while one of them is open
     │  only through api.call / the tool table
 tools         api · registry · tools/{record, learning, preparation, research, vault, handouts, automation,
     │                               director, atlas}
     │  one declaration per operation, shared by every interface
 domain        graph · learn/{fsrs, evidence, schedule, probe, policy, tutor} · tasks · context
               prepare · research · importers · export
               vault · handouts · automation · director · atlas
     │
 core          store (the record) · home (where records live)
 engines       lib/ (speech, voice, Manim, papers, scouting, evidence atoms, manifests, walkthrough, old readers)
```

| Layer | May import | Never imports | Why |
|---|---|---|---|
| core: `store`, `home` | the standard library | anything in `ros` **(checked)** | The record must outlive every other part. |
| `learn.fsrs` | the standard library | anything in `ros` **(checked)** | Pure formulas, verified against golden values. |
| domain | core, other domain modules, `lib` (only `importers` and `prepare`) | `api`, `registry`, `tools`, interfaces **(checked)** | Domain logic is usable from tests, scripts and every interface alike. |
| `registry` | `store` **(checked)** | everything else | Declaring a tool needs nothing but the record type. |
| `tools/*` | `registry`, core, domain **(checked)** | interfaces | A tool is a thin, typed wrapper over domain functions. |
| `api` | `registry`, `tools` | — | The public entry point: `api.call(name, rec, **args)`. |
| interfaces | `api`, `store`, `home`, each other | domain modules, `tools` **(checked)** | Every interface sees the same operations with the same checks. |
| `lib` | itself | the rest of `ros` | Proven engines kept as they are; started only when needed. |

There are no import cycles **(checked)**.

## Invariants

1. **The record is the truth; everything else is derived.** `events.jsonl`, `items/`, `graph/*.jsonl` are plain files
   (`references/DATA_MODEL.md`). `index.sqlite`, lesson logs, exports and caches can always be rebuilt. Never store a
   derived value as if it were a fact.
2. **Append only.** Events and graph lines are appended, never edited. A correction is a new event; a removal is a
   tombstone. Items are immutable and named by their content hash; an edit is a new item that `supersedes` the old.
3. **One writer per record at a time.** Writes take a short OS file lock; inside a process every tool call holds
   `registry.LOCK`. There are no leases or lock files to clean up.
4. **Deterministic ids for imported facts** (`store.event_id(source, key)`), so importing twice adds nothing.
5. **People decide.** Approving, deciding and waiving are `human=True` tools: never offered over MCP, confirmed at a
   terminal in the CLI, made in the portal.
6. **Learners see no keys.** Anything shown before an answer goes through `registry.present`.
7. **Engines are optional.** Missing TTS, Whisper or Manim makes a gate row fail or a task wait; it never breaks a
   lesson or a test.
8. **Standard library only** in `ros` itself.

## How a read stays fast

The index is incremental and every expensive view is too. Use these instead of scanning:

| Need | Use | Cost |
|---|---|---|
| Events of a lesson, a subject or some types | `rec.events(lesson=, subject=, type=, types=, since=, limit=)` | indexed query |
| One event, item or node | `rec.event(id)`, `rec.item(h)`, `rec.node(id)` | one lookup |
| Every item, or each item's newest version | `rec.items_by_id()`, `rec.current_items()` | once per index change |
| A whole-record view that changes rarely | `rec.derived(name, build)` | once per index change |
| A view that grows with events | `rec.fold(name, types, init, step)` | only the new events |
| Learning evidence (rows, FSRS cards, assessments) | `learn.evidence.of(rec)` | only what new events touch |
| The `requires` graph (prerequisites, dependents, closure) | `graph.structure(rec)`, cached on `rec.stamp("edges")` | once per edge change; answers never rebuild it |
| Capabilities for part of the graph | `graph.Learning(rec, as_of, within=ids)` | the closure of `ids` only |
| Gaps and a roadmap | `roadmap.gaps`, `roadmap.roadmap` | linear in the closure of the targets; a repeat is a lookup |

`rec.stamp(*logs)` is the cache key for what depends on `events`, `nodes` or `edges` alone; `rec.derived` is thrown away
by every write, an answer included, so it is wrong for graph structure. A project record reads the user-wide record
through `context.user_record(cfg)`, kept open so its evidence is folded once.

Every tool call runs inside `rec.reading()`: the files are checked for growth once, then every read in the call uses
the index as it is. The record's own writes update the index immediately.

Never loop over `rec.events()` without a filter, call `rec.item()` inside a loop over all events, or recompute a
whole-history view on every write. A benchmark on 93,000 events is the yardstick: a policy decision stays near 20 ms,
an append near 2 ms.

## Adding things

Each recipe lists every place a change touches. If you find yourself editing a long function or adding an `if` chain,
there is a registry for it below; use it.

### A tool (an operation any agent or the portal can use)

1. Write the domain function where it belongs (`graph`, `learn/*`, `prepare`, `research`, …). It takes the record and
   plain values and returns JSON-able data. Raise `ValueError` for bad input and `KeyError` for something missing.
2. Declare it in the matching `ros/tools/*.py` module:
   ```python
   @tool("name", "One sentence a person understands.", writes=True,
         arg=P("string", "what it is", True))
   def name(rec, arg):
       return domain.function(rec, arg)
   ```
   The parameter names must equal the function's **(checked)**. `writes=True` if it appends anything; `human=True` if
   only a person may do it.
3. That is all: the CLI subcommand, the MCP tool and `POST /api/name` exist now. Add a test that calls it through
   `api.call`.

A new domain area gets a new `ros/tools/<area>.py` whose docstring starts "Tools for" **(checked)**, imported in
`ros/api.py`.

### An event type

1. Pick a name: a noun, or `noun.verb` for a family (`lesson.start`); `rec.events(type="lesson")` matches the family.
2. Put `lesson` in `data` when the event belongs to a lesson, so the lesson index finds it.
3. Write it only through a domain function (never from an interface), and document it in the event table of
   `references/DATA_MODEL.md`.
4. If a derived view depends on it, add the type to that view's fold (`learn/evidence.TYPES` for learning evidence).

### A node or edge type

Add it to `NODE_TYPES` or `EDGE_TYPES` in `ros/store.py` and to `references/DATA_MODEL.md`. Ids are `<type>:<key>`.

### A teaching behaviour

Write a rule `def rule(ctx: Context) -> dict | None` in `ros/learn/policy.py` and insert it into `RULES` where it
belongs. Use `ctx.view` (a `probe.LessonView`: the lesson, read once) and `ctx.learning` (capability states), never
fresh scans. Return
`{"action", "reason", ...}`; the reason is logged and must say why in a sentence. Add a test that drives a lesson to
the new decision.

### A readiness check for prepared lessons

Write `def _check(gate: Gate, node: dict | None) -> (problems, warnings)` in `ros/prepare.py` and append
`Row(name, per_node, task_kind, _check)` to `ROWS`. A failing row automatically opens a task of that kind.

### An importer for an old format

Write `def importer(rec, path, **options) -> dict` in `ros/importers.py` and add it to `IMPORTERS`; the `import`
tool's choices come from that registry **(checked)**. Use deterministic event ids so re-importing adds nothing.

### A task kind (work for an agent)

Add it to `tasks.KINDS`, open it with `tasks.open_task(..., key=...)` (the key makes it idempotent), and describe in
the relevant skill which agent takes it and which tool finishes it.

### An automation (something the system does so that nobody has to ask)

Write `def _name(look: Look) -> dict | None` in `ros/automation.py` and add a `Trigger(name, modes, run)` to `TRIGGERS` with the modes it
runs in (`call` after an agent's write, `tick` on the runner's timer, `scan` for files, `daily`). `look` carries the
record and what changed since this trigger's cursor (`Record.since`), so a quiet record costs one comparison. It must be
idempotent: key every task, count only what it newly opens (`tasks.known`), write nothing when nothing changed; the
end-to-end tests tick twice and compare event counts. Work that takes minutes is a `job` task with an allowlisted argv,
run by the `Runner` outside `registry.LOCK`; what follows a finished job goes in `THEN`.

### A director playbook (what an agent does when told something in words)

Write `def _name(user, text, target, title, deadline, pace, materials) -> dict` in `ros/director.py` and add it to
`PLAYBOOKS` under a word of `director.KINDS`. It creates the hubs and records the person's request needs, states the goal,
opens the first tasks and returns what it did; `parse_intent` chooses the playbook from the person's words. Agents then take work with `work`, not by being told a plan.

### A handout kind or gate row

A kind is a `Kind(...)` entry in `handouts.KINDS` (its sections with word budgets, minimum counts, the writer's brief). A
gate row is `Row(name, check(doc) -> (problems, warnings))` in `handouts.ROWS`; a failing row opens a `handout` task. Rendering stays in
`ros/lib/pdf.py` (Markdown subset to Obsidian callouts, LaTeX and HTML); add syntax there once, for all three.

### A vault note type

Add a stub function to `vault.NODE_STUBS` (or a node type to `vault.GENERIC`): frontmatter the system owns (`ros_*` keys
hashed with `ros_hash`), a generated region between the markers, and the person's "My notes" below it, which is never
touched. Sync is incremental by node version; scanning is one stat per file. Nothing is written outside the vault's
`Research OS/` folder and only unedited generated files are ever deleted.

### An audit step or assurance level

Add the step to `research.STEPS` and to the levels in `research.ASSURANCE` that require it; describe it in
`references/RESEARCH.md` and the `audit` skill.

### A skill, agent role, lens or protocol

Plain Markdown with `name` and `description` frontmatter (`skills/<name>/SKILL.md`, `agents/<name>.md`). Prefer a lens
(`skills/<skill>/lenses/<topic>.md`) over a new skill. Name only tools and files that exist; `tests/test_ros_m6.py`
checks invocations, links and file names. `ros install` delivers them to every client.

### A portal view

Add a function to `views` in `ros/portal/app.js` that reads tools through `api(name, args)` and writes through
`api(name, args, true)`; add its link to `index.html`. Keep to the layout and control rules in
`references/PORTAL.md`; `tests/ros-portal-browser.cjs` checks layout at four widths.

### An engine (TTS, renderer, external tool)

Put it in `ros/lib/` with its own CLI (`python -m ros.lib.<name>`), import it lazily from the domain module that uses
it, and make its absence a reported problem, not an exception that escapes.

## Tests

- Unit tests: `python -m unittest discover -s tests -p "test_*.py"` (about 10 s). Name new files `test_ros_<area>.py`.
- Browser: `node tests/ros-portal-browser.cjs`.
- Whole workflows by prompting only: `tests/test_ros_e2e_director.py` drives an agent through `mcp.Server.handle` and a
  person through the portal's HTTP API, and fails if an agent had to call a tool the system should have called itself.
- Speed: `tests/test_ros_director_bench.py` (small by default; `ROS_BENCH=1` for the large cases).
- Every new tool, rule, gate row or importer comes with a test; behaviour shared with the old runtime keeps its parity
  test (`test_ros_graph.py`, `test_ros_importers.py`).
- The suite stays under five minutes; the portal under 60 KB of JS and 20 KB of CSS.
