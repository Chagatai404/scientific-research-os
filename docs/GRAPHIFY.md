# Graphify: code graph bridge (optional)

Research OS does not vendor, install or run Graphify, and works the same without it.

Three graphs stay separate: what the learner understands (capabilities), what the research tested and decided
(questions, hypotheses, experiments, claims), and how the code is built (code symbols). An import or call edge is
never evidence of a scientific relation.

The only bridge is explicit: a research record names the code that implements it (`code_refs` in an old research
note, imported as `code-symbol:<path> --implements--> <record>`), or an agent adds that edge with `add_edge`. Graphify
then supplies the symbols inside each file:

```bash
graphify .                                   # in the research repository, writes graphify-out/graph.json
ros import --kind graphify --path graphify-out/graph.json --repo .
ros code --node experiment:EXP-001           # the files that implement it, with their symbols
```

Paths inside the repository are made relative. Unreadable output imports nothing and says so. The `code` defence item
of a claim (`references/RESEARCH.md`) is written from these links.
