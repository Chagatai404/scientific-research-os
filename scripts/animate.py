"""Animation backends for science-visualize: detect, lint, render, inspect and register. Standard library only.

A teaching animation is a Manim scene written once against the Community Edition API, plus a spec that says why the motion is allowed (its basis),
what the learner predicts first, and how the scene is rendered. This module never installs a backend. It finds the ones that exist (ManimGX,
Manim Community, manim-slides, ffmpeg), runs one on the researcher's scene file, keeps the video, a poster frame and a key-frame strip beside
a record of exactly what ran, and registers the result at ``rendered``. Rendering is not verification: the motion is checked against its
stated basis under VISUALIZATION_PROTOCOL.md, and a scene is code that runs in the chosen environment, so only render scenes you trust.

Commands: capabilities | validate | lint | render | keyframes | present
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import visual_assets
import visuals

SCHEMA = 1
BACKENDS = ('manimgx', 'manim')
FIELDS = {'animation_schema', 'id', 'title', 'scene', 'scene_class', 'backend', 'concepts', 'schematic', 'basis', 'predict', 'pauses',
          'time_mapping', 'seed', 'resolution', 'fps', 'slides'}
REQUIRED = {'animation_schema', 'id', 'title', 'scene', 'scene_class', 'concepts'}
RESOLUTION = re.compile(r'(\d{3,4})x(\d{3,4})\Z')
DEFAULT_TIMEOUT = 900
# A scene that cannot even import its library is not a scene; these are the imports it may use to reach one.
LIBRARIES = {'manimgx', 'manim', 'manim_slides'}
# Not a sandbox. These are the obvious ways a teaching scene reaches the network or runs other programs; a hit blocks rendering.
FORBIDDEN_IMPORTS = {'subprocess', 'socket', 'urllib', 'http', 'requests', 'ftplib', 'smtplib', 'ctypes', 'multiprocessing', 'webbrowser',
                     'shutil', 'asyncio', 'telnetlib', 'xmlrpc', 'pty'}
FORBIDDEN_CALLS = {'eval', 'exec', 'compile', '__import__'}
FORBIDDEN_ATTRS = {('os', 'system'), ('os', 'popen'), ('os', 'remove'), ('os', 'unlink'), ('os', 'rmdir'), ('os', 'rename'), ('os', 'execv'),
                   ('os', 'spawnl'), ('os', 'startfile')}
RANDOM_MODULES = {'random', 'secrets'}
# Measured on this machine (2026-10-16, Windows, Python 3.11 venv): manim-slides 5.7.0 raises AttributeError (ManimConfig has no attribute
# write_to_movie) when constructing a Slide under Manim Community 0.22.0, and works under 0.19.0.
KNOWN_INCOMPATIBLE = [({'manim': '0.22.0', 'manim-slides': '5.7.0'},
                       'manim-slides 5.7.0 fails under Manim Community 0.22.0 (AttributeError: write_to_movie); it rendered under 0.19.0 here. '
                       'Use a separate environment pinned to manim==0.19.0 for slides.')]
ENV_VARIABLE = 'RESEARCH_OS_ANIMATION_ENVS'


class AnimationError(ValueError):
    pass


class LayoutProblems(AnimationError):
    def __init__(self, layout):
        super().__init__('layout problems: ' + '; '.join(layout['problems'] or [layout['text']]))
        self.layout = layout


# ---------------------------------------------------------------- running things

def run_command(args: list[str], cwd: Path | None = None, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Run a program without a shell. The one place this module starts a process, so tests replace it."""
    started = time.monotonic()
    try:
        done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    except FileNotFoundError:
        return {'code': 127, 'stdout': '', 'stderr': f'{args[0]}: not found', 'seconds': 0.0}
    except subprocess.TimeoutExpired:
        return {'code': 124, 'stdout': '', 'stderr': f'{Path(args[0]).name}: timed out after {timeout} s', 'seconds': float(timeout)}
    return {'code': done.returncode, 'stdout': done.stdout, 'stderr': done.stderr, 'seconds': round(time.monotonic() - started, 2)}


