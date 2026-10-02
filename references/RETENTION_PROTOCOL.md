# Domain-aware retention

Use `python scripts/retention.py --root <working-record-root> --as-of YYYY-MM-DD`
for deterministic session candidates. Optional --domain, --subject, --concept,
--project, --course or --goal narrows the view; --limit bounds the block. A project
is one relevance selector, never an importance boost. For a broad retention session
use the whole working-record root so older foundations are not starved by active work.
Keep the learning protocol's probe budget and delayed-retrieval rules.

Optional canonical `retention_focus: foundational | transferable | reasoning | detail`
is a reviewed qualitative choice on a capability, separate from retention_target
and mastery. Foundation includes core relationships, assumptions, useful equations
and vocabulary needed for reasoning; transferable/reasoning covers reconstruction
and high-use derivations. Detail covers lookup-friendly constants, commands and
one-off file/implementation facts. Never infer focus from titles, graph degree,
activity or AI confidence, or silently write it. Missing focus means unspecified.
Qualitative focus bands are ordered, with recorded due dates within each band and
round-robin subject memberships; these are a deterministic session heuristic, not
an optimized psychological spacing law or numeric importance estimate.

Only capabilities with actual prior successful evidence enter retention. Required
dimensions keep their own state/horizon. Weak/unknown independent transfer and
conceptual understanding despite strong application become labelled initial probes,
not claims of previously learned transfer or forgotten theory. Prefer independent
non-project examples for conceptual/transfer questions; rotate suitable examples
with real attempt history rather than relabel the same project exercise. Scoring
and novelty require tutor review. Shared concept/scope/dimension appears once per
block; this suppresses duplicate prompts, never merges capability assessments.

Detail is suppressed unless --include-details explicitly requests it. Working and
reference have no routine burden; --for-use permits contextual refresh for actual
use, including a reviewed detail when both flags are supplied. Core and unspecified
respect recorded horizons; future positive evidence is not selected early unless
for-use. Missing horizons are not invented and imply no automatic urgency. Unknown
transfer is an optional diagnostic recommendation, not a scheduled retention debt.
Existing dates, delayed evidence, targets and scalar schema-1 behavior are preserved.
The helper writes nothing and runs offline; it adds no background scheduler.
