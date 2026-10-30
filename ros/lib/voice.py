"""Narration for sessions: prepare spoken scripts, run a local speech engine, keep the audio in a content-hashed registry, transcribe, and compare engines.

Standard library only. The engines (Piper, Chatterbox, faster-whisper) live in their own virtual environments and are run through ``voice_adapter.py``;
nothing here imports one or installs one. Audio is written once and named by a hash of provider, voice and text, so unchanged text reuses its file and
changed text never overwrites an old recording. The browser's own voice (the baseline already in every session page) makes no file.

Commands: providers | prepare | speak | list | transcribe | bakeoff
A transcript is text the learner said, never evidence that they understand; it enters the normal submit-and-review path.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from array import array
from pathlib import Path

from . import speech_text
SCHEMA = 1
ADAPTER = Path(__file__).with_name('voice_adapter.py')
ENV_VARIABLE = 'RESEARCH_OS_VOICE_ENVS'
DEFAULT_TIMEOUT = 1800
GAP_SECONDS = 0.12
ENGINE_MODULE = {'piper': 'piper', 'chatterbox': 'chatterbox', 'kokoro': 'kokoro_onnx', 'whisper': 'faster_whisper'}
# The delivery the researcher chose in the blind tests of 2026-10-17 (docs/plans/v0.9.6-voice-blind-1.md): a 60/40 voice blend, a little slower than
# default, sentence by sentence with half a second of silence (0.3 s after a colon). Change a value and the narration key changes with it.
KOKORO_DEFAULTS = {'blend': 'af_heart:0.6,af_sky:0.4', 'speed': 0.95, 'gap': 0.5, 'colon_gap': 0.3}
KOKORO_MODEL_ID = 'kokoro-v1.0'

# What each provider is. Licences of engines and voices are read from the installed packages and model cards when they are reported (bake-off report), not asserted here.
PROVIDERS = {
    'browser': {'files': False, 'local': True, 'online': False, 'engine': None, 'languages': 'those the operating system installs',
                'note': 'The baseline: every session page reads aloud with the browser or Obsidian voice. It makes no file and needs nothing installed.'},
    'piper': {'files': True, 'local': True, 'online': False, 'engine': 'piper', 'voice': 'a voice .onnx file per language (--voice tr=PATH)', 'cloning': False,
              'note': 'CPU, fast. One Turkish voice (dfki) exists in the voice set. The engine package and each voice have their own licences: read them before a product ships either.'},
    'chatterbox': {'files': True, 'local': True, 'online': False, 'engine': 'chatterbox', 'voice': 'a language id; an optional reference recording clones a voice', 'cloning': True,
                   'note': 'Multilingual, including Turkish. Heavier: see the bake-off report for what it cost on this machine. Output carries an inaudible watermark (PerTh).'},
    'kokoro': {'files': True, 'local': True, 'online': False, 'engine': 'kokoro', 'cloning': False, 'languages': 'English only',
               'voice': 'model_dir=FOLDER holding kokoro-v1.0.onnx and voices-v1.0.bin; optional blend, speed, gap, colon_gap (defaults are the delivery chosen by blind test)',
               'note': 'The default English voice (82M parameters, CPU, about half real time sentence by sentence). No Turkish. Weights are Apache-2.0 per the model listings; the '
                       'phonemizer package it installs is GPL-3.0-or-later (its metadata) and kokoro-onnx and espeakng-loader state no licence in theirs: read them before an app ships it.'},
    'cloud': {'files': True, 'local': False, 'online': True, 'engine': None, 'implemented': False,
              'note': 'Declared, not built. A cloud voice would be opt-in and show the same "the text is sent to a speech service" notice the page already shows.'},
}


class VoiceError(ValueError):
    pass


# ---------------------------------------------------------------- running the adapter

_MATH_WORDS = {
    "le": "less than or equal to", "leq": "less than or equal to", "ge": "greater than or equal to", "geq": "greater than or equal to",
    "ne": "not equal to", "neq": "not equal to", "approx": "approximately", "infty": "infinity", "pi": "pi", "sigma": "sigma", "mu": "mu",
    "lambda": "lambda", "theta": "theta", "alpha": "alpha", "beta": "beta", "sum": "the sum of", "int": "the integral of", "sqrt": "square root of",
    "cdot": "times", "times": "times", "pm": "plus or minus", "to": "to", "rightarrow": "to", "in": "in",
}
_BRACED = r"\{([^{}]*)\}"


def _math_words(expr: str) -> str:
    """Spoken form of one LaTeX expression."""
    s = expr
    for _ in range(4):
        s = re.sub(r"\\[dt]?frac\s*" + _BRACED + r"\s*" + _BRACED, r" \1 over \2 ", s)
        s = re.sub(r"\\sqrt\s*" + _BRACED, r" square root of \1 ", s)
        s = re.sub(r"\\(?:text|mathrm|mathbf|operatorname)\s*" + _BRACED, r" \1 ", s)
    s = re.sub(r"\\(?:left|right)(?![A-Za-z])", " ", s)
    s = re.sub(r"\^\s*\{?\s*2\s*\}?", " squared ", s)
    s = re.sub(r"\^\s*\{?\s*3\s*\}?", " cubed ", s)
    s = re.sub(r"\^\s*\{([^{}]*)\}", r" to the power \1 ", s)
    s = re.sub(r"\^\s*(\w)", r" to the power \1 ", s)
    s = re.sub(r"_\s*\{([^{}]*)\}", r" sub \1 ", s)
    s = re.sub(r"_\s*(\w)", r" sub \1 ", s)
    s = re.sub(r"\\([A-Za-z]+)", lambda m: " " + _MATH_WORDS.get(m.group(1), m.group(1)) + " ", s)
    for sym, word in (("<=", "less than or equal to"), (">=", "greater than or equal to"), ("!=", "not equal to"),
                      ("<", "less than"), (">", "greater than"), ("=", "equals"), ("/", "over")):
        s = s.replace(sym, f" {word} ")
    s = re.sub(r"[{}\\]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def speakable(text: str) -> str:
    """Plain spoken text from Markdown and inline LaTeX, so a speech engine does not read out the marks."""
    t = str(text).replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"(```|~~~).*?(\1|\Z)", "\n(code omitted).\n", t, flags=re.S)
    t = re.sub(r"\$\$(.+?)\$\$", lambda m: " " + _math_words(m.group(1)) + " ", t, flags=re.S)
    t = re.sub(r"\\\[(.+?)\\\]", lambda m: " " + _math_words(m.group(1)) + " ", t, flags=re.S)
    t = re.sub(r"\\\((.+?)\\\)", lambda m: " " + _math_words(m.group(1)) + " ", t, flags=re.S)
    t = re.sub(r"(?<![\\\w$])\$(?=\S)([^$\n]+?)(?<=\S)\$(?![\w$])", lambda m: " " + _math_words(m.group(1)) + " ", t)
    t = re.sub(r"!\[\[([^\]]*)\]\]", "", t)
    t = re.sub(r"\[\[([^\]]*)\]\]", lambda m: m.group(1).split("|")[-1].split("#")[0] or m.group(1), t)
    t = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"(?:https?://|www\.)\S+", "", t)
    t = re.sub(r"<[^>\n]+>", "", t)
    t = re.sub(r"`+([^`]*)`+", r"\1", t)
    out = []
    for line in t.split("\n"):
        s = line.strip()
        if not s or re.fullmatch(r"([-*_])(\s*\1){2,}", s) or (re.fullmatch(r"[|:\-\s+]+", s) and "-" in s):
            out.append("")
            continue
        s = re.sub(r"^(>\s*)+", "", s)
        s = re.sub(r"^\[![^\]]*\][+-]?\s*", "", s)
        s = re.sub(r"^#{1,6}\s*", "", s)
        s = re.sub(r"^([-*+]|\d+[.)])\s+(\[[ xX]\]\s+)?", "", s)
        if s.startswith("|") or s.count("|") >= 2:
            s = ", ".join(c.strip() for c in s.strip("|").split("|") if c.strip())
        s = re.sub(r"(\*\*|__|\*|~~)", "", s)
        s = re.sub(r"(?<!\w)_|_(?!\w)", "", s)
        s = s.replace("|", ", ").replace("#", "").replace("`", "").replace("*", "").replace("$", "")
        s = re.sub(r"\s+", " ", s).strip()
        if s and s[-1] not in ".!?:;…" and not s.endswith(('."', ".”")):
            s += "."
        out.append(s)
    return re.sub(r"\s+", " ", " ".join(x for x in out if x)).strip()


def run_command(args: list, timeout: int = DEFAULT_TIMEOUT, extra_env: dict | None = None) -> dict:
    """Run a program without a shell. The one place this module starts a process, so tests replace it."""
    started = time.monotonic()
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1', TOKENIZERS_PARALLELISM='false', **(extra_env or {}))
    try:
        done = subprocess.run([str(a) for a in args], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, env=env, **({'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)} if os.name == 'nt' else {}))
    except FileNotFoundError:
        return {'code': 127, 'stdout': '', 'stderr': f'{args[0]}: not found', 'seconds': 0.0}
    except subprocess.TimeoutExpired:
        return {'code': 124, 'stdout': '', 'stderr': f'timed out after {timeout} s', 'seconds': float(timeout)}
    return {'code': done.returncode, 'stdout': done.stdout, 'stderr': done.stderr, 'seconds': round(time.monotonic() - started, 2)}


def python_of(env: Path) -> Path | None:
    for sub in ('Scripts', 'bin', ''):
        for name in ('python.exe', 'python'):
            candidate = env / sub / name if sub else env / name
            if candidate.is_file():
                return candidate
    return None


def launcher(env: Path) -> tuple[Path | None, dict]:
    """The Python and extra environment that run an engine. A normal virtual environment has its own Python; the voice pack that ships in the
    app holds only ``site-packages`` per engine and one shared relocatable Python beside them (``<pack>/python``)."""
    packages = env / 'site-packages'
    if packages.is_dir() and not python_of(env):
        shared = python_of(env.parent / 'python')
        return shared, {'PYTHONPATH': str(packages), 'PYTHONNOUSERSITE': '1', 'HF_HUB_OFFLINE': '1'}
    return python_of(env), {}


def adapter(env: Path, *args, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Run ``voice_adapter.py`` in an environment and return its JSON, or ``{'ok': False, 'error': ...}``."""
    python, extra = launcher(Path(env))
    if python is None:
        return {'ok': False, 'error': f'no Python found in {env}'}
    done = run_command([python, ADAPTER, *args], timeout=timeout, **({'extra_env': extra} if extra else {}))
    for line in reversed(done['stdout'].strip().splitlines()):
        try:
            result = json.loads(line)
            return result if isinstance(result, dict) else {'ok': False, 'error': 'unexpected adapter output'}
        except ValueError:
            continue
    return {'ok': False, 'error': (done['stderr'].strip().splitlines() or ['the adapter printed nothing'])[-1][:300]}


