# Interruptible lesson and selective literacy (offline fixture)

All answers and reviewer attestations here are fictional regression fixtures,
not evidence about the real researcher. The canonical Markdown ledgers deliberately
show conceptual demonstration, partial method evidence, unknown tool operation and
unknown implementation navigation separately. Session answers never update them.

From the repository root:

```bash
python -S -B scripts/tutor_session.py --root examples/tutoring --input session.json
python -S -B scripts/knowledge.py --root examples/tutoring --concept box-counting --json --as-of 2026-10-02
python -S -B scripts/tutor_plan.py --root examples/tutoring --capability box.method --as-of 2026-10-02
```

The session interrupts a concept lesson with clarification, a nested prerequisite,
and a tool implementation question. It returns through those checkpoints, branches
to challenge the method choice, returns to the concept and tests transfer. Four
tutor assessments spend four budget units; the four learner questions spend none.
Concept, method, tool and transfer answer provenance stays separate. Any arbitrary
learner question can use the same event format without a classification label.

The helper prints without writing by default. `--output saved.json` explicitly
creates a complete new checkpoint inside this fixture directory, without overwrite;
then `--input saved.json` reconstructs the same projection in another process.
Use a disposable copy when experimenting. Do not use the real vault for this demo.

For selective artifact mapping, pass `--targets targets.json` instead of `--input`.
Its schema is `{"literacy_schema":1,"mappings":[...]}`. Each mapping declares
`artifact` (confined relative file), `sha256` of its current bytes, `capability`,
`dimension`, `why_consequential` and `introduced_by`. The capability must be a
unique valid schema-3 canonical ledger requiring that literacy dimension. This is
a reviewed, bounded selection, not a scan of every API or an ownership debt store.
Hash the actual bytes in your disposable copy; Git newline conversion can change
raw file hashes. Changed artifacts invalidate their mapping. No source, account,
provider worker, credential or scientific experiment is accessed.
