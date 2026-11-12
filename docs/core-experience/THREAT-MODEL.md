# Core experience trust boundaries (S0)

Scope: the initial read-only workspace inventory and the changed boundaries planned
for S1 onwards. This is a scoped engineering analysis, not a completed security
scan or certification. Existing source and tests provide design evidence; tests
not rerun in this slice are not claimed as newly verified.

| Boundary / asset | Failure to prevent | Existing or required control / evidence |
|---|---|---|
| Physical records to shared workspace view | Same title/id in unrelated records silently transfers ownership or learning history | Qualified physical references; explicit record.json user/project links; excluded unrelated records; title-only candidates remain unresolved. `tests/test_ros_workspace_inventory.py` exercises the boundary. |
| Organization navigation to scientific evidence | Folder membership appears to prove support, mastery or claim acceptance | Inventory emits navigation metadata only; it never appends scientific edges, grades, answers or decisions. Organization preferences remain distinct from scientific facts. |
| Source metadata to filesystem | Inventory follows a source root, junction or network share, or reads private source text | Inventory folds only connection metadata and does not call source resolution, preview or external-root existence checks. The caller supplies open authorized records. This does not grant authority to arbitrary record paths. |
| Historical data to identity corrections | Migration edits immutable history or silently rehomes ambiguous work | S0 has no write/migration API. Copies and hash comparison precede mapping review; S9 must append corrections, test idempotence and compensating rollback. |
| Tool registry to human authority | Agent writes approval, decision or ownership waiver | Existing human-only tool policy, registry checks and MCP filtering must survive new contracts. See `ros/registry.py`, `ros/mcp.py`, `tests/test_ros_interfaces.py`. Inventory creates no authority events. |
| Local/private sources to cloud and web | Provider/custom-agent routing treats a name as permission to leak local content | Existing source grants, localOnly checks and derived-private tracking remain required. S4 must bind actual transport/capabilities to grants, S6 must separate public search from private context. See `ros/sources.py`, `ros/conversation.py`, `ros/runtime.py`, `tests/test_ros_sources.py`. |
| External documents to tools | Untrusted instructions escalate tool, shell, filesystem or application grants | Stored titles/content are untrusted data. Inventory titles are display text, never commands. Later UI must escape them; run grants must remain external to document/model text. |
| Provider authentication to persistence | API key/token enters append-only events, exports, manifests or model context | S4 must store credential references only and test redaction, replace/revoke/missing cases. No credential/provider access occurs in S0. |
| CLI/MCP/HTTP to shared execution | Retry duplicates effects, restart expands scope, HTTP-only execution masks parity gap | S2 requires durable work/run ids, revision-bound approvals, cancellation and idempotency across all clients. Current tool parity alone is insufficient evidence. |
| Model-written renderer to host | Generated code reads private files or bypasses limits | Preserve existing AppContainer fail-closed renderer and provider tool restrictions (`ros/lib/appcontainer.py`, `ros/lib/renderkit.py`, `ros/lib/providers.py`). S0 does not execute render code. |
| Computer adapter to user files/apps | Path escape, overwrite, focus change, repeated delivery, secret read or unauthorized outbound action | S8C must bind plan version, real paths/apps, actions and idempotency; test collisions, symlinks/junctions, interruptions and verified effects. No computer adapter is implemented in S0. |

Priority prerequisite: unresolved identity is a data-integrity boundary. The copied
STAT303 record is empty while historical work is elsewhere; title matching can
suggest a review but cannot authorize a transfer. Inventing answers, assessments,
history or provenance to make a journey look complete would invalidate acceptance.

Remaining S0 limitations: the inventory has no cross-record transaction snapshot;
each record is held in its indexed read context, but another process may append
between per-record synchronizations. It is suitable for copied/offline preview,
not an atomic live migration. Supplied record names must uniquely qualify roots.
The helper is local-only domain functionality with no public exposure; any later
tool/UI wrapper must enforce caller authorization and avoid publishing private
titles/references by default. Existing local source metadata may be stale and
membership does not establish content readability or verification.

## Security review notes (2026-11)

| Boundary | Failure to prevent | Control |
|---|---|---|
| Agent to experiment code | An agent runs `-c`, an unrecorded or edited file, or overwrites the person's script | argv limited to the environment's runners; recorded path plus SHA-256 checked at queue and at launch; `experiment_write` refuses foreign files. The run itself is **not sandboxed**. |
| Experiment process to the shown log | A script forges "completed" or other changed files | exit status and files come from the worker's result; log lines are shown as output only |
| Model to computer grants | A model reuses a grant id as `request_ref`, or a grant outlives its job | runtime-bound `request_ref`, claim once, spent by its first completed plan; remembered grants carry no outbound |
| Paths to hidden areas | `repo\.git\hooks\x`, `~\.claude\skills\x`, bidi overrides, junctions in the bin | every component checked; Cf characters refused; bin purge never enters a link |
| Agent-written notes and web pages to a model | Injected text steers a session or builds an exfiltration address | graph notes carry `untrusted`; after a page read a later page address may not carry a query or fragment |
