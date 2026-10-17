"""Runs inside a speech engine's own virtual environment: synthesize or transcribe one file and print one line of JSON about what happened.

This file is the only code that imports an engine (Piper, Chatterbox, Kokoro, faster-whisper). ``voice.py`` starts it with the engine environment's Python and reads
its JSON; nothing else in Research OS imports an engine. Text is passed in a file and results come back as ASCII-escaped JSON, because a Windows console
cannot be trusted with Turkish characters.

    python voice_adapter.py info
    python voice_adapter.py synth --provider piper --model tr_TR-dfki-medium.onnx --text-file in.txt --out out.wav
    python voice_adapter.py synth --provider chatterbox --lang tr --device cpu --text-file in.txt --out out.wav
    python voice_adapter.py synth --provider kokoro --model-dir DIR --text-file in.txt --out out.wav
    python voice_adapter.py synth --provider kokoro --model-dir DIR --batch-file items.json     (many texts, one model load)
    python voice_adapter.py transcribe --model small --lang tr --audio in.wav --out words.json --words
    python voice_adapter.py serve --dir VOICE_DIR --model small --device cuda     (a persistent worker for spoken questions; stop it by creating VOICE_DIR/stop)
"""
from __future__ import annotations
import argparse
import importlib.metadata
import importlib.util
import json
import re
import sys
import time
import wave
from pathlib import Path

ENGINES = {'piper': 'piper-tts', 'chatterbox': 'chatterbox-tts', 'kokoro_onnx': 'kokoro-onnx', 'faster_whisper': 'faster-whisper'}
SENTENCE_END = r'(?<=[.!?:])\s+'
KOKORO_MODEL, KOKORO_VOICES = 'kokoro-v1.0.onnx', 'voices-v1.0.bin'


def emit(data: dict, code: int = 0) -> int:
    print(json.dumps(data, ensure_ascii=True))
    return code


def fail(message: str) -> int:
    return emit({'ok': False, 'error': message}, 2)


def versions() -> dict:
    found = {}
    for module, package in ENGINES.items():
        if importlib.util.find_spec(module) is not None:
            try:
                found[module] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                found[module] = 'unknown'
    return found


def torch_state() -> dict:
    if importlib.util.find_spec('torch') is None:
        return {}
    import torch
    return {'torch': torch.__version__, 'cuda': bool(torch.cuda.is_available())}


def peak_vram_mb() -> float | None:
    if importlib.util.find_spec('torch') is None:
        return None
    import torch
    return round(torch.cuda.max_memory_allocated() / 1048576, 1) if torch.cuda.is_available() else None


def wav_seconds(path: Path) -> tuple[float, int]:
    with wave.open(str(path), 'rb') as handle:
        return handle.getnframes() / handle.getframerate(), handle.getframerate()


def synth_piper(args, text: str, out: Path) -> dict:
    from piper import PiperVoice, SynthesisConfig
    started = time.perf_counter()
    voice = PiperVoice.load(args.model, use_cuda=args.device == 'cuda')
    loaded = time.perf_counter()
    config = SynthesisConfig(length_scale=args.length_scale) if args.length_scale != 1.0 else None
    with wave.open(str(out), 'wb') as handle:
        voice.synthesize_wav(text, handle, syn_config=config)
    return {'load_seconds': round(loaded - started, 3), 'synth_seconds': round(time.perf_counter() - loaded, 3)}


def synth_chatterbox(args, text: str, out: Path) -> dict:
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    if args.device == 'cpu':
        original = torch.load
        torch.load = lambda *a, **k: original(*a, **{**k, 'map_location': torch.device('cpu')})
    started = time.perf_counter()
    model = ChatterboxMultilingualTTS.from_pretrained(device=args.device)
    loaded = time.perf_counter()
    kwargs = {'language_id': args.lang}
    if args.audio_prompt:
        kwargs['audio_prompt_path'] = args.audio_prompt
    audio = model.generate(text, **kwargs)
    # Not torchaudio.save: on Windows it needs an audio backend that may be missing ("unknown format"). A 16-bit mono WAV needs only the standard library.
    samples = audio.detach().cpu().float().clamp(-1.0, 1.0).reshape(-1).mul(32767).short().numpy()
    with wave.open(str(out), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(model.sr))
        handle.writeframes(samples.tobytes())
    return {'load_seconds': round(loaded - started, 3), 'synth_seconds': round(time.perf_counter() - loaded, 3)}


