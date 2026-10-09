# Research OS HTML design system

Status: proposed design and implementation plan; no production runtime changes.
Date: 2026-10-09. Inspected baseline: e50692b (v0.8.5).
Companion: [visual specimen](html-design-system-preview.html).

## Direction

Research OS sessions should feel like carefully prepared scientific recitations:
a calm article, clear conceptual progression, figures beside the explanation they
support, and questions with progressive hints and worked solutions. Reading is the
primary activity. Controls support reading without turning every paragraph into a
dashboard card.

Use one shared system across tutor, course, literature, methodology, experiment,
review, hypothesis, planning and decision sessions. Adapt section names and content
to the session; do not force every mode into a quiz template.

This is a proposal, not evidence that the current rendering issue has been fixed.
The exact desktop failure still needs reproduction during implementation.

## Evidence and reference interpretation

The supplied `C:/Users/ASUS/Downloads/Recitation 1.html` is a self-contained Quarto
article titled STAT 365 - Recitation 1. It contains six embedded images, successive
sampling explanations, mathematical notation, comparison material, inline
understanding checks, and collapsible answers. Its document instructions are
reference content, not authorization to run scripts or answer its exercises.

Adopt its local sequence: explanation → illustration/example → question → optional
answer. Adopt its self-contained reading experience and restrained callouts.
Improve its skipped heading levels, justified paragraphs and image accessibility;
do not copy its university branding, subject matter, Bootstrap bundle or quiz code.
A persistent contents rail is a proposed improvement, not a claimed feature of the
reference. Rebuild interactions with Research OS's existing state semantics.

Observed in the current repository:

| Area | Current behavior | Design consequence |
| --- | --- | --- |
| `scripts/html_sessions.py::markdown_html` | Lists become individual divs containing their markers; blockquotes are emitted line by line; no dedicated table/image/link parsing | A CSS refresh cannot repair the document structure |
| `_inline` | Supports inline TeX, code and bold through a small converter | Specify supported Markdown explicitly and add semantic conversion fixtures |
| `render_html` | Concatenates prose, then all questions, then all widgets; export resources follow | Explanations and their exercises/visuals lose proximity |
| Heading anchors | Derived from heading text alone | Repeated headings can produce duplicate IDs |
| `assets/html-runtime/theme.css` | Many semantic components use the same bordered blue panel; prose can approach 960px | Visual hierarchy needs stronger differentiation and a narrower reading measure |
| Obsidian host | Removes author styles/scripts and undeclared image sources; injects installed runtime | Session-local CSS or pasted Quarto HTML cannot supply the design system |
| Image resources | PNG/JPEG/WebP declarations and placeholders are supported; unused images are appended | Authors need explicit placement, descriptive captions and validated resources |
| Navigation | Local fragment links survive sanitizer; other links are inert | Internal navigation is feasible; clickable external citations need mediated host support |

Three sampled real historical states under AMS ECAL QML/Tutor Sessions (FastMC
Block 6, FastMC Block 7, and Block 6A Teach-Back) each have zero declared questions,
widgets and resources. This establishes an authoring gap in those samples, not a
vault-wide finding. The previous migration deliberately preserved uncertain
structures; do not infer new figures or answer keys from historical prose.

Git worktree/history were inspected. This checkout was clean and detached at
e50692b before creating `agent/codex/html-design-system-plan`. `.agent-hub` contains
backups, with no visible live ownership registry. Other worktrees exist; no other
agent's changes were integrated. Primary checkout status could not be read under
the sandbox, so its active uncommitted ownership remains unknown. This plan changes
only new documentation files in the isolated worktree. No Research OS project note
was found in the narrow Obsidian project inventory; no permanent decision is recorded.

## Page composition

```text
Session title, type, date and concise purpose
Objectives and prerequisite links
────────────────────────────────────────────────────────────
Contents rail       Main article (reading measure: 68ch)
                    1. Foundation / research question
                    2. Intuition + relevant figure
                    3. Formal statement / assumptions
                    4. Worked example / derivation
                    5. Exploration + conceptual checkpoint
                    6. Method + project application
                    7. Transfer / interpretation / limitations
                    8. Summary + next step + sources
────────────────────────────────────────────────────────────
Ask a question · chronological answers · technical source fold
```

Use one h1, h2 for major sections, and h3 for local examples. Metadata uses small
text, never heading levels. Avoid a duplicate title copied from source Markdown.
Allocate durable section IDs; retain existing IDs or aliases during regeneration.
Use collision-safe IDs for repeated headings. Do not navigate by mutable heading
text alone. Contents reflects h2/h3 hierarchy and excludes controls and hidden keys.

At viewport/container widths of at least 1100px, use a 200px contents rail, a 40px
gap, and a 68ch article. Below that, put collapsible Contents above the article.
Base the breakpoint on the iframe's available width; a wide monitor may contain a
narrow Obsidian split pane. Avoid a second decorative sidebar. Use the iframe as
the reading scroll surface with sticky navigation scoped to it; test embed height
and nested scrolling separately before changing host sizing.