def _executable(directory: Path, name: str) -> Path | None:
    for sub in ('Scripts', 'bin', ''):
        for suffix in ('.exe', ''):
            candidate = directory / sub / f'{name}{suffix}' if sub else directory / f'{name}{suffix}'
            if candidate.is_file():
                return candidate
    return None


def _version(command: Path | str, flag: str = '--version') -> str | None:
    result = run_command([str(command), flag], timeout=60)
    if result['code'] != 0:
        return None
    match = re.search(r'\d+(?:\.\d+)+', (result['stdout'] or result['stderr']))
    return match[0] if match else None


def _package_version(env: Path, package: str) -> str | None:
    python = _executable(env, 'python')
    if python is None:
        return None
    result = run_command([str(python), '-c', f'import importlib.metadata as m;print(m.version({package!r}))'], timeout=60)
    return result['stdout'].strip() if result['code'] == 0 and result['stdout'].strip() else None


def environments(envs: list[str] | None = None) -> list[Path | None]:
    """The environments to look in: the ones named, else those in RESEARCH_OS_ANIMATION_ENVS, plus the PATH (None)."""
    named = [Path(e) for e in (envs or []) if e]
    if not named:
        named = [Path(p) for p in os.environ.get(ENV_VARIABLE, '').split(os.pathsep) if p]
    return named + [None]


def capabilities(envs: list[str] | None = None) -> dict:
    """What can render here. Reports only; nothing is installed. ``backends`` lists each usable renderer with its location and version."""
    found, notes = [], []
    for env in environments(envs):
        for name in BACKENDS:
            location = _executable(env, name) if env else (Path(shutil.which(name)) if shutil.which(name) else None)
            if location is None:
                continue
            entry = {'backend': name, 'command': str(location), 'env': str(env) if env else 'PATH', 'version': _version(location)}
            if env:
                slides = _package_version(env, 'manim-slides')
                entry['manim_slides'] = slides
                for pins, message in KNOWN_INCOMPATIBLE:
                    if entry['version'] and slides and pins.get('manim') == entry['version'] and pins.get('manim-slides') == slides:
                        notes.append(f'{entry["env"]}: {message}')
            found.append(entry)
    tools = {t: bool(shutil.which(t)) for t in ('ffmpeg', 'ffprobe', 'typst', 'latex', 'node')}
    if not found:
        notes.append('no animation backend found: a scene cannot be rendered here. Use key-frame panels or an unrendered storyboard, and say so.')
    if not tools['ffmpeg']:
        notes.append('ffmpeg not found: no poster frame or key-frame strip can be made.')
    return {'backends': found, 'tools': tools, 'python': sys.version.split()[0], 'notes': notes,
            'note': 'Nothing is installed by Research OS. Put a backend in its own virtual environment and name it with --env or '
                    f'{ENV_VARIABLE}. Order of preference: manimgx, then manim (Community).'}


# ---------------------------------------------------------------- spec and lint

