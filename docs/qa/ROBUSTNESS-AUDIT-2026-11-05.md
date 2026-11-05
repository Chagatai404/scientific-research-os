# Robustness audit: failures, crashes, network loss and agent reach (1.7.2)

Date: 2026-11-05. Audited code: `origin/main` at 93f2cd2 (the 1.7.2 release). Live evidence: the `knowledge` record and the
installed 1.7.2 backend.

## What started this

In the CENG487 Lecture 7 learn session, every `handout_check` call came back as "connection error (ECONNRESET)", so the
handout stayed a draft and never reached the vault. The agent reported it as a connection problem and told the person to
check the service. Running the check from the app would have failed the same way.

**Root cause (reproduced):**

1. Two free items on `capability:mathematics.linear-algebra` store `rubric` as a plain string, not `{"criteria": [...]}`.
   `add_item` accepts that shape. Only defence items are validated (`ros/tools/record.py:123`).
2. `handouts._hidden_strings` (`ros/handouts.py:398`) calls `.get("criteria")` on the rubric, so it raises `AttributeError`.
   `learn/tutor.py:110` would crash the same way when grading either item.
3. The session tool bridge (`ros/runtime.py:501`) catches only `ValueError`/`KeyError`. Any other exception ends the HTTP
   handler without a response, so Claude Code sees a dropped connection, not the error.

With the rubric read made tolerant, Lecture 7 **passes** the check (`ready: true`). The only warnings are "no PDF yet" and
"draft until you review it".

The 10:58 vault-sync error (`a handout key is letters, digits, dot, dash or underscore`, from `handouts.folder`) does not
reproduce against the current record. It is unrelated to Lecture 7.

## Findings

Severity: **H** = work stops or fails silently, **M** = wrong or misleading state, **L** = poor diagnostics.

### A. Unexpected exceptions become silent drops

| # | Sev | Where | What happens |
|---|-----|-------|--------------|
| A1 | H | `runtime.py:501` ToolBridge | Non-`ValueError`/`KeyError` exception: no response, connection reset. The agent sees `ECONNRESET` and blames the network. |
| A2 | H | `serve.py:442` `_tool` | Same pattern for every app request: one bad tool call drops the request. The traceback goes to stderr, which the shell discards. |
| A3 | H | `providers.py:164,270` (Codex, local) | Tool-call errors other than `ValueError`/`KeyError` escape the adapter and end the whole run as "The provider stopped unexpectedly". |
| A4 | H | `runtime.py:166-184` `execute` | Six record calls run before the `try` at line 278. If one raises, the thread dies, the run stays `queued`, its `ACTIVE` key is never released and the conversation shows "Working on your question…" until restart. |
| A5 | M | `runtime.py:338-345` | If `record_change` or `run_get` raises inside the error handler, the run is never marked failed. |
| A6 | H | `handouts.py:398`, `tutor.py:110`, `record.py` `add_item` | String rubrics are stored, then crash readers (the root cause above). |

### B. Crashes of whole processes

| # | Sev | Where | What happens |
|---|-----|-------|--------------|
| B1 | H | `desktop/main.cjs:97` | If the backend exits, the app shows one dialog ("Restart Research OS to reconnect"). It does not restart the backend. |
| B2 | H | `desktop/main.cjs:39` | Backend stderr is dropped and nothing writes a log file. After a crash there is nothing to read; this audit found no logs at all. |
| B3 | M | `runtime.py:447,476` Dispatcher, JobWorker | Their loop errors are kept in `self.errors` but never shown anywhere. |
| B4 | M | `runtime.py:67`, `providers.py:55` | Engine and provider subprocesses run with `stderr=DEVNULL`. Failures become generic text ("Engine failed or timed out", "Claude stopped before a terminal result"). |
| B5 | L | `runtime.py:49-54` `recover` | Recovery on start is sound: running runs, operations and notebook jobs are marked interrupted. It only happens on a full restart (see B1). |

### C. Network loss

| # | Sev | Where | What happens |
|---|-----|-------|--------------|
| C1 | H | `providers.py:58-75` `lines` | When the connection drops mid-reply, the stream goes quiet. The UI keeps "Working on your question…" for up to the full deadline (600 s) with no sign of trouble. |
| C2 | H | `providers.py:208` Claude | A failed result is always "Check CLI login, model availability or usage limit". The CLI's own reason (for example a connection error) is in the result event and is thrown away. |
| C3 | H | `providers.py:142` Codex | Any event with an `error` key ends the turn. Codex reports retryable stream disconnects as error notifications while it reconnects (to verify against the Codex app-server protocol), so a brief drop is fatal. |
| C4 | H | everywhere | There is no retry for a session turn, an agent task or a literature search. A failed turn needs the person to send again. |
| C5 | M | `frontend/src/App.tsx:170` | The offline banner uses `navigator.onLine`, which reports the network adapter, not internet reach. A lost upstream link with Wi-Fi still up shows nothing. |
| C6 | M | `dispatch.py` | An agent task that fails for network reasons counts toward the two-failure limit, so a short outage can park tasks as "failed twice". |