def voice_pack() -> Path | None:
    """The voice engines shipped inside the installed app (Python, Kokoro, faster-whisper and both models), or None.
    ROS_VOICE_PACK names one explicitly; the frozen backend looks beside itself, at <install>/resources/voice."""
    for candidate in (os.environ.get('ROS_VOICE_PACK'), Path(sys.executable).resolve().parents[2] / 'voice' if getattr(sys, 'frozen', False) else None):
        if candidate and (Path(candidate) / 'python' / 'python.exe').is_file():
            return Path(candidate)
    return None


def voice_paths() -> tuple[Path, Path, Path]:
    """Where the Kokoro environment, Kokoro model files and Whisper environment are: a path you set, else the bundled pack, else ~/voice-envs."""
    pack, base = voice_pack(), Path.home() / 'voice-envs'
    def choose(name, bundled, fallback):
        return Path(os.environ.get(name) or (pack / bundled if pack else fallback))
    return (choose('ROS_KOKORO_ENV', 'kokoro', base / 'kokoro'), choose('ROS_KOKORO_MODELS', Path('models') / 'kokoro', base / 'kokoro-models'),
            choose('ROS_WHISPER_ENV', 'whisper', base / 'whisper'))


def whisper_model() -> str:
    """The bundled 'small' model folder when there is one (no download, works offline), else the model's name."""
    pack = voice_pack()
    return str(pack / 'models' / 'whisper-small') if pack and (pack / 'models' / 'whisper-small' / 'model.bin').is_file() else 'small'