def validate(spec) -> list[str]:
    if not isinstance(spec, dict):
        return ['spec must be a JSON object']
    problems = []
    if set(spec) - FIELDS:
        problems.append('unknown field(s): ' + ', '.join(sorted(set(spec) - FIELDS)))
    if REQUIRED - set(spec):
        return problems + ['missing field(s): ' + ', '.join(sorted(REQUIRED - set(spec)))]
    if spec['animation_schema'] != SCHEMA or type(spec['animation_schema']) is not int:
        problems.append('animation_schema must be the integer 1')
    if not isinstance(spec['id'], str) or not visuals.VISUAL_ID.fullmatch(spec['id']):
        problems.append('id looks like VIS-name')
    for key in ('title', 'scene', 'scene_class', 'basis', 'predict', 'time_mapping'):
        if key in spec and (not isinstance(spec[key], str) or not spec[key].strip()):
            problems.append(f'{key} must be a nonempty string')
    if isinstance(spec.get('scene'), str) and (spec['scene'].startswith(('/', '\\')) or re.match(r'[A-Za-z]:', spec['scene']) or '..' in Path(spec['scene']).parts):
        problems.append('scene is a path inside the project, relative to the spec file')
    if isinstance(spec.get('scene_class'), str) and not spec['scene_class'].isidentifier():
        problems.append('scene_class must be a Python class name')
    concepts = spec['concepts']
    if not isinstance(concepts, list) or not concepts or any(not isinstance(c, str) for c in concepts):
        problems.append('concepts: a nonempty list of concept ids')
    if 'schematic' in spec and type(spec['schematic']) is not bool:
        problems.append('schematic must be true or false')
    if not spec.get('schematic') and not spec.get('basis'):
        problems.append('basis is required: the equation, data or source that justifies the motion (or set "schematic": true)')
    if 'backend' in spec and spec['backend'] not in ('auto', *BACKENDS):
        problems.append('backend must be auto, manimgx or manim')
    if 'resolution' in spec and not (isinstance(spec['resolution'], str) and RESOLUTION.fullmatch(spec['resolution'])):
        problems.append('resolution looks like 1280x720')
    for key in ('fps', 'seed'):
        if key in spec and (type(spec[key]) is not int or (key == 'fps' and not 1 <= spec[key] <= 120)):
            problems.append(f'{key} must be an integer' + (' from 1 to 120' if key == 'fps' else ''))
    if 'slides' in spec and type(spec['slides']) is not bool:
        problems.append('slides must be true or false')
    pauses = spec.get('pauses', [])
    if not isinstance(pauses, list) or any(not isinstance(p, dict) or set(p) - {'at', 'note'} or 'note' not in p or not isinstance(p['note'], str)
                                           or not (p.get('at') == 'end' or (isinstance(p.get('at'), (int, float)) and not isinstance(p.get('at'), bool) and p['at'] >= 0))
                                           for p in pauses):
        problems.append('pauses: a list of {"at": seconds or "end", "note": text}')
    return problems


def lint_source(text: str, spec: dict | None = None) -> dict:
    """Static checks on a scene file. Errors block rendering; this is a screen for obvious mistakes, not a sandbox."""
    errors, warnings = [], []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return {'errors': [f'syntax error line {exc.lineno}: {exc.msg}'], 'warnings': [], 'classes': [], 'sections': 0}
    imported, classes, uses_random, seeded, sections = set(), [], False, False, 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name.split('.')[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or '').split('.')[0]] if not node.level else ['.']
        else:
            names = []
        for name in names:
            imported.add(name)
            if name in FORBIDDEN_IMPORTS:
                errors.append(f'line {node.lineno}: imports {name}, which a teaching scene does not need (network, processes and file operations are blocked)')
            if name in RANDOM_MODULES:
                uses_random = True
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                errors.append(f'line {node.lineno}: calls {func.id}()')
            if isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name) and (func.value.id, func.attr) in FORBIDDEN_ATTRS:
                    errors.append(f'line {node.lineno}: calls {func.value.id}.{func.attr}()')
                if func.attr in {'next_section', 'next_slide'}:
                    sections += 1
                if func.attr in {'seed', 'default_rng'}:
                    seeded = True
                if func.attr in {'random', 'rand', 'randn', 'randint', 'choice', 'normal', 'uniform', 'shuffle'}:
                    uses_random = True
    if not (imported & LIBRARIES):
        errors.append('the scene imports none of manimgx, manim or manim_slides')
    if uses_random and not seeded and not (spec and 'seed' in spec):
        warnings.append('the scene draws random numbers without a seed: seed it, or give the spec a "seed", so the run can be repeated. One realisation is not an ensemble.')
    if spec:
        wanted = spec.get('scene_class')
        if wanted and wanted not in classes:
            errors.append(f'scene_class {wanted} is not defined in the file (classes: {", ".join(classes) or "none"})')
        if not spec.get('predict'):
            warnings.append('no "predict" prompt: a teaching animation should ask for a prediction before it plays')
        if spec.get('slides') and sections == 0:
            warnings.append('"slides" is true but the scene has no next_section() or next_slide() call, so there is only one slide')
    return {'errors': errors, 'warnings': warnings, 'classes': classes, 'sections': sections}


