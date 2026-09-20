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

## Independent research context

When independence matters, context is part of the experimental design.

For source discovery:
- formulate the question neutrally;
- do not inspect implementation details, preferred equations, current citations, or desired conclusions unless they are necessary to define the system being searched;
- search for alternatives and counterevidence, not only support.

For source verification:
- provide the claim and source(s);
- withhold the scout's conclusion and authoring-agent rationale when practical;
- verify exact support, scope, and limitations independently.

For adversarial review:
- do not begin from an assumption that the preferred interpretation is correct;
- actively search for plausible competing explanations and evidence that would change the decision.

For reconciliation:
- only after independent discovery/verification, compare external evidence against the repository, implementation, and current hypothesis;
- treat disagreement as information rather than something to smooth over.

Do not call two agents independent if one was given the other's reasoning and asked merely to approve or critique it.

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