def holds(env: Path, module: str) -> bool:
    """Whether an environment folder has the package (a venv, or the pack's bare site-packages)."""
    return any((env / sub / module).exists() for sub in ('site-packages', 'Lib/site-packages', 'lib/python3.11/site-packages', 'lib/python3.12/site-packages'))


def kokoro_ready() -> tuple[Path, Path] | None:
    """The Kokoro environment and the folder of its model files when both are set up here, else None."""
    env, weights, _ = voice_paths()
    ok = holds(env, 'kokoro_onnx') and (weights / 'kokoro-v1.0.onnx').is_file() and (weights / 'voices-v1.0.bin').is_file()
    return (env, weights) if ok else None


def environments(envs: list[str] | None = None) -> list[Path]:
    """The environments to look in: those named, else RESEARCH_OS_VOICE_ENVS, else the Kokoro that came with the app."""
    named = [Path(e) for e in (envs or []) if e]
    listed = [Path(p) for p in os.environ.get(ENV_VARIABLE, '').split(os.pathsep) if p]
    ready = kokoro_ready()
    return named or listed or ([ready[0]] if ready else [])


def default_voices(provider: str) -> dict:
    """Engine settings nobody had to pass: Kokoro's model folder from the pack (or ROS_KOKORO_MODELS)."""
    ready = kokoro_ready() if provider == 'kokoro' else None
    return {'model_dir': str(ready[1])} if ready else {}


