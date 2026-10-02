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