def split_sentences(text: str) -> list[str]:
    """Sentences as the researcher heard them in the blind test: split after . ! ? and a colon."""
    import re
    return [s for s in re.split(SENTENCE_END, text.strip()) if s]


def parse_blend(spec: str) -> list[tuple[str, float]]:
    """``af_heart:0.6,af_sky:0.4`` or ``af_heart``. Weights must be positive; they are scaled to sum to one."""
    parts = []
    for item in (spec or '').split(','):
        name, _, weight = item.strip().partition(':')
        if not name:
            raise ValueError(f'empty voice name in {spec!r}')
        try:
            value = float(weight) if weight else 1.0
        except ValueError:
            raise ValueError(f'weight {weight!r} for {name} is not a number') from None
        if not value > 0:
            raise ValueError(f'weight for {name} must be positive')
        parts.append((name, value))
    if not parts:
        raise ValueError('a voice is needed')
    total = sum(w for _, w in parts)
    return [(n, w / total) for n, w in parts]


def load_kokoro(args):
    """The model, the (blended) voice style and the load time. Raises with a plain message when the model files or a voice are missing."""
    from kokoro_onnx import Kokoro
    folder = Path(args.model_dir or '')
    for name in (KOKORO_MODEL, KOKORO_VOICES):
        if not (folder / name).is_file():
            raise FileNotFoundError(f'{name} not found in {folder}')
    started = time.perf_counter()
    model = Kokoro(str(folder / KOKORO_MODEL), str(folder / KOKORO_VOICES))
    loaded = time.perf_counter()
    blend = parse_blend(args.voice_blend)
    known = set(model.get_voices())
    missing = [n for n, _ in blend if n not in known]
    if missing:
        raise ValueError(f'unknown Kokoro voice {missing[0]!r}; available: {", ".join(sorted(known))}')
    style = blend[0][0] if len(blend) == 1 else sum(w * model.get_voice_style(n) for n, w in blend)
    return model, style, round(loaded - started, 3)


def render_kokoro(model, style, text: str, args, out: Path) -> dict:
    """One pass over the sentences of ``text``, a set silence between them (shorter after a colon, none after the last), one 16-bit mono WAV."""
    import numpy as np
    sentences, parts, rate, first = split_sentences(text), [], 24000, None
    started = time.perf_counter()
    for index, sentence in enumerate(sentences):
        t = time.perf_counter()
        audio, rate = model.create(sentence, voice=style, speed=args.speed, lang='en-us')
        first = first if first is not None else time.perf_counter() - t
        parts.append(np.asarray(audio, dtype=np.float32).reshape(-1))
        if index < len(sentences) - 1:
            parts.append(np.zeros(int(rate * (args.colon_gap if sentence.endswith(':') else args.gap)), dtype=np.float32))
    samples = (np.clip(np.concatenate(parts), -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(out), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(rate))
        handle.writeframes(samples.tobytes())
    return {'synth_seconds': round(time.perf_counter() - started, 3), 'sentences': len(sentences), 'first_sentence_seconds': round(first or 0.0, 3)}


def synth_kokoro(args, text: str, out: Path) -> dict:
    """One model load, one text, one WAV."""
    model, style, load_seconds = load_kokoro(args)
    return {'load_seconds': load_seconds, **render_kokoro(model, style, text, args, out)}


def synth_kokoro_batch(args) -> dict:
    """One model load for many texts: ``--batch-file`` is a JSON list of {"id", "text", "out"}. Each text is rendered exactly as ``synth_kokoro`` would
    render it alone (no silence added after the last sentence), so a recording does not depend on what it was batched with."""
    items = json.loads(Path(args.batch_file).read_text(encoding='utf-8'))
    if not isinstance(items, list) or not items or any(not isinstance(i, dict) or not {'id', 'text', 'out'} <= set(i) for i in items):
        raise ValueError('the batch file is a non-empty list of {id, text, out}')
    model, style, load_seconds = load_kokoro(args)
    results = []
    for item in items:
        done = render_kokoro(model, style, str(item['text']).strip(), args, Path(item['out']))
        seconds, rate = wav_seconds(Path(item['out']))
        results.append({'id': item['id'], 'audio_seconds': round(seconds, 3), 'sample_rate': rate, **done})
    return {'load_seconds': load_seconds, 'synth_seconds': round(sum(r['synth_seconds'] for r in results), 3), 'items': results}


# ---------------------------------------------------------------- the speech-to-text worker (spoken questions)
# A worker keeps one Whisper model loaded and answers audio dropped in `<dir>/inbox`. The host (the Obsidian plugin) records the learner's voice and writes it
# there; the worker writes `<dir>/out/<id>.json` and a lease `<dir>/worker.json` that says whether anyone is listening. The loop knows nothing about Whisper
# (it takes a function), so it is tested with a fake; only ``make_transcriber`` imports the engine.
VOICE_NAME = re.compile(r'[A-Za-z0-9_-]{1,64}\.(webm|ogg|wav)\Z')   # \Z, not $: "a.webm" followed by a newline is not a safe name
MAX_AUDIO_BYTES = 3 * 1024 * 1024
MAX_AUDIO_SECONDS = 120
MAX_PENDING = 20
OUTPUT_KEEP_SECONDS = 3600
LEASE_FILE = 'worker.json'


def add_cuda_dll_paths() -> list[str]:
    """The CUDA libraries come from pip packages (nvidia-cublas-cu12, nvidia-cudnn-cu12); Windows only finds their DLLs once their folders are searchable."""
    import os
    import site
    found = []
    for base in site.getsitepackages():
        for folder in sorted((Path(base) / 'nvidia').glob('*/bin')):
            found.append(str(folder))
            if hasattr(os, 'add_dll_directory'):
                os.add_dll_directory(str(folder))
            os.environ['PATH'] = str(folder) + os.pathsep + os.environ.get('PATH', '')
    return found


def write_json_atomic(path: Path, data: dict) -> None:
    import os
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, path)


