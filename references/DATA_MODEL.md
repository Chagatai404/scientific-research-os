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
| `logs/<lesson>.md` | Lesson logs, regenerated from events. |
| `index.sqlite` | The rebuildable index. |

Writes append whole lines, flush and fsync under a short OS lock. Readers skip a torn last line and report it. The
index remembers how far it has read each file and a hash of that prefix; if a prefix changed, it rebuilds.

## Two graphs, two kinds of record

Records are of two roles, set in `record.json` (the `link` tool writes it):

| Role | Holds | `record.json` |
|---|---|---|
| user-wide | the researcher's **knowledge graph**: every domain, subject, course, goal and project; the capabilities under them with prerequisites; the learning history and lessons | `{"role": "user"}` |
| project | one project's **research graph**: questions, hypotheses, experiments, decisions, claims, sources (a reading of a repository's `research/graph` plus its reports) | `{"role": "project", "user": "<record>", "project": "project:<key>"}` |

The graphs share ids, not files: a research node that `requires capability:x` names capability `x` of the user-wide
record. `context` joins them for an agent: a project's next research steps with the user's state in each capability it
needs (`untracked` when the user-wide graph has no such capability), or, in the user-wide record, a summary of every
linked project. Every `part-of` target (`subject:`, `course:`, `goal:`, `project:`) has a node of its own.

## Node types

domain, subject, concept, capability, course, goal, project, block, paper, question, hypothesis, claim, experiment,
decision, code-symbol, source, lesson.

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

## Items

`kind` (choice, numeric, free), `prompt`, and per kind `options` + `answer` (index), `answer` + `tolerance`, or a
hidden `rubric`; optional `explanation`, `hints`, `option_feedback`, `concepts` (node ids), `difficulty`,
`supersedes`, `defence`.
