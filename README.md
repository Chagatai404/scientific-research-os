# Scientific Research OS

A model-independent research and learning workflow for human-led scientific work with AI assistance.

The system separates two loops:

- **Learning:** prepare and verify → check prior retention → probe → map frontier → teach/visualize → retrieve → record → target-appropriate follow-up → reinforce or promote by human choice.
- **Research:** question → inspect knowledge/retention → independent discovery → separate verification → prepared evidence and lesson sanity check → learn → reconcile → synthesize → specialist validation → full adversarial review → triage → plan → explicit human approval → build/experiment → validate/attack results → human decision → learn again → persist.

The human researcher is always the final authority. AI agents may search, explain, implement, critique, reproduce, verify, and propose changes, but they do not silently promote claims into permanent knowledge or accepted research conclusions.

## Core design

```text
Obsidian vault                 Git research repo
(understanding)                (evidence)
      │                              │
      ├─ concepts                    ├─ src/
      ├─ derivations                 ├─ tests/
      ├─ quizbook                    ├─ notebooks/
      ├─ literature notes            ├─ configs/
      └─ learning maps               └─ results/
              \                      /
               \                    /
                human researcher
                       │
              assigns the task/role
                       │
        ┌──────────────┼──────────────┐
        │              │              │
      Claude         Codex          other AI
        │              │              │
        └─────── interchangeable tools ┘
                       │
          tutoring / literature / coding
          experiments / review / audit
          verification / reproducibility
```

The user decides which tool performs which task. A project may choose conventions—for example, using one tool more often for tutoring and another for implementation—but those conventions belong to the project or user workflow, not to Scientific Research OS itself.

For substantive research, prefer **one coordinating primary agent at a time**, with separate literature discovery and source-verification agents and relevant independent reviewers. Follow the canonical [research protocol](references/RESEARCH_PROTOCOL.md); the summaries here do not replace its gates.

Cross-validation means independent reconstruction or verification, not asking a second agent whether it agrees with the first.

## Repository layout

```text
skills/                 Canonical model-independent skills
agents/                 Canonical specialist/subagent role definitions
references/             Shared scientific policies
assets/obsidian/        Obsidian templates
scripts/                Portable local tooling
extensions/             Capability contracts and optional integrations
adapters/                Notes for Claude Code and Codex
examples/                Example project integration
tests/                   Lightweight self-checks
```

## Skills

- `course-study` — university coursework, from syllabus and lectures to practice, exams and prerequisite repair.
- `notes-to-latex` — faithful handwritten technical notes to LaTeX, with visible ambiguity and disclosed corrections.
- `tutor` — source-grounded live tutoring with prerequisite probing and retrieval checks.
- `visualize` — scientific diagrams, plots, interactive exploration, and physics/mathematical animation.
- `study-source` — deeply study a paper, book chapter, website, lecture, or video.
- `derive` — reconstruct mathematics/physics from assumptions and sanity checks.
- `form-hypothesis` — turn ideas into falsifiable scientific hypotheses.
- `design-experiment` — design reproducible experiments before running them.
- `stats-audit` — audit statistical validity and leakage.
- `physics-audit` — audit physical assumptions, units, geometry, and limiting behavior.
- `research-review` — adversarial review of claims and evidence.
- `research-session` — orchestrate a complete human-led research session.
- `geant4` — plan and validate detector/particle simulation with explicit physical configuration.
- `ml-experiment` — classical/deep ML experiments with leakage controls and fair evaluation.
- `qml-experiment` — QML experiments inheriting ML rigor, with explicit execution regimes and claim limits.

Skills describe workflows and capabilities. They are not tied to a particular model or provider.

## Specialist agents

- literature-scout
- source-verifier
- physics-reviewer
- statistics-reviewer
- reproducibility-auditor
- adversarial-reviewer
- visualizer
- simulation-reviewer
- ml-reviewer
- qml-reviewer

These are **task roles**, not provider identities. Any compatible AI system may perform them if it has the required capabilities.

Use specialist agents when work benefits from isolated context, independent verification, or parallelizable evidence gathering. Do not spawn them for trivial tasks.

## Research independence and bias control

For hypothesis-sensitive, model-selection, or implementation-defining questions, separate:

```text
neutral research question
        ↓
independent literature discovery
        ↓
independent source verification
        ↓
prepared evidence + lesson sanity check → learn/probe/visualize
        ↓
reconciliation → synthesis → relevant specialist validation
        ↓
adversarial review → blocker/relevance triage
        ↓
plan → explicit human approval → build/experiment
        ↓
result validation/attack → human decision → learning → persist
```

