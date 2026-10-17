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
"""
from __future__ import annotations
import argparse
import importlib.metadata
import importlib.util
import json
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
    args = parser.parse_args(argv)
    try:
        if args.command == 'info':
            return emit({'ok': True, 'python': sys.version.split()[0], 'engines': versions(), **torch_state()})
        if args.command == 'transcribe':
            return transcribe(args)
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
