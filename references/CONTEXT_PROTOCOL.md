# Context Protocol

Agents do not carry the learner's history or the project's research record in a chat. They
rebuild it, every time, from the canonical records, and prove they did. This protocol
describes the mechanism implemented by `scripts/context_kernel.py`; it is not a substitute
for it.

## What it is, and is not

The **context kernel** is read-only. It consults the learning graph, research graph, project
note, code graph, paper library, visual registry and earlier sessions, retrieves a *bounded*
subgraph, and writes a **context receipt**. It never grades, accepts, edits or infers.

- It does not decide scientific validity, learner mastery or research acceptance.
- A bounded subgraph is reported as bounded (`truncated`, plus a limitation). It is never
  presented as the whole graph.
- An empty graph, a missing graph, an invalid graph and an unreadable graph are four
  different statuses. None of them is silently read as "nothing known".

## Run it

```
python scripts/context_kernel.py preflight --workflow tutor --target concept:box-counting \
    --project "Demo Project" --vault "<vault>" [--session Sessions/x.md] [--record RQ-001] [--expect-empty]
python scripts/context_kernel.py validate <receipt.json> [--workflow tutor] [--no-degraded]
```

Exit status 2 means **blocked**. Print the blocking source and stop; do not continue from memory.

## Workflows and what each cannot proceed without

`essential` sources that are missing, invalid, unreadable or unconfigured **block**.
`advisory` sources that are broken only **degrade** the receipt. `off` sources are not used.

| Workflow | learning | research | project | code | library | visuals | sessions |
|---|---|---|---|---|---|---|---|
| tutor | essential | essential | essential | advisory | advisory | advisory | advisory |
| course-study | essential | off | off | off | off | advisory | advisory |
| standalone-question | advisory | off | off | off | off | advisory | advisory |
| math-review | advisory | essential | advisory | advisory | advisory | off | off |
| statistics-review | advisory | essential | advisory | advisory | advisory | off | off |
| physics-review | advisory | essential | advisory | advisory | advisory | off | off |
| research-plan | advisory | essential | essential | advisory | advisory | off | advisory |
| research-implement | advisory | essential | essential | advisory | advisory | off | off |
| literature | advisory | advisory | advisory | off | essential | off | off |
| research-review | advisory | essential | advisory | advisory | advisory | off | off |
| decision-synthesis | advisory | essential | advisory | advisory | advisory | off | off |

Project sources (research, project, code) are `not-applicable` when no project is named.

## Source statuses

`ok`, `empty` (readable, no records), `missing` (path absent), `invalid` (present but no usable
records, or a parse failure), `unavailable` (could not be read), `not-configured` (no path was
ever given), `not-applicable`. A source with some records and some validation errors is `ok`
with `partial: true`, which degrades the receipt and lists the diagnostics.

`empty` on an essential source degrades the receipt unless the caller declares
`--expect-empty` (a new learner or a new project).

## Outcomes

- **ready** - every essential source is usable and nothing was cut off.
- **degraded** - usable, with limitations (broken advisory source, partial data, bounded
  retrieval, unresolved target, unexpected emptiness). Work the limitations do not touch may
  continue; state the limitation.
- **blocked** - an essential source is unavailable. Dependent actions are refused.

An unresolved target concept is *unknown*, never *demonstrated*. Only `demonstrated` and
`retained` capabilities are classed as demonstrated; `unknown` stays `unassessed`.

## The receipt (schema 1)

`receipt_schema`, `workflow`, `mode` (`bootstrap` | `resume` | `standalone`), `outcome`,
`request` (normalized, re-runnable), `sources[]` (name, level, status, path, `fingerprint`,
counts, diagnostics, partial), `retrieval` (limits, `learner`, `research`, `project`,
`library`, `visuals`, `sessions`, `code`), `limitations[]`, `blocking[]`, `created_at`,
`as_of`, `receipt_id`.

`receipt_id` is a digest of everything except the timestamp: edit a receipt by hand and
`validate` rejects it (`CONTEXT_INVALID`). It is tamper-*evident*, not tamper-proof.

## Freshness

Each source is fingerprinted by content (a cheap stat digest first, a content digest only
when stat disagrees). When a relevant canonical record changes, the receipt is
`CONTEXT_STALE`. `preflight` reuses a still-fresh receipt and rebuilds a stale one, so it is
cheap to call again after the learner answers or a record changes.

## Where it is enforced

| Action | Gate |
|---|---|
| `html_sessions.py create` | Runs the preflight itself; refuses (exit 2) and creates nothing if blocked; stores a binding in `state.json`. `--waive-context REASON` records an explicit waiver. |
| `add_question`, `append_session`, `review_response` with new teaching or a next question | Requires the bound context to be current. A stale binding is rebuilt from its stored request; a blocked rebuild raises `CONTEXT_BLOCKED` and writes nothing. |
| `tasks.py` stages 7, 8, 14, 15 | Needs exactly one input of kind `context-receipt` of an allowed workflow. Reasons: `CONTEXT_REQUIRED`, `CONTEXT_BLOCKED`, `CONTEXT_STALE`, `CONTEXT_INVALID`, `CONTEXT_WORKFLOW_MISMATCH`. Completed tasks are never re-blocked. |

A verdict alone (`review_response` with no new teaching) is not gated, and a learner's own
submissions are never lost because the agent's context is broken. Historical sessions without
a binding keep working; `html_sessions.py context SESSION --bind` adopts one.

Stage 3 (independent literature discovery) is deliberately **not** given project context.

## Limits of this mechanism

It proves which records were consulted and that they have not changed. It cannot prove a
model read or understood the receipt; the gated actions above are what make skipping it fail.