The initial literature search should not be shaped by the project's preferred implementation, equations, existing citations, or desired conclusion unless those details are genuinely necessary to define the system or regime.

A disagreement between external evidence and the current codebase is a research finding, not something to smooth over.

When practical, an independent reviewer should receive the claim, source, artifact, experiment, or acceptance criteria without being given the authoring agent's full reasoning first.

Standalone tutoring uses prepared authoritative material without requiring a full
research cycle. Research-linked tutoring uses a compact verified evidence pack;
its sanity check establishes lesson readiness, not independent corroboration or
research acceptance. Full adversarial review remains after synthesis. See the
[entry paths and handoffs](references/RESEARCH_PROTOCOL.md).

## Retention and the knowledge frontier

Working quizbook notes hold one learning record per capability, with stable IDs,
explicit prerequisites, and retrieval history. These records can exist before
permanent-note promotion; human-reviewed concept notes link to them. Note existence
does not imply mastery. The [learning protocol](references/LEARNING_PROTOCOL.md) distinguishes
`unknown`, `learning`, `demonstrated`, `retained`, `fragile`, and `stale`; stale means
missing recent evidence, not proven forgetting.

Understanding a capability does not mean every exact detail deserves permanent
memorization. Choose a separate optional retention target:

- **core:** maintain fluent unaided reconstruction, explanation or application.
- **working:** understand deeply and refresh around actual future use.
- **reference:** understand what/why/when and keep a path to recover exact details;
  no routine spaced-review burden. Reference material can be scientifically critical.

Missing targets remain **unspecified**. The learner decides meaningful choices;
the tutor may recommend a target with a short rationale. Historical attempts,
failures and review dates stay intact. A reference record's old horizon is evidence
context, not an automatic retention-priority warning.

| View | Question |
|---|---|
| Subject | What do I know? |
| Course | What do I need for this class? |
| Project | What do I need for this research/project? |
| Goal | What is worth building and retaining for where I want to go? |

One capability may appear in several courses, projects and goals without being
duplicated. Membership is explicit. Every view includes required external
prerequisites and shows evidence state, retention target, freshness and frontier.
Frontier is eligibility based on conservative prerequisite evidence, not a global
priority score or an instruction to review every node. Read the
[metadata and command contract](assets/obsidian/README.md) for state derivation,
unknown freshness, diagnostics and legacy handling.

Tutor preparation includes questions, acceptable answers, misconceptions, hints,
and visual candidates. Diagnostic blocks normally use 3–5 questions, one at a time,
with hidden balanced MCQ answer positions and symmetric options. Recognition alone
does not establish retention. For targets needing delayed checks, intervals adapt to retrieval evidence;
there is no background scheduler or prescribed optimal spacing algorithm.

## University courses and handwritten notes

Use `course-study` to inspect the syllabus/outcomes, map prerequisites, check prior
knowledge, study a topic, practice, retrieve/apply, use assignment/exam feedback,
and update the course map. It supports lecture preparation/review, homework, exam
preparation, cumulative review and prerequisite repair. Ordinary course study
follows the [course learning protocol](references/COURSE_LEARNING_PROTOCOL.md),
without research agents or research approval. Research procedures apply when the
learner explicitly moves into a substantive research question. Course and session
templates are optional; no Obsidian setup is required for this workflow.

Use `notes-to-latex` with visible handwritten pages to get a fragment or full
LaTeX document. The default is faithful-clean transcription, preserving apparent
mathematical mistakes and marking meaningful ambiguity. Explicitly requested
polished output reports substantive corrections separately. Unclear figures get
placeholders rather than invented geometry. The
[transcription protocol](references/LATEX_TRANSCRIPTION_PROTOCOL.md) requires no
OCR engine, external AI API or LaTeX compiler in Research OS.

## Scientific visual teaching

The [visualization protocol](references/VISUALIZATION_PROTOCOL.md) selects the
simplest suitable diagram, plot, interactive view, or animation. It distinguishes
schematic, model-driven, and simulation/data-driven visuals and requires rendering
inspection or an explicit unverified-draft disclosure. Quantitative physics must
come from stated equations, models, simulations, or data, never decorative motion.

Mermaid, Matplotlib, Plotly, SVG, PyVista, Manim Community, and optional Motion Canvas
are capability recommendations. None is required to install or validate Research OS.
Manim Community is the default Manim recommendation; no backend is installed automatically.

## Scientific compute

