# Computer work: adapters, grants and evidence (S8C design gate)

Status: design only, written 2026-11-10 against `a9640da` plus the S7 work then in progress (since committed as `947ca01`). No code
exists for anything below. Every capability status here is **planned** or, after implementation, starts as
**declared**. Nothing is tested or live-verified until the tests in the last section pass. Spec:
`.plans/core-experience-spec.md` §4, "Bilgisayarımda bir işi yap", and §5, "Bilgisayar eylemi". Boundary row:
`THREAT-MODEL.md`, "Computer adapter to user files/apps". Once reviewed, the schemas land in `CONTRACTS.md`, as that
document already reserves for S8C.

## 1. What the person gets

The person can say "Copy this course's PDFs to the folder I chose and open the summary note in the other app". The
work is placed in the right workspace (§7). The agent turns the request into a **computer plan** with concrete real
paths, app identities and operation classes. The plan is authorised once (§3). After that a **deterministic executor**
carries it out step by step, without asking again. Success is judged by re-reading the files and the app state, never
by the agent's message.

Core decision: **a plan is data, and the executor is not a model.** A model proposes, revises and explains plans. It
never holds a file handle, a shell or a click loop. Every effect comes from fixed Research OS code that checks the
grant before each action. This keeps prompt injection (file names, document text, UI labels, web pages) out of the
effect path.

## 2. Adapter order and host choice (decided)

| Order | Adapter | Mechanism | Host | v1 status |
|---|---|---|---|---|
| a | Service connector | The service's own API, through the profile and credential-reference rules of S4 | `ros/lib/<service>.py` engine, outbound class | **None in v1.** Capability discovery reports "no connector for X". Any connector that sends, publishes or spends is outbound and needs a decision. |
| b | File operations | Python standard library: `os`, `shutil.copyfileobj`, `hashlib`, plus `ctypes` for `GetFinalPathNameByHandleW` and the Recycle Bin | New engine `ros/lib/fileops.py`. It runs through the existing operation path: `execution` queue, `runtime.execute_operation`, `engine_process`, `ros.lib.desktop_operations` (frozen: `--worker operation`, so no new allowlist entry) | planned |
| c1 | Open a document with a named app | `CreateProcessW` with the pinned exe and exactly one quoted document argument. The default association (`os.startfile`) is used only when the plan said "default app", the handler resolved at plan time (`AssocQueryStringW`) is unchanged, and the type is allow-listed. | `ros/lib/winui.py` engine, same worker path | planned |
| c2 | Act inside another app | **Windows UI Automation through `ctypes` COM** (`CUIAutomation`): `ElementFromHandle`, `FindFirst` on AutomationId/Name/ControlType, then the Invoke, Value, Text (read-only), Toggle, SelectionItem, ExpandCollapse and Window patterns. No coordinate clicks, no `SendInput` keystrokes, no screenshots. | `ros/lib/winui.py`, one engine call per step | planned |
| — | The provider's own computer use (Codex `computer_use`, a Claude Code computer-use MCP) | — | — | **unsupported in v1** |

Why c2 is UI Automation through `ctypes` and not the alternatives:

| Option | New dependency | Policy enforced per action | Data leaving the computer | Testable with a fixture | Verdict |
|---|---|---|---|---|---|
| `ctypes` UI Automation in our worker | none (same style as `appcontainer.py`) | yes: the executor checks each step | none (no pixels) | yes: a WinForms fixture | **chosen** |
| PowerShell plus .NET `UIAutomationClient` | none, but a second runtime | yes | none | yes | rejected: fails under Constrained Language Mode or AppLocker, a script surface, slow start per step |
| pywinauto / comtypes | heavy, third-party | yes | none | yes | rejected: AGENTS.md rule 5 |
| Delegating to Codex or Claude computer use | none | **no**: their click loop is outside our checks | screenshots go to the cloud | no | rejected for v1. Codex runs already switch `computer_use` off (`CODEX_MINIMAL_CONFIG`). Enabling it is a person's choice (§11). |