def silent_wav(path: Path, seconds: float = 1.0, rate: int = 16000) -> None:
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(2 * int(rate * seconds)))


def make_transcriber(model_name: str, device: str, compute_type: str, language: str | None):
    """Load Whisper once and warm it up (the first GPU call takes about half a minute, so it happens before anyone is told the worker is ready).
    A GPU that fails to load or warm falls back to the CPU, and the reason is reported. Returns (transcribe(path) -> dict, details)."""
    import tempfile
    add_cuda_dll_paths()
    from faster_whisper import WhisperModel
    attempts = [(device, compute_type)] + ([('cpu', 'int8')] if device == 'cuda' else [])
    fallback, model, used = None, None, None
    for dev, comp in attempts:
        started = time.perf_counter()
        try:
            model = WhisperModel(model_name, device=dev, compute_type=comp)
            with tempfile.TemporaryDirectory(prefix='warm-') as tmp:
                warm = Path(tmp) / 'warm.wav'
                silent_wav(warm)
                list(model.transcribe(str(warm), language=language or 'en', beam_size=1)[0])
            used = (dev, comp, round(time.perf_counter() - started, 2))
            break
        except Exception as exc:  # noqa: BLE001 - the reason is part of the report
            fallback = f'{dev}: {type(exc).__name__}: {exc}'[:300]
            model = None
    if model is None:
        raise RuntimeError(fallback or 'no speech model could be loaded')

    def transcribe_file(path: Path) -> dict:
        started = time.perf_counter()
        segments, info = model.transcribe(str(path), language=language or None, beam_size=5, vad_filter=True,
                                          vad_parameters={'min_silence_duration_ms': 500})
        text = ' '.join(s.text.strip() for s in segments).strip()
        return {'text': text, 'language': info.language, 'audio_seconds': round(info.duration, 2), 'transcribe_seconds': round(time.perf_counter() - started, 2)}
    details = {'model': model_name, 'device': used[0], 'compute_type': used[1], 'warm_seconds': used[2], 'fallback_reason': fallback if used[0] != device else None}
    return transcribe_file, details


