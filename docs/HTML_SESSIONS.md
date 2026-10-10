# HTML-native research sessions

This implementation provides v0.8.5. Release readiness is recorded in
[the implementation plan](plans/v0.8.5-html-native-sessions.md); `VERSION` changes
only after the required gates pass. Core scientific workflows remain provider-neutral.

## Files and ownership

An existing `topic.md` gains `topic.html` and `topic.state.json`. JSON owns authored
content, question declarations and raw interaction history. HTML is generated.
Markdown retains the complete source and a `ros-session` embed for Obsidian search,
backlinks, graph relationships, headings and compatibility with earlier helpers.
Canonical capability ledgers, EvidenceAtoms, research records, tutor checkpoint
declarations and retention calculations retain their own schemas and ownership.
Browser feedback never grants mastery, delayed retention or scientific acceptance.

Create/update through the API. Direct bridge edits cause a conflict; the explicit
import operation backs up reviewed edits. A failed projection write leaves a recovery
journal; recovery refuses to overwrite subsequent user changes. Each writer uses
the same exclusive `<topic>.session.lock`; an abandoned lock requires inspecting
the interrupted writer before manually removing it. Never remove an active lock.

## Setup

From a configured repository:

```powershell
python scripts/install.py --html-companion
```

This stages the companion under `.obsidian/plugins/research-os-html` and the pinned
runtime under `.research-os/runtime`. Enable **Research OS HTML Sessions** in
Obsidian's Community plugins settings. Existing plugin/runtime conflicts stop the
installer; back up and explicitly replace reviewed versions. The HTML companion is
desktop-only. It does not change other enabled plugins or require a cloud service.

`install.py --target codex` or `--target claude` bundles the same central session
helper and runtime with every workflow skill. Installation updates those skill
directories with an overlay that preserves extra files and backs up replaced files.
The user's current installed agent bundles are separate from the repository and
must be updated intentionally. No paid model or essential remote CDN is required.

## Authoring

Use the existing `vault.py new` command for installed templates; all session
templates now route through the HTML API. Manual Obsidian template insertion alone
is incomplete and fails validation. Non-session notes keep their existing formats.

```powershell
python scripts/html_sessions.py --root "C:/path/to/vault" create "Sessions/Lesson.md" --source prepared.md
python scripts/html_sessions.py --root "C:/path/to/vault" update "Sessions/Lesson.md" --source revised.md
python scripts/html_sessions.py --root "C:/path/to/vault" append "Sessions/Lesson.md" --source next-entry.md
python scripts/html_sessions.py --root "C:/path/to/vault" validate
```

The Python API supports structured questions and widgets without writing JavaScript:

```python
from pathlib import Path
from html_sessions import create_session, install_runtime, update_session

root = Path("C:/path/to/vault")
install_runtime(root)
create_session(root, "Sessions/Velocity.md", prepared_markdown,
    questions=[{
        "id": "velocity-1", "kind": "numeric", "prompt": "Compute velocity",
        "answer": 3, "tolerance": 0.1, "units": "m/s",
        "hints": ["Divide displacement by elapsed time."],
        "solution": "Use the stated displacement and time, with consistent units."
    }], widgets=[{"id": "vector-demo", "kind": "vector"}])
```

Prepared answers must be scientifically verified. They are inspectable offline;
solution reveal gates support teaching rather than exam secrecy. Free responses
await human assessment. Numeric tolerances are absolute and units are exact labels;
the renderer never silently converts units. Source frontmatter and structured
metadata must agree; change lifecycle/status through an explicit source update.

Follow [the authoring protocol](../references/HTML_SESSION_PROTOCOL.md). Theory,
intuition and mathematics precede methods/tools and project application. Keep one
active question at a time, balanced hidden MCQ positions, actual reasoning,
assistance, diagnostic budgets, transfer and human promotion gates.

## Components and mathematics

The [runtime reference](../assets/html-runtime/README.md) documents semantic
`data-ros` components, six assessment formats, hints, solutions, confidence,
checkpoints, open questions and extensions. Content supports definitions,
derivations, evidence, decisions, warning callouts and code/output panels.
Research templates cover literature/evidence, adversarial review, experiment
analysis, methodology, planning, hypotheses and retrospectives.

KaTeX 0.16.22 and embedded WOFF2 fonts are bundled with license and source hashes.
Inline/display LaTeX, matrices, aligned equations, subscripts, Greek notation and
numbered `\tag` equations use the original expression. Unsupported syntax visibly
falls back to literal TeX. Quoted Obsidian formula callouts are recognized.
Session contents navigation uses derived local heading anchors.

Sampling and vector widgets show stated analytic models using accessible controls,
SVG and Canvas. They are demonstrations, not validated simulations or experimental
data. More elaborate visualizations require reviewed local extensions.

## State and open questions

Schema 1 stores stable identity/type, source/metadata, questions, events,
open questions, lifecycle/timestamps, widgets and approved resource declarations.
Events have unique bounded IDs and one of `response`, `hint`, `solution`,
`confidence`, `checkpoint`, `reset`, `open-question`. Replayed duplicate IDs do not
append another answer. Events are `pending-review`; confidence is not correctness.
Open-question records include session, available concept, prompt, timestamp, open
status and later explanation references. No renderer makes an external AI call.

Inspect `topic.state.json` to resume, or use `load_session()`/`append_event()`.
The runtime restores actual responses, hints and confidence from persisted events.
Existing tutoring return points remain in the separate tutor checkpoint payload.
Review real reasoning before adding canonical learning-ledger attempts and then use
the existing retention tooling. This preserves the previous retention semantics.

## Security and local extensions

