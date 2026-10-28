"""Assemble the voice pack that ships inside the installer: a relocatable Python, the Kokoro and faster-whisper packages,
both models and their licences, so read-aloud and dictation work on a computer that has nothing installed.

Layout written to desktop/voice/ (copied to <install>/resources/voice/ by electron-builder):

    python/                  CPython 3.12 (standalone, relocatable), stdlib only
    kokoro/site-packages/    kokoro-onnx, onnxruntime, numpy, espeakng-loader, phonemizer, soundfile ...
    whisper/site-packages/   faster-whisper, ctranslate2, onnxruntime, av, tokenizers, numpy ... (CPU only: no CUDA libraries)
    models/kokoro/           kokoro-v1.0.onnx, voices-v1.0.bin
    models/whisper-small/    the CTranslate2 'small' multilingual model
    LICENSES.txt             package and model licences

The sources are the engine environments of the machine that builds the installer (default ~/voice-envs, override with
ROS_VOICE_SRC): kokoro/, whisper/, kokoro-models/ and the Hugging Face cache for Systran/faster-whisper-small. Nothing is
downloaded here. Run: python desktop/build-voice.py [--check]
"""
from __future__ import annotations
import argparse
import email
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'voice'
SRC = Path(os.environ.get('ROS_VOICE_SRC') or Path.home() / 'voice-envs')
SKIP_TOP = {'__pycache__', 'nvidia', '_virtualenv.py', '_virtualenv.pth', 'test', 'tests', 'docs', 'pip', 'setuptools', 'pkg_resources'}
SKIP_STDLIB = {'__pycache__', 'test', 'tests', 'idlelib', 'tkinter', 'turtledemo', 'lib2to3', 'ensurepip', 'site-packages', 'turtle.py', 'pydoc_data'}
LICENCE_NOTES = """Voice pack licences
===================

Models
- Kokoro v1.0 (kokoro-v1.0.onnx, voices-v1.0.bin): Apache-2.0 per the hexgrad/Kokoro-82M model card.
- faster-whisper small (Systran/faster-whisper-small, a CTranslate2 conversion of OpenAI Whisper small): MIT.

Programs that are not MIT/BSD/Apache and are shipped here as separate files you may replace
- phonemizer (GPL-3.0-or-later) and the espeak-ng data/library inside espeakng-loader (GPL-3.0-or-later) are used by Kokoro to turn text into
  phonemes. They run in a separate Python process started by Research OS and are not linked into it. Their licence texts are below and
  their source is available from their projects (https://github.com/bootphon/phonemizer, https://github.com/espeak-ng/espeak-ng).

Python packages (name, version, licence as declared in the package metadata)
"""


def base_python() -> Path:
    for line in (SRC / 'kokoro' / 'pyvenv.cfg').read_text(encoding='utf-8').splitlines():
        if line.startswith('home'):
            return Path(os.path.realpath(line.split('=', 1)[1].strip()))
    raise SystemExit('kokoro/pyvenv.cfg names no base Python')


