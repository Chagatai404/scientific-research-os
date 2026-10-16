# Code learning protocol (v0.9.5)

The Research OS asks the researcher to own the concepts; this protocol asks the same of the code. It owns how code is taught and how
claims about code are checked. It changes **none** of: research stages and the plan approval gate (`RESEARCH_PROTOCOL.md`), what counts
as learning evidence (`LEARNING_PROTOCOL.md`), or ownership gaps (`RESEARCHER_OWNERSHIP_PROTOCOL.md`). Teaching never bypasses the plan
or its approval, and an approval is never lowered by a teaching preference.

Why: in a randomized trial of junior developers learning an unfamiliar library, learners who used an AI assistant scored lower on a
comprehension quiz, most on debugging; those who delegated fully scored worst, and those who generated code then asked specific
follow-up questions kept their learning (Shen and Tamkin 2026, arXiv 2601.20245; small sample, as its authors say). The defaults below
exist to prevent full delegation of the code a researcher will have to defend.

## The loop

1. **Existing or inherited code.** Map first (`code_walkthrough.py map`, and the code graph), then tour dependency-first: the files with no
   local dependencies, up to the entry points; trace one input end to end; then a small modification exercise. The result is a Code Map note
   in the vault (which module implements which concept or decision), kept short and human-reviewed. Structure stays in the code graph.
2. **New work.** Before the plan is presented, ask the researcher for their own approach and compare it with the plan. The plan lists
   **change units** (`units`): files, purpose, linked concepts, risk class, teaching level. The unchanged plan approval authorizes the
   build. Then build unit by unit and walk through each unit after it is built.
3. **Handover.** Consequential units without learner evidence appear as open ownership gaps (`ownership-gaps`); they never block research by
   default and surface when the researcher claims personal understanding, presents, modifies or defends the work.

## Risk class, pace, and the floor

`units` proposes a risk class from path and symbol names. A unit is **consequential** if it touches data loading, splits, preprocessing,
normalization, metrics, loss or objectives, seeds, geometry or detector configuration, thresholds, labels, simulation or anything a claim
depends on; documentation and tests are routine. The researcher confirms or changes the class.

A consequential unit gets a **walkthrough and probes at every pace**. `checkpoint_pace` (`light`, `normal`, `frequent`, in the learner profile)
sets only how much routine code is walked through: a summary, a walkthrough, or a walkthrough with probes. **The walkthrough is default-on
for consequential units. The researcher may skip one; the skip is recorded with its reason and the unit becomes an open ownership gap.**
Skipping is a choice, not a failure, and nothing here forbids it.

## Choices the agent made

While building, record every consequential choice the plan did not specify: a library, a default, a threshold, a seed, a split, a
normalization. Each goes in the record's `choices` with the reason and alternatives and is shown to the researcher, who accepts, changes or
leaves it open. An open consequential choice is proposed as an ownership gap. Hidden choices are validity risks as well as learning gaps.

## The walkthrough record (`walkthrough_schema: 1`)

A JSON record per walkthrough:

```json
{"walkthrough_schema": 1, "id": "WT-001", "pace": "normal",
 "units": [{"id": "U1", "path": "src/split.py", "title": "Train/test split", "risk": "consequential", "risk_reason": "touches split",
            "status": "pending | walked | skipped", "skip_reason": null, "concepts": ["data-leakage"],
            "heading": "How the split is made", "target": "data-leakage", "card": {"core_idea": "..."}, "literacy": {"...": "..."},
            "claims": [{"id": "U1-C1", "kind": "structure | behavior | test | choice-effect", "statement": "The split is done before scaling.",
                        "locator": {"path": "src/split.py", "start": 12, "end": 20, "sha256": "...", "commit": "..."}, "evidence": "X1"}],
            "probes": [{"id": "P1", "kind": "code-comprehension | tool-exercise | implementation-task", "prompt": "..."}]}],
 "approved_commands": [{"id": "A1", "argv": ["python", "-m", "pytest", "-q"], "cwd": ".", "approved_by": "researcher", "approved_at": "2026-10-16"}],
 "executed": [], "choices": [{"id": "CH1", "unit": "U1", "choice": "seed 0", "reason": "...", "alternatives": ["..."], "consequential": true, "decision": "open"}]}
```

* **Claims about code carry a locator** (`locate` takes it from the code: path, line range of at most 80 lines, a hash of those lines, the
  commit). `verify` re-reads the code: a missing file, an out-of-range line or a changed hash is reported, and a locator that was not taken
  from the code cannot match.
* **A claim of behaviour, or of results (passes, verified), cites a recorded execution** (`evidence`). The author saying a test passes is not
  evidence; a recorded run with exit status and output hash is. A cited run that failed contradicts the claim.
* **`approved_commands` is the researcher's attestation.** An agent never writes it. `trace` runs one command from it, without a shell, inside
  the repository, and is a dry run unless `--run` is given. Executing project code is an action under the research protocol's approval
  boundary, so a command that is not listed does not run.

## What the walkthrough contains

