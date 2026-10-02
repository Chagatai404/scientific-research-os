# Derived knowledge and research maps

```bash
python scripts/knowledge_maps.py --root "<working-record-root>" --research-root "<research-record-root>" --as-of YYYY-MM-DD
python scripts/knowledge_maps.py --root "<working-record-root>" --research-root "<research-record-root>" --vault "<vault-root>" --as-of YYYY-MM-DD --apply
```

Default is a read-only dry-run listing proposed files. The research root defaults
to the working-record root; --research-root supports separate research storage.
Apply writes the master Knowledge Map.excalidraw.md at the vault root and scoped
maps under 02 Knowledge/Domains/<domain-id>/ and 02 Knowledge/Subjects/<subject-id>/.
Stable ontology IDs avoid filename/title collisions; source titles label the nodes.
This extends the vault's knowledge area and does not relocate existing notes.

All shapes/labels/edges are generated through the existing uncompressed Excalidraw
renderer. Domains, subjects, shared concepts, applications, assessable capabilities
and research records occupy labelled rows. Cross-domain foundations retain one
identity. A concept is not graded by aggregating capability scores: individual
profiles show their scope, required dimensions and transfer evidence, plus frontier
or evidence issues. Unknown concepts remain visible. Amber links identify required
foundations not established by current general evidence; capability prerequisites
use existing transitive readiness. Green means the displayed capability profile is
current, never an associated research finding. Research nodes show their actual
lifecycle separately; research edges retain their canonical relation names. No
supports/contradicts claim is invented from an application link or a mastery state.

Generated drawings are presentation views, never a data source. Recompute after
working-record updates; source projection hashes and assessment dates identify
the snapshot. Do not import a drawing's edited states back into learning/research.
With more than --max-nodes (default 80), produce an explicitly labelled overview
instead of a hairball. Scoped maps/query helpers expose detailed canonical evidence;
very large scopes also use an overview and require narrower concept queries. No
claim about omitted nodes is inferred. Concept prerequisites are included even
when their evidence lies outside the selected subject/domain.

Apply is idempotent: unchanged source/date/options produces identical bytes. Only
managed files listed in hidden .research-os/maps.json may be replaced or removed;
hashes and the generated marker protect manually edited/unmanaged drawings. Root
confinement rejects escapes/symlink traversal, preflight precedes writes, a lock
coordinates generators and each replacement is atomic. This is not a transaction
with Obsidian's unsaved editor buffers: close generated drawings before regeneration.
A failed multi-file update may leave some new views; rerunning unchanged inputs can
finish it. Preserve any human annotations separately; conflicting edits require
manual review. Invalid source diagnostics stop generation rather than show false
state. No plugin is installed and no actual user vault is changed by tests.
