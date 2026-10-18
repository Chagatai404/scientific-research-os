# Upgrading to v0.9.6

v0.9.6 adds a live blackboard to HTML sessions: the tutor lectures on a dark chalkboard in real time, speaks each sentence with a local Kokoro voice, and
takes written or spoken open questions at any moment. Installing it replaces helper scripts, skills, agents, the shared session runtime and the Obsidian
companion (the installer backs up anything it overwrites). Your notes, sessions, answers, learning history, research records and accepted evidence stay as
they are. Everything below is optional except step 1, and every command has a dry run first.

**Not yet rehearsed on a fresh machine.** The steps were exercised on fixtures, on temporary installs and once on the author's own vault. The microphone
path has been tested end to end with a recorded spoken question (Whisper on the GPU) but **not by a person speaking into a running Obsidian**; see
"What was checked, and what was not".

## Before you start

Back up the vault or commit it. Run every command without `--apply` first. Voice is optional: without it the board still lectures, using the device voice
or captions.

## Steps

1. **Install the new skills, agents and helpers** (both providers):

   ```bash
   python scripts/install.py --status
   python scripts/install.py --target all --dry-run
   python scripts/install.py --target all
   ```

   New: `board_script.py`, `references/LIVE_LECTURE.md` (the procedure any lecturing agent follows), and `board-append` / `board-position` in
   `html_sessions.py`.

2. **Roll the companion and the session runtime into the vault.** The installer refuses to overwrite a plugin or runtime that differs from the
   repository, so move the old ones aside first (a copy outside the vault is a backup):

   ```bash
   python scripts/install.py --html-companion --dry-run
   python scripts/install.py --html-companion
   ```

   Then reload the plugin in Obsidian (Settings, Community plugins, switch "Research OS HTML Sessions" off and on). Existing sessions regenerate their
   HTML projection; the Markdown and JSON are never changed. The plugin label still reads 0.3.0; its code is the new one.

3. **Optional: the voice, in its own environments.** Nothing is installed globally. Create two virtual environments and point the workers at them:

   - Kokoro (the tutor's voice): `kokoro-onnx`, and the model files in a folder you name with `--voice model_dir=<dir>`.
   - Whisper (your spoken questions): `faster-whisper`; for the GPU also `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` (the worker registers their DLLs),
     and `av<17`.

   ```bash
   python scripts/voice.py providers --env <kokoro-env>
   python scripts/voice.py tts-worker --env <kokoro-env> --dir <vault>/.research-os/voice --voice model_dir=<model-dir>
   python scripts/voice.py worker --env <whisper-env> --dir <vault>/.research-os/voice --model small --device cuda
   python scripts/voice.py worker-status --dir <vault>/.research-os/voice
   python scripts/voice.py worker-status --dir <vault>/.research-os/voice --tts
   ```

   Each worker needs about 15 seconds to load and warm up; the page says "Voice ready" afterwards. Leave both running while you study; create
   `<dir>/stop` or `<dir>/tts-stop` (or press Ctrl+C) to stop them. `--device cpu` runs Whisper without a GPU, more slowly.

4. **Optional: have an agent lecture.** The agent follows `references/LIVE_LECTURE.md`: it opens a board with `html_sessions.py`, extends it while it plays
   with `board-append`, and reads where you are with `board-position`. A session that began in prose gets a board with `html_sessions.py board-open`. The tutor skill now teaches on the board by default, so start a new agent session after installing (an agent already running keeps the skill it loaded). Any agent that can run a shell command can do this.

## What changes for you

- **A blackboard widget** (`kind: board`): dark chalk, Kalam handwriting, formulas in KaTeX, drawings, arrows, axes and plots, highlights and erasing,
  all from a small validated script (`board_schema: 1`; `scripts/board_script.py`). Nothing from outside is executed.
- **A live voice**: the page asks the Obsidian host for each sentence and plays it as it arrives (blend of the `af_heart` and `af_sky` voices, chosen by
  blind listening tests). If the worker is off or fails, the page falls back to the device voice or captions and says so once.
- **Spoken open questions**: push to talk in the question box, a transcript appears in the box, and you press Send. It is recorded as an ordinary open
  question and counts as no learning evidence. The sandboxed page never gets the microphone; the Obsidian host records and relays the audio.
- **Outside links stay supplementary.** The board explains everything itself.

## What was checked, and what was not

Checked by executed tests: the board grammar (57 shared cases in Python and in JavaScript), validation and refusals, the lecture-extension and
position commands, the host's relay of audio in both directions, the live-voice path in a real Chromium with a fake worker, installation parity, and the
documentation rules.

**Not checked, stated plainly:**

- **A person speaking into a running Obsidian.** The worker round trip was measured (a recorded question transcribed in about 2 seconds on the GPU),
  but the push-to-talk button inside Obsidian's own window was not exercised by a person.
- **Live-voice speed under load.** Kokoro runs on the CPU at roughly half real time when the machine is idle; while the full release gate ran, a sentence
  took about 10 seconds. The look-ahead prefetch hides this only on an idle machine.
- **Turkish.** English is the priority. No Turkish voice has passed a listening test; Turkish falls back to the device voice.
- **Chatterbox on a GPU** and **fitted FSRS parameters** are still not done.

## Undoing it

The installer's backups hold what it replaced: put the old plugin folder back in `<vault>/.obsidian/plugins/` and reload it. Delete
`<vault>/.research-os/voice/` to remove the worker queues (it holds only audio in transit and the worker leases, plus audio you chose to keep with
`--keep-audio`). The skills' previous versions are in the installer's backup folders beside them.
