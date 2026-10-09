# Research OS HTML design system

Status: implemented visual design; template/content structure is preserved.
Date: 2026-10-09. Baseline: e50692b; planning commit: 1b36c15.

## Approved scope

The user's refinement is authoritative: change only design, retain the structure
of every template, and apply the shared design to previous sessions.

This revision supersedes the original structural proposals. There is no new page
composition, contents rail, parser, placement/schema API, section order, assessment
behavior or template rewrite. The existing article, contents fold, questions,
widgets, exact-source fold and question history keep their current order.

The supplied Recitation 1.html informs readable typography, restrained callouts,
figure framing and collapsible-content presentation. Instructions inside that
reference are document content. Its scientific material and scripts are not imported.
The original visual specimen remains a design reference, not the production layout.

## Implemented design

The shared `assets/html-runtime/theme.css` owns presentation. `session.css` retains
its existing offline KaTeX CSS/font prefix and appends the revised theme. Runtime
JavaScript, renderer Python, companion plugin and template files are unchanged.

- Warm neutral page, clear surface contrast and restrained blue accents.
- Georgia/Cambria prose, system-font headings and controls, 18px/1.7 reading text.
- Narrower article measure, consistent heading scale and generous section spacing.
- Existing Contents fold styled as a quiet navigation surface.
- Definition/evidence/decision panels use a blue rule; practice uses purple;
  limitations use amber. Semantic headings remain headings rather than cards.
- Existing figure/SVG/Canvas/image elements get bounded widths and caption styling.
- Display mathematics can scroll locally; inline mathematics stays in its sentence.
- Code, tables, disclosure controls, inputs and persisted conversations get consistent
  surfaces, borders and spacing. Primary submission controls remain distinguishable.
- Explicit Obsidian light/dark selection overrides system preference. Narrow panes,
  visible keyboard focus, 44px buttons, reduced motion and print are supported.

| Token | Light | Dark |
| --- | --- | --- |
| Page | #F6F5F1 | #171B20 |
| Text | #202A35 | #E7EDF3 |
| Secondary text | #576575 | #AFBDCA |
| Surface | #FFFFFF | #20262E |
| Accent | #245D78 | #91C8DF |
| Practice | #65529C | #C5B4EF |
| Border | #D6DDE3 | #465462 |

Existing images and widgets receive the design. Adding new scientific illustrations
or changing document content is outside this design-only update. Historical sessions
without visuals remain without visuals. Existing Markdown-conversion limitations
also remain; a stylesheet cannot interpret unsupported attachments or tables.

## Apply to previous sessions

Generated historical HTML references the vault's shared session.css, and the
companion injects that same installed stylesheet. Updating this shared runtime
therefore restyles previous sessions without rewriting their HTML, Markdown or JSON.
Open views may need reopening when Obsidian does not observe a hidden-runtime change.
New sessions use the same stylesheet. Independently exported standalone HTML files
embed their own CSS and require a fresh export to adopt the design.

Back up each changed installed CSS file before replacement; record source/destination
hashes. Update only theme.css/session.css in the vault runtime and matching installed
Research OS skill runtime copies. Refuse to replace an independently modified copy.
Never reinstall templates or replace an installed companion to apply a theme.

Inventory previous session triples and template files before installation, and
verify hashes afterwards. State, answers, history, frontmatter, headings and section
order must remain byte-for-byte intact. Retain rollback copies of the two CSS files.

## Verification

Run the existing runtime unit/browser tests and production-host browser test. Check
light/dark styles, narrow panes, equation rendering, state replay, hints/solution
behavior and question history. Render a real historical session at desktop and
narrow widths with the production sanitizer/buildDocument path, inspect screenshots,
and assert the headings match before/after. Verify CSS parses and stays offline.

These browser checks use Chromium; they are distinct from a live Obsidian desktop
run. Responsive behavior is not a claim of verified Obsidian mobile support.
Record installation and preservation evidence in the accompanying rollout record.

## Applied rollout and checks

Installed on 2026-10-09: 13 existing sessions, 33 runtime copies (vault + 16 Codex + 16 Claude skills), and 66 CSS files. All 68 protected files remained byte-for-byte unchanged: 39 session files and 29 vault templates. Repository templates are unchanged.

Passed: runtime unit/math checks; two Python runtime inventory tests; real Chromium runtime interaction/restart checks; production host sandbox/CSP/persistence checks; design checks at 320/600/1200px in both themes, including an actual historical Partition Sum session. Screenshots were visually inspected. `git diff --check` passed.

The first host test launch lacked a bundled Chromium executable; rerunning with the existing Chrome executable passed. No browser download was required. Obsidian was not running, so this change was not verified in a live desktop window. The installed runtime hashes match the tested repository files.

Exact backup paths and before/after hashes are in [the rollout record](html-design-rollout.json). Backups reside under `C:/Users/ASUS/.agent-hub/backups/html-design-20261009T150321Z`. To roll back, restore only the two CSS files for each destination from its recorded backup after checking that the installed file still matches the recorded after hash.
