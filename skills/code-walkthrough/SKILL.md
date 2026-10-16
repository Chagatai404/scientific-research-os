---
name: code-walkthrough
description: Teach the researcher the code that was written for them or inherited, so they can explain, run, verify, modify and defend it. Use after an approved build unit, when taking over a codebase, or before presenting or modifying code. For a one-off question about a snippet, answer directly instead.
---

# Code Walkthrough

Read `references/CODE_LEARNING_PROTOCOL.md`, `references/TEACHING_FORMAT.md` and `references/RESEARCH_PROTOCOL.md`. Teaching never
bypasses the plan or its approval; an approval is never lowered by a pace.

## Context preflight (required)

Before any walkthrough, load context from the canonical records instead of relying on the chat:

```
python scripts/context_kernel.py preflight --workflow code-walkthrough --target concept:<id>     --project "<project>" --vault "<vault>" [--session <path>] [--record <RQ-id>] [--expect-empty]
```

Read the receipt it prints. **BLOCKED** (exit 2) means an essential source is missing, invalid,
unreadable or unconfigured: stop, report which source and why, and do not continue from memory.
**DEGRADED** means continue only where the limitations do not reach, and say so. Empty is not
unavailable: declare a new learner or project with `--expect-empty`. An unresolved concept is
unknown, never demonstrated. Dependent actions check the receipt themselves (`html_sessions.py create`,
`tasks.py` stages 7/8/14/15), so skipping this step fails rather than passes silently.
See `references/CONTEXT_PROTOCOL.md`. Read the Student Brief in the receipt and define unseen code terms before using them.

## Workflow

1. **Inherited or existing code:** `python scripts/code_walkthrough.py --repo <repo> map`, then `graphify query` for calls. Tour the
   layers dependency-first, trace one input end to end, then set one small modification exercise. Propose a short Code Map note; the
   researcher reviews it.
2. **New work, before the plan:** ask the researcher how they would build it, then compare it with your plan. List **change units**
   (`units --base <rev>`): files, purpose, linked concepts, risk class (a proposal; the researcher confirms), teaching level (`levels`). The
   plan approval is unchanged and still required.
3. **After each built unit** make a walkthrough record (`references/CODE_LEARNING_PROTOCOL.md`): claims about the code, each with a locator
   taken from the code (`locate`), claims of behaviour or results citing a recorded execution (`trace`), the choices you made that the plan did
   not specify, and probes. A **consequential unit is always walked through and probed**; skipping one is the researcher's choice and is recorded
   with its reason as an open ownership gap (`ownership-gaps`). Routine units follow the profile's `checkpoint_pace`.
4. **Run the checks you can:** `python scripts/code_walkthrough.py --repo <repo> verify <record.json>` must come back consistent before you
   present the walkthrough. For a consequential unit, hand the record to the `walkthrough-verifier` agent.
5. **Teach it as a Teaching Card** (`blocks <record.json>` gives the declarations): one idea first, the code terms, a diagram from the code
   graph, one input traced through the real code with each step cited, then 2–4 probes: predict the output (you run it to know the answer),
   find the line to change for a requirement, explain a function back. A "what breaks if this is removed" exercise runs only in a scratch
   worktree and only if the researcher approves.
6. **Evidence comes from the learner's answers**, reviewed against criteria and proposed to the ledger (`tutor_gate.py evidence`); your
   explanation and their viewing are not evidence.
7. **Keep the notebook ledger current (research repos with a `notebooks/` folder).** When a unit is completed and its tests pass, run
   `python scripts/notebook_coverage.py ledger --repo <repo>` (a dry run: it reports new and closed gaps), and, in a repo that already
   keeps `research/NOTEBOOK_COVERAGE.md`, the same with `--write` to regenerate it. Tell the researcher which gaps are new. In that repo notebooks
   are AI-written documentation of *finished* work, so never create or change one unasked, and never decide a unit is complete: the
   researcher does. The ledger is a derived file; leave it uncommitted for them to review. See `references/CODE_LEARNING_PROTOCOL.md`.
8. **Notebooks as the thing to trace (research repos).** A notebook's stored outputs and prose are AI-written claims, not authority. To check one,
   run it with `python scripts/notebook_trace.py run --repo <repo> --record <record.json> --notebook <id> --run`: only a notebook the researcher
   listed in `approved_notebooks` runs, in a scratch clone of the committed state with its own `uv` environment (never the real source tree), with
   secrets scrubbed from the environment and a timeout. It reports whether the fresh output matches, differs only in last digits or image bytes, or is
   **stale**, and records the run in the record's `executed` list. A mutation exercise (`mutate --spec`) changes one string in a notebook cell or a
   source file *of the copy*, runs the notebook before and after, and reports what changed: ask the researcher to predict first, show nothing until
   they have, and never mutate the repository itself. Without `--run` both commands only describe what they would do. See `references/CODE_LEARNING_PROTOCOL.md`.

## Limits you must state

`approved_commands` in the record is the researcher's attestation; you never write it, and `trace` runs only what it lists, without a shell, in
the repository. Never read `.env` files, keys or credentials into a walkthrough; never copy private data into the vault; excerpts are short with
`path:line`. A consistent `verify` shows the cited lines exist and match and behavioural claims cite runs, not that your explanation is right.

## Mandatory session artifacts

When this workflow creates or continues a substantive session, follow
`references/HTML_SESSION_PROTOCOL.md`: use the centralized
`scripts/html_sessions.py` API, preserve Markdown backlinks, produce HTML and
structured state, and validate the artifacts. Before creating or resuming, run
`scripts/html_sessions.py context <session>`: it lists unchecked answers and open
questions and loads the project's research and knowledge graphs, which remain the
memory; the page is only a view. Post questions, checks and teaching through the
live loop in that protocol so the session reads in order and updates without reload. Ordinary notes, evidence records and source files retain
their canonical formats. Browser feedback never automatically establishes mastery.
