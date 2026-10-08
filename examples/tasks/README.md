# Durable task orchestration example

This is a synthetic manual workflow, not scientific evidence or a live provider
integration. `demo.py` builds byte-hash bindings from local files at run time so
Git newline settings cannot make the example stale. It writes nothing without
`--output`. Generated plans should be placed only in a selected temporary project.

```powershell
python -S -B examples/tasks/demo.py --root examples/tasks
```

For a disposable project, copy this directory, then run the generator with that
directory as root and `--output plan.json`. Use these commands from the repository
(substitute the absolute temporary path for `<project>`):

```text
python -S -B scripts/tasks.py --root <project> plan --input plan.json
python -S -B scripts/tasks.py --root <project> plan --input plan.json --apply
python -S -B scripts/tasks.py --root <project> ready
python -S -B scripts/tasks.py --root <project> start scout
python -S -B scripts/tasks.py --root <project> start verify
python -S -B scripts/tasks.py --root <project> start visual
python -S -B scripts/tasks.py --root <project> status
```

The parent may continue unrelated prerequisite preparation while these records are
RUNNING. The built-in manual adapter launches no process: `start` returns the bounded
handoff and canonical job handle for explicit separate execution by the owner.
Other provider IDs remain BLOCKED unless the host registers an adapter through the
Python API. No automatic substitution, agent login, arbitrary command execution,
permanent daemon or hidden experiment is installed.

Deliver a confined JSON result with exactly:

```json
{
  "task_result_schema": 1,
  "task_id": "verify",
  "attempt": 1,
  "handle": "job-<handle returned by start/status>",
  "execution": "completed",
  "stopped": true,
  "reported_by": "Execution owner",
  "context_exposure": {
    "mode": "bounded",
    "input_paths": ["claim.txt", "source.txt"],
    "notes": "Actual exposure; no scout rationale or coordinator history."
  },
  "artifact_refs": []
}
```

Then `collect verify --result verify-result.json`. The manual execution owner must
actually confirm the attempt stopped; provider adapters must acknowledge stopping
before collection. `execution: failed` records failure without affecting unrelated
results. Output refs are `{path, sha256, kind: "artifact"}`. Collection snapshots
the bounded result and outputs into `.research-tasks/artifacts/<task>/<attempt>/`.
The canonical task refs point at those immutable snapshots; the original wrapper
preserves its exact delivered bytes and original artifact declarations. Consult
canonical `artifact_refs` for saved copies. Reusing delivery filenames on retry
does not erase prior attempts. Hashes detect later tampering; files are not an ACL.

`cancel <id>` keeps a running task and its writer reservation until stop is
acknowledged. For manual execution only, the owner may use
`reconcile <id> --acknowledge-stopped` or `cancel <id> --acknowledge-stopped`.
A stale timestamp never proves stopping. `retry <id>` archives a stopped FAILED/
CANCELLED attempt and rechecks all gates; `start` launches the new attempt with a
new job handle. Changed inputs require restoring the immutable version or planning
a new task ID. Replan never silently edits existing tasks. Limit: 100 tasks, 20
attempts/history entries, 30 refs per list, 2 MiB JSON and 50 MiB per bound artifact.

Provider API: pass `providers={"name": adapter}` to `plan`/`operate`. An adapter
implements `launch(handle, packet)` (idempotent by canonical handle, return promptly),
`status(handle)` (running/complete/failed/stopped/unknown), and `cancel(handle)`
(True only after stopping is acknowledged). It owns detached execution, restart
lookup and private handles outside this store. A launch error retains RUNNING intent;
reconcile the canonical handle before retrying. Tests use a fake detached adapter,
not real Codex/Claude background infrastructure. Status does not automatically collect
or cancel work. Raw provider diagnostics never enter canonical results/logs.

Writers additionally require an isolated existing Git worktree with absolute path,
branch and commit baseline, a recorded human approval bound to the task/stage,
presented plan, exact write/run scope and workspace. The worktree must belong to
the project repository and match branch/HEAD; the main project directory is rejected.
Running/cancel-requested writers reserve both workspace and branch. `.git` and
`.research-tasks` are excluded from task-owned write paths.
An exclusive `.research-task-writer.lock` in the selected worktree also rejects
another store's writer; its job/owner must match before release. Never delete it
merely because it looks old. Git branch ownership must be unique. Programs that
ignore the lock are outside this cooperative guard. Create worktrees through
the host's normal authorized workflow, not this helper. The CLI never performs
scientific writes/runs itself; provider and human execution must enforce the packet's
scope. An approval record is a human attestation, not cryptographic proof of its author.

COMPLETE means collected execution artifacts. It never creates evidence receipts,
mastery or research acceptance. Stage 8 needs a completed source-verifier dependency
and bound valid EXACT_SUPPORT/TRANSFERRED EvidenceAtoms, with all derivation inputs;
TRANSFERRED remains qualified. Use the literature checker for factual/qualified
synthesis and conflict/access controls. Stage 7 requires external discovery dependency.
Stage 14/15 and any scientific write/run require current human approval, rechecked
before start, collection and retry. These structural gates cannot decide whether all
scientifically necessary dependencies were declared; the coordinator remains responsible
for completeness, interpretation, minimal context and approval authenticity.

The store uses an exclusive update lock and atomic state replacement, not a multi-file
transaction. A crash can leave a lock or partial snapshots. Review actual execution
and state before repairing locks; never automatically clear a stale RUNNING writer.
The helper cannot stop out-of-band writers or prove that prose labeled as a source
contains no scout rationale. Context declarations are attestations, not independence
proof. Never put secrets or raw provider sessions into plans, results or artifacts.
