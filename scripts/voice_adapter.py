"""Runs inside a speech engine's own virtual environment: synthesize or transcribe one file and print one line of JSON about what happened.

This file is the only code that imports an engine (Piper, Chatterbox, faster-whisper). ``voice.py`` starts it with the engine environment's Python and reads
its JSON; nothing else in Research OS imports an engine. Text is passed in a file and results come back as ASCII-escaped JSON, because a Windows console
cannot be trusted with Turkish characters.

    python voice_adapter.py info
    python voice_adapter.py synth --provider piper --model tr_TR-dfki-medium.onnx --text-file in.txt --out out.wav
    python voice_adapter.py synth --provider chatterbox --lang tr --device cpu --text-file in.txt --out out.wav
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

ENGINES = {'piper': 'piper-tts', 'chatterbox': 'chatterbox-tts', 'faster_whisper': 'faster-whisper'}


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
    p.add_argument('--provider', choices=('piper', 'chatterbox'), required=True)
    p.add_argument('--model', help='piper: the .onnx voice file')
    p.add_argument('--lang', default='en')
    p.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    p.add_argument('--text-file', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
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
        details = (synth_piper if args.provider == 'piper' else synth_chatterbox)(args, text, args.out)
        seconds, rate = wav_seconds(args.out)
        total = time.perf_counter() - started
        return emit({'ok': True, 'provider': args.provider, 'audio_seconds': round(seconds, 3), 'sample_rate': rate, 'total_seconds': round(total, 3),
                     'rtf': round(details['synth_seconds'] / seconds, 3) if seconds else None, 'peak_vram_mb': peak_vram_mb(), 'device': args.device,
                     'engine_versions': versions(), **details})
    except Exception as exc:  # noqa: BLE001 - whatever the engine raises goes back as data for the caller
        return fail(f'{type(exc).__name__}: {exc}'[:600])


if __name__ == '__main__':
    raise SystemExit(main())