Shell or Code mode is never the computer adapter. A Code session's own Bash, Read and Write tools stay inside
`record_repo` under `NEVER_RUN`, and nothing there counts as an S8C grant. The engines are optional (ARCHITECTURE "An engine"). `winui.available()` returns `(ok, reason)`, as
`appcontainer.available()` does. When it fails (not Windows, UI Automation missing, no desktop session), app steps stay
blocked with a plain reason and nothing falls back to blind input. File steps are portable. The Python CLI and MCP keep
working on every OS, with `computer_capabilities` reporting app control as `unsupported`.

The file worker is **not** run in an AppContainer. The code is ours, not model-written. An AppContainer could only
reach the person's folders if their DACLs were changed, and changing the security descriptors of real user folders is
a worse harm. Real-path validation and handle checks (§4) are the boundary instead.

## 3. Permission contract

### Authority: only these create a grant

1. **Plan approval.** The human tool `computer_approve(plan, revision, decision, remember=false)` binds one plan
   revision. One approval covers every step, retry and resume of that revision.
2. **Structured request.** The human tool `computer_grant(workspace_id, roots, apps, ops, outbound=[])` is called by the
   desktop "Do on my computer" form. Paths and app executables come from the native picker (a new IPC
   `computer:pick`, modelled on `source:pick`). When the person submits the form, that **is** the grant: the person's
   explicit request is the authority and no preview approval follows. A plan inside it starts at once.
3. **Standing grant.** `remember=true` on approval, or the form's "for this workspace" option. Later plans in the same
   workspace whose scope is a subset of it run without asking.

All three are `human=True`. They are never offered over MCP; the CLI confirms them at the terminal; the portal requires
the desktop credential or pairing token plus CSRF. **Chat text never grants anything on any interface.** Over MCP "the
person's message" is just the agent's text. An external client gets the portal link to the plan, the existing trusted
handoff. Revocation: human `computer_revoke(grant)`.

### What a grant binds

`ComputerGrant = {schema: "ros.computer-grant.v1", id, workspace_id, plan?: {id, revision}, roots: [{path, volume_serial,
file_id, access: "read"|"write"}], apps: [AppIdentity], ops: [...], outbound: [{kind, target}], via: "approval"|"form"|"standing",
actor: "person"}`.

- **Roots** are real, local, absolute folders or files, resolved with `strict=True` when granted. A network share is
  refused (`home.local_path`). The root itself must not be a reparse point. Volume serial plus file id pin it, so a
  folder later replaced by a junction with the same name no longer matches. `AppData`, dot folders, `.git`, secrets
  and the Research OS home are refused as roots or inside roots. The same exclusions as `sources` apply.
- **Op classes:** `inspect` (metadata), `copy`, `move`, `rename`, `mkdir`, `open_with`, `app_edit`, `trash`
  (Recycle Bin), `replace` (overwrite, with a backup), and `outbound`, `delete_permanent` and `spend`. The last three
  are never implied. The user decision allows them when they are explicitly in scope. **The proposal for v1** ships no
  executor for `delete_permanent` or `spend`: they are refused with "needs your decision; not supported yet", and
  `trash` serves as the interim. That narrows the fixed decision, so it is the person's call (§11).
- **`AppIdentity`:** `{kind: "win32", image: <real exe path>, version: <file version>, size, mtime}` or
  `{kind: "packaged", family: <package family name>}`. App families classed as mail, chat, browser, uploader or
  installer carry `outbound: true` and need an outbound grant even for `open_with`.
- **Outbound** covers connectors that send or publish, app steps that invoke a Send, Publish, Share or Buy element, and
  copy or move destinations under a synced root. Synced roots are any path under `%OneDrive%`/`%OneDriveCommercial%`
  or carrying a cloud-files reparse tag. Copying or moving a local-only source's file anywhere outbound is refused, as
  `runtime.source_refusal` already does for cloud reads.

### Plans and revisions

The agent tool `computer_plan(workspace_id, request_ref, steps, plan?)` appends `computer.plan` with
`revision = sha256(canonical {workspace_id, steps, derived scope})`. The derived scope is the union of the steps'
roots, apps, ops and outbound. The result's `status` is `authorized` (a live grant covers the scope),
`awaiting_approval` (it returns a preview: each step in plain words, irreversible steps labelled, and a diff against the
covering grant), or `refused` (structural errors, §4). Re-planning after a failure produces a new revision. If it is
still a subset of the grant it runs without asking; if it widens, it waits. Restarting or retrying never widens.

