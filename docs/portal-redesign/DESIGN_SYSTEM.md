# Workspace design system

The interface serves a goal: read, learn or investigate. It opens with a conversational composer and knowledge
map. Five primary sections: Conversation, Learn, Research, Graph, Library. Workspaces are navigation tabs.
Model choice uses one expandable picker; graph lenses and relations use direct buttons instead of dropdowns.
Microphone capture requires a click, dictation stays an unsent draft, and Kokoro playback is an explicit control.

Dark blue charcoal background, pale blue ink, muted slate metadata, mint active controls. System UI for chrome;
Georgia for long reading text. An 8 px spacing grid, 44 px minimum controls, visible keyboard focus.
Use one semantic h1 per view and a 72-character reading measure. Secondary metadata stays compact.

Desktop: compact 208 px sidebar, flexible central workspace and optional 272 px context inspector. Every grid
child has `min-width: 0`. Inspector collapses into normal document flow at intermediate widths; on phones the
navigation becomes a collapsible block above the content. Nothing overlays the reading surface. The document
scrolls with the page; only long tables, code and math scroll horizontally within their own frames.

Heading anchors and document sections are keyboard linkable. The skip link targets the main workspace.
Context contains the document outline, original source information and typed incoming/outgoing references.
Empty, loading and error states have visible text; errors have a retry action. Saved UI preferences are best-effort
local browser state. They never become scientific evidence.

Graph relation labels and arrow direction remain visible; colour supplements text. Possible/inferred relations
must retain their provenance, never appear as verified evidence. A list provides a keyboard-accessible equivalent.
Respect reduced motion, wrap long titles/filenames, and keep figures next to their Markdown reference.
