# Core experience baseline

Baseline source: `d0ff6782e7f2d092076ec52ae2863199e5b9b3e8` (1.7.3).
Measured 2026-11-09 on branch `agent/codex/core-experience`. This is the
identity/projection prerequisite, not complete journey acceptance.

## Existing evidence and limits

The planning evidence in `.plans/core-experience-evidence.md` recorded architecture
(12 tests) and workspace (21 tests) passing. Its isolated full run had 1065 tests,
9 failures, 65 errors and 9 skips; it did not pass. Socket bind, temporary-folder,
junction, clone, PDF engine, AppContainer and fixture assertions require separate
environment/application classification. These are historical observations, not a
new passing test run. The coordinator reran with workspace-local temporary folders,
UTF-8, isolated ROS_HOME, ROS_NO_VAULT=1 and permitted local socket/process access:
1071 tests passed, 9 skipped, in 844.951 seconds. The existing portal Chromium
scenario passed 19 steps; workspace responsive checks passed at 320–1920 pixels;
35 frontend tests passed. These are baseline checks, before the completed runtime
and new grouped workspace UI. Private logs remain git-excluded.

Static journey limitations identified there remain acceptance work: new Learn and
Research work can open under the previous record scope; title text replaces source
identity; HTTP alone orchestrates some operations; project stage uses record-wide
task heuristics. Existing FSRS, assessed evidence, append-only history and domain
tool registry are retained. No paid provider or live personal record was used here.

## Read-only mapping preview

`ros.workspace_inventory.inventory(rec, linked_records=())` takes caller-supplied
open records. It returns version 1, qualified `hubs`, `mapped`, `ambiguous`,
`unassigned`, `excluded_records` and aggregate `counts`. A reference is
`{owner_record, entity_id}`; it identifies the original physical record, not a new
canonical workspace. It has no fabricated revision. Every mapping includes the
explicit metadata basis. It is a domain helper, not a registered public tool.

Explicit `record.json` user/project links qualify a shared course/project hub;
organization placement, `part-of`, `hub`/`hub_record` and source-connection metadata
provide membership. Organization placement overrides older `part-of` placement,
including an explicit Inbox. Multiple explicit owners stay ambiguous. Title
matching is a conservative candidate heuristic and never assigns ownership.
The caller chooses authorized records; the helper does not discover records or
read source roots, source bytes, conversations or assessment content. Cycles stop.
The current graph and active library fold are inventoried; removed library entries
and event-only work without nodes are outside this initial projection. Archived
graph entities are retained in the inventory. This is not a complete migration.

A synthetic fixture models the empty dedicated STAT303 record and lessons,
conversation and material in Knowledge. Nine tests cover explicit mapping, conflict,
title uncertainty, source inheritance, preference updates, cycles, rename stability,
unlinked record isolation and unchanged originals/no fabricated learning events.

The coordinator made a git-excluded private copy of three records: 704 files,
99,251,866 bytes; source-before/copy/source-after SHA-256 matched per file. SQLite,
caches, logs and settings were excluded. Inventory writes only disposable indexes;
source JSONL, config, items and bundles remained hash-equal after the benchmark.
No personal titles, paths or detailed ownership map are published here.

| Aggregate (all three copied records) | Count |
|---|---:|
| Hub identities | 28 |
| Explicitly mapped representations | 483 |
| Ambiguous representations (all title-only) | 134 |
| Unassigned representations | 229 |

The dedicated STAT303 record has zero work representations. Explicit membership
for its shared hub identifies 1 conversation, 1 lesson and 63 materials in Knowledge.
Candidate-only matches are 1 connection, 1 handout, 3 lessons, 27 materials and
43 sources. These are representation counts, not distinct files or verified
ownership. A single source may have multiple representations. The affected
historical journey required review of those ambiguous mappings. The user explicitly
approved the 75 STAT303 candidates. Another 12 references identify that exact course
through its recorded handout namespace or tutor-session path, rather than title
similarity. On 2026-11-10 the coordinator applied those 87 explicit memberships to
the private copy. The overview now contains 8 sessions, 134 source representations
and 10 handouts, with no missing references. Repeating the assignment changed zero
records. All original bytes were preserved: only 87 membership events were appended
to the copied Knowledge event file; every other manifest file retained its hash.
Live records were not modified. These counts are not deduplicated file counts or
proof that the App displays them correctly; S3 must verify the organized view.

The QML hub has explicit mappings across the copies for 2 connections,
2 conversations, 13 decisions, 9 experiments, 14 hypotheses, 311 materials and
4 questions; 1 source is a title-only candidate. These figures do not establish
scientific claim correctness or authorize accepting any decision.

## Inventory performance

Windows 11 build 26200, Python 3.14.4, AMD64 Family 25 Model 68 Stepping 1,
16 logical CPUs. Serial `perf_counter` measurements, 20 rounds each. Cold means
a fresh Record connection; OS disk cache is uncontrolled. First private call also
built disposable indexes (809.701 ms). The distribution below includes that call;
p95 uses nearest-rank. No UI layout, network, provider or rendering time is included.

| Dataset | Cold p50 / p95 ms | Warm p50 / p95 ms | After preference update p50 / p95 ms |
|---|---:|---:|---:|
| Synthetic two-record fixture | 35.418 / 41.018 | 9.396 / 11.628 | 10.083 / 12.589 |
| Private three-record copy | 195.880 / 304.392 | 97.035 / 147.747 | Not run (copies receive no event writes) |

Reproduce with `ROS_NO_VAULT=1`, workspace `.test-temp` for TEMP/TMP, and
`python tests/bench_core_experience.py --rounds 20 --output <local-json>`.
For an authorized copy add `--snapshot <copied-ROS_HOME>` (must contain
`projects/stat303`). Raw samples/environment stay in the output JSON. Synthetic
preference updates deliberately append to disposable fixture events; the report
labels that fact. Benchmarking a live record is outside this procedure.

Proposed same-machine regression thresholds for this helper: private-copy warm
p95 <= 200 ms and fresh-connection p95 <= 450 ms after initial index construction.
These are provisional inventory budgets, not AC14 acceptance of the whole product.
Repeat under isolated load and measure UI payload/layout separately before fixing
cross-machine or end-to-end budgets. Small sample size and concurrent coordinator
checks limit statistical precision.

The grouped `workspace_overview` initially repeated row metadata reads and reopened
Knowledge on every request. Request-scoped batching and reuse of the established
Knowledge handle remove that work. Freshness tests also cover writes indexed by
another handle, so cached projections refresh across clients. On the same private
copy, a final 10-call series had median 135.683 ms, first call 362.694 ms and
subsequent maximum 165.304 ms. All 152 representations and zero missing references
were retained. Earlier intermediate medians were 1654.454 and 1154.296 ms under
uncontrolled machine load; these are diagnostic samples, not a controlled speedup
claim or full UI acceptance. Raw samples remain git-excluded.

## Identity contract recommendation

S1 should create a persistent workspace identity independent of title/path and keep
the qualified legacy hub and original work references as aliases/provenance. A
work has one primary owner; multiple explicit legacy candidates require resolution.
Store source identity plus an actual revision when available, never a title-derived
revision. New work creation must consume the chosen workspace, while old history
stays in place. No title candidate in this preview is an automatic migration input.