### The check before every action (executor, not model)

Before each step, the executor checks, inside `runtime._run_action` (cancellation is serialised with effects): the run
is live and not cancelled; the plan revision is unchanged; the grant exists and is not revoked, and the workspace
matches; the op is in the grant; every real path (re-resolved now) lies under a granted root whose volume serial and
file id still match; the app identity matches; the outbound class is granted; the step's idempotency key is not
already terminal. Any failure stops that step with a typed reason (§8). There is no partial authority.

### Narrowing and injection

- A new mode, `computer`, gets `computer_capabilities`, `computer_inspect`, `computer_plan`, `computer_run` and
  `computer_status`, plus the base reads and workspace identity reads. No other mode receives them; in particular
  research, learn, chat and build infer no filesystem or app grant.
- `computer` is **non-native** (`native=False`). It runs with the existing no-built-in-tools provider configuration:
  Claude with `--tools ''`, Codex with the private `CODEX_HOME` and `computer_use`/`shell_tool` off. Without that,
  Claude Code's own Read and Write tools would bypass the grants.
- A custom agent with `base: mode:computer` can only drop tools, for example an inspect-only agent. It cannot add roots,
  because manifests have no authority fields. The human tools are in the registry's human set, so manifests refuse them.
- File names, folder listings and UI Automation names are returned with `"untrusted": true` and are data. Nothing they
  say changes a plan's scope. Only a person's act does that.

## 4. File-operation semantics (`ros/lib/fileops.py`)

**Path resolution.** Every path is checked component by component under its root with `os.lstat`. Any symlink,
junction or other reparse point in any component is **refused, never followed**. This reuses
`renderkit.is_link` logic, copied into the engine because lib modules stay independent, and it includes OneDrive cloud
placeholders, which are reparse points. After opening, the executor compares `os.fstat(fd)` ino/dev with the pre-open
`lstat`, and `GetFinalPathNameByHandleW` with the validated real path. This closes the race between check and use. The
executor also refuses: `..`, alternate data streams (`:`), `\\?\`, device names, trailing dots or spaces, and names
starting with `-` or `/` in an app argument.

**Collisions.** The default `on_collision: "stop"` applies. An existing destination is never overwritten. If the
destination already holds identical bytes (equal SHA-256), the step records `skipped_identical` and writes nothing.
`on_collision: "rename"` writes `name (2).ext` and so on, chosen deterministically at plan time and shown in the
preview. `replace` only with the `replace` op. Before replacing, the old file is moved to
`<home>/computer/undo/<action>/`.

**Same-name files.** `computer_plan` refuses a plan in which two steps target the same final path. The agent must pick
`rename`, or distinct destinations, before anything runs.

**Commit without overwrite.** Data is first written to `<dst-dir>/.ros-partial-<key>`. That name is deterministic from
the idempotency key. The executor writes, then `fsync`s, then verifies the destination hash against the hash computed
while reading the source. Commit uses **`os.rename` on Windows** (it refuses an existing target) and **`os.link` plus
`unlink` of the partial on POSIX**. `os.replace`, `shutil.move` and `shutil.copy*` are never used for the commit. That
rule is the overwrite guarantee, and a test greps for it.

**Moves.** On one volume, a file move is one atomic no-replace phase. On Windows that is `os.rename`. On POSIX, where
`os.rename` silently overwrites, it is `os.link(src, dst)` followed by `unlink(src)`. Across volumes: (1) stage, verify and
commit the destination; (2) re-check the source fingerprint (size, `mtime_ns`, file id, and the hash computed during
the copy); (3) remove the source only if the fingerprint is unchanged. The source is never removed before a verified
destination exists. A changed source leaves both files in place, and the step is marked `source_changed`.

**Changed source.** The fingerprint is taken before reading, and size, mtime and file id are re-stat'ed after reading.
Any difference discards the partial file and fails the step with `source_changed`.

**Full disk and permissions.** `shutil.disk_usage` must show the source size plus 1% headroom before staging.
`ENOSPC` or `EACCES` partway through removes our own partial file and fails with `disk_full` or `access_denied`. The
source is untouched. Elevation is never requested.

**Execution unit (one model, decided).** `computer_run(plan, revision)` queues **one** operation of kind
`computer_exec` per attempt. Its id is `computer-exec:<plan>@<revision>#<attempt>`, written with `append_once` (today
`operation_queue` uses uuid4 and `rec.append`, so P1 adds a keyed variant). `attempt` is 1 plus the number of earlier
units for that revision. A new attempt is allowed only when the previous one is terminal (`interrupted`, `failed` or
cancelled). Two clients racing compute the same id, and one wins. A model retry (the `a2:`-scoped tool operations)
returns the existing unit. The Coordinator runs the unit on one thread. Its worker runs the steps **in order**, each as
one `engine_process` call with `parent_entry`. Step N+1 starts only after step N is `verified` or `skipped_identical`.