def serve_loop(directory: Path, transcribe_file, details: dict, *, now=time.time, sleep=time.sleep, poll: float = 0.25, beat: float = 2.0, settle: float = 0.6,
               keep_audio: bool = False, max_loops: int | None = None) -> dict:
    """Answer audio in ``<directory>/inbox`` until ``<directory>/stop`` appears. Returns the final counts. Never raises on a bad file: it writes an error result."""
    import os
    inbox, out = Path(directory) / 'inbox', Path(directory) / 'out'
    inbox.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    stop = Path(directory) / 'stop'
    if stop.exists():
        stop.unlink()
    lease = {'schema': 1, 'pid': os.getpid(), 'started_at': now(), 'transcribed': 0, 'failed': 0, 'last_error': None, **details}

    def publish(state: str) -> None:
        lease.update(state=state, heartbeat=now())
        write_json_atomic(Path(directory) / LEASE_FILE, lease)
    publish('ready')
    last_beat, last_clean, loops = now(), now(), 0
    while not stop.exists() and (max_loops is None or loops < max_loops):
        loops += 1
        waiting = []
        for path in inbox.iterdir():
            if not path.is_file():
                continue
            if not VOICE_NAME.match(path.name):
                path.unlink(missing_ok=True)   # nothing but a recording with a safe name belongs here
                continue
            if now() - path.stat().st_mtime < settle:
                continue                        # still being written
            waiting.append(path)
        waiting.sort(key=lambda p: (p.stat().st_mtime, p.name))
        for path in waiting[MAX_PENDING:]:
            write_json_atomic(out / f'{path.stem}.json', {'id': path.stem, 'error': 'The voice queue is full; try again in a moment.'})
            path.unlink(missing_ok=True)
        for path in waiting[:MAX_PENDING]:
            publish('busy')
            result = {'id': path.stem}
            try:
                if path.stat().st_size > MAX_AUDIO_BYTES:
                    raise ValueError(f'The recording is larger than {MAX_AUDIO_BYTES // 1048576} MB.')
                heard = transcribe_file(path)
                if heard.get('audio_seconds', 0) > MAX_AUDIO_SECONDS:
                    raise ValueError(f'The recording is longer than {MAX_AUDIO_SECONDS} seconds.')
                result.update(heard, model=lease.get('model'), device=lease.get('device'))
                lease['transcribed'] += 1
            except Exception as exc:  # noqa: BLE001 - the learner sees this message, the loop goes on
                result['error'] = f'{type(exc).__name__}: {exc}'[:300]
                lease['failed'] += 1
                lease['last_error'] = result['error']
            write_json_atomic(out / f'{path.stem}.json', result)
            if keep_audio:
                (Path(directory) / 'kept').mkdir(exist_ok=True)   # out of the inbox, or it would be heard again on the next pass
                os.replace(path, Path(directory) / 'kept' / path.name)
            else:
                path.unlink(missing_ok=True)
        if waiting:
            publish('ready')
            last_beat = now()
        elif now() - last_beat >= beat:
            publish('ready')
            last_beat = now()
        if now() - last_clean >= 60:
            for old in out.glob('*.json'):
                if now() - old.stat().st_mtime > OUTPUT_KEEP_SECONDS:
                    old.unlink(missing_ok=True)
            last_clean = now()
        sleep(poll)
    publish('stopped')
    return {'transcribed': lease['transcribed'], 'failed': lease['failed']}


def serve(args) -> int:
    import os
    directory = Path(args.dir)
    directory.mkdir(parents=True, exist_ok=True)
    stub = {'schema': 1, 'state': 'warming', 'pid': os.getpid(), 'heartbeat': time.time(), 'model': args.model, 'device': args.device}
    write_json_atomic(directory / LEASE_FILE, stub)        # visible while the model loads, so the page can say "warming up"
    try:
        transcribe_file, details = make_transcriber(args.model, args.device, args.compute_type, None if args.language == 'auto' else args.language)
    except Exception as exc:  # noqa: BLE001
        write_json_atomic(directory / LEASE_FILE, dict(stub, state='error', heartbeat=time.time(), last_error=f'{type(exc).__name__}: {exc}'[:300]))
        return fail(f'{type(exc).__name__}: {exc}'[:600])
    print(json.dumps({'ok': True, 'state': 'ready', **details}, ensure_ascii=True), flush=True)
    counts = serve_loop(directory, transcribe_file, details, keep_audio=args.keep_audio)
    return emit({'ok': True, 'stopped': True, **counts})


