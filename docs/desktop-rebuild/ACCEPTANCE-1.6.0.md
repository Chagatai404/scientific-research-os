# Desktop 1.6.0 acceptance

Verified 2026-10-29 on Windows 11 Pro, branch `release/1.6.0-guided-sessions`.

## Fixed

- Desktop sessions ran no skill. Since 1.5.0 the composer sent no mode, so every session was a read-only chat with a one-sentence
  prompt and 50 of 162 tools: no `start`, `next`, `answer`, `due` or `find`. A session now has a type (Ask, Learn, Research, Defend) that
  carries its skill and its tool grant (`ros/modes.py`), is kept by the conversation, and records the learner's own words for `answer`
  and `ask`.
- Agents were not independent in sessions. `delegate` runs the scout, verifier, adversary or librarian as its own bounded provider run
  in a fresh context with its own small tool grant.
- Lesson narration found no engine in the installed app (read-aloud found the bundled Kokoro; narration only looked at an environment
  variable). One resolver in `ros/lib/voice.py` serves read-aloud, dictation and narration.
- A migrated note filed by path showed "No readable text", so a session could not read the AMS Ecal plan, state or decisions.
  `workspace_document` reads it from the selected vault, a migrated vault or a folder in the record's `readable_roots`, in pages, with
  a disclosure block, and never from a path a node names.
- ManimGX is bundled (`voice/animation`: its own CPython 3.14 and the packages) and found by `ros/lib/animate.py` without any setting.
- Agent tasks are dispatched automatically (`ros/dispatch.py`, `runtime.Dispatcher`, Settings → Agents) within limits, never the kinds
  that end in a verdict, run an experiment or need rendering.

## Evidence

- `python -m unittest discover -s tests -p "test_*.py"`: 898 tests, OK (9 skipped).
- `python desktop/verify.py` steps frontend tests, typecheck, frontend build, the four browser journeys, the workspace benchmark and the
  packaged lifecycle: all exit 0. The browser gate caught a real regression (the session type picker pushed the graph canvas under its
  30% floor at 320 × 1000); it is fixed and the whole non-Python gate was run again after the fix.
- On the real AMS Ecal record: `find` returns the living plan, DEC-012 and the literature records; `workspace_document` returns the
  first 30,000 of 169,206 characters of the plan, 84,238 of the state and 69,112 of the decisions; a node pointing at a file outside the
  allowed folders is refused.
- The bundled voice pack builds (1.45 GB) and proves Kokoro, Whisper and ManimGX from a stripped environment. A one-scene render
  through `animate.render` with no settings produced the video, poster, key frames and registry entry (7 s at 1080p60, no GPU).
- Session tests drive a fake provider through `runtime.execute`: the whole probe, answer, close loop, the answer binding, delegation
  with a fresh context, and the grants. Dispatch tests cover the fresh context, the bound `finish`, the kinds never taken, the hourly
  limit, the pause switch, two failures, and the thread's lifecycle.

## Limits

- No session was run end to end with a real Claude or Codex model in the installed app. The loop is verified with fixture providers;
  how well a real model follows the Learn skill is not measured.
- Dispatch and delegation were verified with fixture providers; no real model has taken a task yet. On first start the dispatcher will
  work the tasks already waiting (at the time of writing 3 bundle and 13 handout tasks in Knowledge) with the model last written to.
- `visual`, `animation` and `video` tasks still need a client with a shell: an agent with record tools cannot render and look at a
  result. ffmpeg (poster frame, key frames) is the computer's, not bundled.
- A scene was rendered through the bundled ManimGX on this machine only; whether it renders on a computer with no GPU was not tested.
- Only Windows 10/11 64-bit on one machine has been run.