Scientific Compute makes the tools that produce scientific evidence part of the
existing research workflow: inspect environment and configuration, plan controls
and resources, obtain approval, run at the approved scale, then validate the actual
outputs. It adds no second lifecycle and does not change learning, retention,
course study or transcription.

**Methodology skills** (`geant4`, `ml-experiment`, `qml-experiment`) own scientific
reasoning through canonical protocols. **Tool packs** hold software-specific
guides and strictly declarative discovery metadata. The six shipped packs are
`geant4`, `pytorch`, `sklearn`, `pennylane`, `qiskit` and `root-scikit-hep`.
Framework packs do not become global skills. Installation and tests work with none
of these frameworks installed; no automatic dependency installation is provided.

A computational manifest records provenance, not scientific validity. It separates
observed facts (versions, platform, discovered components) from declared choices
(physics list, split, model, circuit, shots/backend) and derived calculations.
Unknown values stay null; the OS never guesses scientific configuration from an
installed package. Project-pinned versions take precedence over newer releases.

From the repository, or from an installed compute skill directory:

```sh
python scripts/scientific_tools.py list
python scripts/scientific_tools.py probe geant4
python scripts/scientific_tools.py probe --all
python scripts/scientific_tools.py probe pytorch --accelerator
python scripts/scientific_tools.py manifest --experiment RQ-001 --repo /path/to/project --tool sklearn --declared /path/to/reviewed-config.json
python scripts/computational_manifest.py /path/to/saved-manifest.json
```

Commands print JSON. Save manifest stdout to a UTF-8 file for later inspection.
`--declared` accepts an explicit JSON mapping; omit it to leave choices unrecorded.
`--reproduction-command` records an inert string and never runs it. Manifest
generation probes only named `--tool` entries; no tool flag means Git/Python/OS
only. No local Research OS config or source checkout is required by these helpers.

Default package discovery reads distribution metadata without importing frameworks.
Only fixed, code-owned version probes can execute from profiles. The optional
`--accelerator` flag uses a fixed isolated PyTorch query without a GPU workload;
unavailable/failed queries remain unknown. Trust the installed interpreter/packages
and PATH tools: discovery is not a sandbox for malicious installed software.
Partial HEP environments retain per-component status, such as ROOT absent and
Uproot present. Availability is not proof of operational or scientific validity.

The scale ladder is environment probe → smoke → toy → pilot → production.
It grants no authorization: a probe does not permit an experiment and a successful
pilot does not authorize production. Follow the existing explicit approval gate.

See the [computational protocol](references/COMPUTATIONAL_PROTOCOL.md),
[manifest and workflow examples](examples/compute/README.md), and
[tool-pack contribution contract](extensions/scientific-tools/README.md).
Add software knowledge with `extensions/scientific-tools/<new-tool>/PROFILE.toml`
and `GUIDE.md`, then run the validator/tests. A new global skill requires distinct
scientific methodology; a new executable probe requires a reviewed code allowlist
change, not a command string in TOML.

## Connected research and learning (v0.6)

Opt-in schema-1 research records (`research_schema: 1`: research question,
hypothesis, experiment, research decision) plus explicit links to EvidenceAtoms,
computational manifests, learning capabilities, verified visuals and code files
form a **research graph** that is computed from the plain-Markdown records, never
stored separately. Legacy notes stay valid and untracked. The research graph, the
learning graph and the (optional) code graph remain separate; the system exposes
state and the human researcher decides.

```sh
python scripts/research.py validate --root <project>          # ERROR / WARNING / INFO diagnostics
python scripts/research.py status   --root <project> [--json] # states, pending validation/decisions
python scripts/research.py frontier --root <project>          # unranked mechanical transitions
python scripts/research.py graph    --root <project> --experiment EXP-001   # Mermaid
python scripts/research.py context  --root <project> --experiment EXP-001   # bounded, deterministic
python scripts/knowledge.py --root <vault> --capability <id> --dependencies --json
python scripts/visuals.py   --root <vault> --reusable         # verified teaching visuals only
python scripts/vault_health.py --root <vault>                 # read-only structural audit
python scripts/bootstrap.py --root <vault>                    # dry-run legacy learning proposals
python scripts/scaffold.py course --root <vault> --course-id stat-101 --title "Statistics 101"
```

