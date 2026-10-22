# The director and the automation

The researcher directs: they say what they want to learn or find out, and later judge the findings, fully informed.
Everything between those two is done by the system and its agents, without anyone starting or stopping a process.

## Saying what you want

| You say | `engage` does |
|---|---|
| "teach me STAT303" | makes the course record (joined to your user-wide record), states the goal, opens an `outline` and a `scout` task, gives the course a home and an `Inbox/` in your vault. Lessons, lecture notes, recitations and a chapter follow from the outline. |
| "teach me about quantum error correction" | a subject hub and goal in the user-wide record, with the same two tasks |
| "is it true that protons shower wider than pions?" | makes the project record, frames the question in your words, opens three neutral literature searches (competing models, null results, validity limits) |
| "quiz me", "continue", or nothing | tells you what is due or what comes next |

An agent passes your words as `intent`; `kind`, `target` and `title` are worked out from them when it does not say. Saying
the same thing twice changes nothing. In a client with MCP prompts, `learn`, `investigate`, `continue` and `review` are
offered as commands, so you need to remember none.

## What happens by itself

`reconcile` looks at what changed in a record since it last looked and runs the triggers that care (`ros.automation.TRIGGERS`).
It runs after every writing call in the CLI and MCP, at the start of every `brief`, and on a timer inside `ros serve` and
`ros mcp`. There is no daemon, no pid file and no lease: the cursors are in `<record>/cache/automation.json`, derived, and
every trigger is idempotent. An `automation.run` event is written only when a pass opened or wrote something, so the
portal can show what the system did on its own.

| Trigger | Fires on | Does |
|---|---|---|
| `claims_audit` | a claim is added or changed | checks its numbers against its files, requests every required audit |
| `approval_runs` | you approve an experiment | opens a `run` task for an executor: every rung of the scale ladder within the plan's budget |
| `literature_flow` | scouts finish | opens one verification per candidate; when all are done, the literature handout |
| `bundle_tasks` | the graph or evidence changes | prepares the next lessons of a goal or of what a project needs |
| `course_handouts` | the graph changes | a lecture note for each next capability of a course, a recitation once it is ready, a chapter |
| `bundle_gate` | a bundle's plan changes | runs the readiness gate, opens a task for each missing piece |
| `handout_gate` | an agent finishes writing a handout | gate, note in the vault, PDF job |
| `renders` | narration without audio, voice engine configured | a voice job |
| `vault_sync` | the record changes | notes follow the record |
| `vault_scan` | every half minute | what you did in the vault flows back; files dropped in an `Inbox/` are read in |
| `review_note` | once a day | the review note |

What needs a model (outlining, writing, grading, auditing, running experiments) waits as tasks until an agent is attached;
`brief` says how many wait and for how long. Everything else needs no agent.

## Jobs

Local engine runs (a PDF build, a voice render) are `job` tasks. The process serving the portal or MCP (or `ros go` in the
foreground) claims one, runs its command **outside** the registry lock so the portal stays responsive, and finishes it
with `job_done`, which then does what the job said (attach the PDF). A job runs only a command this program built: the
running Python, `-m`, one of its own engines, a folder inside the record. A crashed runner's claim lapses after thirty
minutes. Outputs are named by the hash of their input, so two runners doing the same job is wasteful, not wrong.

## The agent's loop

```
brief                                    what needs the researcher, what waits
engage --intent "<their words>"         when they say what they want
work --by <you>                          the next task, claimed, with its skill, role and finishing tool
  ... do it with the skill it names ...
finish --task <id> --record <record>    then work again, until it returns nothing
```

`work` takes the most urgent task across every linked record (a person waiting on a grade, then audits, then a run, then
lessons, then groundwork), oldest first. Two agents never get the same task.

## The researcher's part

`brief` lists what needs them, each with a headline; `evidence --subject <id>` has everything: a claim's audit chain with each
reviewer's notes, the number checks, citations, the adversary's memo, ownership, the handout and the vault note; an
experiment plan with what approving it authorizes (every rung of its ladder within its stated budget, nothing beyond).
Approving, deciding and waiving are theirs (`human` tools): never offered over MCP, confirmed at a terminal in the CLI,
made in the portal.

`doctor` says what is not set up (the vault, a PDF toolchain, an agent client) and the one command that fixes each.