def transcribe(args) -> int:
    from faster_whisper import WhisperModel
    started = time.perf_counter()
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    loaded = time.perf_counter()
    segments, info = model.transcribe(args.audio, language=args.lang or None, word_timestamps=args.words, vad_filter=False, beam_size=5)
    pieces, words = [], []
    for segment in segments:
        pieces.append(segment.text.strip())
        for word in (segment.words or []):
            words.append({'w': word.word.strip(), 'start': round(word.start, 3), 'end': round(word.end, 3)})
    result = {'ok': True, 'text': ' '.join(pieces).strip(), 'language': info.language, 'language_probability': round(info.language_probability, 3),
              'duration': round(info.duration, 3), 'load_seconds': round(loaded - started, 3), 'seconds': round(time.perf_counter() - loaded, 3),
              'model': args.model, 'device': args.device, 'engine_versions': versions()}
    if args.words:
        result['words'] = words
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        result = {k: v for k, v in result.items() if k not in ('text', 'words')}
        result['written'] = str(args.out)
    return emit(result)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('info')
    p = sub.add_parser('synth')
    p.add_argument('--provider', choices=('piper', 'chatterbox', 'kokoro'), required=True)
    p.add_argument('--model-dir', help='kokoro: the folder holding kokoro-v1.0.onnx and voices-v1.0.bin')
    p.add_argument('--voice-blend', default='af_heart:0.6,af_sky:0.4', help='kokoro: voice styles and weights, e.g. af_heart:0.6,af_sky:0.4')
    p.add_argument('--speed', type=float, default=0.95, help='kokoro: below 1 is slower')
    p.add_argument('--gap', type=float, default=0.5, help='kokoro: seconds of silence after a sentence')
    p.add_argument('--colon-gap', type=float, default=0.3, help='kokoro: seconds of silence after a sentence that ends in a colon')
    p.add_argument('--model', help='piper: the .onnx voice file')
    p.add_argument('--lang', default='en')
    p.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    p.add_argument('--text-file', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--batch-file', type=Path, help='kokoro: a JSON list of {id, text, out}; the model loads once for all of them')
    p.add_argument('--length-scale', type=float, default=1.0, help='piper: above 1 is slower')
    p.add_argument('--audio-prompt', help='chatterbox: a reference voice recording')
    p = sub.add_parser('transcribe')
    p.add_argument('--audio', required=True)
    p.add_argument('--model', default='small')
    p.add_argument('--lang')
    p.add_argument('--device', default='cpu')
    p.add_argument('--compute-type', default='int8')
    p.add_argument('--words', action='store_true')
    p.add_argument('--out')
    p = sub.add_parser('serve', help='keep Whisper loaded and answer recordings dropped in <dir>/inbox (spoken questions)')
    p.add_argument('--dir', required=True)
    p.add_argument('--model', default='small')
    p.add_argument('--device', choices=('cpu', 'cuda'), default='cuda')
    p.add_argument('--compute-type', default='float16')
    p.add_argument('--language', default='en', help="a language code, or 'auto' to detect it (unreliable on a few words)")
    p.add_argument('--keep-audio', action='store_true', help='keep each recording after it is transcribed (by default it is deleted)')
    args = parser.parse_args(argv)
    try:
        if args.command == 'info':
            return emit({'ok': True, 'python': sys.version.split()[0], 'engines': versions(), **torch_state()})
        if args.command == 'transcribe':
            return transcribe(args)
        if args.command == 'serve':
            return serve(args)
        if args.batch_file:
            if args.provider != 'kokoro' or args.device != 'cpu':
                return fail('--batch-file is for Kokoro on the CPU')
            started = time.perf_counter()
            details = synth_kokoro_batch(args)
            return emit({'ok': True, 'provider': 'kokoro', 'total_seconds': round(time.perf_counter() - started, 3), 'device': 'cpu', 'engine_versions': versions(), **details})
        if not args.text_file or not args.out:
            return fail('synth needs --text-file and --out')
        text = args.text_file.read_text(encoding='utf-8').strip()
        if not text:
            return fail('the text file is empty')
        if args.provider == 'piper' and not args.model:
            return fail('piper needs --model, the voice .onnx file')
        if args.device == 'cuda':
            try:
                import torch
                torch.cuda.reset_peak_memory_stats()
            except Exception:  # noqa: BLE001 - torch absent or no GPU: the engine reports its own error
                pass
        started = time.perf_counter()
        if args.provider == 'kokoro' and args.device == 'cuda':
            return fail('Kokoro runs on the CPU build of onnxruntime here; use --device cpu')
        details = {'piper': synth_piper, 'chatterbox': synth_chatterbox, 'kokoro': synth_kokoro}[args.provider](args, text, args.out)
        seconds, rate = wav_seconds(args.out)
        total = time.perf_counter() - started
        return emit({'ok': True, 'provider': args.provider, 'audio_seconds': round(seconds, 3), 'sample_rate': rate, 'total_seconds': round(total, 3),
                     'rtf': round(details['synth_seconds'] / seconds, 3) if seconds else None, 'peak_vram_mb': peak_vram_mb(), 'device': args.device,
                     'engine_versions': versions(), **details})
    except Exception as exc:  # noqa: BLE001 - whatever the engine raises goes back as data for the caller
        return fail(f'{type(exc).__name__}: {exc}'[:600])


if __name__ == '__main__':
    raise SystemExit(main())