**Step idempotency** lives in the action events and the filesystem, not in the operation id. The key is
`key = sha256(workspace_id | plan_id | revision | step_id)`, and phase events use
`event_id('computer-action', key + phase)`. A new attempt skips steps that are already terminal and reconciles
unfinished ones (below). `operation_start` refusing a non-queued operation therefore never blocks a resume, because a
resume is a new unit.

**Cancellation.** The human `computer_cancel(exec)` appends `computer.cancelled` for the unit. As with `run_cancel`, the
Coordinator also sets the unit's `ACTIVE` cancel event and kills the current engine child. The executor checks for
`computer.cancelled` before every step under a record-scoped action lock (`_computer_action`, mirroring
`_run_action`). Other processes therefore observe the cancellation before their next effect.

**Directories** are expanded at plan time into per-file steps (`mkdir` plus a file op per entry, then removal of
emptied source folders for a move). Each entry is link-checked. A plan over 2,000 entries is refused with "split this
task". A directory is never moved as one opaque unit.

**Committed but unrecorded.** The worker cannot write the record, because lib does not import domain. A kill after the
rename but before the worker returns would otherwise leave a commit nobody recorded. Reconciliation therefore reads
the filesystem, not only the journal. Before acting, every resume and `runtime.recover` checks the step's
deterministic names. A lone partial file is deleted (we created it) and the step is `interrupted`; a destination with
the expected hash but no recorded commit is recorded `committed`; a cross-volume move with a committed destination and
an unchanged source continues to source removal. `recover` must not apply its generic "interrupted" message to computer operations without this reconciliation.

**Engine budget.** Each action is one `engine_process` call. Its timeout is
`30 s + size / 20 MB/s`, capped at 30 min, replacing the fixed `timeout + 15`. Actions hold the global `ENGINE_WORKER`
lock, so a large copy serialises with PDF rendering and web operations. That is accepted in v1 and shown as "waiting
for another engine". Cancelling kills the worker. Reconciliation then runs as described above.

**Undo information** is recorded per action: copy, the created file goes to the Recycle Bin; move, move back if the
origin is free; rename, rename back; mkdir, remove if empty; replace, restore the backup; trash, restore from the
Recycle Bin, best effort, labelled `partial`. The human tool `computer_undo(action)` runs the inverse as a new action through the same executor. Every preview and
result says `reversible: true|partial|false`. Outbound, `delete_permanent` and spend are `false`.

**Operation results are worker-only.** Add the computer operation kinds to `execution.WORKER_ONLY`, so no client can
finish one with a forged "verified" result through the public `operation_finish`.

## 5. App-control semantics (`ros/lib/winui.py`)

**Open-with restrictions** match the desktop's own `source:open` rules. Refused types: executables, scripts,
shortcuts, `.lnk`, `.url`, `.hta`, `.msi`, `.ps1`, `.bat`, `.cmd`, `.js`, `.vbs`, `.reg`, `.scr` and `.cpl`. The
document argument is a single quoted real path that has passed the §4 checks. The exe is the pinned identity. The
default-association route only works for allow-listed document types.

**Window identity.** A process launched from a granted identity is bound by: pid and process creation time; the image
path (`QueryFullProcessImageNameW`) or the package family (`GetPackageFamilyName`); the top-level HWND and window
class; a title that contains the document's base name. Single-instance apps that hand off to an existing process are re-bound by identity plus title, never by focus. Two
matching windows are ambiguous: stop and ask.

