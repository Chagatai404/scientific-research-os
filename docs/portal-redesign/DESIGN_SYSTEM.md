# Workspace design system

The implemented graph landing follows the independent patterns in [REFERENCE_UI_SPEC.md](REFERENCE_UI_SPEC.md).
The reference-led plan tracks unfinished classroom, research and document work. No reference code or assets are reused.

The graph owns the first viewport. A compact question dock stays below its unobstructed region; camera fitting
uses the actual available canvas size. Navigation starts collapsed for new preferences and opens to a 232 px rail
on desktop or a drawer on phones. Horizontal workspace links replace a workspace dropdown. Top chrome occupies
64 px on desktop and 112 px on phones, including search. The previous hero and graph-below-form layout are removed.

The background is charcoal (`#121416`), raised surfaces `#1b1e22`, primary text `#edf0f3`, metadata `#adb5bf` and
the action accent `#93d8c5`. Proposed opaque text contrasts range from 8.08:1 to 16.14:1. Controls keep 44 px hit
targets and visible focus. System UI serves chrome, Georgia long reading text. Reading measure is 72 characters.

The knowledge lens uses compact circular nodes, thin arrows and stable connected-component regions. Grouping
is derived presentation, never a scientific relation. The research lens optionally shows directed lanes. Selected
edges expose type, direction and provenance; explicitly unverified edges are dashed. Zoom controls label density.
Mouse/touch drag, pointer zoom, fit and keyboard controls share one camera, retained per record/lens/focus.
The equivalent node list can select, focus and open the same entities. Selection/list panels reserve graph space,
scroll inside their bounds, receive keyboard focus and close with Escape back to the canvas.

The composer retains one model picker, dictation and reply audio, with a direct Send action. Voice readiness
reflects service availability. Recording/transcription blocks Send; transcripts stay editable drafts. Late transport
responses preserve newer edits. Drafts are scoped to record and session. Recent chat links are a bounded browser
index, not a complete server-side conversation archive.

Documents retain semantic headings, section anchors, sanitized AST Markdown/math and contextual references.
Phone document context uses a separate row so it cannot squeeze the reading column to a sliver. Wide tables,
code and math scroll inside their frames. Empty/loading/error states stay explicit; local preferences are never
scientific evidence. The old portal remains the complete compatibility route for human decisions and vault controls.

Known budget gap: first-party styles currently combine the baseline sheets with a graph-specific sheet and exceed
the intended compact stylesheet budget; production JS also retains a large combined chunk. Consolidation and
dependency splitting remain hardening work. A passing visual matrix does not establish payload-budget compliance.
