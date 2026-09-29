# Agent Policy

## Human authority

The user is the principal investigator and learner.

Agents may:
- search,
- summarize,
- explain,
- propose,
- implement, test, and reproduce within the explicitly approved plan scope,
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
- provide the claim/design, relevant sources or raw artifacts, and acceptance criteria with minimal authoring rationale; do not pass the full tutoring/coordinator conversation as an independence claim;
- actively search for plausible competing explanations and evidence that would change the decision.

For reconciliation:
- only after independent discovery/verification, compare external evidence against the repository, implementation, and current hypothesis;
- treat disagreement as information rather than something to smooth over.

Do not call two agents independent if one was given the other's reasoning and asked merely to approve or critique it.

## Lesson preparation contexts

The research protocol distinguishes standalone tutoring, research-linked tutoring,
and a full substantive research cycle. Ordinary isolated teaching does not require
a research-agent team. For research-linked teaching, keep important source
verification separate before relying on the claims; reuse applicable recorded
independent evidence rather than repeating agents by ceremony.

The coordinator/tutor may receive learner history, dependency maps, and the verified
evidence pack. Keep preferred implementation details and learner guesses out of
neutral discovery; give the verifier atomic claims and sources rather than the
scout's reasoning. Record actual context exposure, including unavoidable prior
knowledge, instead of assuming different agent names establish independence.

The pre-tutor sanity check is an integration/readiness check owned by the
coordinator, not a new reviewer role. It may use verified results, but is not
independent corroboration or the full post-synthesis adversarial review.
Question preparation and visual planning may share the verified pack without
claiming independence. Parallel work starts only when its evidence inputs exist;
pending verification is not permission to present a claim as established.

Later specialist reviewers should receive the specific scientific claim, sources,
artifacts, or design criteria needed to reconstruct their assessment, without the
authoring agent's full reasoning when practical. Record any necessary context
sharing and remaining limitations. Review findings return to the coordinator;
neither lesson readiness nor reviewer agreement authorizes implementation.

## When to use subagents

For a substantive research cycle, the canonical `RESEARCH_PROTOCOL.md` requires
a separate literature scout and source verifier, dispatched by the coordinator.
Assigned specialists perform only their bounded task and return findings; these
cycle-wide requirements do not instruct each specialist to spawn another cycle.
Dispatch with fresh/minimal
context where supported; do not use a full-history fork as an independence claim.
The main agent may know the code, but passes only necessary neutral scope to the
scout and atomic claims/sources to the verifier. Record context exposure and
limitations. If independent agents or source access are unavailable, disclose the
gap and arrange separate verification; never label self-review independent or
silently skip the stage before relying on consequential claims.

Select additional specialists by scientific risk; do not instantiate every role.
Reviews are read-only unless an approved reproduction explicitly permits runs.
Apply the research protocol's A–D triage to findings, including source conflicts.
Severity tracks potential effect on the current conclusion, not sophistication.
Prefer cheap informative tests and replaceable choices; avoid review recursion
without new evidence. Resolve disputes with evidence, not majority vote.
Review completion permits planning only. Build agents and experiment execution
require explicit approval of the presented plan; discussion is not approval.

Use subagents when:
- independent lines of inquiry can run in parallel,
- a specialist benefits from an isolated context,
- review should be independent of the authoring context,
- a large exploratory task would pollute the main context.

Do not use subagents for:
- trivial questions,
- single-file straightforward edits,
- tightly sequential reasoning where state must remain shared.

## Bounded evidence work and selective escalation

Discovery, extraction, deterministic validation, source verification and synthesis
are logical contracts; they need not each use a separate model call. Preserve the
independent verification boundary. Small agents can handle retrieval, metadata,
candidate extraction, locators and simple atomic verification when evaluated for
that task. Use deterministic tooling for structure, provenance and receipt checks.
Escalate conflicts, ambiguous terms, nontrivial regime transfer, complex derivation,
causal interpretation and model selection as REASONING_REQUIRED. The coordinator
chooses reasoning capability and synthesizes compact verified atoms. Reuse unchanged
records; do not pass full histories or repeat full-source reading by ceremony.
See the EvidenceAtom contract for receipt and cache invalidation requirements.

## Convergence

Specialists return reports to the main agent.
The main agent synthesizes.
The human decides.