**Preconditions.** Before each step the executor checks: the identity is still bound and the HWND is alive; the target
element is found under that HWND, and its process id equals the bound pid; a state fingerprint (window title, the
sha256 of the target element's value, the document's size, mtime and file id) equals the one expected after the
previous step. Focus is never required, because patterns act on elements. Coordinates and keystrokes are not used.

**User interference.** A fingerprint mismatch means the person or the app changed something. The executor re-reads the
state once, records `needs_attention` with what differs (hashes and names, not values), and stops. It never retries
blindly and never loops clicking. Continuing requires a new plan revision, which runs without asking if it stays
inside the grant.

**Invoke** is allowed only on the elements recorded in the approved plan step: AutomationId, Name and ControlType must
all match. An element whose name or class marks it as Send, Publish, Share, Buy or Upload is outbound, and needs the
outbound class.

**Before an in-place edit**, the executor copies the document into `<home>/computer/undo/<action>/`, so the edit is
reversible as `partial`.

**Verification comes from the saved file, not the UI.** After the plan's Save element is invoked, the executor waits up
to N s for the document's mtime and size to change, then evaluates the plan's predicate locally. The predicates are
`file_changed`, `sha256_equals`, `text_contains` (`.txt`, `.md`, `.csv`, UTF-8 or UTF-16) and `docx_text_contains`
(`zipfile` plus XML). The result is a boolean plus the new hash. It also confirms that the file at the **granted path**
changed, and that no new file appeared in the folder (no "save as" elsewhere). A save to a synced root is outbound.

**Cancel and resume.** Cancel stops between UI Automation calls. A single pattern call is atomic from our side. The
app is left open and is never killed: closing it could discard the person's work. Resume re-binds the identity,
re-checks the preconditions and continues from the first step that is not `verified`.

## 6. Evidence: what is recorded and what is never recorded

**Recorded** in the workspace's physical record, as append-only events: plan and revision; grant id and actor; each
step's op, real paths, volume serial and file ids; sizes, before/after SHA-256 and mtimes; phase transitions and the
decision refs; app identity, window class, element AutomationId, Name and ControlType; verification predicate results,
reversibility and undo location. The `computer.action` events are the only per-step evidence. The conversation's run
step for `computer_run` holds just the unit id, and `computer_status` reads the action events. `backend.log` carries
ids and error classes only.

**Never recorded:** file contents, UI Automation values or text, screenshots, clipboard, keystrokes, full UI trees.
Text that a plan writes through ValuePattern is document content. It is stored once as a content-addressed item in the
person's own record and referenced by hash. Run steps, logs and model results carry its hash and length only.
`computer_inspect` returns names, sizes and mtimes, never contents. For a cloud model, listings under a local-only
connection's root are refused, as `source_refusal` does. Nothing in `ros/tools/computer.py` reads connected files or the
network, so the existing `tests/test_ros_source_grants.py` scan keeps passing.

## 7. Workspace placement (AC18)

A computer task belongs to the selected workspace. If none is selected, `workspace_identity_resolve` runs on the
request's explicit course or project reference. If nothing resolves, the task goes to `ws:general-work:workspace`.
`ambiguous` returns the short choice and creates nothing. A computer task never creates a course or project.

**Routing from the same entry.** Requests start in the ordinary entry box. They reach computer work in one of two
ways:

- The entry offers a "Do on my computer" action, which is the form of §3.
- `engage` gains a director kind and playbook, `computer`. It resolves the workspace as described above and opens or
  reuses a `computer`-mode conversation there through the existing conversation path. It returns that conversation's
  link.

A chat, learn or research session that hears a computer request calls `engage`, which it is already granted. Those
sessions never receive computer tools themselves.

General work exists only after the human `workspace_ensure(kind="general")`. The first human computer act whose
workspace resolves to General (form submit or plan approval) calls it idempotently. Agents never create it. An MCP
proposal made while it does not exist returns `missing` with the portal link. Plans, grants and actions live in
`identity.record`.

## 8. Tools, events and errors

**Agent tools** (`ros/tools/computer.py`, "Tools for computer work"):

