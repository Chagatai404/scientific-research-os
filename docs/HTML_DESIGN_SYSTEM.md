# Research OS HTML design system (v2: Whiteboard & Chalkboard)

The HTML view is a scientific reading and practice environment. The source
template, authored section order, question definitions, session schema, review
rules and mastery rules remain unchanged. The renderer repairs malformed HTML
semantics; shared CSS and runtime controls provide the presentation.

## Reading shell

Two boards share one token set in `theme.css`. Light mode is the Whiteboard:
a warm off-white surface (#FBFAF6) on a desk tone, marker-dark ink and marker
blue/green/red accents, avoiding the glare of pure white. Dark mode is the
Chalkboard: green slate (#1E2A25) rather than black, with chalk-soft accents.
Every text pair meets WCAG AA (most AAA). The keyboard focus ring is amber in
both boards so it is never confused with blue selection. The host theme chooses
the board; there is no extra switch.

Reading prose uses Source Serif 4 (falling back to Georgia/Cambria) at 18px with
1.72 line height and an 840px measure. Controls and labels use Atkinson
Hyperlegible Next, designed for low-vision legibility, falling back to Segoe UI
and system faces. Both, plus Atkinson Hyperlegible Mono for code, are embedded
offline as Latin and Latin-Extended variable WOFF2 subsets (SIL OFL 1.1). Surfaces separate by tone rather than stacked borders and shadows.

Controls share one 44px height and 10px radius. The variant states the stakes:
filled blue for the one next step (Submit response, Send), outlined for optional
actions, text-only for low-stakes reveals and code copy, and red outline for
Clear response, which sits apart on the right of the action row.

The header holds only the title and optional subtitle; kind, status and date
badges are omitted. Save status is one quiet line in the progress row.
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

Tutor controls use whole-row choices with a letter key over the native input,
native input labels, visible keyboard focus, and one open question at a time.
Nothing asks for a dead click or a wait: the next hint button appears only after
the previous hint, Show solution appears only after an attempt, confidence is a
single-click 1–5 scale, and Clear response becomes Undo clear until the draft
changes again (no timers). Feedback follows the existing assessment
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

## v2 rollout (2026-10-10)

`html_design_rollout.py --apply` installed the v2 runtime, embedded fonts and
renderer helper into the shared vault runtime plus 32 skill bundles (33 runtime
locations, 165 files) and regenerated all 13 existing session HTML views. Session
Markdown, canonical JSON and the 37 vault template files were verified unchanged.
Replaced files and the hash manifest are kept under
`C:/Users/ASUS/.agent-hub/backups/html-design-v2-20261010`. The rollout accepts
installs matching `b473868` (the v0.8.5 design) as a known baseline.
