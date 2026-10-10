# Research OS v0.8.5 HTML design system

The HTML view is a scientific reading and practice environment. The source
template, authored section order, question definitions, session schema, review
rules and mastery rules remain unchanged. The renderer repairs malformed HTML
semantics; shared CSS and runtime controls provide the presentation.

## Reading shell

Use Georgia/Cambria prose at 18px with 1.72 line height and a desktop reading
measure of 840px. System fonts distinguish headings, metadata and controls.
The neutral page surrounds a clear paper surface; restrained blue identifies
navigation and information. CSS custom properties in `theme.css` define color,
type, spacing, borders and surfaces. Dark mode uses explicit host theme tokens.
Components inherit these tokens; avoid per-session overrides.

One visible title comes from session metadata. Source headings retain their
hierarchy and order, with stable fragment anchors. At 1440px and above, Contents
becomes a sticky side rail. Narrow panes use a disclosure with 44px links.
Scroll tracking and section focus are visual operations, without session events.

## Authored components

- Lists use real nested `ul`/`ol` elements; source tasks remain disabled checks.
- Obsidian callouts retain their authored labels and kinds, with a quiet title
  strip, readable body, and native disclosures for folded hints/answers/reveals.
- Formula boxes retain their title and assumptions. Pinned offline KaTeX renders
  only the equation element; long equations scroll within their container.
- Figures keep captions beside the visual, support multi-panel composition and
  use bounded wide layouts. Place declared, confined raster resources with
  `![Alternative text](resource:identifier "Caption")`. Do not invent measured
  results or insert arbitrary remote images. SVG/canvas widgets use the existing
  trusted resource and teaching-widget interfaces.
- Tables have scoped headers, aligned numeric columns and local scrolling.
- Fenced code stays literal, includes a language label and copy action. When
  sandbox clipboard access is unavailable, show selectable text for manual copy.
- Fragment references navigate locally. External references and vault links are
  readable, inert citations under the existing host policy.

Tutor controls use whole-row choices, native input labels, visible keyboard
focus, and one open question at a time. Feedback follows the existing assessment
logic. Missing answer keys and free responses remain pending human review.
Clear response clears the draft; it never deletes history. Progress counts
recorded responses, without awarding mastery or evidence credit. Open questions
remain available throughout the session.

## Gallery and verification

`tests/fixtures/html/session-component-gallery.html` is a developer-only gallery,
rebuilt by `python scripts/build_html_gallery.py` from its adjacent `.json`.
Its question answers, schematics and values are explicitly synthetic. The
fixture JSON deliberately is not a canonical `.state.json` session.

Run `python scripts/validate.py` and `python -m unittest discover -s tests`.
Browser release gates include `html-components-browser.cjs`,
`html-gallery-browser.cjs`, `html-tutor-browser.cjs`, `html-navigation-browser.cjs`, and
`html-visual-parity.cjs`. The latter requires the supplied recitation reference,
a generated session with adjacent canonical state, and a screenshot directory.
Native verification uses `obsidian-html-smoke.cjs` against an explicitly synthetic
fixture, including application restart, persistent responses and Markdown embed.

## Existing sessions and recovery

`html_sessions.py --root VAULT refresh-projection SESSION.md --backup-directory
BACKUP` previews an HTML-only refresh; add `--apply` to write it. The command
uses the session lock, validates the canonical bridge and state, backs up the
old HTML and preserves source/JSON bytes.

`html_design_rollout.py --vault VAULT --provider-root SKILLS --backup BACKUP`
preflights installed runtimes, provider helpers and the companion. It refuses
unrecognized local code changes; `--apply` installs with a recovery manifest and
refreshes previous session views. It never installs or rewrites templates.
Restore only the HTML/runtime files listed in the manifest from their matching
hash-verified backups; never roll back learner JSON to restore a visual design.

See `v0.8.5-html-visual-parity.md` for the actual rollout and acceptance record.