| Tool | Writes | Notes |
|---|---|---|
| `computer_capabilities` | no | adapters and app identities with declared, tested, live-verified or unsupported status, and the reason |
| `computer_inspect(workspace_id, root, path?, app?)` | no | metadata inside granted or attached roots, or a bounded element list of a bound window |
| `computer_plan` | yes | |
| `computer_run(plan, revision)` | yes | queues one `computer_exec` unit (§4) and returns its id; a plan that is `awaiting_approval` is refused |
| `computer_status(plan|run)` | no | |

**Human tools:** `computer_approve`, `computer_grant`, `computer_revoke`, `computer_undo` and `computer_cancel` (§4).

**Events.** All go in `references/DATA_MODEL.md`: `computer.plan`; `computer.grant`; `computer.grant.revoked`;
`computer.cancelled`; `computer.action` (the phase is one of
`queued|started|staged|committed|source_removed|verified|skipped_identical|failed|interrupted|needs_attention|undone`).

**Schemas:** `ros.computer-plan.v1` (steps `{id, op, src?, dst?, app?, element?, value_item?, on_collision, verify}`),
`ros.computer-grant.v1`, `ros.computer-action.v1`, `ros.computer-capabilities.v1`.

**Errors** are `ValueError` with a `code`: `scope_denied`, `stale_plan`, `grant_revoked`, `path_link_refused`, `path_outside_root`, `collision`, `source_changed`,
`disk_full`, `access_denied`, `app_identity_mismatch`, `window_ambiguous`, `needs_attention`, `outbound_not_granted`,
`unsupported_op`, `capability_missing`.

## 9. Implementation packets

S7 (`947ca01`, committed while this design was written) owns `ros/dispatch.py`, `ros/research.py`, `ros/tasks.py`,
`ros/tools/research.py`, `frontend/src/Research.tsx` and `frontend/src/ActivityBoard.tsx`. **Neither packet touches
them.** Before dispatch, check its plan gate and `research_control` for a reusable plan-revision helper. There is no new
dispatch task kind in v1; execution is the coordinator operation path. The research `approve` tool is not reused,
because it is experiment-specific.

**P1: grants, plans, file executor, mode** (high reasoning). Owns `ros/computer.py` (domain: plan and grant folds,
scope check, keys, reconciliation decisions); `ros/lib/fileops.py`; `ros/lib/desktop_operations.py` (adds
`computer_file` and `computer_app` kinds, lazy import of `winui`); `ros/execution.py` (keyed `operation_queue`,
`WORKER_ONLY`); `ros/runtime.py` (the `computer_exec` step loop reached from `execute_operation`, the
`_computer_action` lock and per-action check, the Coordinator cancel branch, size timeout, `recover` reconciliation);
`ros/director.py` (the `computer` playbook, §7); `ros/tools/computer.py`; `ros/api.py` (import);
`ros/modes.py` (`Mode("computer", ..., native=False)`); `skills/computer/SKILL.md`; `references/DATA_MODEL.md`,
`CONTRACTS.md` (S8C section), `docs/ARCHITECTURE.md` (recipe "A computer action"), this file's status, `README.md`,
`CHANGELOG.md`; tests `tests/test_ros_computer_files.py`, `tests/test_ros_computer_grants.py`,
`tests/test_ros_computer_workspace.py`, plus updates to `tests/test_architecture.py` (new domain module),
`tests/test_ros_sessions.py` (new mode) and `tests/test_ros_m6.py` (skill and doc names).

**P2: app control and the desktop surface** (high for `winui`, medium for UI; starts after P1 merges). Owns
`ros/lib/winui.py`; `desktop/main.cjs` and `desktop/preload.cjs` (`computer:pick` IPC); the new
`frontend/src/ComputerWork.tsx` (form, plan preview card, evidence and undo list) and its test, plus one route or
link line in the conversation view agreed with the coordinator after S7 lands; `tests/fixtures/computer/editor-fixture.ps1`
(a WinForms TextBox plus Save button, built into Windows); `tests/test_ros_computer_app.py`;
`tests/computer_native_smoke.py`; the matching documentation lines.

## 10. Test plan

### AC17 file fixtures (P1)

These run hermetically: `ROS_NO_VAULT=1`, a temporary `ROS_HOME`, disposable folders and a fake provider.

