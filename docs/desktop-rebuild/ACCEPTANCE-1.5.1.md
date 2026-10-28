# Desktop 1.5.1 acceptance

Verified 2026-10-28 on Windows 11 Pro (AMD Ryzen 7 7735HS, 16 GB), branch `fix/voice-and-composer`.

## Fixed

- Kokoro read-aloud and dictation failed in the installed app with "Optional worker unavailable": the frozen backend did not ship
  `voice_adapter.py`. It does now (`desktop/backend.spec`), and the worker reports an engine's own error when it has one.
- The reasoning-effort slider no longer breaks the composer layout (checked at 1280 and 420 px).

## Bundled

- `desktop/build-voice.py` assembles a self-contained voice pack into `resources/voice/` (about 1.2 GB): Python 3.12, Kokoro and
  faster-whisper (CPU only), both models, licences. The installer is about 0.95 GB (1.6 GB installed).
- Handout PDFs print with the app's own Chromium (`desktop/printer.cjs`); no Chrome, Edge or LaTeX is needed inside the app.

## Evidence

- From source with an empty home folder and `ROS_VOICE_PACK` set: Kokoro spoke a sentence and Whisper transcribed it back exactly.
- From the packaged backend (`win-unpacked`) with an empty home folder, a minimal PATH and no `ROS_*` variables: the catalog reports
  both engines ready; speech took about 8 s and transcription about 9 s, and the transcript matched the sentence word for word.
- An Electron-printed handout page rendered identically to Chrome's (same page size, headings, math, footer).
- `tests/test_ros_voice_bundle.py`, `tests/test_ros_app_printer.py`, the frontend tests and the full `python desktop/verify.py` gate
  (results in the release notes).

## Limits

- Only Windows 10/11 64-bit on one machine has been run. Lower-spec machines are untested.
- Manim animations and the Codex or Claude CLIs are not bundled; model sign-in is the person's own.
- The voice pack's GPL parts (phonemizer, espeak-ng) ship as separate files with their licence texts; the project is free and open source.
