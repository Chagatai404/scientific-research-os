# Live lecture (v0.9.6)

How a tutor agent gives a lecture in real time on the blackboard, with the Kokoro voice, and takes written or spoken questions at any moment. It works with any agent that can run commands; nothing here names a model. `HTML_SESSION_PROTOCOL.md` owns sessions, `VOICE_PROTOCOL.md` owns the voices, `TUTORING_GATES.md` still decides when a teaching block may start and when a probe is due.

## What the learner needs running (check, never assume)

| Piece | Check | Start (ask the researcher first; installing or starting a process is theirs to approve) |
|---|---|---|
| The Obsidian view with the companion plugin and the current runtime | the session page shows a board with a "Voice" menu offering "Live voice" | `python scripts/install.py --html-companion`, then reload Obsidian |
| Live voice (the tutor speaks) | `python scripts/voice.py worker-status --dir <vault>/.research-os/voice --tts` exits 0 | `python scripts/voice.py tts-worker --env <kokoro env> --dir <vault>/.research-os/voice --voice model_dir=<Kokoro folder>` |
| Spoken questions | `python scripts/voice.py worker-status --dir <vault>/.research-os/voice` exits 0 | `python scripts/voice.py worker --env <whisper env> --dir <vault>/.research-os/voice` |

**Bring them up with one command, before the learner starts:** `python scripts/html_sessions.py --root <vault> start <session> --holder <name>` runs `voice.py up --dir <vault>/.research-os/voice`. It starts each missing worker **detached** from your shell, so it does not end with a single command (a worker survived its launcher in testing; why the voice used to read "off" between turns is not confirmed, and a worker may still end when the agent session itself ends, so run `start` at the beginning of every session), waits until each lease says `ready`, and prints `ready: true` only when both are. The first time, name the environments once with `voice.py up --dir <vault>/.research-os/voice --env <kokoro env> --env <whisper env> --voice model_dir=<Kokoro folder> --save`; later runs need no arguments. `voice.py up --check` starts nothing. Logs are in `<vault>/.research-os/voice/logs/`. Nothing is installed; a worker that cannot start is reported with the end of its log, and the lecture then offers captions or the device voice and says so.

**Never open a browser.** The session is in Obsidian, which the learner already has open. Do not open Chrome or any browser, a `file://` page or a local server to show, check or "verify" a lecture unless the researcher asks for that in the message. Verify with `board_script.py check`, `board-position` and the session state.

If a worker is not running the lecture still plays (device voice or captions) and typed questions still work; say which, once, and go on. A standalone export has no host, so no live voice and no asking aloud there.

## Starting

1. Read the resume brief (`html_sessions.py context`) and do the workflow's own session start, as for any session. Never lecture from chat memory.
2. Create the session with a board widget **left open**: `{"id": "lecture", "kind": "board", "script": {"board_schema": 1, "open": true, "steps": [...]}}`, placed in the lesson with `<!-- ros-widget: lecture -->`. Write the first two or three steps. The page opens at "Press Start"; the learner presses it (the browser only lets audio start after a click).
   A session that already exists without a board (started before this was installed, or in prose) gets one with `html_sessions.py update <session> --source change.json`, where the JSON holds `widgets` (the existing ones plus the board) and `text` with the `<!-- ros-widget: lecture -->` marker added where the lecture belongs. Do this instead of carrying on in prose.
3. Renew your lease while you work (`wait --holder`), so the page can say a tutor is connected.

## The loop

- **Stay ahead of the learner, not far ahead.** `python scripts/html_sessions.py --root <vault> board-position <session>` says which step they are on, its state (`playing`, `paused`, `waiting`, `done`) and how old that report is. Keep two or three unplayed steps in front of them; when fewer remain, write the next ones with `board-append <session> lecture --source steps.json`. Writing far ahead makes an answer to a question wait behind them; writing too little leaves the board saying "Waiting for the tutor".
- **A step is one spoken sentence and what is drawn while it is said** (`say`, up to 600 characters; keep it to a breath or two). Say formulas in words ("L of w equals w squared minus four w plus five"); write the TeX on the board with `math`. Cues start `delay` seconds into the sentence, so write, draw and highlight as the words arrive. Use `write`, `math`, `arrow`, `circle`, `rect`, `axes`, `plot`, `dot` and `move`, `highlight` and `erase` (`board_script.py` lists the grammar; `examples/board-lecture-gradient.json` is a worked lecture). **Compute plotted points and positions from the formula or the data**; never draw a curve by eye and call it the result.
- **Explain everything on the board and in speech.** External links are supplementary; the lecture must stand without them.
- **Ids are unique across the whole script** (steps and the things they draw). Never change a step the learner has started: the board then shows "The tutor revised the lecture" and waits for Replay. Add new steps instead.
- **Probes and checks** follow the tutoring gates: post a question with `add-question` at the point the lecture reaches it, then carry on or wait as the gate says.

## A question at any time (typed, or spoken and corrected by the learner)

A spoken question arrives exactly like a typed one: an open question the learner sent. The lecture on the page has already paused while they asked.

1. `wait <session> --holder <name> --timeout 60` returns on their Send. Read the question from `open_questions` in the state.
2. `board-position` tells you where they are. Write the answer as new steps and put them right after that step: `board-append <session> lecture --source answer.json --after <step id>`. The board plays them next and then continues with what was already written. If the answer changes what comes next, say so in speech and follow with revised steps added after the answer (new ids).
3. Record the answer in the Q&A history with `answer` (a short written version of what you said, with the formula and the key reason). The board is the explanation; the history is the record. As always, answering a question is not evidence that the learner understands it.
4. Keep `open: true` while you are still lecturing. End with `--open false` on the last steps, so the board finishes instead of waiting.

## Honest limits

The first sentence of a lecture takes about a second and a half to speak after it is asked for; later sentences are ready ahead of time. Your own turns, not the voice, are the slow part of an answer: keep a short buffer so a question does not wait behind long unplayed material. Nothing the board or the voice does is evidence of learning. Tested with scripted hosts and real browsers and workers, not yet in a real Obsidian window with a real microphone.

## Staged sessions

In a session with a plan the lecture reports its position as the widget `plan-lecture`; `board-position <session>` returns it with the `segment` the step belongs to. The page freezes the
lecture path at its first step and resumes from `lecture-step:` checkpoints after a reload. Written probe answers reach you through `wait` as `plan-answer` items; review them with
`plan-review` (see `HTML_SESSION_PROTOCOL.md`). Do not rewrite the plan under a lecture that has started unless `--allow-reroute` is truly what you mean.