# ---------------------------------------------------------------- media helpers

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _slug(value: str) -> str:
    return re.sub(r'[^a-z0-9._-]+', '-', value.lower()).strip('-')


def probe(video: Path) -> dict:
    """Duration, size and frame rate from ffprobe, or an empty dict when ffprobe is absent."""
    if not shutil.which('ffprobe'):
        return {}
    result = run_command(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,r_frame_rate:format=duration',
                          '-of', 'json', str(video)], timeout=120)
    if result['code'] != 0:
        return {}
    try:
        data = json.loads(result['stdout'])
        stream = data['streams'][0]
        num, _, den = stream['r_frame_rate'].partition('/')
        return {'width': stream['width'], 'height': stream['height'], 'fps': round(float(num) / float(den or 1), 2), 'duration': round(float(data['format']['duration']), 3)}
    except (KeyError, IndexError, ValueError, ZeroDivisionError):
        return {}


def keyframes(video: Path, strip: Path, poster: Path | None = None, count: int = 6, duration: float | None = None) -> dict:
    """A poster frame (the middle of the video) and a strip of ``count`` evenly spaced frames. Both are PNG; absent ffmpeg returns a reason."""
    if not shutil.which('ffmpeg'):
        return {'made': [], 'reason': 'ffmpeg not found'}
    duration = duration or probe(video).get('duration')
    if not duration:
        return {'made': [], 'reason': 'could not read the video duration'}
    made = []
    if poster is not None:
        done = run_command(['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{duration / 2:.3f}', '-i', str(video), '-frames:v', '1', str(poster)], timeout=120)
        if done['code'] == 0 and Path(poster).exists():
            made.append(Path(poster))
    rate = max(count / duration, 0.01)
    done = run_command(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(video), '-vf', f'fps={rate:.6f},scale=320:-2,tile={count}x1', '-frames:v', '1', str(strip)], timeout=180)
    if done['code'] == 0 and Path(strip).exists():
        made.append(Path(strip))
    return {'made': made, 'reason': None if len(made) == (2 if poster is not None else 1) else 'ffmpeg did not produce every frame'}


# ---------------------------------------------------------------- choosing and running a backend

def choose(spec: dict, envs: list[str] | None = None, backend: str | None = None) -> dict | None:
    """The first usable backend honouring the spec's preference. ManimGX before Manim Community unless the spec asks otherwise."""
    wanted = backend or spec.get('backend', 'auto')
    usable = capabilities(envs)['backends']
    if spec.get('slides') and wanted == 'auto':
        wanted = 'manim'
    for entry in usable:
        if wanted in ('auto', entry['backend']):
            if wanted == 'auto' and entry['backend'] != 'manimgx' and any(u['backend'] == 'manimgx' for u in usable):
                continue
            return entry
    return None


def _tail(text: str, lines: int = 12) -> str:
    return '\n'.join(text.strip().splitlines()[-lines:])