### D. The agent cannot reach tools it needs

A learn session gets `handout_check` but none of the tools that finish the job. Of 81 tools that are neither person-only
nor granted to any mode, these matter:

- **Delivery:** `handout_build`, `handout_attach`, `vault_sync`, `vault_note`, `vault_status`, `vault_review`. Without these
  the agent cannot put a handout in the vault ("I have no tool that builds a handout into the vault").
- **Reading the person's material:** `source_list`, `source_search`, `source_preview`, `source_children`, `source_capture`,
  `library_process`, `library_status`. This is why the agent could not read `CENG487_Fall_2026.pdf` or the
  Nielsen–Chuang file.
- **Seeing state:** `jobs`, `automation`, `doctor`, `agents_status`, `queue`, `workspace_activity`.
- **Preparation:** `bundle_voice`, `bundle_animate`, `precheck`, `reconcile`, `roadmap_tasks`, `cancel`.

The internal plumbing (`run_*`, `dispatch_*`, `session_*`, `operation_*`, `workbench_*`, `workspace_chat_*`) is correctly
excluded. The 27 person-only tools (approve, decide, waive, source and workspace management) stay person-only.

### E. Work left to the person that is not a decision

Requirement (from the researcher, 2026-11-05): the person makes decisions and learns. Checks, builds and renders are the
system's job.

| # | Today | Should be |
|---|-------|-----------|
| E1 | Handout check and build run only when someone calls them | The record checks and builds a handout as soon as it is written, then retries after fixes |
| E2 | "1 visual: it needs a shell to render and look at the picture" is left for the person | Rendered by the job worker or an agent with a shell |
| E3 | A handout stays a "draft until you mark it reviewed" | Reading it is learning, not a gate. It reaches the vault as soon as it passes the check, marked agent-written |
| E4 | Tasks "failed twice" sit silently | They are retried with backoff. Only a failure with a reason that needs a decision is shown, with that reason |

### F. Limits

| # | Sev | Where | What happens |
|---|-----|-------|--------------|
| F1 | M | `frontend/src/AgentSettings.tsx:12`, `dispatch.py:66` | Tasks per hour: the menu offers 3, 6, 12 or 30 (default 6); the backend caps it at 60. Agents run one at a time, 20–60 s per task, so 30 is used up in about 20 minutes. |
| F2 | M | `dispatch.py:57-58` | Per-task budgets: scout has 10 steps, a handout 24, a 900 s deadline. "Unfinished" outcomes count as failures, so a task that ran out of steps twice is parked. |
| F3 | M | `execution_limits` | Session context is 24,000 characters, output 4,096 tokens (about 24,000 characters, then "Output budget reached"), 40 tool steps, 600 s. |
| F4 | M | `dispatch.py` ledger | A task cancelled by app shutdown is recorded as `failed` (`task:6201f565589358da`: "cancelled"), so quitting the app counts against a task. |
| F5 | L | `dispatch_end` text | An "unfinished" task says "it is taken again later" even when it is now parked as "failed twice". |

### G. Other mismatches seen

- The `research-os` MCP server Claude Code uses runs from the local checkout `C:\Users\ASUS\scientific-research-os`, which
  is at 1.2.1 (`27df821`). The app and the records are at 1.7.2.
- The running app is the build installed under `C:\Users\ASUS\ros-install-test-13`.

## Fix plan

Each slice gets regression tests and is committed when its tests pass. The full release gate runs once, at the end.

1. **No silent drops (A1–A6).** Bridge, portal and adapters turn any exception into a readable error naming the tool and
   the error type, and log the traceback. `execute` covers its whole body. The error handler cannot leave a run open. A
   rubric is normalized on write and read tolerantly.
2. **Process supervision (B1–B4).** A rotating backend log under the profile folder. The shell restarts a backend that
   exits unexpectedly (bounded attempts, with backoff), and `recover` marks interrupted work. Worker and dispatcher errors
   and subprocess stderr tails are kept in the log and shown on the activity board.
3. **Network loss (C1–C6).** A stall watchdog shows "No response from the model for N s; retrying" on the run. The
   provider's real error text is kept. Retryable Codex notices pass through. Turns, agent tasks and literature searches
   retry with backoff on transport errors, and tell the person when they stop. A real reachability check backs the
   offline banner. Network failures do not count toward the two-failure limit.
4. **Agent reach (D).** Grant delivery, source reading and state tools to learn, research and build sessions and to the
   agent roles that need them. Person-only tools stay person-only.
5. **Nothing mechanical left for the person (E1–E4).** Check and build automatically after a handout is written. Render
   visuals in the job worker. Drop the review gate on vault delivery. Retry parked tasks.
6. **Limits (F1–F5).** Raise and widen the hourly choices, lift per-task budgets, stop counting shutdowns and "unfinished"
   as failures, and fix the misleading text.
