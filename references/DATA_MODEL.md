# Data model

One record per course or project, in `$ROS_HOME/projects/<name>/` (default `~/ResearchOS`) or a research
repository's `.ros/`. Plain files are the truth; `index.sqlite` is a cache that can always be deleted.

| File | Contents |
|---|---|
| `events.jsonl` | One fact per line: `id`, `ts` (UTC), `actor`, `type`, `subject`, `data`, optional `source`. Append only. |
| `items/<sha256>.json` | An immutable item, named by the hash of its canonical content (fields `id` and `meta` excluded). |
| `graph/nodes.jsonl` | Node versions, last write wins by `id`; `{"deleted": true}` is a tombstone. Ids are `<type>:<key>`. |
| `graph/edges.jsonl` | Edge versions keyed by `(src, type, dst)`, same rules. |
| `bundles/<id>/` | A prepared lesson: `plan.json`, media, `manifest.json`. |
| `handouts/<id>/` | A handout: `source.json` (kind, sources, Markdown), figures, the built `.pdf`/`.html`. See `references/HANDOUTS.md`. |
| `cache/automation.json` | Per-mode cursors of the automation (`reconcile`); a cache, safe to delete. |
| `logs/<lesson>.md` | Lesson logs, regenerated from events. |
| `index.sqlite` | The rebuildable index. |

Writes append whole lines, flush and fsync under a short OS lock. Readers skip a torn last line and report it. The
index remembers how far it has read each file and a hash of that prefix; if a prefix changed, it rebuilds.

Outside the record, `$ROS_HOME/settings.json` holds the person's choices (`vault`, `vault_root` default `Research OS`,
`director_name`, `pdf_engine`, `portal_port`), and `$ROS_HOME/vault/<id>.sqlite` is the vault manifest (what the system
wrote and what it saw: path, size, mtime, hash). Both are rebuildable or re-askable; neither is the truth.

## Two graphs, two kinds of record

Records are of two roles, set in `record.json` (the `link` tool writes it):

| Role | Holds | `record.json` |
|---|---|---|
| user-wide | the researcher's **knowledge graph**: every domain, subject, course, goal and project; the capabilities under them with prerequisites; the learning history and lessons | `{"role": "user"}` |
| project | one project's **research graph**: questions, hypotheses, experiments, decisions, claims, sources (a reading of a repository's `research/graph` plus its reports) | `{"role": "project", "user": "<record>", "project": "project:<key>"}` |

The graphs share ids, not files: a research node that `requires capability:x` names capability `x` of the user-wide
record. `context` joins them for an agent: a project's next research steps with the user's state in each capability it
needs (`untracked` when the user-wide graph has no such capability), or, in the user-wide record, a summary of every
linked project. Every `part-of` target (`subject:`, `course:`, `goal:`, `project:`) has a node of its own. `ros init`
sets a new record up: it joins the user-wide record (the only one, or `--user`) under `project:<name>` or, with
`--kind course`, `course:<name>`, and creates that hub node in both records; `--user-wide` makes the record the user-wide
one (there is one), and `--no-link` leaves it alone.

## Goals, gaps and roadmaps

The graphs are there to find what you do not know yet and to order learning it. `gaps` and `roadmap` are **views**:
computed from the graphs each time, never stored (so never stale), and read-only. A **target** is a capability, a hub
(course, subject, domain, block, project, concept: its members), a goal, a research node of a project record (the
capabilities it requires), or several, comma-separated; with none, a project record means its whole research plus what
you tagged with its hub, and the user-wide record the goals' targets.