Figures can expand to 900px within the document shell when detail needs it.
Paragraphs retain the 68ch measure. At 320px, only equations, tables or code may
scroll horizontally inside their own containers; the document must not overflow.

## Tokens

These are proposed values. Verify contrast and long-session comfort before freezing.
Use system fonts offline; a font download must never be required for reading.

| Token | Light | Dark / rule |
| --- | --- | --- |
| Page | `#F6F5F1` | `#171B20` |
| Surface | `#FFFFFF` | `#20262E` |
| Text | `#202A35` | `#E7EDF3` |
| Secondary text | `#576575` | `#AFBDCA` |
| Border | `#D6DDE3` | `#465462` |
| Primary accent | `#245D78` | `#91C8DF` |
| Practice accent | `#65529C` | `#C5B4EF` |
| Caution accent | `#875A12` | `#EAC37A` |
| Positive feedback | `#28634E` | `#8ED0B3` |
| Error | `#A23434` | `#F3A1A1` |
| Prose | Georgia, Cambria, serif; 18px / 1.7 | Optional system sans reading preference |
| Headings and UI | system-ui, Segoe UI, sans-serif | h1 36/1.15, h2 26/1.25, h3 21/1.35 |
| Caption / metadata | system sans, 14px / 1.5 | Essential instructions at least 16px |
| Code | Consolas, ui-monospace, monospace; 14px / 1.6 | Preserve whitespace |
| Spacing | 4, 8, 12, 16, 24, 32, 48, 64px | Section gap 48px; paragraph gap 16px |
| Radius | 6px controls, 8px callouts/figures | No pill-shaped article containers |
| Focus | 3px accent outline, 3px offset | Visible for every interactive element |

Use flat surfaces, fine rules, minimal shadows, and text labels in addition to
color. Color distinguishes role, not arbitrary section number. Inherit Obsidian's
light/dark selection through the existing host bridge. Match plots and SVG labels
to the same tokens, with distinct line styles/markers where color matters.

## Component contract

| Component | Presentation and behavior |
| --- | --- |
| Ordinary explanation | Unboxed prose; lists, emphasis and links render semantically |
| Definition | Short labeled block with one restrained accent rule; ordinary concept discussion stays unboxed |
| Intuition | Prose and adjacent diagram; short takeaway beneath the figure |
| Equation | Original TeX, bounded horizontal scroll, optional stable number; nearby symbol definitions and assumptions |
| Derivation | Numbered logical steps with equations and reasons; optional detail fold after essential steps |
| Worked example | Labeled scenario, givens, reasoning and result; visually lighter than practice |
| Figure | Number/title, embedded visual, caption, provenance and accessible explanation |
| Exploration | Controls, live value, explanatory graphic and model assumptions; static fallback visible without JS |
| Practice | Purple label, short prompt, input, primary Check answer/Save response, secondary hints and solution |
| Evidence | Claim, source locator, evidence status and uncertainty; status is supplied by canonical records |
| Warning / limitation | Amber label and concise consequence; do not hide scientifically material caveats |
| Code and output | Separate labeled panels; code can fold, result and interpretation remain visible |
| Decision | Context, proposed/accepted status, rationale and alternatives from recorded facts |
| Sources | Ordered, precise locators with readable URLs; link interaction matches host capabilities |
| Ask a question | Preserve inline Send and persisted chronological conversation; show pending/answered status plainly |

Hints reveal progressively. A worked example's reasoning can be open by default;
an assessment solution keeps the existing meaningful-attempt gate. Support explicit
learner-request reveal only through a designed, tested action consistent with the
authoring protocol. Never include a supposedly hidden answer in the visible label.
Use one active diagnostic question at a time without forbidding access to completed
material. Keyboard focus stays predictable when revealing content.

Feedback distinguishes correct, incorrect, pending human review, and save failure.
Show saving/saved/error states without claiming mastery. Browser feedback and
confidence never update canonical capability or scientific acceptance records.
Historical free-text answers remain visible; structured assessments cannot be
retroactively invented. Preserve hints, responses, question history and return points.

## Visual authoring standard

Every substantive session gets a visual review during authoring. For topics with
geometry, relationships, distributions, processes or parameter dependence, include
at least one useful embedded visual. For a purely textual session, record why a
visual adds no value. Do not require ornamental images or pad every section.

Choose the simplest faithful representation:

1. Inline sanitized SVG for geometry, conceptual relationships and small diagrams.
2. Locally generated PNG/WebP plots for data, uncertainty, model comparison or
   publication output; embed using declared resource IDs.
3. Existing runtime widgets when changing a parameter clarifies a relationship.
4. New reviewed local runtime extensions only when simpler forms cannot explain it.

Place each figure directly after its first explanatory reference. Its caption states
what to observe, units, conditions, and whether it is a schematic, analytic model,
simulation or observed data. Data plots link to source/run provenance and distinguish
uncertainty from decorative shading. Do not fabricate experimental curves.