The host sanitizes authored markup and inserts a CSP before content. The iframe
has `sandbox="allow-scripts"` without same-origin, form, popup or navigation
permissions for the parent. The iframe receives no Obsidian, filesystem, Node or
Electron API. Messages require the exact frame window, a per-load token and session
identity. The host accepts bounded progress events, not arbitrary file operations.
Agent markup cannot supply executable script/style tags, handlers or remote URLs.

Resources are confined to `<topic>.assets/` or the runtime extension folder.
PNG/JPEG/WebP images are signature-checked and inlined. SVG diagrams use sanitized
markup; SVG image files and arbitrary historical attachments are retained through
the Markdown bridge rather than automatically executed or imported.
Local `.js` modules require a declared SHA-256 plus a matching independently
reviewed entry in `.research-os/runtime/extensions/trusted-modules.json`:

```json
{"Sessions/Velocity.assets/plot.js": "<reviewed 64-character SHA-256>"}
```

A session cannot approve its own module. Approved modules run in the iframe and
may register a runtime component. CSP blocks resource fetching/imports, but a
sandbox cannot guarantee that malicious trusted code never navigates its own frame.
Review executable modules before approving hashes; this is a deliberate trust
boundary, not a claim of absolute network isolation for arbitrary code.
Symlink paths, traversal, hidden-vault reads and mutable hash mismatches fail closed.

## Migration, reports and recovery

```powershell
python scripts/html_sessions.py --root "C:/path/to/vault" inventory
python scripts/html_sessions.py --root "C:/path/to/vault" migrate
python scripts/html_sessions.py --root "C:/path/to/vault" migrate --apply
python scripts/html_sessions.py --root "C:/path/to/vault" migrate --resume
python scripts/html_sessions.py --root "C:/path/to/vault" migrate --rollback
```

Dry-run is the default. Metadata, directories, identities and structural markers
identify candidates; explicit ordinary-note types override incidental mentions of
sessions. Ambiguous notes require review. Templates and implementation docs are
excluded. Backups/manifest/report live under `.research-os/migrations/v0.8.5`.
Original bytes are retained. The manifest records source/output hashes and recovery
instructions. Retry verifies unchanged files; rollback refuses later edits.
If a new historical batch appears after completion, use a new `--journal` path.

Conservative conversion recognizes headings, code, math and known callouts. Explicit
legacy active questions with learner answer slots can become free-response
components without inferred grades. Uncertain pairings, historical solutions,
Markdown tables, wikilinks and unsupported attachments remain visibly preserved
source; the bridge retains their native Obsidian behavior. No missing answers or
historical learning achievements are invented. This limitation appears in the
conversion report and does not alter scientific conclusions.

An explicit exception manifest `.research-os/session-exceptions.json` uses schema 1
and `exceptions:[{path,kind,reason}]`; kind is `imported-archive` or
`pending-migration`. Inventory reports exceptions. They must never silently excuse
a newly generated session. The repository's one historical compatibility fixture
is reported as an archive by its validator.

```powershell
python scripts/html_sessions.py --root "C:/path/to/vault" import "Sessions/Lesson.md"
python scripts/html_sessions.py --root "C:/path/to/vault" import "Sessions/Lesson.md" --apply
python scripts/html_sessions.py --root "C:/path/to/vault" recover "Sessions/Lesson.md"
python scripts/html_sessions.py --root "C:/path/to/vault" recover "Sessions/Lesson.md" --apply
```

Moving/renaming an artifact invalidates its active view with an explicit repair
message. Move the trio and update embed references together; automated trio rename
is not implemented. Existing historical Markdown paths remain unchanged.

## Export and troubleshooting

```powershell
python scripts/html_sessions.py --root "C:/path/to/vault" export "Sessions/Lesson.md" "C:/new/path/Lesson.html"
```

Export inlines runtime, fonts and approved resources. Existing destinations are
never overwritten. Standalone pages clearly announce that vault persistence is
unavailable and offer a progress JSON download; browser storage is not authoritative.

If a view reports missing runtime, stage it with the installer. Hidden runtime paths
use confined adapter reads, because Obsidian does not index dot directories as
TFiles. Content-hash watchers reload actual runtime changes; access-time events
must not regenerate the iframe. The **Reload HTML sessions and trusted resources**
command provides a manual fallback. Missing state/schema/resource and save errors
are explicit. Keep unsaved progress open and use **Show progress JSON to copy** before repairing a failure.

Required verification: Python tests, host Node tests, real Chromium runtime/host
tests, actual-vault source/hash checks and the explicit desktop operational smoke
test. Responsive browser checks do not establish actual mobile support.

## Live tutoring

Open views update in place when the agent writes: no reload, drafts and scroll kept.
`html_sessions.py context SESSION` prints the resume brief (pending learner activity,
project note, research graph and knowledge graph state); read it before resuming.
`add-question SESSION --source q.json` posts one question at the current end of the
session; `wait SESSION` blocks until an explicit Submit or Send; `review SESSION ID
--verdict ... --feedback f.txt [--transcript t.md] [--next-question q.json]` records
the check that replaces the learner's "Checking…" with the verdict and explanation.
See [the protocol](../references/HTML_SESSION_PROTOCOL.md) for the full loop.

Open questions use an inline **Send** button and chronological question/answer history below the composer. Send records for the session agent; it does not call an AI service. Read `open_questions`, answer the actual prompt, then use `answer_open_question(root, session, question_id, answer)` or `html_sessions.py --root VAULT answer SESSION QUESTION_ID --source answer.txt`. This preserves earlier answers and pending questions without awarding learning evidence. Reopening restores the recorded conversation.
