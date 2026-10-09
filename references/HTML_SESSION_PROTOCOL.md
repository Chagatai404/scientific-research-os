# HTML-native session authoring (v0.8.5)

Every new substantive tutoring, course, research, literature, review, experiment
analysis, retention, methodology, planning or decision session must have sibling
HTML and structured state artifacts. Ordinary paper/concept/evidence/research
records and source files remain their existing formats; a record is not a session.
Use `scripts/html_sessions.py` as the centralized creation/update/migration API.
Run its `--help` for exact commands. Use the configured vault or an explicitly
chosen local workspace; do not invent a second untracked output convention.
Validate the session inventory before declaring a session complete. Missing HTML
is an error; archival exceptions must be machine-readable and appear in the report.

## Ownership and synchronization

Session JSON owns authored content and browser event history. HTML and the Markdown
bridge are projections. Keep original Markdown path, frontmatter, body, wikilinks
and heading anchors for search/backlinks/Excalidraw. Do not edit generated HTML.
Central updates verify bridge hashes and reject conflicting manual changes; import
reviewed bridge edits explicitly. Browser events are append-only raw progress.
Read unresolved questions and actual answers from state before resuming; preserve
the separate tutor checkpoint declaration and its diagnostic budget/return points.
Never overwrite user answers or silently regenerate state from HTML.

Canonical learning schemas 1/2/3 and retention.py still own capability evidence,
mastery, freshness, retention choices and scheduling. Browser recognition scores,
confidence or completed controls are not reviewed reconstruction/transfer evidence.
Review actual reasoning and assistance through the existing learning protocol before
adding ledger attempts. Never fabricate learning history or promote permanent notes.
EvidenceAtoms, exact citations, provenance and research decisions stay authoritative.

## Teaching and interaction

Use this sequence: objectives/prerequisite recall → foundations → intuition →
mathematics → useful exploration → conceptual checkpoint → method/tool execution →
project application → transfer → retention/summary. Teach how the work is performed.
Ask one question at a time and preserve the existing diagnostic budget. Keep expected
answers and answer-position plans out of the learner-facing question. Solutions are
revealed only after a meaningful attempt or explicit learner request. Local scoring
is pedagogical feedback, not secure examination; offline answer keys are inspectable.
Learners can interrupt through open-question capture without spending probe budget.
No renderer-initiated external AI calls, background grading or paid-model dependency.

Use semantic components for definitions, derivations, evidence, code/output, warnings,
decisions and uncertainties. Include precise source locators. Match visual interaction
to learning value; mark schematic/model-driven demonstrations and assumptions. Do
not portray illustrative mathematics as experimentally validated simulation data.
Preserve literal LaTeX; report unsupported syntax instead of changing an expression.

## Obsidian and fallback

Install the companion plugin and shared runtime using the documented installer.
Markdown bridges use a `ros-session` code block to embed their HTML. Sessions run
inside opaque-origin sandboxed iframes; the renderer receives no Obsidian, filesystem,
Node or Electron APIs. Only narrowly validated progress events cross the host bridge.
Missing plugin/runtime must produce actionable setup instructions, not fake success.
Desktop verification and mobile verification are separate gates. Mobile stays gated
until tested on an actual device. Standalone export is offline and announces the
absence of vault persistence; exported progress requires an explicit user export.

Legacy Markdown checkbox submission remains a compatibility fallback. Explicit
submission is required; never infer completion from idle timers or modification
timestamps. Update projections through the central API and retain chronology.

## Migration

Inventory and dry-run before applying. Back up exact bytes with a versioned manifest.
Convert only discovered session records. Preserve original content, links, equations,
answers, confidence prose and decisions without inferring missing relationships.
Uncertain structures remain legacy components and conversion warnings. Retry safely;
rollback must refuse to discard subsequent edits. A fixture migration is not proof
that the user's actual vault has been migrated.
