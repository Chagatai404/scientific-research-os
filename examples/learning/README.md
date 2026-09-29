# Synthetic learning records

These records are fictional fixtures, not evidence of any person's understanding
or scientific claims. The question/assessment references are illustrative stubs.

At `--as-of 2026-09-29`, density is retained, gamma-density is an active frontier
node, and shower-profile is blocked by gamma-density. The subject `probability`
contains density and gamma-density. Project `demo` includes gamma-density and
shower-profile, with density pulled in as an external prerequisite. `legacy.md`
remains untracked despite its old `solid` label.

From the repository root:

```bash
python scripts/knowledge.py --root examples/learning --subject probability --as-of 2026-09-29
python scripts/knowledge.py --root examples/learning --project demo --as-of 2026-09-29
```

On `2026-10-06`, density is stale because its recorded review horizon has passed,
so gamma-density no longer qualifies as frontier. No forgetting is inferred.
Input files are never modified. Dates are fixed so this example is reproducible.

## Goal and retention example

Density is core, gamma-density working, and profile reference; these fictional
choices do not change their evidence. Density intentionally has no goal metadata.
`research-foundations` selects gamma-density and profile plus external density;
`applied-probability` selects gamma-density plus external density.

```bash
python scripts/knowledge.py --root examples/learning --goal research-foundations --as-of 2026-09-29
```