def detect(envs: list[str] | None = None) -> list[dict]:
    """Which engines each environment holds, and their versions. Reports only; nothing is installed."""
    found = []
    for env in environments(envs):
        info = adapter(env, 'info', timeout=300)
        if info.get('ok'):
            found.append({'env': env, 'engines': info.get('engines', {}), 'torch': info.get('torch'), 'cuda': info.get('cuda'), 'python': info.get('python')})
    return found


def find_env(found: list[dict], provider: str) -> dict:
    module = ENGINE_MODULE['whisper'] if provider == 'whisper' else ENGINE_MODULE.get(PROVIDERS.get(provider, {}).get('engine') or '', '')
    for entry in found:
        if module and module in entry['engines']:
            return entry
    raise VoiceError(f'no environment with {provider} was found; name one with --env or {ENV_VARIABLE}. Nothing is installed for you.')


# ---------------------------------------------------------------- audio

def read_wav(path: Path) -> tuple[array, int]:
    with wave.open(str(path), 'rb') as handle:
        if handle.getsampwidth() != 2 or handle.getnchannels() != 1:
            raise VoiceError(f'{Path(path).name}: only 16-bit mono audio is joined')
        samples = array('h')
        samples.frombytes(handle.readframes(handle.getnframes()))
        if sys.byteorder == 'big':
            samples.byteswap()
        return samples, handle.getframerate()


def resample(samples: array, source: int, target: int) -> array:
    """Linear interpolation. Only used when two voices of one narration run at different rates."""
    if source == target or not samples:
        return samples
    count = max(1, round(len(samples) * target / source))
    out = array('h')
    for i in range(count):
        position = i * (len(samples) - 1) / max(count - 1, 1)
        low = int(position)
        high = min(low + 1, len(samples) - 1)
        out.append(int(samples[low] + (samples[high] - samples[low]) * (position - low)))
    return out


