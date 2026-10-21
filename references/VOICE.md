# Voice

Spoken lessons in English and Turkish: scripts written to be heard, formulas said in words, recordings kept in the vault, and an optional spoken answer. `TEACHING_FORMAT.md` still owns what a
Teaching Card is. Nothing here installs an engine; engines live in their own virtual environments and are found by name.

## Pieces

| Piece | What it does |
|---|---|
| `ros.lib.speech_text` | Says formulas in words (English, Turkish), marks language spans, applies a pronunciation lexicon, spells digits. Standard library only. |
| `ros.lib.voice` | Prepares a script, runs an engine, joins the audio, keeps it in the narration registry, transcribes, runs the bake-off. Standard library only. |
| `ros/lib/voice_adapter.py` | The only file that imports an engine; run with the engine environment's Python. Prints one line of ASCII JSON. |
| Card `spoken` / `audio` | The script (per language) and the recording (per language). The page plays the recording on request and otherwise reads the section with the device voice. |

## Writing a spoken script

Plain words, plus spans: `{{math: \frac{a}{b}}}` is a formula said in the script's language; `{{en: gradient descent}}` or `{{tr: ...}}` is spoken by that language's voice (code-switching, one
file in the end). Digits in plain text are spelled (`3 events` becomes `three events`; Turkish `%5` and `3,14` become `yüzde beş`, `üç virgül bir dört`; an English `1,000` is left to the engine, because a
thousands separator is not guessed). `python -m ros.lib.voice prepare --lang tr --text-file script.txt` shows exactly what would be said and exits 1 if a span cannot be said.

**What the formula rules cover:** numbers, letters, Greek, `+ - = < > / *`, fractions (a simple one as "a over b", otherwise "the fraction with numerator ... and denominator ... , end fraction"), powers
(squared, cubed, "to the n", and "to the power of ..., end of power" when the exponent is more than one unit), subscripts, roots, sums, products, integrals, limits, trigonometric and logarithm functions,
absolute value, vectors, hats, bars, `\in`, `\leq`, `\approx` and a few more. Parentheses are spoken literally ("open parenthesis ... close parenthesis"); `f(x)` is "f of x" only for the letters f, g, h.
**What they refuse, with the reason:** matrices and aligned equations, line breaks, an unpaired `|`, a prime, an arrow outside a limit, `\forall`, `\exists`, `\mapsto`, `:` and anything unknown. You write those in
words. The rules say a formula flat and literally; they do not decide what an ambiguous formula means, and a long sum's scope runs to the end of its group.

**Known weak spots.** The Turkish phrasings were written without review by a native speaker. The standard Turkish letter name for `v` is "ve", which is also the word for "and": "m v kare" is said "me ve kare".
Word order for `\sum`, `\int` and `\lim` in Turkish avoids suffixes ("1 ile sonsuz arasında") because suffix harmony is not modelled. Units are not recognised; write them as words or `\text{}`.

## Providers

`python -m ros.lib.voice providers [--env DIR ...]` lists the manifest and which engines the named environments hold. `RESEARCH_OS_VOICE_ENVS` names environments without a flag.

