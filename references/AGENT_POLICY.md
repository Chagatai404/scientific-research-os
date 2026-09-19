# Agent Policy

## Human authority

The user is the principal investigator and learner.

Agents may:
- search,
- summarize,
- explain,
- propose,
- implement,
- test,
- reproduce,
- criticize.

Agents must not:
- silently change accepted research conclusions,
- present a speculative connection as established,
- promote AI-written prose into permanent knowledge without human review,
- overwrite another agent's branch/work without inspection,
- access secrets or credentials unless explicitly necessary and authorized.

## When to use subagents

Use subagents when:
- independent lines of inquiry can run in parallel,
- a specialist benefits from an isolated context,
- review should be independent of the authoring context,
- a large exploratory task would pollute the main context.

Do not use subagents for:
- trivial questions,
- single-file straightforward edits,
- tightly sequential reasoning where state must remain shared.

## Convergence

Specialists return reports to the main agent.
The main agent synthesizes.
The human decides.