def join_wavs(files: list[Path], out: Path, gap: float = GAP_SECONDS) -> dict:
    """Join mono 16-bit files with a short silence between them, at the first file's sample rate."""
    pieces = [read_wav(f) for f in files]
    rate = pieces[0][1]
    joined = array('h')
    silence = array('h', [0] * int(rate * gap))
    for index, (samples, source) in enumerate(pieces):
        if index:
            joined.extend(silence)
        joined.extend(resample(samples, source, rate))
    if sys.byteorder == 'big':
        joined.byteswap()
    with wave.open(str(out), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(joined.tobytes())
    return {'seconds': round(len(joined) / rate, 3), 'sample_rate': rate}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- the registry

def narration_key(provider: str, version: str | None, voices: dict, segments: list[dict], device: str, rate: float) -> str:
    payload = {'provider': provider, 'version': version, 'voices': voices, 'segments': segments, 'device': device, 'rate': rate}
    return sha(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


def parse_voices(pairs: list[str] | None) -> dict:
    voices = {}
    for pair in pairs or []:
        lang, _, path = pair.partition('=')
        if not lang or not path:
            raise VoiceError(f'--voice expects lang=path, not {pair!r}')
        voices[lang] = path
    return voices


def kokoro_settings(voices: dict, lang: str | None = None, device: str = 'cpu', rate: float = 1.0) -> dict:
    """The validated Kokoro delivery. Refuses before any engine runs: another language, the GPU, a missing model folder, a number that is not one."""
    if lang is not None and lang != 'en':
        raise VoiceError(f'Kokoro speaks English only; the {lang} part of this script needs another provider (a {{{{{lang}: ...}}}} span cannot be read in an English voice)')
    if device != 'cpu':
        raise VoiceError('Kokoro runs on the CPU here (--device cpu)')
    if rate != 1.0:
        raise VoiceError('--rate does not apply to Kokoro; give --voice speed=0.9')
    if not voices.get('model_dir'):
        raise VoiceError('Kokoro needs --voice model_dir=FOLDER, the folder with kokoro-v1.0.onnx and voices-v1.0.bin')
    settings = {'model_dir': voices['model_dir'], 'blend': voices.get('blend', KOKORO_DEFAULTS['blend'])}
    for name in ('speed', 'gap', 'colon_gap'):
        try:
            settings[name] = float(voices.get(name, KOKORO_DEFAULTS[name]))
        except ValueError:
            raise VoiceError(f'{name} must be a number, not {voices[name]!r}') from None
    if not 0.5 <= settings['speed'] <= 2.0 or not 0.0 <= settings['gap'] <= 5.0 or not 0.0 <= settings['colon_gap'] <= 5.0:
        raise VoiceError('speed must be 0.5 to 2 and the gaps 0 to 5 seconds')
    return settings


def kokoro_voice_id(settings: dict) -> str:
    """Everything that changes how it sounds, so a changed delivery never reuses an old recording."""
    return f'{KOKORO_MODEL_ID}:{settings["blend"]}@{settings["speed"]}/g{settings["gap"]},{settings["colon_gap"]}'


def synth_segment(entry: dict, provider: str, segment: dict, voices: dict, device: str, rate: float, out: Path, workdir: Path, index: int) -> dict:
    text_file = workdir / f'segment-{index}.txt'
    text_file.write_text(segment['text'], encoding='utf-8')
    args = ['synth', '--provider', provider, '--lang', segment['lang'], '--device', device, '--text-file', text_file, '--out', out]
    if provider == 'kokoro':
        s = kokoro_settings(voices, segment['lang'], device, rate)
        args += ['--model-dir', s['model_dir'], '--voice-blend', s['blend'], '--speed', str(s['speed']), '--gap', str(s['gap']), '--colon-gap', str(s['colon_gap'])]
    elif provider == 'piper':
        if segment['lang'] not in voices:
            raise VoiceError(f'no Piper voice for {segment["lang"]}: give --voice {segment["lang"]}=PATH')
        args += ['--model', voices[segment['lang']], '--length-scale', str(rate)]
    elif provider == 'chatterbox' and voices.get('prompt'):
        args += ['--audio-prompt', voices['prompt']]
    result = adapter(entry['env'], *args)
    if not result.get('ok'):
        raise VoiceError(f'{provider} failed on a {segment["lang"]} segment: {result.get("error")}')
    return result


def narration_identity(prepared: dict, provider: str, voices: dict, version: str | None, device: str, rate: float) -> tuple[dict, str]:
    """The voice ids and the registry key of a prepared script. One definition, so a sentence has the same key whether it is spoken alone or as a step of a board."""
    voice_ids = {seg['lang']: (Path(voices[seg['lang']]).name if provider == 'piper' and seg['lang'] in voices else seg['lang']) for seg in prepared['segments']}
    if provider == 'kokoro':
        voice_ids = {lang: kokoro_voice_id(kokoro_settings(voices)) for lang in voice_ids}
    return voice_ids, narration_key(provider, version, voice_ids, prepared['segments'], device, rate)


def write_record(root: Path, record_file: Path, wav_file: Path, key: str, provider: str, version: str | None, device: str, rate: float, lang: str,
                 voice_ids: dict, prepared: dict, info: dict, synth_seconds: float, source: dict | None = None) -> dict:
    record = {'narration_schema': SCHEMA, 'key': key, 'provider': provider, 'provider_version': version, 'device': device, 'rate': rate, 'lang': lang,
              'voices': voice_ids, 'segments': prepared['segments'], 'text_sha256': sha(prepared['text'].encode('utf-8')),
              'audio': {'file': wav_file.relative_to(root).as_posix(), 'sha256': sha(wav_file.read_bytes()), **info},
              'rtf': round(synth_seconds / info['seconds'], 3) if info['seconds'] else None, 'created': time.strftime('%Y-%m-%d'),
              'basis': 'Spoken from the script by a speech engine. A recording is not a check of the content: the script is reviewed as text.'}
    if source:
        record['source'] = source
    record_file.write_text(json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    return record


def check_directory(directory: str) -> None:
    if not directory or '\\' in directory or ':' in directory or any(p in {'', '.', '..'} for p in directory.split('/')):
        raise VoiceError('the directory is a relative path inside the vault')


def speak(root: Path, script: str, lang: str, provider: str, envs: list[str] | None = None, voices: dict | None = None, lexicon: dict | None = None,
          device: str = 'cpu', rate: float = 1.0, directory: str = 'Narration', source: dict | None = None) -> dict:
    """Prepare a script, speak it with a local engine, and register the audio. Reuses an existing recording of the same text and voice."""
    if provider not in PROVIDERS or not PROVIDERS[provider]['files']:
        raise VoiceError(f'{provider!r} makes no audio file here (use kokoro, piper or chatterbox; the browser voice needs none)')
    if not PROVIDERS[provider].get('engine'):
        raise VoiceError(f'{provider} is declared, not built')
    check_directory(directory)
    prepared = speech_text.prepare(script, lang, lexicon)
    if prepared['problems']:
        raise VoiceError('the script cannot be spoken yet: ' + '; '.join(prepared['problems']))
    if not prepared['segments']:
        raise VoiceError('the script has nothing to say')
    root, voices = Path(root).resolve(), voices or default_voices(provider)
    if provider == 'kokoro':
        for seg in prepared['segments']:
            kokoro_settings(voices, seg['lang'], device, rate)
    entry = find_env(detect(envs), provider)
    version = entry['engines'].get(ENGINE_MODULE[PROVIDERS[provider]['engine']])
    voice_ids, key = narration_identity(prepared, provider, voices, version, device, rate)
    folder = root / directory
    record_file, wav_file = folder / f'{key[:16]}.narration.json', folder / f'{key[:16]}.wav'
    if record_file.exists():
        existing = json.loads(record_file.read_text(encoding='utf-8-sig'))
        return {'key': key, 'reused': True, 'audio': existing['audio']['file'], 'seconds': existing['audio']['seconds']}
    started = time.time()
    with tempfile.TemporaryDirectory(prefix='narrate-') as tmp:
        work, parts, details = Path(tmp), [], []
        for index, segment in enumerate(prepared['segments']):
            part = work / f'part-{index}.wav'
            details.append(synth_segment(entry, provider, segment, voices, device, rate, part, work, index))
            parts.append(part)
        joined = work / 'joined.wav'
        info = join_wavs(parts, joined)
        folder.mkdir(parents=True, exist_ok=True)
        if wav_file.exists():
            raise VoiceError(f'{wav_file.name} already exists without a record; remove it or change the text')
        shutil.copyfile(joined, wav_file)
    synth_seconds = round(sum(d.get('synth_seconds', 0) for d in details), 3)
    record = write_record(root, record_file, wav_file, key, provider, version, device, rate, lang, voice_ids, prepared, info, synth_seconds, source)
    return {'key': key, 'reused': False, 'audio': record['audio']['file'], 'seconds': info['seconds'], 'rtf': record['rtf'], 'wall_seconds': round(time.time() - started, 1)}


def discover(root: Path, directory: str = 'Narration') -> list[dict]:
    folder = Path(root).resolve() / directory
    out = []
    for path in sorted(folder.glob('*.narration.json')) if folder.is_dir() else []:
        try:
            record = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and record.get('narration_schema') == SCHEMA:
            out.append(record)
    return out


# ---------------------------------------------------------------- transcription
def transcribe(audio: Path, envs: list[str] | None = None, lang: str | None = None, model: str = 'small', device: str = 'cpu', words: bool = False) -> dict:
    """Text from a recording, with word times when asked. The text is the learner's answer to review, never evidence by itself."""
    entry = find_env(detect(envs), 'whisper')
    with tempfile.TemporaryDirectory(prefix='transcribe-') as tmp:
        out = Path(tmp) / 'result.json'
        args = ['transcribe', '--audio', audio, '--model', model, '--device', device, '--out', out] + (['--lang', lang] if lang else []) + (['--words'] if words else [])
        result = adapter(entry['env'], *args)
        if not result.get('ok'):
            raise VoiceError('transcription failed: ' + str(result.get('error')))
        return json.loads(out.read_text(encoding='utf-8'))


def normalize(text: str) -> str:
    """Lower-case with Turkish dotted and dotless i handled, punctuation removed, for comparing what was said with what was meant."""
    text = text.replace('İ', 'i').replace('I', 'ı').lower()
    return ' '.join(re.findall(r'\w+', text))


def _distance(a: list, b: list) -> int:
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def error_rates(reference: str, heard: str) -> dict:
    """Word and character error rates of a transcript against the intended text. A proxy for intelligibility, not a replacement for listening."""
    ref, hyp = normalize(reference).split(), normalize(heard).split()
    ref_chars, hyp_chars = list(normalize(reference).replace(' ', '')), list(normalize(heard).replace(' ', ''))
    return {'wer': round(_distance(ref, hyp) / len(ref), 3) if ref else None, 'cer': round(_distance(ref_chars, hyp_chars) / len(ref_chars), 3) if ref_chars else None,
            'words': len(ref)}


# ---------------------------------------------------------------- bake-off

def bakeoff(samples_file: Path, outdir: Path, providers: dict, envs: list[str] | None, whisper_model: str = 'small', only: list[str] | None = None,
            lexicon: dict | None = None) -> dict:
    """Run every sample through every provider and measure what a decision needs. ``providers`` maps a provider name to
    ``{'voices': {lang: path}, 'device': 'cpu'|'cuda', 'languages': [...]}``. Audio is kept for listening; the listening rating is left blank on purpose."""
    data = json.loads(Path(samples_file).read_text(encoding='utf-8-sig'))
    outdir = Path(outdir)
    found = detect(envs)
    rows = []
    for name, config in providers.items():
        entry = find_env(found, name)
        folder = outdir / name
        folder.mkdir(parents=True, exist_ok=True)
        for sample in data['samples']:
            if (only and sample['id'] not in only) or sample['lang'] not in config.get('languages', [sample['lang']]):
                continue
            prepared = speech_text.prepare(sample['script'], sample['lang'], lexicon)
            row = {'provider': name, 'sample': sample['id'], 'kind': sample['kind'], 'lang': sample['lang'], 'device': config.get('device', 'cpu'),
                   'words': speech_text.words(prepared['text']), 'problems': prepared['problems']}
            if prepared['problems']:
                rows.append(dict(row, error='; '.join(prepared['problems'])))
                continue
            with tempfile.TemporaryDirectory(prefix='bake-') as tmp:
                parts, details = [], []
                try:
                    for index, segment in enumerate(prepared['segments']):
                        part = Path(tmp) / f'part-{index}.wav'
                        details.append(synth_segment(entry, name, segment, config.get('voices', {}), config.get('device', 'cpu'), 1.0, part, Path(tmp), index))
                        parts.append(part)
                    target = folder / f'{sample["id"]}.wav'
                    info = join_wavs(parts, target)
                except VoiceError as exc:
                    rows.append(dict(row, error=str(exc)))
                    continue
            synth = round(sum(d['synth_seconds'] for d in details), 3)
            row.update({'audio_seconds': info['seconds'], 'synth_seconds': synth, 'rtf': round(synth / info['seconds'], 3),
                        'cold_start_seconds': round(max(d['load_seconds'] for d in details), 3), 'peak_vram_mb': max((d.get('peak_vram_mb') or 0) for d in details) or None,
                        'engine_versions': details[0].get('engine_versions'), 'audio': target.relative_to(outdir).as_posix(), 'spoken_text': prepared['text']})
            try:
                heard = transcribe(target, envs, sample['lang'], whisper_model)
                # Whisper writes digits where the script says words; spell them the same way before comparing, or the voice is blamed for the formatting.
                row.update({'heard': heard['text'], 'heard_language': heard['language'],
                            **error_rates(prepared['text'], speech_text.spell_numbers(heard['text'], sample['lang']))})
            except VoiceError as exc:
                row['round_trip_error'] = str(exc)
            rows.append(row)
    report = {'bakeoff_schema': 1, 'whisper_model': whisper_model, 'created': time.strftime('%Y-%m-%d'), 'rows': rows,
              'decision_rule': ['Turkish intelligibility to your ear', 'runs on this machine (CPU or the 6 GB GPU)', 'licence permits the future app', 'stability'],
              'caveat': 'Word error rate against a Whisper transcript measures how well Whisper recovered the text, not how a person hears it; it can hide a voice that is clear to Whisper and odd to a listener. Your rating comes first.'}
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    (outdir / 'report.md').write_text(report_markdown(report), encoding='utf-8', newline='\n')
    return report


def report_markdown(report: dict) -> str:
    lines = ['# Voice bake-off', '', f'Speech-to-text for the round trip: faster-whisper `{report["whisper_model"]}`. {report["caveat"]}', '',
             '| Provider | Sample | Lang | Audio s | Synth s | RTF | Cold start s | VRAM MB | WER | CER | Your rating (1-5) |', '|---|---|---|---|---|---|---|---|---|---|---|']
    for r in report['rows']:
        if r.get('error'):
            lines.append(f'| {r["provider"]} | {r["sample"]} | {r["lang"]} | failed: {r["error"][:80]} | | | | | | | |')
            continue
        lines.append(f'| {r["provider"]} | {r["sample"]} | {r["lang"]} | {r["audio_seconds"]} | {r["synth_seconds"]} | {r["rtf"]} | {r["cold_start_seconds"]} | '
                     f'{r["peak_vram_mb"] or "-"} | {r.get("wer", "-")} | {r.get("cer", "-")} | |')
    lines += ['', 'Decision rule, in order: ' + '; '.join(report['decision_rule']) + '.', '']
    return '\n'.join(lines)


# ---------------------------------------------------------------- command line

def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)

    def common(p):
        p.add_argument('--env', action='append', default=[], help=f'a virtual environment holding an engine (repeatable; or {ENV_VARIABLE})')

    p = sub.add_parser('providers', help='what each provider is and which engines are installed here')
    common(p)
    p = sub.add_parser('prepare', help='the segments a script would be spoken as (exit 1 if a span cannot be said)')
    p.add_argument('--lang', required=True)
    p.add_argument('--text')
    p.add_argument('--text-file', type=Path)
    p.add_argument('--lexicon', type=Path)
    p = sub.add_parser('speak', help='speak a script and register the audio')
    common(p)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--provider', choices=('piper', 'chatterbox', 'kokoro'), required=True)
    p.add_argument('--lang', required=True)
    p.add_argument('--text')
    p.add_argument('--text-file', type=Path)
    p.add_argument('--voice', action='append', default=[], help='lang=path (Piper voices), prompt=path (Chatterbox reference recording), or for Kokoro model_dir=FOLDER '
                   'with optional blend=af_heart:0.6,af_sky:0.4 speed=0.95 gap=0.5 colon_gap=0.3')
    p.add_argument('--lexicon', type=Path)
    p.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    p.add_argument('--rate', type=float, default=1.0)
    p.add_argument('--directory', default='Narration')
    p = sub.add_parser('list', help='recordings in the registry')
    p.add_argument('--root', type=Path, required=True)
    p = sub.add_parser('transcribe', help='text from a recording')
    common(p)
    p.add_argument('audio', type=Path)
    p.add_argument('--lang')
    p.add_argument('--model', default='small')
    p.add_argument('--device', default='cpu')
    p.add_argument('--words', action='store_true')
    p = sub.add_parser('bakeoff', help='run the sample scripts through each provider and write a report')
    common(p)
    p.add_argument('--samples', type=Path, default=Path(__file__).resolve().parents[2] / 'assets/speech/bakeoff-samples.json')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--piper-voice', action='append', default=[], help='lang=path')
    p.add_argument('--chatterbox-device', choices=('cpu', 'cuda'))
    p.add_argument('--kokoro-model-dir', type=Path, help='the folder holding kokoro-v1.0.onnx and voices-v1.0.bin (use with --providers kokoro)')
    p.add_argument('--providers', default='piper,chatterbox')
    p.add_argument('--whisper-model', default='small')
    p.add_argument('--only', action='append', default=[])
    p.add_argument('--lexicon', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'providers':
            print(json.dumps({'providers': PROVIDERS, 'installed': [{**e, 'env': str(e['env'])} for e in detect(args.env)]}, indent=2, ensure_ascii=False))
            return 0
        if args.command in ('prepare', 'speak'):
            script = args.text if args.text is not None else (args.text_file.read_text(encoding='utf-8') if args.text_file else None)
            if script is None:
                raise VoiceError('give --text or --text-file')
            lexicon = speech_text.load_lexicon(args.lexicon)
            if args.command == 'prepare':
                prepared = speech_text.prepare(script, args.lang, lexicon)
                print(json.dumps(prepared, indent=2, ensure_ascii=False))
                return 1 if prepared['problems'] else 0
            print(json.dumps(speak(args.root, script, args.lang, args.provider, args.env, parse_voices(args.voice), lexicon, args.device, args.rate, args.directory),
                             indent=2, ensure_ascii=False))
            return 0
        if args.command == 'list':
            print(json.dumps([{k: r[k] for k in ('key', 'provider', 'lang', 'created')} | {'audio': r['audio']['file'], 'seconds': r['audio']['seconds']} for r in discover(args.root)], indent=2))
            return 0
        if args.command == 'transcribe':
            print(json.dumps(transcribe(args.audio, args.env, args.lang, args.model, args.device, args.words), indent=2, ensure_ascii=False))
            return 0
        if args.command == 'bakeoff':
            providers = {}
            for name in [n for n in args.providers.split(',') if n]:
                if name == 'piper':
                    voices = parse_voices(args.piper_voice)
                    providers[name] = {'voices': voices, 'device': 'cpu', 'languages': sorted(voices)}
                elif name == 'chatterbox':
                    providers[name] = {'voices': {}, 'device': args.chatterbox_device or 'cpu', 'languages': ['en', 'tr']}
                elif name == 'kokoro':
                    providers[name] = {'voices': {'model_dir': str(args.kokoro_model_dir)} if args.kokoro_model_dir else {}, 'device': 'cpu', 'languages': ['en']}
                else:
                    raise VoiceError(f'{name} is not a provider that can be compared')
            report = bakeoff(args.samples, args.out, providers, args.env, args.whisper_model, args.only, speech_text.load_lexicon(args.lexicon))
            print(report_markdown(report))
            return 0
    except (VoiceError, speech_text.Unspeakable, OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