Frontier is not a recommendation; a valid manifest or `EXACT_SUPPORT` evidence is
not scientific acceptance; a learning dependency is advisory and never blocks
approved work; a rendered visual is not a verified one; a stale or missing
capability is never treated as known. `bootstrap.py` and `scaffold.py` propose
first and write only on an explicit flag; nothing migrates a vault automatically.
Tutor plans each block from the knowledge graph (TESTS / ASSUMES / INTRODUCES,
terminology gate, verified inline visuals). Optional adapters for Obsidian Bases,
Breadcrumbs, Excalidraw and Graphify live in `extensions/obsidian-adapters/` and are
never required. The [synthetic connected example](examples/connected-research/README.md)
demonstrates every command; the protocol is
[RESEARCH_GRAPH_PROTOCOL.md](references/RESEARCH_GRAPH_PROTOCOL.md).

## Quick start

Use Python **3.11+**. Repository scripts and tests use only the standard library;
PyYAML and visualization packages are not Research OS dependencies.

### 1. Configure your vault

Copy:

```text
research-os.example.toml -> research-os.toml
```

Edit the vault path.

### 2. Validate the repo

```bash
python scripts/validate.py
python -m unittest discover -s tests -v
```

### 3. Install skills and agents globally

Dry run first:

```bash
python scripts/install.py --target all --dry-run
```

Then:

```bash
python scripts/install.py --target all
```

This installs:

- skills to `~/.claude/skills/` and `~/.agents/skills/`
- Claude-compatible subagents to `~/.claude/agents/`
- Codex custom agents to `~/.codex/agents/`

Each installed skill receives copies of the canonical `references/` documents. In the source tree, resolve skill `references/` paths against the repository root. Installed standalone agents receive the shared agent policy, triage, and approval boundary in their generated instructions; edit canonical sources and reinstall, rather than editing generated copies.

The standalone visualizer also receives the source and visualization policies.
Reinstallation replaces existing skill directories and agent definitions; review
any local customizations before installing.

The installed definitions are the same scientific roles expressed through provider-specific adapter formats. Installing them does **not** assign Claude or Codex permanent responsibilities.

### 4. Install Obsidian templates

```bash
python scripts/install.py --obsidian
```

The destination is read from `research-os.toml`. This command also installs the
default skill/agent targets. Template files with matching names are overwritten;
existing notes are not migrated. Preserve any template customizations first.

### 5. Start a live tutor session

```bash
python scripts/vault.py new \
  --template 00_Tutor_Session.md \
  --title "Generalized Fractal Dimensions" \
  --dest "00 Tutor Sessions"
```

Append a logged teaching turn:

```bash
python scripts/vault.py append \
  --note "00 Tutor Sessions/2026-09-20 Generalized Fractal Dimensions.md" \
  --speaker "Tutor" \
  --text "Today we will first establish the scaling-law foundation."
```

Open the note:

```bash
python scripts/vault.py open \
  --note "00 Tutor Sessions/2026-09-20 Generalized Fractal Dimensions.md"
```

### 6. Generate a subject, course, project or goal graph

Try the [synthetic learning example](examples/learning/README.md):

```bash
python scripts/knowledge.py --root examples/learning --subject probability --as-of 2026-09-29
python scripts/knowledge.py --root examples/learning --project demo --as-of 2026-09-29
python scripts/knowledge.py --root examples/learning --goal research-foundations --as-of 2026-09-29
python scripts/knowledge.py --root examples/learning --course stat-xxx --as-of 2026-09-29
```

For your records, replace the input directory and scope IDs. The command reads notes
without editing them and emits Markdown/Mermaid. `--output <new-file.md>` creates a
file without overwriting an existing one. No Obsidian plugin is needed. Record a fixed
`--as-of` date for reproducible output; otherwise the local current date is used.

### Upgrading existing learning records

Reinstall reviewed skills/agents/templates to get the new policies. Learning metadata
is opt-in: old notes remain readable and are skipped as untracked by the generator.
Existing `status`, confidence, review timestamps, and `solid` labels are not converted
into mastery evidence. Adopt tracking one capability at a time; preserve old logs.
There is no bulk vault migration or automatic permanent-note promotion. Existing
schema-1 records remain valid; `retention_target`, `goals` and `courses` are optional.
No old record is silently assigned core retention or inferred context membership.

## Tool independence

Scientific Research OS is model- and provider-independent.

The framework defines:

- scientific workflows,
- evidence standards,
- specialist task roles,
- review boundaries,
- human authority points.

It does **not** prescribe that a particular provider must perform a particular type of work.

For example, `literature-scout` requires capabilities such as:

- scholarly/web search,
- source retrieval,
- citation metadata,
- optional citation-context search.

Claude, Codex, ChatGPT, MCP servers, connectors, or future tools may satisfy those capabilities differently.