def render_with(entry: dict, spec: dict, scene: Path, work: Path, allow_layout_problems: bool = False, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Run one backend on a scene in a working directory. Returns the video, the commands run and what the layout check said."""
    width, height = (int(x) for x in RESOLUTION.fullmatch(spec.get('resolution', '1280x720')).groups())
    fps = str(spec.get('fps', 30))
    cls, command, commands, layout = spec['scene_class'], entry['command'], [], {'checked': False, 'problems': [], 'text': ''}
    out = work / f'{_slug(spec["id"])}.mp4'
    if entry['backend'] == 'manimgx':
        inspect = run_command([command, 'inspect', str(scene), cls], cwd=work, timeout=timeout)
        commands.append({'argv': [Path(command).name, 'inspect', scene.name, cls], 'code': inspect['code'], 'seconds': inspect['seconds']})
        report = inspect['stdout'] + inspect['stderr']
        line = next((l for l in report.splitlines() if l.strip().lower().startswith('layout:')), '')
        layout = {'checked': bool(line) and 'not checked' not in line, 'problems': [l.strip() for l in report.splitlines() if re.match(r'\s*\[\d+\]', l)],
                  'text': line.strip()}
        if inspect['code'] not in (0, 1):
            raise AnimationError('inspect failed: ' + _tail(report))
        if inspect['code'] == 1 and not allow_layout_problems:
            raise LayoutProblems(layout)
        done = run_command([command, 'render', str(scene), cls, '-o', str(out), '-r', f'{width}x{height}', '--fps', fps], cwd=work, timeout=timeout)
        commands.append({'argv': [Path(command).name, 'render', scene.name, cls, '-o', out.name, '-r', f'{width}x{height}', '--fps', fps],
                         'code': done['code'], 'seconds': done['seconds']})
    else:
        media = work / 'media'
        done = run_command([command, 'render', '-r', f'{width},{height}', '--fps', fps, '--media_dir', str(media), str(scene), cls], cwd=work, timeout=timeout)
        commands.append({'argv': [Path(command).name, 'render', '-r', f'{width},{height}', '--fps', fps, '--media_dir', 'media', scene.name, cls],
                         'code': done['code'], 'seconds': done['seconds']})
        if done['code'] == 0:
            produced = sorted(media.rglob(f'{cls}.mp4'), key=lambda p: p.stat().st_mtime) if media.exists() else []
            if produced:
                shutil.move(str(produced[-1]), out)
    if done['code'] != 0 or not out.exists():
        raise AnimationError(f'{entry["backend"]} render failed (exit {done["code"]}): ' + _tail(done['stderr'] or done['stdout']))
    result = {'video': out, 'commands': commands, 'layout': layout, 'seconds': done['seconds']}
    if spec.get('slides') and entry['backend'] == 'manim':
        env = Path(entry['env']) if entry['env'] != 'PATH' else None
        slides = _executable(env, 'manim-slides') if env else (Path(shutil.which('manim-slides')) if shutil.which('manim-slides') else None)
        if slides is None:
            result['slides_note'] = 'manim-slides is not installed in that environment, so no slide deck was made'
        else:
            html = work / f'{_slug(spec["id"])}.slides.html'
            conv = run_command([str(slides), 'convert', '--to', 'html', '--one-file', '--offline', cls, str(html)], cwd=work, timeout=timeout)
            commands.append({'argv': ['manim-slides', 'convert', '--to', 'html', '--one-file', '--offline', cls, html.name], 'code': conv['code'], 'seconds': conv['seconds']})
            if conv['code'] == 0 and html.exists():
                result['slides'] = html
            else:
                result['slides_note'] = 'manim-slides convert failed: ' + _tail(conv['stderr'] or conv['stdout'], 4)
    elif spec.get('slides'):
        result['slides_note'] = f'ManimGX presents sections as slides: run `{Path(command).name} present <scene> {cls}`; no deck file is made'
    return result


def render(spec_path: Path, root: Path, *, envs: list[str] | None = None, backend: str | None = None, allow_layout_problems: bool = False,
           directory: str = 'Visuals', timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Lint, render, make the key frames and register the result. Never overwrites; a failure leaves nothing behind."""
    spec_path, root = Path(spec_path).resolve(), Path(root).resolve()
    spec = json.loads(spec_path.read_text(encoding='utf-8-sig'))
    problems = validate(spec)
    if problems:
        raise AnimationError('invalid spec: ' + '; '.join(problems))
    if not directory or '\\' in directory or ':' in directory or any(p in {'', '.', '..'} for p in directory.split('/')):
        raise AnimationError('the directory is a relative path inside the vault')
    scene = (spec_path.parent / spec['scene']).resolve()
    if spec_path.parent.resolve() not in scene.parents and scene.parent != spec_path.parent.resolve():
        raise AnimationError("the scene must be inside the spec file's folder")
    if not scene.is_file():
        raise AnimationError(f'scene file not found: {spec["scene"]}')
    lint = lint_source(scene.read_text(encoding='utf-8'), spec)
    if lint['errors']:
        raise AnimationError('scene refused: ' + '; '.join(lint['errors']))
    base, folder = _slug(spec['id']), root / directory / _slug(spec['id'])
    record_file = folder / f'{base}{visuals.SUFFIX}'
    spec_sha = visual_assets.digest_spec(spec)
    if record_file.exists():
        existing = json.loads(record_file.read_text(encoding='utf-8-sig'))
        if existing.get('spec_sha256') == spec_sha and existing.get('source_sha256') == sha(scene.read_bytes()):
            return {'visual_id': spec['id'], 'reused': True, 'artifact': existing['artifact'], 'rendered': True}
        raise AnimationError(f'{spec["id"]} already exists with a different spec or scene; choose a new id')
    entry = choose(spec, envs, backend)
    if entry is None:
        return {'visual_id': spec['id'], 'rendered': False, 'reused': False, 'missing': ['manimgx or manim (Community)' + (' with manim-slides' if spec.get('slides') else '')],
                'fallback': 'No backend can render this scene here. Return the scene source and an unrendered storyboard, or key-frame panels, and say that nothing was rendered.',
                'warnings': lint['warnings']}
    started = time.time()
    with tempfile.TemporaryDirectory(prefix='animate-') as tmp:
        work = Path(tmp)
        copy = work / scene.name
        shutil.copyfile(scene, copy)
        rendered = render_with(entry, spec, copy, work, allow_layout_problems, timeout)
        video, info = rendered['video'], probe(rendered['video'])
        poster, strip = work / f'{base}.poster.png', work / f'{base}.keyframes.png'
        frames = keyframes(video, strip, poster, duration=info.get('duration'))
        folder.mkdir(parents=True, exist_ok=True)
        placed = {}
        try:
            for key, path in (('video', video), ('poster', poster), ('strip', strip), ('slides', rendered.get('slides'))):
                if path and Path(path).exists():
                    target = folder / Path(path).name
                    if target.exists():
                        raise AnimationError(f'{target.name} already exists')
                    shutil.copyfile(path, target)
                    placed[key] = target
            scene_copy = folder / f'{base}.scene.py'
            spec_copy = folder / f'{base}.animation.json'
            scene_copy.write_bytes(scene.read_bytes())
            spec_copy.write_text(json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
            placed['scene'], placed['spec'] = scene_copy, spec_copy

            def relative(path):
                return path.relative_to(root).as_posix()

            schematic = bool(spec.get('schematic'))
            record = {'visual_schema': 1, 'visual_id': spec['id'], 'title': spec['title'], 'concepts': spec['concepts'], 'kind': 'animation',
                      'source_type': 'schematic' if schematic else 'generated', 'verification_status': 'rendered', 'artifact': relative(placed['video']),
                      'quantitative': not schematic, 'mode': 'animation', 'spec_sha256': spec_sha, 'source_sha256': sha(scene.read_bytes()), 'generator': 'animate.py'}
            exports = [{'path': relative(placed[k]), 'format': 'png'} for k in ('poster', 'strip') if k in placed]
            if exports:
                record['exports'] = exports
            if not schematic:
                record['basis'] = (f'{spec["basis"].strip()} Rendered by {entry["backend"]} {entry["version"] or ""} from {relative(placed["scene"])} '
                                   f'(scene sha256 {record["source_sha256"][:12]}…). Rendering is not verification: the motion is checked against this basis separately.')
            problems = visuals.issues(record, root)
            if problems:
                raise AnimationError('record invalid: ' + '; '.join(problems))
            report = {'render_schema': 1, 'visual_id': spec['id'], 'backend': {'backend': entry['backend'], 'version': entry['version'],
                                                                          'env': 'PATH' if entry['env'] == 'PATH' else Path(entry['env']).name}, 'commands': rendered['commands'],
                      'python': sys.version.split()[0], 'platform': sys.platform, 'seconds_render': rendered['seconds'], 'seconds_total': round(time.time() - started, 2),
                      'video': {'sha256': sha(placed['video'].read_bytes()), 'bytes': placed['video'].stat().st_size, **info}, 'layout': rendered['layout'],
                      'keyframes': {'made': [p.name for p in frames['made']], 'reason': frames['reason']}, 'lint_warnings': lint['warnings'],
                      'seed': spec.get('seed'), 'slides': rendered.get('slides_note') or (placed['slides'].name if 'slides' in placed else None)}
            (folder / f'{base}.render.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
            visual_assets._write_record(record_file, record)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
    return {'visual_id': spec['id'], 'rendered': True, 'reused': False, 'artifact': record['artifact'], 'backend': entry['backend'], 'version': entry['version'],
            'seconds': report['seconds_render'], 'layout': rendered['layout'], 'exports': [e['path'] for e in exports], 'warnings': lint['warnings'],
            'slides': report['slides'], 'next': 'Inspect the key frames and play the video against the stated basis before moving past rendered.'}


def present_command(spec: dict, entry: dict) -> list[str]:
    """The command that presents a scene as slides. Returned, never run: it opens a window and waits for a person."""
    cls = spec['scene_class']
    if entry['backend'] == 'manimgx':
        return [Path(entry['command']).name, 'present', spec['scene'], cls]
    return ['manim-slides', 'present', cls]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('capabilities', help='which backends exist (reports only)')
    p.add_argument('--env', action='append', default=[], help='a virtual environment to look in (repeatable)')
    p = sub.add_parser('validate', help='structural problems with a spec (exit 1 if any)')
    p.add_argument('spec', type=Path)
    p = sub.add_parser('lint', help='static checks on a scene file (exit 1 on errors)')
    p.add_argument('scene', type=Path)
    p.add_argument('--spec', type=Path, help='also check the scene against its spec')
    p = sub.add_parser('render', help="render a spec's scene and register it at rendered")
    p.add_argument('spec', type=Path)
    p.add_argument('--root', type=Path, required=True, help='the vault the result goes into')
    p.add_argument('--env', action='append', default=[])
    p.add_argument('--backend', choices=('auto', *BACKENDS))
    p.add_argument('--allow-layout-problems', action='store_true')
    p.add_argument('--directory', default='Visuals')
    p.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT)
    p = sub.add_parser('keyframes', help='a poster frame and a key-frame strip from a video')
    p.add_argument('video', type=Path)
    p.add_argument('--out', type=Path, required=True, help='the strip PNG to write')
    p.add_argument('--poster', type=Path)
    p.add_argument('--count', type=int, default=6)
    p = sub.add_parser('present', help='print the command that presents a scene as slides (not run)')
    p.add_argument('spec', type=Path)
    p.add_argument('--env', action='append', default=[])
    args = parser.parse_args(argv)
    try:
        if args.command == 'capabilities':
            print(json.dumps(capabilities(args.env), indent=2))
            return 0
        if args.command == 'validate':
            problems = validate(json.loads(args.spec.read_text(encoding='utf-8-sig')))
            print('\n'.join(problems) if problems else 'ok')
            return 1 if problems else 0
        if args.command == 'lint':
            spec = json.loads(args.spec.read_text(encoding='utf-8-sig')) if args.spec else None
            result = lint_source(args.scene.read_text(encoding='utf-8'), spec)
            print(json.dumps(result, indent=2))
            return 1 if result['errors'] else 0
        if args.command == 'render':
            result = render(args.spec, args.root, envs=args.env, backend=args.backend, allow_layout_problems=args.allow_layout_problems,
                            directory=args.directory, timeout=args.timeout)
            print(json.dumps(result, indent=2, default=str))
            return 0 if result['rendered'] else 3
        if args.command == 'keyframes':
            result = keyframes(args.video, args.out, args.poster, args.count)
            print(json.dumps({'made': [str(p) for p in result['made']], 'reason': result['reason']}, indent=2))
            return 0 if not result['reason'] else 2
        if args.command == 'present':
            spec = json.loads(args.spec.read_text(encoding='utf-8-sig'))
            entry = choose(dict(spec, slides=True), args.env)
            if entry is None:
                print('no backend found', file=sys.stderr)
                return 3
            print(' '.join(present_command(spec, entry)))
            return 0
    except LayoutProblems as exc:
        print(json.dumps({'rendered': False, 'layout': exc.layout, 'message': str(exc), 'next': 'Fix the scene, or pass --allow-layout-problems to render anyway and record them.'}, indent=2))
        return 4
    except (AnimationError, OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