SVG has a meaningful accessible name and adjacent long description where needed.
Canvas and interactive charts have a numerical/text equivalent. Controls have units,
bounded values, reset and an interpretable output. Avoid hover-only explanations.
Complex visuals include a static snapshot for offline export and print.

Keep existing confinement and image budgets: 32 resource files, 2 MiB per raster
image, 8 MiB total resources. Use `data-resource-id` for images, not arbitrary `src`.
Do not expand allowed URL schemes or script privileges to accommodate the example.
Pasted raw SVG in Markdown is not currently a supported authoring path; implement
an explicit validated figure declaration/placement API rather than assuming it works.

## Rendering and authoring architecture

Keep JSON canonical and Markdown/HTML as projections through the central API.
Adopt a constrained, documented Markdown parser with semantic lists, tables,
emphasis and links, plus an explicit Obsidian adapter for callouts, wikilinks and
attachments. Evaluate a pinned parser against offline installation and dependency
policy in Phase 1; do not grow an ad hoc regex parser into a general HTML engine.
Raw executable HTML remains unsupported. Unknown syntax remains readable with a
specific conversion warning and access to exact source.

Introduce explicit placement references for question/widget/figure IDs in the
authored document. Resolve them into semantic components in document order.
Preserve existing IDs and event payloads. Unplaced legacy items remain in a clearly
labeled supplementary section. Validate missing IDs, duplicate placements, unknown
resource IDs and nonmatching declarations. No automatic inference of relationships.

Proposed state additions: a versioned presentation/placement contract and structured
figure descriptions, including caption and provenance. Final field names and schema
version require a compatibility review; reject unsupported versions visibly. A
preview flag can compare old/new rendering without rewriting state. Avoid a second
independent copy of authored prose or answers in a new blocks array.

Shared tokens/components belong in editable `theme.css` and `runtime.js`; rebuild
`session.css` and `session.js` with the existing KaTeX build process. Apply the same
renderer and runtime to the dedicated view, Markdown embed and standalone export.
Host-only frame sizing/status belongs in the companion stylesheet.

Citation navigation needs an explicit host-mediated link protocol. Local anchors
already survive sanitization. Until mediation is implemented, expose external
citations as readable/copyable URLs instead of styling inert text as working links.
Keep CSP, module trust, filesystem confinement and authenticated state messages.

Update `references/HTML_SESSION_PROTOCOL.md`, session templates and relevant skill
authoring guidance so agents author figures, placement, semantic sections, source
locators and a visual review by default. Reinstalling the shared runtime alone will
not add missing figures to existing content.

## Implementation sequence and acceptance gates

| Phase | Work and likely files | Gate |
| --- | --- | --- |
| 0. Reproduce | Actual affected session, installed runtime/companion, dedicated view and embed; inspect errors and compare export | A documented reproducer and categorized failures, including missing assets versus unsupported syntax |
| 1. Semantic rendering | `scripts/html_sessions.py`, parser dependency policy, HTML session fixtures | Nested lists, tables, grouped callouts, images, links, duplicate headings and TeX preserve meaning; malicious inputs still fail safely |
| 2. Composition | Versioned placement/figure API, central validation and deterministic export | Questions/visuals render beside their explanation; old states and existing events replay without loss |
| 3. Visual system | `theme.css`, `runtime.js`, rebuilt bundles, companion sizing | Approved specimen matches dedicated view/embed/export in light/dark and narrow panes |
| 4. Authoring | Protocol, templates, workflow guidance, examples | Fresh tutor and research sessions include appropriate inline visuals with captions/provenance and real sources |
| 5. Interaction/accessibility | Contents, reveal controls, save feedback, mediated citations | Keyboard navigation, focus, contrast, reduced motion, fallback and print pass; state survives reopen |
| 6. Rollout | Versioned backups, inventory, dry-run and selected session conversion, installer docs | Real-vault verification, safe retry/rollback, retained answers/source/history; release gates documented |

Start with one new tutor lesson and one new experiment/review specimen. Then refresh
selected existing sessions through the API with exact backups and human review of
scientific content. Do not mass rewrite the vault for a theme change. Keep desktop
and actual-mobile verification distinct; responsive CSS does not establish mobile
support. Plan work on an isolated branch and check other agent ownership before edits.

Validation matrix: dedicated view, Markdown embed, offline export; light/dark;
320/600/900/1200px iframe widths; 200% zoom; long equations/tables/code; missing or
invalid resources; runtime absence; unsupported math; keyboard-only; reopen with
saved responses and open questions; print/static figures; duplicate headings.

Use existing tests (`test_html_sessions.py`, `test_html_integration.py`,
`test_html_runtime.py`, `html-host.test.js`, `html-runtime-browser.js`,
`html-browser-e2e.cjs`) plus focused semantic/placement regressions. Run the actual
Obsidian smoke gate after implementation and inspect a real authored session with
screenshots. Previous release test results do not verify this proposed design.

Completion means correct semantic rendering, useful inline visuals, comfortable
reading and intact research/learning history in the actual installed workflow.
The accompanying specimen demonstrates visual direction only; it has no vault
bridge, production math bundle, grading or persistence.
