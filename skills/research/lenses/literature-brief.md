# Lens: literature brief and findings handout

After the scouts, verifiers and ingest tasks of a question have finished, the researcher needs one document to judge from.

1. `handout_create --kind literature --scope '["question:<key>"]' --title "<question in short>"`, then write it as in
   the handouts lens of the `prepare` skill. The context lists the sources the record holds, the scout and verifier
   results, and the hypotheses.
2. Report each source with its verification verdict and locator. Do not merge papers into a model of your own; map the
   evidence, say where it conflicts, and say what was not found.
3. When an experiment has been approved, run and audited, `handout_create --kind findings --scope '["experiment:<key>"]'`:
   the context carries the approval, each claim with every step's verdict and notes, and the decisions so far. Write the
   results with the files and numbers they come from, and end with a decision memo that is a proposal.
4. Tell the researcher the handout is ready (portal: the decision card links to it) and stop: they decide.
