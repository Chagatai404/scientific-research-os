# v0.8 integration and read-only context exercise

The release chain is checked in `tests/test_v08_integration.py`, reusing bounded,
disposable fixtures from the task, literature, access, tutoring and defense suites.
No real scientific source or learner is represented by their synthetic receipts.

```text
python -S -B -m unittest discover -s tests -p test_v08_integration.py -v
python -S -B examples/release/context.py --root examples/release --question question.md --implementation workflow.py --as-of 2026-10-08
```

`context.py` also accepts a selected real project's question Markdown and Python
implementation. It accepts at most 1 MiB per selected UTF-8 file, reads only that
limit plus one overflow sentinel byte on initial and final reads, uses temporary
copies for projections, checks their original bytes again, and never imports the
implementation or writes to the project. Hidden paths, escapes and symlinks are
rejected. Choose ordinary, non-secret files. It plans two question-only manual
scouts without launching them; implementation context is reserved for later
reconciliation and defense. No local code is treated as independent external
scientific evidence. Missing source verification and human evidence remain
UNCERTAIN and UNKNOWN. The emitted viva question is preparation, not an assessment.

The real AMS exercise and structural counts are recorded in
[the release results](RESULTS.md). Live discovery, authenticated access,
independent full-source reading and actual human tutoring remain validation work.
There is no throughput, token-saving or wall-clock parallelism claim.