| Provider | Languages | Local | Engine licence | Voice or model licence | Measured here |
|---|---|---|---|---|---|
| browser (the page's own) | whatever the device installs | yes | n/a | n/a | the baseline; no file |
| Piper 1.8.0 | English and one Turkish voice (`dfki`) | CPU | **GPL-3.0-or-later** (package metadata) | the `dfki` Turkish voice: dataset **CC BY-NC-SA 4.0**, non-commercial (its model card) | see below |
| **Kokoro-82M** (`kokoro-onnx` 0.6.1), **the default English voice** | English only (the model has other languages' voices; none for Turkish) | CPU, about 0.4 to 0.6 real time sentence by sentence | package metadata states no licence for `kokoro-onnx` or `espeakng-loader`; its `phonemizer` is GPL-3.0-or-later | weights Apache-2.0 per the model listings | chosen by blind test, see below |
| Chatterbox Multilingual 0.1.7 | 23 languages including Turkish | CPU here; GPU untested | MIT (package metadata) | MIT (model page); inaudible PerTh watermark in every output | see below |
| cloud voices | - | no | - | - | declared, not built; would be opt-in with the existing "text is sent to a speech service" notice |

**Measured on this machine** (2026-10-16, idle, Whisper `small` for the round trip; engine called once per language segment, model loaded each call):

| | Real-time factor | Cold start per call | Word error rate, English | Word error rate, Turkish |
|---|---|---|---|---|
| Piper (CPU) | 0.049 to 0.113 (a 47 s passage in 2.4 s) | 6.5 to 7.1 s | 0 to 0.12 | 0.08 to 0.27 |
| Chatterbox (CPU, four short samples) | 7.4 to 13.3 (a 9 s sentence in 75 to 111 s) | 22 to 31 s | 0 and 0.094 | 0.16 and 0.233 |

Not measured: Chatterbox on the GPU (6 GB card, about 2 GB free, 4 GB held by other processes, and a CUDA build of PyTorch was not installed), Chatterbox on the long passages and the code-switched sample
(too slow to run on CPU), Piper's GPU mode, other voices, and any rating beyond one. Word error rate against a Whisper transcript measures how
well Whisper recovered the text, not how a person hears it: a voice can read clean to Whisper and odd to an ear, and Whisper's own Turkish accuracy was not measured on reference recordings.

**Listening verdict (first criterion).** Heard by the researcher, 2026-10-16: **both engines, in both English and Turkish, sound unnatural** in the flow of the speech, the pauses, the tone and the stress. English was no better than Turkish, and Piper's English voice (`lessac`) is one of its best, so this is the ceiling of these local open voices at default settings, not a Turkish-only or a text-preparation fault. Nothing was tuned (pause length, variation settings, Chatterbox's expressiveness controls, a reference recording) and Chatterbox was run on CPU only. The raw reports are `docs/plans/v0.9.5-s8-bakeoff-piper.md` and `-chatterbox.md`. **Superseded 2026-10-17: Kokoro-82M passed the next listening test (the sections "Blind listening test" and "The live voice" below), so it is now the English teaching voice; Piper and Chatterbox stay what this paragraph says they are, and Turkish has no passing voice yet.** Until something passes for a language, its voices are for drafts and for checking a script, not the teaching voice; the browser voice is the baseline and on this machine it is one old Windows Turkish voice (Microsoft Tolga) and no English voice in the in-app browser.

**Reading of the results, not a decision.** Piper is fast enough to generate on a CPU and its Turkish is recovered by Whisper at 8 to 27% word error, but its Turkish voice cannot ship in a product (non-commercial
dataset) and its engine is GPL. Chatterbox's licences fit a product and its Turkish is recovered at 16 to 23%, but on CPU it is 7 to 13 times slower than real time, so it is only usable with a GPU that has room for it.
The working hypothesis in the plan (Piper local tier, Chatterbox quality tier) therefore stands only for personal use today. The decision rule is, in order: Turkish intelligibility to your ear; runs on this
machine; licence permits the future app; stability.

## The chosen delivery

**The Kokoro provider** speaks the delivery the researcher chose in two blind rounds (`docs/plans/v0.9.6-voice-blind-1.md`): voice styles `af_heart` 60% and `af_sky` 40%, speed 0.95, sentence by sentence, 0.5 s of silence after a sentence and 0.3 s after one that ends in a colon.
`python -m ros.lib.voice speak --root <bundle> --directory audio --provider kokoro --env <kokoro env> --lang en --text-file s.txt --voice model_dir=<folder with kokoro-v1.0.onnx and voices-v1.0.bin>` runs it; `--voice blend=af_heart:0.6,af_sarah:0.4`, `speed=`, `gap=` and `colon_gap=` change the delivery, and each change makes a new recording (the model folder's location does not). The whole script goes to the engine in one call, so the model loads once. It refuses before any engine runs: a non-English segment (including a `{{tr: ...}}` span), `--device cuda`, `--rate` (use `speed=`) and a missing model folder. Checked against the real engine: the paragraph rated in round 2 comes out with the same 705,440 frames and a largest sample difference of 2 out of 32,768. Its model files are not downloaded for you (the 325 MB `kokoro-v1.0.onnx` and the 28 MB `voices-v1.0.bin` come from the kokoro-onnx GitHub release); install the engine in its own environment.

## Recordings in a bundle

`bundle_voice` (or `python -m ros.lib.voice speak --root <bundle> --directory audio ...`) speaks each narration
segment and writes `audio/<key>.wav` with `<key>.narration.json` (`narration_schema: 1`: provider and version, voice
file names, the segments, the audio hash, real-time factor). The key hashes provider, version, voices, segments,
device and rate: unchanged text reuses the file, changed text makes a new one, nothing is overwritten. **A recording
is not a check of the content**; the script is reviewed as text. The portal plays a segment's recording when it is
shown, at the learner's chosen speed, and Replay plays it again.

## Spoken answers

`python -m ros.lib.voice transcribe recording.wav --lang tr [--words]` runs faster-whisper locally. The transcript is the learner's *answer to review*, entered through the normal submit path; it is never evidence
that they understand. Turkish accuracy of `small` is unmeasured on real learner speech.

## Not done

Word-level highlighting from alignment, compressed audio, a cloud provider, and a persistent engine worker (each
render starts a process and loads the model; preparation is unattended, so this costs time, not the learner's).