Likewise, `tutor`, `physics-reviewer`, `reproducibility-auditor`, and other roles can be assigned to whichever tool the user chooses.

A project may define its own preferred tool conventions in project-local instructions such as `CLAUDE.md`, `AGENTS.md`, or equivalent files.

## Suggested coordination pattern

A simple default for substantial work is:

```text
human defines question
        ↓
primary agent coordinates the canonical research cycle
        ↓
human inspects result
        ↓
independent result reviewers verify/reproduce as warranted
        ↓
human accepts, rejects, or revises
```

Use simultaneous agents only when true parallelism adds value and their contexts can remain independent.

Git is the coordination layer for reproducible artifacts. Obsidian is the learning/understanding layer. The human researcher is the convergence point.

## Security

- Do not store API keys, tokens, passwords, `.env` contents, or private credentials in this repo.
- Skills and agents must not read secrets unless the user explicitly requests a task that requires them.
- Treat skill repositories as executable instructions: review external skills before installing them.
- Prefer read-only subagents for literature and review work.
- Never let an AI agent silently rewrite accepted research conclusions.

## Status

**v0.6.0 — Connected Research & Learning OS** adds opt-in schema-1 research records
with a derived research graph, frontier and bounded context; advisory learning
dependencies; graph-first Tutor planning with a question concept contract and
terminology gate; a verified-only visual registry with a source-first policy and
inline Obsidian embeds; a candidate-only legacy bootstrap, a read-only vault
health audit and course/source scaffolding; and optional Bases, Breadcrumbs,
Excalidraw and Graphify adapters. See the
[implementation and verification record](references/V0.6_IMPLEMENTATION.md).
Standard library only; existing v0.5 behavior, evidence semantics and human
approval gates are unchanged.

**v0.5.0 — Scientific Compute & Model Validation** adds computational provenance,
declarative optional tool packs, Geant4/ML/QML methodology, a ROOT/Scikit-HEP bridge
and provider-symmetric deployment. See the
[implementation decision and slice record](references/V0.5_IMPLEMENTATION.md).
The v0.4.5 learning architecture and existing evidence/approval semantics remain
unchanged. HPC/cloud/QPU automation, experiment tracking services, automatic
dependency installation, Obsidian plugins and synchronization remain out of scope.

**v0.4.5 — Learning Architecture & Academic Workflow** adds selective retention,
goal maps, dedicated university-course study, and faithful handwritten-note LaTeX
transcription. Schema 1 remains backward compatible; evidence-state and research
authorization semantics are unchanged. See the
[implementation decision](references/V0.4.5_IMPLEMENTATION.md).
These learning capabilities remain available alongside scientific compute.


**v0.4.0 — Evidence integrity and low-token verification** added a small reliability
layer over the v0.3 research workflow:

- JSON EvidenceAtoms with claim envelopes, comparison semantics and numerical provenance;
- deterministic validation, independent verification receipts and stale-record checks;
- bounded scouting/verification, labelled adversarial reasoning and selective escalation;
- reusable project-local evidence and Markdown rendering;
- regression fixtures for all five motivating scientific failure categories.

```sh
python scripts/validate_evidence.py examples/evidence
python scripts/validate_evidence.py examples/evidence --markdown --facts-only
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --target all --dry-run
```

See [EvidenceAtom format and lifecycle](references/EVIDENCE_FORMAT.md), the
[synthetic example](examples/evidence/README.md), and the
[architecture decision](references/V0.4_IMPLEMENTATION.md). Existing Markdown-only
projects continue to work; adopt structured records for consequential claims as
they are reused. Installed research-session/research-review skills include the
standalone validator. No dependency installation is needed.

Validation checks recorded structure and attestations, not scientific truth.
Independent source reading, scientific interpretation and human acceptance remain
necessary. Compact handoffs and reusable evidence are intended to reduce repeated
context; token savings and small-model reliability require actual workflow evaluation.

**v0.3.0 — Retention, Knowledge Frontier & Visual Teaching** introduced:

1. evidence-based long-term retention records;
2. subject/project knowledge graphs and derived frontier;
3. a scientific visualization skill and physics-animation contract;
4. bounded, prepared probing with MCQ quality controls;
5. verified preparation before research-linked tutoring.

The v0.2 scientific independence, human authority, and explicit build/experiment
approval boundaries remain in place. This release remains Markdown plus lightweight
Python: no database, dashboard, LMS, vector store, daemon, or rendering framework.

Future extensions should be added only after a recurring workflow proves it is needed.