A `goal:<key>` node (the `goal` tool) may carry `targets` (node ids), `deadline` (ISO date), `pace` (minutes a week)
and `priority`; a capability node may carry `effort` (minutes, an author's estimate). They are inputs; nothing derived
is stored.

Each capability in the targets' prerequisite closure is **met** (its own evidence is valid) or a step of one kind:

| kind | when | minutes |
|---|---|---|
| `define` | a project needs it and the user-wide graph has no such capability | 15 |
| `fix` | it has recorded problems or is in a `requires` loop | 15 |
| `new` | unknown | 45 (+15 with no questions written, -10 with a prepared lesson) |
| `continue` | learning | 30 (same adjustments) |
| `repair` | fragile | 20 |
| `review` | stale, or demonstrated with no review date | 10 (5 for a reference capability) |

A capability judged on several dimensions costs one pass per dimension not yet demonstrated. Steps are ordered by
wave (one more than the highest wave of its unmet prerequisites, so a wave can be studied in any order; a loop has none),
then by how many targets and research nodes wait on it, then chain length, effort and id, so the order is total and
stable. A step is `available` exactly when `Learning.is_frontier` says so. With a `pace` the steps are laid into weeks;
with a `deadline` the verdict is `feasible` (at most 85% of the capacity), `tight` or `infeasible`.

## Node types

domain, subject, concept, capability, course, goal, project, block, paper, question, hypothesis, claim, experiment,
decision, code-symbol, source, lesson, handout, visual.

## Edge types

requires, teaches, tests, supports, invalidates, implements, cites, supersedes, part-of, about, applied-in,
addresses, decides, relates.

## Event types

| Type | Subject | Data |
|---|---|---|
| `retrieval` | capability | day, period, timing, method, outcome, assistance, evidence, review (imported learning history) |
| `lesson.start`, `lesson.close` | lesson | title, scope / summary |
| `attempt` | item | lesson, response (or `dont_know`) |
| `grade` | item | lesson, attempt, verdict, feedback, criteria_met |
| `hint`, `reveal` | item | lesson, index |
| `teach` | capability | lesson, mode, content |
| `ask`, `answer` | lesson / ask id | text or mode / text |
| `policy` | lesson | action, reason, item, capability, mode |
| `task.open`, `task.claim`, `task.done`, `task.cancel` | task | kind, ref, brief, … / by / result / reason |
| `bundle.ready` | bundle | manifest digest |
| `verdict` | claim | step, verdict, notes, checklist, evidence |
| `approval`, `decision`, `waiver` | subject | decision / outcome, rationale / reason |
| `commitment`, `commitment.status`, `proposal` | source / commitment / proposals | text, evidence_required / status / change |
| `intent` | hub | the person's words, the playbook chosen, the records it needs |
| `handout.revise`, `handout.built` | handout | source digest, reviewer / pdf path, engine, digest |
| `automation.run` | automation | mode, what each trigger did (only written when something happened) |
| `note.annotate`, `note.reviewed`, `note.dismiss`, `note.release` | node / note path | the person's text in a vault note / marked reviewed / dismissed a suggestion / took the note over |
| `inbox.found` | file path | kind, size, hash of a file dropped in the vault's Inbox (an `ingest` task follows) |

Task kinds: `grade`, `answer`, `visual`, `narration`, `animation`, `video`, `audit`, `verify`, `review`, `item`, `scout`
(search the literature for a question), `ingest` (read a dropped file), `outline` (plan a course), `bundle` (prepare a
lesson), `handout` (write one), `run` (run an approved experiment), `job` (a command the runner executes: PDF builds,
voice). The first claim of a task wins; a claim lapses after 30 minutes.

Importers (`import --kind`): `learning`, `sessions`, `research`, `graphify`, `documents`, `projects`, `notes`,
`session_notes`, `papers`, `legacy_tasks`, `visuals`, `resources`, `handouts`. `migrate` runs them all and
`migrate_check` lists every file of the old vault with where it went or why it was retired.

## Items

`kind` (choice, numeric, free), `prompt`, and per kind `options` + `answer` (index), `answer` + `tolerance`, or a
hidden `rubric`; optional `explanation`, `hints`, `option_feedback`, `concepts` (node ids), `difficulty`,
`supersedes`, `defence`.
