---
name: derive
description: Reconstruct a mathematical, statistical, physical, or ML formula from motivations, definitions, and assumptions. Use when the user wants to understand where an equation comes from or needs a derivation they can reproduce themselves.
---

# Derive

1. State the target result.
2. Explain what problem forces us to introduce this quantity/result.
3. List only the starting facts and assumptions actually needed.
4. Derive in motivated steps. For each non-obvious move explain why someone would try it.
5. Check algebra/calculus carefully.
6. Check units or dimensions when applicable.
7. Test simple and limiting cases.
8. Explain the geometric/physical/statistical meaning.
9. Identify where approximations enter.
10. Give one reconstruction exercise without the solution first.
11. Record authoritative sources validating the result.


## Context preflight (required)

Before any derivation or check, load context from the canonical records instead of relying on the chat:

```
python scripts/context_kernel.py preflight --workflow math-review --target concept:<id>     --project "<project>" --vault "<vault>" [--session <path>] [--record <RQ-id>] [--expect-empty]
```

Read the receipt it prints. **BLOCKED** (exit 2) means an essential source is missing, invalid,
unreadable or unconfigured: stop, report which source and why, and do not continue from memory.
**DEGRADED** means continue only where the limitations do not reach, and say so. Empty is not
unavailable: declare a new learner or project with `--expect-empty`. An unresolved concept is
unknown, never demonstrated. Dependent actions check the receipt themselves (`html_sessions.py create`,
`tasks.py` stages 7/8/14/15), so skipping this step fails rather than passes silently.
See `references/CONTEXT_PROTOCOL.md`.

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
