# Lens: writing a handout

You were given a `handout` task: write a study document for one handout (`references/HANDOUTS.md`). Start with
`handout_read --handout <id>`: the `context` is what the record knows, the sections are what to write.

- **Write from the context and from sources you have checked.** Capabilities and their prerequisites say what the reader
  already has; narration segments are prepared explanations you may build on; `prompts` are the questions the reader is
  *tested* on, so teach the idea they test but never copy their answers. If you cannot source a statement, say so in the
  text; do not present it as fact.
- **Words first, then the picture, then the formula.** Define a word before using it. Short paragraphs. Math in `$...$`.
- **Boxes, sparingly.** `:::definition`, `:::rule`, `:::keyidea`, `:::mistake` for what deserves one; `:::example` with
  every step after `=== solution`; `:::exercise` that grow in difficulty, each with a full solution; `:::question`
  recall prompts the reader answers from memory before opening the answer.
- **Ground it.** Every factual section carries `locators` (page, section, source key) or `derivation: true` if the
  section derives its result. Add each source once with a key and cite `[@key]`.
- **A lecture note follows study order.** Scope and learning goals, notation and prerequisites, core ideas and
  completed derivations, worked examples, gap fills and corrections, then practice questions. Use descriptive
  titles without layer codes. Keep proofs beside the concepts they explain. Omit optional sections only when
  inapplicable; put recall answers after practice and sources at the end.
- **A recitation's exercises are for study.** They never become assessment items; do not add them with `add_item`.
- **A findings handout informs a decision it does not make.** State what the numbers are and where they come from, give
  each claim's audit chain as recorded, and label the decision memo a proposal. The researcher decides.
- **A literature brief names what it did not find.** List the searches run, null results and competing models, and what
  you read only in part (an abstract is an abstract).
- Figures: put them in `figures/` with `handout_file` and look at them before you refer to them.

Then `handout_check`, fix every row it lists, and `handout_build`; finish the task with the handout id.