| Case | Expected result |
|---|---|
| Two `notes.pdf` from different folders into one destination | The plan is refused without `rename`. With `rename`, both arrive, hashes match and nothing is overwritten. |
| Move into an existing destination | Stops with `collision`. Source and destination bytes are unchanged and no partial file is left. |
| A junction (`_winapi.CreateJunction`) or symlink in a source, destination or root component | `path_link_refused`. Root replaced by a junction with the same name: refused by file id. |
| Source modified by a test seam between pre-stat and post-stat | `source_changed`; no destination file. |
| `ENOSPC` seam | `disk_full`; source intact. |
| Cancel after step 1 | Step 2 never starts. Resume runs only step 2, and file and event counts show no double copy. |
| Worker killed after commit, before it returns, and again before source removal in a cross-volume move (seam) | `recover` reconciles. Resume completes. The file is never absent from both places. |
| Same key queued twice through CLI, MCP and HTTP | One effect. |
| Path outside root, op not granted, stale revision, revoked grant, workspace mismatch | All refused. |
| A file named like an instruction to widen the grant | No scope change. |
| MCP tool list | Has no human computer tool. |
| A manifest that holds `computer_approve` | Refused. |
| A `computer` mode turn | Has no built-in provider tools (Claude argv, Codex config fixture). |
| Destination under a fake `%OneDrive%` | `outbound_not_granted`. |
| `replace` | Refused without the op. With it: backup created, undo restores. |
| Undo of copy and move | Works. |
| Sentinel text written into source files | Never appears in events, run steps or logs. |
| A grep test over `fileops.py` | `os.replace`, `shutil.move` and `shutil.copy` are absent, and every `os.rename` is inside an `os.name == 'nt'` branch. A POSIX fixture shows a same-volume move refusing an existing target. |
| Two clients call `computer_run` at once; resume after an interrupt | One unit per attempt. The resume is a new attempt that skips verified steps. |
| A folder copy containing a junction entry | The plan is refused at expansion. |
| `operation_finish` from a client on a computer operation | Refused. |

### AC17 app fixtures (P2)

These run on Windows only, as a local gate that skips with a reason when no interactive desktop is available.

| Case | Expected result |
|---|---|
| Open the editor fixture through `open_with` with its pinned identity, set the value, invoke Save | `text_contains` verified from the file. |
| The test changes the TextBox between steps | `needs_attention`. No further calls. |
| A second fixture instance with the same title | `window_ambiguous`. |
| Fixture closed | Precondition fails. |
| Cancel mid-plan, then resume | Continues correctly. |
| An element named "Send" not in the plan | Refused. |
| Refused type (`.lnk`, `.ps1`) or an argument starting with `-` | Refused. |
| Disallowed app identity | Refused. |

### AC18 (P1)

Three unrelated tasks through CLI, MCP and HTTP on three fixed-clock days all land in `ws:general-work:workspace` and
no new record appears; a STAT303-related task with STAT303 selected lands in STAT303's record; an ambiguous request
creates nothing.

### Native smoke (P2)

The smoke is separately permitted and run only with `ROS_COMPUTER_NATIVE_SMOKE=1`. It records `live-verified` only for
the exact adapter and app version it ran. The person must explicitly grant:

(1) running it on their real desktop session, which opens windows and visibly changes the screen; (2) the **app** to
drive: Windows 11 Notepad is only a candidate (packaged, tabs, autosave, may not expose ValuePattern), others are Word,
LibreOffice or an editor of their choice; (3) a **disposable root**, created by the smoke and checked local, because
Desktop and Documents may be redirected to OneDrive; (4) **no outbound** class; (5) optionally one real document,
otherwise copies only.

## 11. Choices that belong to the person

1. Which app, and which version of it, the native smoke drives (item 2 above). Until then app control is only
   fixture-tested.
2. Whether provider computer use (Codex or Claude) may ever be enabled as a later, opt-in adapter. It sends screenshots
   to the provider and bypasses per-action checks. The recommendation is no for v1.
3. Whether the standing "for this workspace" grant should expire. The proposal is no expiry, revocable at any time in
   Settings.
4. Whether v1 may ship without an executor for `delete_permanent` and `spend`, with `trash` as the interim (§3). The
   fixed decision allows both when they are explicitly in scope. Adding them later means a preview that is always
   labelled irreversible, plus a per-plan grant.