A session built on the Teaching Card (`TEACHING_FORMAT.md`) and the `implementation` block, whose eight literacy items are the right shape: why
chosen, assumptions, how it works, how to run, how to verify, where to change it, how it fails, alternatives. One idea first; code terms
defined before use (term ledger); a call-flow or data-flow diagram from the code graph; one input traced through the real code, each step
cited; then probes of the kinds `code-comprehension`, `tool-exercise` and `implementation-task`: predict the output (checked by running it),
find the line to change for a stated requirement, explain a function back, and, only with the researcher's approval and in a scratch
worktree, "what breaks if this guard is removed?".

## Evidence

Viewing a walkthrough is never evidence of understanding, and neither is the author's explanation. Evidence is the learner's answer to a probe,
reviewed against criteria, through the existing ledger (`tutor_gate.py evidence` proposes; the human accepts). Map code understanding to the
tool and implementation-navigation dimensions, separate from the concept. A `verify` that comes back consistent shows the cited lines exist and
match and the behavioural claims cite runs; it does not show the explanation is right or that the researcher understands it.

## Guards

* Paths matching the secrets denylist (`.env` files, keys, credentials, `.git`) are never read into a walkthrough, a locator or the vault.
* Excerpts are short and carry `path:line`; never whole files. No private data is copied into the vault; link the reproducible artifact.
* The record is a working record. Promotion of anything to permanent notes stays the researcher's choice.
* A walkthrough never says "verified" about what only the author asserted.

## Commands

```
python scripts/code_walkthrough.py --repo <repo> units --base <rev> [--head <rev>]     # change units (proposals)
python scripts/code_walkthrough.py --repo <repo> locate <path> <start> <end> [--commit <rev>]
python scripts/code_walkthrough.py --repo <repo> verify <record.json>                  # exit 1 if inconsistent
python scripts/code_walkthrough.py --repo <repo> trace <record.json> <command-id> [--run]
python scripts/code_walkthrough.py --repo <repo> map
python scripts/code_walkthrough.py --repo <repo> levels <record.json>                  # what each unit gets at the pace
python scripts/code_walkthrough.py --repo <repo> ownership-gaps <record.json>          # proposals only
python scripts/code_walkthrough.py --repo <repo> blocks <record.json>                  # teaching-block declarations
```

## Notebook coverage in research repos (v0.9.5)

Some research repositories keep notebooks as **AI-written documentation of completed, tested implementations**: reusable code lives in the package with tests, and a notebook later explains what was done.
Treat such a notebook's prose and stored outputs as claims to check against the code, not as authority, and never add a notebook while the work it would describe is in progress.

`python scripts/notebook_coverage.py scan --repo <repo>` (read-only) lists the source modules no notebook covers; `ledger --repo <repo> [--write]` regenerates `research/NOTEBOOK_COVERAGE.md`, a derived file that records when each gap was first
seen and when a notebook closed it. Evidence is read from the repository: **covered** means a notebook's code imports the module (directly, as a submodule or through the package's re-exports); **mentioned** means a notebook names it in backticks or as a path
without importing it; **tested** means the test file the module map names exists; the **status** is the module map's own word. The tool never writes, runs or changes a notebook, never decides a unit is complete, and writes only the ledger, only with `--write`.
After a unit is completed and its tests pass, run it and tell the researcher what is new; whether a gap deserves a notebook is theirs to decide.

### Running notebooks to check them (`scripts/notebook_trace.py`)

`trace` runs a listed command; for a research repo whose notebooks document completed work, the thing worth running is the notebook. The researcher lists notebooks in the record as
`approved_notebooks`: `{"id", "path", "approved_by", "approved_at", "timeout"}` (a timeout in seconds, up to 7200; the heavy ones deserve a deliberate number). An agent never adds to that list.

`notebook_trace.py run --repo <repo> --record <record.json> --notebook <id> --run` makes a scratch `git clone --local` of the committed state (so no `.env`, no virtual environment, nothing ignored, and uncommitted
changes are not in it, which the output states), builds the copy's own environment with `uv sync --frozen`, scrubs secrets and any variable that points at the real environment from the process environment, and runs
the notebook with `--allow-errors` so that a failing cell is reported, not fatal. The copy matters: a project's own virtual environment normally has the package installed *editable*, pointing at the real source,
so a notebook run with it would import the real code. It compares fresh outputs with stored ones cell by cell: `identical`, `numerically-equal` (last-digit noise), `image-bytes-differ`, `text-differs` or `now-errors`;
a notebook is **stale** if any cell's text now differs or now errors. It appends the run to `executed` (with `--update-record`), and removes the copy. A match shows the notebook still tells the truth about the code
today, not that its explanation is right. Without `--run` it only describes what it would do.

`mutate --spec` runs the notebook, applies **one** change (one string, found exactly once, in one code cell or one file under `src/` or `notebooks/` *of the copy*), runs it again and reports the cells that changed:
a "what breaks" exercise. Ask for a prediction first and reveal nothing until it is made. The repository is never changed.
