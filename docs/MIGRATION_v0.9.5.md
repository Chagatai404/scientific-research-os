# Upgrading to v0.9.5

v0.9.5 changes nothing in your vault by itself. Installing it replaces helper scripts, skills, agents, the shared session runtime and the Obsidian
companion (the installer keeps a backup of anything it overwrites). Your notes, sessions, answers, learning history, research records, paper catalog,
visuals and accepted evidence stay as they are. Everything below is optional except step 1, and every command has a dry run first.

**Not yet rehearsed on your real vault.** The steps were exercised on fixtures and temporary installs (`tests/`, `scripts/release_gates.py`), and the
rollout tool was extended to recognise a v0.9.0 installation and tested on one rebuilt from the v0.9.0 release commit. They have not been applied to
a vault or provider folder, and the installed copies still hold the v0.9.0 skills (including the old `visualize`).

## Before you start

Back up the vault or commit it. Run every command without `--apply` first.

## Steps

1. **Install the new skills, agents and helpers** (both providers):

   ```bash
   python scripts/install.py --status
   python scripts/install.py --target all --dry-run
   python scripts/install.py --target all
   ```

   `--status` reports what differs by content. The installer overlays known files, keeps extra files of yours and backs up any file whose content
   differs. **The skill `visualize` is renamed `science-visualize`**: the old directory is moved into a `.research-os-retired` folder beside it (never
   deleted) so a host does not see two skills for one job; it is moved only if it carries our shared reference. New skills: `chemistry-audit`,
   `biology-audit`, `code-walkthrough`. New read-only agents: `chemistry-reviewer`, `biology-reviewer`, `walkthrough-verifier`.

2. **Roll the session runtime and the companion forward** (the only step that touches sessions; it changes their HTML projection, never the Markdown or JSON):

   ```bash
   python scripts/html_design_rollout.py --vault <vault> --backup <new-empty-folder>            # dry run
   python scripts/html_design_rollout.py --vault <vault> --backup <new-empty-folder> --apply
   ```

   It refuses if the installed runtime or companion was edited locally. v0.8.5 to v0.9.0 installations are recognised. It replaces the companion's `main.js`
   only, so afterwards copy `extensions/obsidian-html/manifest.json` over the vault's copy to bring the plugin's version label to 0.3.0, then reload
   the plugin in Obsidian.

3. **Optional: link your paper-library indexes.** `python scripts/library_index.py backfill-plan --library <library>` is read-only and lists the links that can be
   built from identifiers already in your catalog (nothing is fetched or guessed). `library_index.py backfill-apply --index <files> --backup <new-folder>` shows the exact edits as a dry run; add `--apply` to write them. Applying edits your files, so it backs each one up first, changes only the planned lines and leaves an entry with several different identifiers for you. It was applied to the maintainer's library on 2026-10-17 (59 links in 4 files).
   `library_index.py lint` fails an index entry that has neither a link nor an explicit "no identifier" marker.

4. **Optional: animation and voice engines.** Neither is installed for you. Put each in its own virtual environment and name it:
   `animate.py capabilities --env <dir>` and `voice.py providers --env <dir>` (or `RESEARCH_OS_ANIMATION_ENVS` and `RESEARCH_OS_VOICE_ENVS`).
   Without them, animation returns an honest unrendered result and narration is the page's own browser voice. See `references/ANIMATION_PROTOCOL.md`
   and `references/VOICE_PROTOCOL.md` before choosing anything: they record what was measured here, what broke and the licences.

## What changes for you

- **Teaching Cards** (`references/TEACHING_FORMAT.md`): a section can declare its one idea, a prediction prompt, vetted outside resources, a spoken script
  and a recording. A section without a card renders exactly as before.
- **A learner model**: a term ledger and glossary; the Student Brief rides in the context receipt. It never stores a learning style.
- **Diagrams from specs** (`science-visualize`, `references/DIAGRAM_PROTOCOL.md`): geometry in 2D and 3D, molecules and C-alpha traces, drawn from coordinates
  that `scientific_verify.py` checks. A figure is registered at `rendered`, never `verified`.
- **Chemistry and biology**: exact checks for formulas, molar mass, stoichiometry and sequences; reviewer agents; audit skills.
- **Code walkthroughs** for consequential changes, default-on; skipping one records an open ownership gap.
- **Animation** (`animate.py`) and **voice** (`voice.py`), both optional and both detecting engines you installed.
- **Review scheduling** (`fsrs_schedule.py`, `references/FSRS_PROTOCOL.md`): FSRS-6 estimates when each learned item is likely to be forgotten, from checked
  attempts only (recognition and open-notes attempts do not count, and "Easy" is never produced). It is a derived view with generic parameters, not fitted
  to you, and it never replaces a `Next review` you wrote. `fsrs_schedule.py due` lists what is due.
- **Notebook coverage** (`notebook_coverage.py`, research repos only): lists completed, tested modules that no notebook imports and keeps a derived
  `research/NOTEBOOK_COVERAGE.md`. Notebooks there are AI-written documentation of finished work; this never creates or edits one and never decides a unit is complete.
- **Notebook trace** (`notebook_trace.py`, research repos only): runs notebooks *you* list under `approved_notebooks` in a scratch clone with its own `uv`
  environment, and reports whether the fresh output matches the stored one or is stale. An approval may also name read-only `inputs` (ignored data copied into the
  copy) and `groups` (the project's own dependency groups, installed into the copy only, which can be large downloads). A mutation exercise changes one
  string in the copy and shows what moved. Nothing runs without `--run`, and the repository is never changed.

## What was checked, and what was not

Checked by executed tests: every new script, the schemas and refusals, installation parity for both providers, the page policies (frames and media only
when a card asks), the click-to-load resource cards and the recorded-narration player (in one browser), the rollout from v0.9.0, and two end-to-end
lessons (one chemistry, one biology) from checked claims through a diagram, a spoken script, a recording and the page.

**Not checked, stated plainly:**

- **Voice quality.** Both local engines tried were judged unnatural by ear, in English and Turkish. The recording feature works; no engine has passed the
  listening test, and Chatterbox was run on CPU only.
- **Scheduling and notebooks.** The FSRS code matches the reference library on 1,260 reviews, but its parameters are defaults, not fitted to you. The notebook
  trace ran against one real repository (`ams-ecal-qml`): notebook 08 matched, and 02, 03 and 05 came back stale without the cause being investigated. The
  mutation exercise was tested with a fake runner, not on real code, and dependency `groups` were installed in a scratch copy but no notebook run has needed them.
- **The Turkish phrasings** of spoken formulas were not reviewed by a native speaker.
- **Obsidian.** The companion's `open-resource` handler and the recorded-narration fallback were tested in code, not inside a running Obsidian. YouTube playback
  and PhET embeds were not played end to end.
- **ManimGX** was measured at 1280x720 and 30 fps on one machine; its vendor speed claim is neither confirmed nor refuted. `manim-slides` 5.7.0 does not work
  under Manim Community 0.22.0.
- **Licences.** ManimGX's wheel is GPL-3.0-or-later; the Piper engine is GPL-3.0-or-later and its Turkish voice's dataset is non-commercial. None of
  this matters for personal use; all of it matters before a product ships any of them.

## Undoing it

Installer backups are in `.research-os-install-backups` and retired skills in `.research-os-retired`; the rollout's `--backup` folder holds the previous
runtime, companion and every session's old HTML. Restoring those files restores v0.9.0. Nothing here migrates your data, so there is nothing else to undo.
