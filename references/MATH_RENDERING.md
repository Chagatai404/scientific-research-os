# Obsidian mathematics contract

For generated lesson, concept, derivation, physics, statistics, ML and QML notes,
put mathematical quantities in MathJax: `$E_{\mathrm{vis}}$`, `$X^{0}$`. Use braces
for subscripts/superscripts and upright descriptive labels. Ordinary Unicode prose
is fine; identifiers, filenames and commands belong in code, not mathematical form.
Do not use raw `E_vis` or HTML sub/sup for mathematical quantities. Display delimiters
occupy their own lines; keep the entire equation inside the pair, not split across
Markdown blocks. Do not escape the dollar delimiters, and preserve literal TeX
backslashes rather than introducing string-escape control characters.

```markdown
> [!formula] Visible energy
> $$
> E_{\mathrm{vis}} = \sum_i E_i
> $$
>
> **Variables:** $E_i$: energy contribution of component $i$.
```

Use this standard formula callout for important equations when it improves clarity,
not for every trivial expression. Title/equation are required; variable definitions,
units, assumptions, validity regime and source are optional and must be supported.
Missing metadata stays absent; never invent provenance or applicability.
Every line, including blank lines between math and metadata, retains its `>` prefix.
The custom formula type renders as an Obsidian callout even without custom CSS.

`scripts/math_notes.py` supplies inline, display and formula helpers preserving
literal expressions; the CLI warns about raw mathematical notation, HTML sub/sup,
unbalanced inline/display delimiters and one-line display pairs. Fenced/inline code
and wiki/Markdown links are ignored. Currency and ambiguous prose need manual
review; this is not a full TeX parser or proof of MathJax rendering. Test fixtures
cover fractions, sums, integrals, Greek letters, matrices and callout nesting.
Audit warnings before saving generated notes; use Obsidian's actual preview when
available. No rewriting of existing user notes or automatic permanent promotion.

## HTML sessions: one inline grammar everywhere

HTML sessions render lesson text, headings, callouts, lists, tables, **and every question
surface** (prompts, options, hints, explanations, tutor feedback, open questions and their
answers) with one grammar, implemented twice and held identical by a shared corpus
(`scripts/rich_text.py` and `assets/html-runtime/richtext.js`,
`tests/fixtures/richtext-cases.json`). It replaces the earlier regular-expression renderer.

- **Emphasis:** `*em*`, `_em_`, `**strong**`, `__strong__`, nested freely with the CommonMark
  flanking rules (so `snake_case` and `2 * 3 * 4` stay literal). Also `~~strike~~`, `==highlight==`,
  and `<sub>`, `<sup>`, `<mark>`, `<br>`. Single `~` and `^` are ordinary characters.
- **Mathematics:** inline `$x_i^2$` (Pandoc rules: `$5 and $6` is prose) and `\(x\)`; display
  `$$...$$`, `\[...\]`, or a bare `\begin{aligned}`/`align`/`equation`/`gather`/`multline`/`cases`
  environment, single- or multi-line. TeX is atomic: nothing inside it is ever emphasis or
  escaping. Authored text is never rewritten; the source is the element's text and `data-source`.
- **Numbered equations and references:** end a display with `{#eq:name}` (or put `\label{name}`
  inside it) to number it `(n)` in document order; cite it with `\eqref{name}` or `[@eq:name]`,
  before or after. An unknown reference is shown as a diagnostic, never silently dropped.
- **Links:** `[label](#anchor)` jumps in the page; `[[Note|alias]]` keeps its target; other URLs are
  shown inert with their address.
- **Unsupported syntax:** an unterminated `\(` or `\[`, an unresolved reference, or TeX KaTeX
  rejects (for example an unknown macro) stays visible exactly as written, highlighted, with a
  short diagnostic. KaTeX runs with `trust: false`; scripts, raw HTML and event handlers cannot
  come from text.

`<option>` text and accessible names use the plain form (TeX source, markup removed).
Changing the renderer changes the generated HTML of sessions that used the affected constructs:
refresh those projections with `html_sessions.py refresh-projection` (canonical Markdown and state
are never rewritten; the old HTML is backed up).