def copy_tree(src: Path, dst: Path, skip: set[str]) -> None:
    shutil.copytree(src, dst, ignore=lambda _dir, names: [n for n in names if n in skip or n.endswith('.pyc')], dirs_exist_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='only say whether the sources exist')
    args = ap.parse_args()
    snap = sorted((Path.home() / '.cache' / 'huggingface' / 'hub' / 'models--Systran--faster-whisper-small' / 'snapshots').glob('*'))
    need = {'kokoro env': SRC / 'kokoro' / 'Lib' / 'site-packages', 'whisper env': SRC / 'whisper' / 'Lib' / 'site-packages',
            'kokoro model': SRC / 'kokoro-models' / 'kokoro-v1.0.onnx', 'kokoro voices': SRC / 'kokoro-models' / 'voices-v1.0.bin',
            'whisper small model': snap[-1] / 'model.bin' if snap else Path('missing-whisper-small')}
    missing = [f'{k}: {v}' for k, v in need.items() if not v.exists()]
    if missing:
        print('Cannot build the voice pack; missing:\n  ' + '\n  '.join(missing), file=sys.stderr)
        return 2
    if args.check:
        print('voice sources found under', SRC)
        return 0
    if OUT.exists():
        shutil.rmtree(OUT)
    py = base_python()
    OUT.mkdir(parents=True)
    # Python: the interpreter, its DLLs and a trimmed standard library. No pip, no tkinter, no tests.
    (OUT / 'python').mkdir()
    for name in ('python.exe', 'python3.dll', 'python312.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt'):
        if (py / name).is_file():
            shutil.copy2(py / name, OUT / 'python' / name)
    copy_tree(py / 'DLLs', OUT / 'python' / 'DLLs', {'_ctypes_test.pyd', '_testcapi.pyd', '_tkinter.pyd', 'tcl86t.dll', 'tk86t.dll'})
    copy_tree(py / 'Lib', OUT / 'python' / 'Lib', SKIP_STDLIB)
    for engine in ('kokoro', 'whisper'):
        copy_tree(SRC / engine / 'Lib' / 'site-packages', OUT / engine / 'site-packages', SKIP_TOP)
    (OUT / 'models' / 'kokoro').mkdir(parents=True)
    for name in ('kokoro-v1.0.onnx', 'voices-v1.0.bin'):
        shutil.copy2(SRC / 'kokoro-models' / name, OUT / 'models' / 'kokoro' / name)
    (OUT / 'models' / 'whisper-small').mkdir(parents=True)
    for file in snap[-1].iterdir():
        shutil.copy2(file.resolve(), OUT / 'models' / 'whisper-small' / file.name)
    # Licences: what each package says about itself, and the texts of the GPL ones.
    rows, texts, seen = [], [], set()
    for engine in ('kokoro', 'whisper'):
        for info in sorted((OUT / engine / 'site-packages').glob('*.dist-info')):
            meta = email.message_from_string((info / 'METADATA').read_text(encoding='utf-8', errors='replace')) if (info / 'METADATA').is_file() else None
            if not meta or info.name in seen:
                continue
            seen.add(info.name)
            lines = (meta.get('License') or '').strip().splitlines()
            licence = meta.get('License-Expression') or (lines[0] if lines else '') or next((c.split('::')[-1].strip() for c in meta.get_all('Classifier', []) if c.startswith('License ::')), 'not stated')
            rows.append(f"- {meta.get('Name')} {meta.get('Version')}: {licence[:120]}")
            if 'GPL' in licence.upper() or meta.get('Name', '').lower() in ('phonemizer', 'espeakng-loader'):
                for file in list(info.glob('licenses/*')) + list(info.glob('LICEN*')) + list(info.glob('COPYING*')):
                    if file.is_file():
                        texts.append(f"\n----- {meta.get('Name')} {file.name} -----\n" + file.read_text(encoding='utf-8', errors='replace'))
    (OUT / 'LICENSES.txt').write_text(LICENCE_NOTES + '\n'.join(sorted(set(rows))) + '\n' + ''.join(texts), encoding='utf-8')
    size = sum(f.stat().st_size for f in OUT.rglob('*') if f.is_file())
    print(json.dumps({'voice_pack': str(OUT), 'megabytes': round(size / 1e6)}))
    # Prove it runs from the pack alone: no virtual environment, no user site, a stripped environment.
    for engine, module in (('kokoro', 'kokoro_onnx'), ('whisper', 'faster_whisper')):
        env = {'SYSTEMROOT': os.environ.get('SYSTEMROOT', ''), 'PYTHONPATH': str(OUT / engine / 'site-packages'), 'PYTHONNOUSERSITE': '1'}
        done = subprocess.run([str(OUT / 'python' / 'python.exe'), '-c', f'import {module}; print("{module} ok")'], env=env, capture_output=True, text=True)
        print(done.stdout.strip() or done.stderr.strip()[-300:])
        if done.returncode:
            return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
