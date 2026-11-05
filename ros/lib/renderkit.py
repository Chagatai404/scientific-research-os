"""The safe renderer: what an unattended agent uses to make a teaching figure. Standard library only; imports nothing from ``ros``.

The model gets no shell and no built-in file tools. It gets seven bridge tools (``TOOLS``) that confine themselves in the code below:

- ``scratch_list``, ``scratch_read``, ``scratch_write``: a fresh temporary folder holding a COPY of what the task needs, never the
  bundle folder. Every path is resolved and refused if it is absolute, has ``..``, a drive letter, a stream (``:``), a UNC or ``\\\\?\\``
  form, a reserved device name, or passes through a link or junction (no link is ever followed or created by this code).
- ``render``: runs a Python figure script from the scratch folder inside a Windows AppContainer (``ros.lib.appcontainer``): no
  network, no files outside the scratch and a private copy of the interpreter and plotting packages, no child process, CPU, memory,
  time, output and disk limits. There is no other way to run code; where the container is unavailable ``available()`` says why.
- ``look``: returns a rendered picture to the model as image content.
- ``publish``: copies one validated output (magic bytes, size and pixel caps, sanitized SVG) and a plain-text RESULT note into the
  bundle. Nothing else leaves the scratch folder.

The model and the code it writes are untrusted; so are the bundle text, source files and web material that may steer it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from . import appcontainer

MAX_WRITE = 200_000            # bytes of text one scratch_write may hold
MAX_READ = 60_000              # characters one scratch_read returns
MAX_FILES = 300                # files in the scratch folder
MAX_SCRATCH = 64 << 20         # bytes in the scratch folder when a script is not running (while it runs: appcontainer's disk watch)
MAX_IMAGE = 8 << 20            # bytes of one picture
MAX_LOOK = 4 << 20             # bytes of a picture returned to the model
MAX_VIDEO = 60 << 20
MAX_PIXELS = 16_000_000        # width x height
MAX_SIDE = 6000
MAX_SVG = 1 << 20
MAX_NOTE = 4000
TEXT_SUFFIXES = {'.py', '.txt', '.md', '.json', '.csv', '.svg', '.mmd'}
RESERVED = re.compile(r'^(?:CON|PRN|AUX|NUL|COM[0-9\u00b9\u00b2\u00b3]|LPT[0-9\u00b9\u00b2\u00b3]|CONIN\$|CONOUT\$)(?:\..*)?$', re.I)
SEGMENT = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_. +()\[\]=,#@%~-]{0,119}$')
REPARSE = 0x400


class RenderError(ValueError):
    """A refusal the model is told in plain words; nothing was done."""


# ---------------------------------------------------------------------------------------------------------------- confinement

def is_link(path) -> bool:
    """A symbolic link, junction or any other reparse point (never followed here)."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    import stat
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, 'st_file_attributes', 0) & REPARSE)


def clean_relative(rel) -> list[str]:
    """The segments of a scratch-relative path, or a refusal. Only plain forward-slash names are accepted."""
    if not isinstance(rel, str) or not rel or len(rel) > 240 or '\x00' in rel or any(ord(c) < 32 for c in rel):
        raise RenderError('a scratch path is a short relative name such as out/figure.png')
    if '\\' in rel or ':' in rel or rel.startswith('/') or rel.startswith('~'):
        raise RenderError('use a relative path with forward slashes and no drive letter, stream or absolute form')
    parts = rel.split('/')
    for part in parts:
        if part in ('', '.', '..'):
            raise RenderError('a scratch path has no empty, "." or ".." parts')
        if part != part.strip() or part.endswith('.') or part.endswith(' '):
            raise RenderError('a scratch path part must not end with a dot or a space')
        if RESERVED.match(part):
            raise RenderError('%s is a reserved device name' % part)
        if not SEGMENT.match(part) or '$' in part:
            raise RenderError('%r is not a plain file name (letters, digits, dot, dash, underscore, space)' % part)
    return parts


class Scratch:
    """One task's private working folder: ``in/`` (copies of what the task needs), ``work/`` (scripts), ``out/`` (what scripts
    produce), plus ``tmp/`` and ``mpl/`` for the interpreter. Created fresh, removed when the task ends."""

    def __init__(self, parent: Path, inputs: dict | None = None):
        parent = Path(parent)
        parent.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix='task-', dir=parent))
        self.real = Path(os.path.realpath(self.root))
        for name in ('in', 'work', 'out', 'tmp', 'mpl'):
            (self.root / name).mkdir()
        for name, data in (inputs or {}).items():
            target = self.resolve('in/' + name, parent_ok=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data[:MAX_SCRATCH // 4])

    # -- the one place a name becomes a path
    def resolve(self, rel, parent_ok=False) -> Path:
        """The real path of a scratch-relative name, refused when it could leave the folder: every part is checked and no part may be
        a link or junction. ``parent_ok`` lets a file be created (its folders may not exist yet)."""
        parts = clean_relative(rel)
        current = self.root
        for part in parts:
            current = current / part
            if is_link(current):
                raise RenderError('%s is a link; links are not followed' % rel)
        real = Path(os.path.realpath(current))
        try:
            real.relative_to(self.real)
        except ValueError:
            raise RenderError('%s leaves the scratch folder' % rel) from None
        return current

    def files(self, limit=400) -> list[dict]:
        rows = []
        for base, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = [d for d in dirs if not is_link(os.path.join(base, d))]
            for name in names:
                path = Path(base) / name
                if is_link(path):
                    continue
                try:
                    rows.append({'path': path.relative_to(self.root).as_posix(), 'bytes': path.stat().st_size})
                except OSError:
                    continue
                if len(rows) >= limit:
                    return rows
        return sorted(rows, key=lambda r: r['path'])

    def size(self) -> int:
        return sum(r['bytes'] for r in self.files(10_000))

    # -- the model's file tools
    def list(self):
        rows = [r for r in self.files() if not r['path'].startswith(('tmp/', 'mpl/'))]
        return {'files': rows, 'note': 'in/ holds copies of the task inputs, work/ your scripts, out/ what a script writes.'}

    def read(self, path, start=0):
        target = self.resolve(path)
        if not target.is_file():
            raise RenderError('%s is not a file in the scratch folder' % path)
        if target.suffix.lower() not in TEXT_SUFFIXES:
            raise RenderError('only text files can be read; use look for a picture')
        raw = target.read_bytes()[:MAX_WRITE * 4]
        if b'\x00' in raw[:4096]:
            raise RenderError('%s is not a text file' % path)
        text = raw.decode('utf-8', 'replace')
        start = max(0, int(start or 0))
        return {'path': path, 'text': text[start:start + MAX_READ], 'more': len(text) > start + MAX_READ, 'untrusted': True}

    def write(self, path, text):
        if not isinstance(text, str):
            raise RenderError('text is a string')
        parts = clean_relative(path)
        target = self.resolve(path, parent_ok=True)
        if target.suffix.lower() not in TEXT_SUFFIXES:
            raise RenderError('only text files can be written here: ' + ', '.join(sorted(TEXT_SUFFIXES)))
        if parts[0] in ('tmp', 'mpl'):
            raise RenderError('that folder is the interpreter\'s own')
        data = text.encode('utf-8')
        if len(data) > MAX_WRITE:
            raise RenderError('a file is at most %d KB of text' % (MAX_WRITE // 1000))
        if target.exists() and (target.is_dir() or is_link(target)):
            raise RenderError('%s cannot be replaced' % path)
        if len(self.files()) >= MAX_FILES and not target.exists():
            raise RenderError('the scratch folder holds at most %d files' % MAX_FILES)
        if self.size() + len(data) > MAX_SCRATCH:
            raise RenderError('the scratch folder is full')
        target.parent.mkdir(parents=True, exist_ok=True)
        # the folders just created are checked again: nothing between here and the file may be a link
        self.resolve(path)
        target.write_bytes(data)
        return {'path': path, 'bytes': len(data)}

    def output(self, path, limit=MAX_VIDEO) -> bytes:
        """The bytes of one scratch file that may leave it: a regular, singly linked file inside the scratch folder."""
        target = self.resolve(path)
        st = os.lstat(target)
        import stat
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise RenderError('%s is not a plain file' % path)
        if st.st_size > limit:
            raise RenderError('%s is larger than %d MB' % (path, limit >> 20))
        return target.read_bytes()

    def close(self):
        remove_tree(self.root)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def remove_tree(root) -> None:
    """Delete a folder that untrusted code wrote in. A link or junction is removed itself, never entered, so what it points at survives."""
    root = Path(root)
    if not root.exists() and not is_link(root):
        return
    if is_link(root):
        try:
            os.rmdir(root)
        except OSError:
            os.unlink(root)
        return
    for entry in os.scandir(root):
        path = Path(entry.path)
        if is_link(path):
            try:
                os.rmdir(path)
            except OSError:
                try:
                    os.unlink(path)
                except OSError:
                    pass
        elif entry.is_dir(follow_symlinks=False):
            remove_tree(path)
        else:
            try:
                os.chmod(path, 0o600)
                os.unlink(path)
            except OSError:
                pass
    try:
        os.rmdir(root)
    except OSError:
        pass


# ---------------------------------------------------------------------------------------------------------------- output checks

def _png(data):
    if len(data) < 33 or data[12:16] != b'IHDR':
        return None
    return struct.unpack('>II', data[16:24])


def _jpeg(data):
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack('>H', data[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack('>HH', data[i + 5:i + 9])
            return w, h
        i += 2 + length
    return None


def _webp(data):
    kind = data[12:16]
    if kind == b'VP8X' and len(data) >= 30:
        return 1 + int.from_bytes(data[24:27], 'little'), 1 + int.from_bytes(data[27:30], 'little')
    if kind == b'VP8 ' and len(data) >= 30:
        return struct.unpack('<HH', data[26:30])[0] & 0x3FFF, struct.unpack('<HH', data[26:30])[1] & 0x3FFF
    if kind == b'VP8L' and len(data) >= 25:
        bits = int.from_bytes(data[21:25], 'little')
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


SVG_ELEMENTS = {'svg', 'g', 'defs', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'text', 'tspan', 'title', 'desc', 'use',
                'linearGradient', 'radialGradient', 'stop', 'clipPath', 'marker', 'symbol', 'pattern', 'metadata'}
SVG_ATTRIBUTES = {'id', 'class', 'x', 'y', 'x1', 'y1', 'x2', 'y2', 'cx', 'cy', 'r', 'rx', 'ry', 'width', 'height', 'd', 'points', 'transform', 'viewBox',
                  'preserveAspectRatio', 'fill', 'fill-opacity', 'fill-rule', 'stroke', 'stroke-width', 'stroke-opacity', 'stroke-linecap', 'stroke-linejoin',
                  'stroke-dasharray', 'stroke-dashoffset', 'stroke-miterlimit', 'opacity', 'font-family', 'font-size', 'font-weight', 'font-style',
                  'text-anchor', 'dominant-baseline', 'alignment-baseline', 'baseline-shift', 'letter-spacing', 'dx', 'dy', 'rotate', 'textLength',
                  'offset', 'stop-color', 'stop-opacity', 'gradientUnits', 'gradientTransform', 'spreadMethod', 'fx', 'fy', 'clip-path', 'clipPathUnits',
                  'markerWidth', 'markerHeight', 'markerUnits', 'refX', 'refY', 'orient', 'marker-start', 'marker-mid', 'marker-end', 'patternUnits',
                  'patternTransform', 'version', 'xmlns', 'xml:space', 'role', 'aria-label', 'aria-hidden', 'visibility', 'display', 'lang', 'href',
                  '{http://www.w3.org/1999/xlink}href', 'style', '{http://www.w3.org/XML/1998/namespace}space'}
_SVG_NS = '{http://www.w3.org/2000/svg}'
_PAINT_REF = re.compile(r'url\(\s*#[A-Za-z0-9_.:-]+\s*\)')


def sanitize_svg(data: bytes) -> bytes:
    """The same bytes, if the SVG is purely declarative: only allow-listed elements and attributes, no script, event handler, style
    sheet, foreignObject, image or animation, and no reference except to an id inside the file. Anything else is refused, not repaired."""
    if len(data) > MAX_SVG:
        raise RenderError('an SVG is at most 1 MB')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        raise RenderError('an SVG is UTF-8 text') from None
    if re.search(r'<!(?:DOCTYPE|ENTITY)|<\?(?!xml\s)|<!\[CDATA\[', text, re.I):
        raise RenderError('this SVG has a doctype, entity, processing instruction or CDATA section')
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise RenderError('this SVG is not well-formed XML (%s)' % exc) from None
    count = 0
    for el in root.iter():
        count += 1
        if count > 5000:
            raise RenderError('this SVG has more than 5000 elements')
        if not isinstance(el.tag, str) or not el.tag.startswith(_SVG_NS):
            raise RenderError('this SVG has an element outside the SVG namespace')
        name = el.tag[len(_SVG_NS):]
        if name not in SVG_ELEMENTS:
            raise RenderError('this SVG uses <%s>, which is not allowed' % name)
        for key, value in el.attrib.items():
            local = key.rsplit('}', 1)[-1]
            if key.lower().startswith('on') or local.lower().startswith('on') or key not in SVG_ATTRIBUTES:
                raise RenderError('this SVG has the attribute %s, which is not allowed' % key)
            if local == 'href':
                if not (value.startswith('#') and name in ('use', 'linearGradient', 'radialGradient', 'pattern')):
                    raise RenderError('this SVG links to something outside itself (%s)' % value[:60])
            low = value.lower().replace(' ', '')
            if 'javascript:' in low or 'data:' in low or '@import' in low or 'expression(' in low:
                raise RenderError('this SVG has a script or data reference in %s' % key)
            if 'url(' in low and not (_PAINT_REF.sub('', value).lower().find('url(') < 0):
                raise RenderError('this SVG references an external resource in %s' % key)
    return data


def classify(data: bytes) -> dict:
    """What bytes are, by their magic bytes (never by name), with pixel size where it is cheap to read: ``{kind, mime, ext, width, height}``
    or a refusal. SVG goes through ``sanitize_svg``."""
    head = data[:16]
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        kind, mime, ext, dims = 'image', 'image/png', '.png', _png(data)
    elif head.startswith(b'\xff\xd8\xff'):
        kind, mime, ext, dims = 'image', 'image/jpeg', '.jpg', _jpeg(data)
    elif head[:6] in (b'GIF87a', b'GIF89a'):
        kind, mime, ext, dims = 'image', 'image/gif', '.gif', struct.unpack('<HH', data[6:10]) if len(data) >= 10 else None
    elif head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        kind, mime, ext, dims = 'image', 'image/webp', '.webp', _webp(data)
    elif head[4:8] == b'ftyp':
        kind, mime, ext, dims = 'video', 'video/mp4', '.mp4', None
    elif head[:4] == b'\x1a\x45\xdf\xa3':
        kind, mime, ext, dims = 'video', 'video/webm', '.webm', None
    elif re.match(rb'\s*(<\?xml[^>]*\?>\s*)?(<!--.*?-->\s*)*<svg[\s>]', data[:2000], re.S):
        sanitize_svg(data)
        return {'kind': 'svg', 'mime': 'image/svg+xml', 'ext': '.svg', 'width': None, 'height': None, 'bytes': len(data)}
    else:
        raise RenderError('this is not a PNG, JPEG, GIF, WebP, SVG, MP4 or WebM file (its first bytes say so)')
    limit = MAX_VIDEO if kind == 'video' else MAX_IMAGE
    if len(data) > limit:
        raise RenderError('a %s is at most %d MB; this one is %.1f MB' % (kind, limit >> 20, len(data) / 1048576))
    if kind == 'image':
        if not dims or dims[0] < 1 or dims[1] < 1:
            raise RenderError('the picture\'s size could not be read; it may be damaged')
        if dims[0] > MAX_SIDE or dims[1] > MAX_SIDE or dims[0] * dims[1] > MAX_PIXELS:
            raise RenderError('the picture is %dx%d pixels; at most %d on a side and %d million pixels' % (dims[0], dims[1], MAX_SIDE, MAX_PIXELS // 1_000_000))
    return {'kind': kind, 'mime': mime, 'ext': ext, 'width': dims[0] if dims else None, 'height': dims[1] if dims else None, 'bytes': len(data)}


# ---------------------------------------------------------------------------------------------------------------- the runtime

PROBE = r'''
import json, os, site, sys, sysconfig
os.environ.setdefault("MPLBACKEND", "Agg")
before = set(sys.modules)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot
for extra in ("contourpy", "fontTools.ttLib", "fontTools.subset", "matplotlib.backends.backend_agg", "matplotlib.backends.backend_svg", "matplotlib.backends.backend_pdf",
              "matplotlib.contour", "matplotlib.patheffects", "matplotlib.animation", "matplotlib.sankey", "mpl_toolkits.mplot3d", "PIL.Image", "PIL.PngImagePlugin",
              "PIL.JpegImagePlugin", "PIL.GifImagePlugin", "PIL.WebPImagePlugin", "scipy"):
    try:
        __import__(extra)
    except Exception:
        pass
sites = [p for p in dict.fromkeys([sysconfig.get_paths()["purelib"], *site.getsitepackages(), site.getusersitepackages()])
         if os.path.isdir(p) and os.path.basename(p).lower() == "site-packages"]
sites = [(os.path.normcase(os.path.realpath(p)), os.path.realpath(p)) for p in sites]
found = {}
for name, mod in list(sys.modules.items()):
    path = getattr(mod, "__file__", None)
    if not path or name in before:
        continue
    real = os.path.realpath(path)
    for low, shown in sites:
        if os.path.normcase(real).startswith(low + os.sep):
            found[(shown, real[len(low) + 1:].split(os.sep)[0])] = True
            break
print(json.dumps({"base_prefix": sys.base_prefix, "packages": sorted(found), "version": "%d.%d.%d" % sys.version_info[:3], "matplotlib": matplotlib.__version__}))
'''


def candidate_pythons() -> list[str]:
    """Interpreters worth probing for matplotlib, best first: the one named by ``ROS_RENDER_PYTHON``, this one (outside a frozen app),
    then the first on PATH, then the one shipped with the animation pack."""
    found = []
    if os.environ.get('ROS_RENDER_PYTHON'):
        found.append(os.environ['ROS_RENDER_PYTHON'])
    if not getattr(sys, 'frozen', False):
        found.append(sys.executable)
    for name in ('python', 'python3'):
        which = shutil.which(name)
        if which:
            found.append(which)
    pack = os.environ.get('ROS_VOICE_PACK')
    if pack:
        found.append(str(Path(pack) / 'animation' / 'python' / 'python.exe'))
    seen, out = set(), []
    for path in found:
        if 'windowsapps' in path.lower():  # the Microsoft Store stub: running it can open the Store
            continue
        key = os.path.normcase(os.path.realpath(path)) if os.path.exists(path) else path
        if key not in seen and os.path.exists(path):
            seen.add(key)
            out.append(path)
    return out


def probe(python: str) -> dict | None:
    """Ask a trusted interpreter (ours, not the model's code) what it needs to draw with matplotlib; None when it cannot."""
    try:
        with tempfile.TemporaryDirectory(prefix='ros-probe-') as empty:  # an empty working folder: nothing of ours is first on its path
            done = subprocess.run([python, '-c', PROBE], capture_output=True, text=True, timeout=120, cwd=empty,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), env=dict(os.environ, MPLCONFIGDIR=empty))
        if done.returncode != 0:
            return None
        return json.loads(done.stdout.strip().splitlines()[-1])
    except (OSError, ValueError, subprocess.TimeoutExpired, IndexError):
        return None


_SKIP_LIB = {'test', 'tests', 'idlelib', 'tkinter', 'turtledemo', 'ensurepip', 'site-packages', 'lib2to3', 'pydoc_data', 'turtle.py', '__pycache__'}


def _copy_tree(src: Path, dst: Path, skip=()):
    shutil.copytree(src, dst, ignore=lambda d, names: [n for n in names if n in skip or n.endswith(('.pyc.tmp',))], dirs_exist_ok=True)


def build_runtime(target: Path, info: dict) -> None:
    """A private copy of the interpreter and only the packages matplotlib actually imports, so the container can read it and nothing
    else of the machine's Python (no pywin32, no pip, no other packages). ``target`` is built whole in a sibling folder, then renamed."""
    base = Path(info['base_prefix'])
    partial = target.with_name(target.name + '.partial')
    remove_tree(partial)
    partial.mkdir(parents=True)
    for item in base.iterdir():
        if item.is_file() and (item.name.lower() in ('python.exe', 'python3.dll') or re.match(r'(?i)(python3\d+|vcruntime.*|msvcp.*|concrt.*|ucrtbase.*)\.dll$', item.name)):
            shutil.copy2(item, partial / item.name)
    if (base / 'DLLs').is_dir():
        _copy_tree(base / 'DLLs', partial / 'DLLs')
    _copy_tree(base / 'Lib', partial / 'Lib', _SKIP_LIB)
    packages = partial / 'Lib' / 'site-packages'
    packages.mkdir(parents=True, exist_ok=True)
    tops = sorted({top for _base, top in info['packages']})
    for sitedir, top in info['packages']:
        sitedir = Path(sitedir)
        names = {top.lower().replace('_', '-')}
        for entry in sitedir.iterdir():
            name = entry.name
            low = re.split(r'-', name, maxsplit=1)[0].lower().replace('_', '-')
            if name == top or name == top + '.libs' or (name.endswith(('.dist-info', '.egg-info')) and low in names | {'pillow' if top == 'PIL' else '', 'fonttools' if top == 'fontTools' else '',
                                                                                    'python-dateutil' if top == 'dateutil' else ''}):
                if entry.is_dir():
                    _copy_tree(entry, packages / name, ('__pycache__',) if False else ())
                else:
                    shutil.copy2(entry, packages / name)
    # the matplotlib font list, built once by this trusted interpreter, so a task does not rebuild it
    cache = partial / 'mplcache'
    cache.mkdir()
    subprocess.run([str(partial / 'python.exe'), '-I', '-B', '-c', 'import matplotlib.pyplot'], capture_output=True, timeout=300,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), env=dict(os.environ, MPLCONFIGDIR=str(cache), MPLBACKEND='Agg', PYTHONNOUSERSITE='1'))
    (partial / 'ros-runtime.json').write_text(json.dumps({'version': info['version'], 'matplotlib': info['matplotlib'], 'tops': tops}), encoding='utf-8')
    if target.exists():
        remove_tree(target)
    os.replace(partial, target)


def find_python() -> dict | None:
    """The first candidate interpreter that can draw with matplotlib, as ``probe`` describes it (with its path under ``python``)."""
    for python in candidate_pythons():
        info = probe(python)
        if info:
            return dict(info, python=python)
    return None


def find_manim(python: str) -> tuple[Path | None, str]:
    """The site-packages folder that gives this interpreter ManimGX (software rendering, x264 inside its own native module: no child process,
    no ffmpeg, no LaTeX), or ``(None, reason)``. Manim Community needs ffmpeg and LaTeX as child processes and cannot run in the container."""
    found = []
    if os.environ.get('ROS_MANIMGX_SITE'):
        found.append(Path(os.environ['ROS_MANIMGX_SITE']))
    try:
        from . import voice
        pack = voice.voice_pack()
        if pack:
            found.append(Path(pack) / 'animation' / 'manimgx' / 'site-packages')
    except Exception:
        pass
    found += [Path.home() / 'voice-envs' / 'manimgx' / 'Lib' / 'site-packages', Path.home() / 'voice-envs' / 'manimgx' / 'lib' / 'site-packages']
    reasons = []
    for site in found:
        if not (site / 'manimgx').is_dir():
            continue
        try:
            with tempfile.TemporaryDirectory(prefix='ros-probe-') as empty:
                done = subprocess.run([python, '-s', '-B', '-c', 'import manimgx'], capture_output=True, text=True, timeout=120, cwd=empty,
                                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), env=dict(os.environ, PYTHONPATH=str(site), PYTHONNOUSERSITE='1'))
        except (OSError, subprocess.TimeoutExpired) as exc:
            reasons.append(str(exc)[:120])
            continue
        if done.returncode == 0:
            return site, ''
        reasons.append('ManimGX does not load with the renderer\'s Python (%s)' % (done.stderr.strip().splitlines() or ['?'])[-1][:120])
    return None, (reasons[0] if reasons else 'ManimGX is not installed (the animation pack or ~/voice-envs/manimgx)')


def check() -> tuple[bool, str, dict | None]:
    """Whether the safe renderer can work on this computer, without building anything: the container, then a Python with matplotlib.
    ``(ok, reason, info)``; the reason is plain words for the person."""
    ok, why = appcontainer.available()
    if not ok:
        return False, why, None
    info = find_python()
    if not info:
        return False, 'no Python with matplotlib was found to draw figures with', None
    site, why = find_manim(info['python'])
    info['manim'], info['manim_reason'] = str(site) if site else None, why
    return True, '', info


def sweep(base_dir, older_than=3600) -> None:
    """Remove scratch folders a crashed run left behind."""
    folder = Path(base_dir) / 'scratch'
    if not folder.is_dir():
        return
    now = time.time()
    for entry in folder.iterdir():
        try:
            if entry.name.startswith('task-') and now - entry.stat().st_mtime > older_than:
                remove_tree(entry)
        except OSError:
            pass


def bundle_inputs(folder, limit=1 << 20) -> dict:
    """What a figure task may see of its bundle, as copies: ``plan.json`` and the small plain files of ``visuals/``. Never the folder."""
    out, root = {}, Path(folder)
    candidates = [root / 'plan.json']
    visuals = root / 'visuals'
    if visuals.is_dir() and not is_link(visuals):
        candidates += sorted(p for p in visuals.iterdir())[:30]
    for path in candidates:
        try:
            if is_link(path) or not path.is_file() or path.stat().st_size > limit:
                continue
            rel = path.relative_to(root).as_posix()
            clean_relative('in/' + rel)
            out[rel] = path.read_bytes()
        except (OSError, RenderError):
            continue
    return out


class Renderer:
    """The prepared runtime: where it is and whether the container may use it. ``Renderer.prepare(base)`` builds it on first use."""

    def __init__(self, root: Path, sid: str):
        self.root, self.sid = Path(root), sid
        self.python = self.root / 'python.exe'
        self.manim = None  # the ManimGX site-packages folder, when the container may read it

    @staticmethod
    def prepare(base_dir, info=None) -> 'Renderer':
        """Find an interpreter with matplotlib, copy it, give the container read access to the copy. Raises RenderError with the reason
        (shown to the person as "the safe renderer is not available on this computer: ...")."""
        if info is None:
            ok, why, info = check()
            if not ok:
                raise RenderError(why)
        base = Path(base_dir)
        base.mkdir(parents=True, exist_ok=True)
        sweep(base)
        key = hashlib.sha256(json.dumps([info['base_prefix'], info['version'], info['matplotlib'], info['packages'], 'v1']).encode()).hexdigest()[:12]
        root = base / ('runtime-' + key)
        try:
            if not (root / 'ros-runtime.json').is_file():
                for old in base.glob('runtime-*'):
                    if old != root:
                        remove_tree(old)
                build_runtime(root, info)
            sid = appcontainer.container_sid()
            marker = root / 'granted.txt'
            if not marker.is_file() or marker.read_text(encoding='utf-8') != sid:
                appcontainer.grant(root, sid)
                marker.write_text(sid, encoding='utf-8')
        except (OSError, subprocess.SubprocessError) as exc:
            raise RenderError('the drawing runtime could not be prepared: ' + str(exc)[:300]) from None
        renderer = Renderer(root, sid)
        if info.get('manim'):
            try:
                appcontainer.grant(info['manim'], sid)
                renderer.manim = Path(info['manim'])
            except OSError as exc:  # not the person's folder to change: figures still work, animations wait
                info['manim_reason'] = 'the container cannot be given read access to ManimGX (%s)' % str(exc)[:160]
        return renderer

    def run_script(self, scratch: Scratch, script: str, wall=60, cancel=None, scene=None) -> dict:
        """Run a Python script of the scratch folder in the container. Returns the program's exit, output and what ended it."""
        target = scratch.resolve(script)
        if target.suffix.lower() != '.py' or not target.is_file():
            raise RenderError('give the path of a .py file in the scratch folder (write it with scratch_write)')
        appcontainer.grant(scratch.root, self.sid, write=True)
        shutil.copytree(self.root / 'mplcache', scratch.root / 'mpl', dirs_exist_ok=True)
        windir = os.environ.get('SystemRoot') or r'C:\Windows'
        env = {'SystemRoot': windir, 'PATH': str(self.root) + os.pathsep + windir + r'\System32', 'TEMP': str(scratch.root / 'tmp'), 'TMP': str(scratch.root / 'tmp'),
               'MPLCONFIGDIR': str(scratch.root / 'mpl'), 'MPLBACKEND': 'Agg', 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1',
               'HOME': str(scratch.root), 'USERPROFILE': str(scratch.root), 'PYTHONHASHSEED': '0',
               'LOCALAPPDATA': str(scratch.root / 'tmp'), 'APPDATA': str(scratch.root / 'tmp')}  # Windows needs LOCALAPPDATA to start a container; any folder will do
        if scene:
            if not self.manim:
                raise RenderError('animations are not available on this computer (ManimGX cannot be read by the container)')
            env['PYTHONPATH'] = str(self.manim)
            argv = [str(self.python), '-s', '-B', '-m', 'manimgx', 'render', str(target.relative_to(scratch.root)).replace(os.sep, '/'), scene['class'],
                    '-o', 'out/%s.mp4' % scene['class'], '-r', '%dx%d' % (scene['width'], scene['height']), '--fps', str(scene['fps'])]
            return appcontainer.run(argv, scratch.root, env, read_dirs=[self.root, self.manim], write_dirs=[scratch.root], wall=min(float(wall), 150), cpu=150,
                                    memory=2500 << 20, watch=scratch.root, cancel=cancel)
        return appcontainer.run([str(self.python), '-I', '-B', str(target)], scratch.root, env, read_dirs=[self.root], write_dirs=[scratch.root],
                                wall=min(float(wall), 120), cpu=90, memory=1500 << 20, watch=scratch.root, cancel=cancel)


# ---------------------------------------------------------------------------------------------------------------- the model's tools

TOOLS = {
    'scratch_list': ('List the files in your private scratch folder (copies of the task inputs in in/, your scripts, what scripts wrote to out/).', {}),
    'scratch_read': ('Read one text file of the scratch folder (text only, up to 60,000 characters).',
                     {'path': ('string', 'relative path such as in/plan.json', True), 'start': ('integer', 'first character, to read on')}),
    'scratch_write': ('Write one text file in the scratch folder: .py, .txt, .md, .json, .csv, .svg or .mmd, up to 200 KB. This is how you write a figure script.',
                      {'path': ('string', 'relative path such as work/figure.py', True), 'text': ('string', 'the whole file', True)}),
    'render': ('Run a Python script of the scratch folder in a sealed container (matplotlib and numpy; no network, no files outside the scratch folder, '
               'no other programs; 60 s). Save pictures under out/ (for example plt.savefig("out/figure.png", dpi=150)). To render a ManimGX animation instead, '
               'give scene_class: the scene is rendered to out/<scene_class>.mp4 with a storyboard picture beside it (look at that). Returns what was written and whether each file passes the checks.',
               {'script': ('string', 'relative path of the .py file, such as work/figure.py', True), 'seconds': ('integer', 'time limit, up to 60 (150 for an animation)'),
                'scene_class': ('string', 'the ManimGX Scene class to render from the script (an animation); omit for a plain script'),
                'width': ('integer', 'animation width in pixels, default 960, at most 1280'), 'height': ('integer', 'animation height, default 540, at most 720'),
                'fps': ('integer', 'animation frames per second, default 15, at most 30')}),
    'look': ('Look at a picture of the scratch folder (PNG, JPEG, GIF or WebP, up to 4 MB): it is returned to you as an image. A figure is not done until you have looked at it.',
             {'path': ('string', 'relative path such as out/figure.png', True)}),
    'publish': ('Put one finished picture into the lesson bundle, with your RESULT note beside it. Only a picture that passes the checks is copied; the note is plain text.',
                {'path': ('string', 'the scratch path of the picture, such as out/figure.png', True), 'name': ('string', 'file name in the bundle, such as variance.png', True),
                 'result': ('string', 'your RESULT note: what you looked at, what you fixed, how many elements (plain text, up to 4000 characters)', True)}),
}


def tool_specs() -> list[dict]:
    """The bridge-tool declarations of the render tools, in the shape the adapters take."""
    specs = []
    for name, (help_text, params) in TOOLS.items():
        props = {k: {'type': v[0], 'description': v[1]} for k, v in params.items()}
        specs.append({'name': name, 'description': help_text, 'parameters': {'type': 'object', 'properties': props, 'required': [k for k, v in params.items() if len(v) > 2 and v[2]],
                                                                             'additionalProperties': False}})
    return specs


class Session:
    """One task's render tools: a scratch folder and the six tools over it. Used as a context manager so the folder is always removed."""

    def __init__(self, renderer: Renderer, scratch_parent, bundle: Path | None, inputs: dict | None = None, make_image=None, cancel=None):
        self.renderer, self.bundle, self.cancel = renderer, Path(bundle) if bundle else None, cancel
        self.scratch = Scratch(scratch_parent, inputs)
        self.make_image = make_image  # (fields, bytes, mime) -> a result carrying the picture; None returns words only
        self.published = []

    def __enter__(self):
        return self

    def close(self):
        self.scratch.close()

    def __exit__(self, *exc):
        self.close()

    def call(self, name, args):
        if name not in TOOLS:
            raise RenderError('no such render tool')
        if not isinstance(args, dict):
            raise RenderError('arguments are an object')
        unknown = set(args) - set(TOOLS[name][1])
        if unknown:
            raise RenderError('unknown argument: ' + ', '.join(sorted(map(str, unknown))))
        return getattr(self, '_' + name)(**args)

    def _scratch_list(self):
        return self.scratch.list()

    def _scratch_read(self, path, start=0):
        return self.scratch.read(path, start)

    def _scratch_write(self, path, text):
        return self.scratch.write(path, text)

    def _outputs(self) -> list[dict]:
        rows = []
        for item in self.scratch.files():
            if not item['path'].startswith('out/'):
                continue
            row = {'path': item['path'], 'bytes': item['bytes']}
            try:
                row.update({k: v for k, v in classify(self.scratch.output(item['path'])).items() if k in ('mime', 'width', 'height')}, valid=True)
            except (RenderError, OSError) as exc:
                row.update(valid=False, problem=str(exc)[:200])
            rows.append(row)
        return rows[:50]

    def _render(self, script, seconds=60, scene_class=None, width=960, height=540, fps=15):
        scene = None
        if scene_class:
            if not isinstance(scene_class, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,60}', scene_class):
                raise RenderError('scene_class is the name of a Scene class')
            width, height, fps = int(width or 960), int(height or 540), int(fps or 15)
            if not (160 <= width <= 1280 and 90 <= height <= 720 and 1 <= fps <= 30):
                raise RenderError('an animation is between 160x90 and 1280x720 at 1 to 30 frames a second')
            scene = {'class': scene_class, 'width': width, 'height': height, 'fps': fps}
        result = self.renderer.run_script(self.scratch, script, wall=max(1, min(int(seconds or 60), 150 if scene else 60)), cancel=self.cancel, **({'scene': scene} if scene else {}))
        message = {'cpu': 'it used more CPU time than allowed', 'timeout': 'it ran past the time limit', 'output': 'it printed too much', 'disk': 'it wrote too much',
                   'cancelled': 'the task was stopped'}.get(result['ended'])
        return {'ok': result['ended'] == 'exit' and result['code'] == 0, 'exit': result['code'], 'seconds': result['seconds'], **({'stopped': message} if message else {}),
                'stdout': result['stdout'][-3000:], 'stderr': result['stderr'][-3000:], 'outputs': self._outputs(), 'untrusted': True}

    def _look(self, path):
        data = self.scratch.output(path, MAX_LOOK)
        info = classify(data)
        if info['kind'] != 'image':
            raise RenderError('look shows pictures (PNG, JPEG, GIF, WebP); render an SVG or video to a PNG to see it')
        fields = {'path': path, 'mime': info['mime'], 'width': info['width'], 'height': info['height'], 'bytes': info['bytes'], 'shown': True}
        return self.make_image(fields, data, info['mime']) if self.make_image else dict(fields, shown=False, note='this model cannot be shown a picture')

    def _publish(self, path, name, result):
        if self.bundle is None:
            raise RenderError('there is no bundle to publish to')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,80}', name) or RESERVED.match(name):
            raise RenderError('name is a plain file name such as variance.png')
        if not isinstance(result, str) or not result.strip():
            raise RenderError('write the RESULT note: what you looked at and what you fixed')
        data = self.scratch.output(path, MAX_VIDEO)
        info = classify(data)
        if Path(name).suffix.lower() not in (info['ext'], '.jpeg' if info['ext'] == '.jpg' else info['ext']):
            raise RenderError('the name must end in %s: that is what the file is' % info['ext'])
        folder = self.bundle / 'visuals'
        for part in (self.bundle, folder):
            if is_link(part):
                raise RenderError('the bundle folder is a link; nothing was written')
        folder.mkdir(parents=True, exist_ok=True)
        picture, note = folder / name, folder / (name + '.result.md')
        if is_link(picture) or is_link(note):
            raise RenderError('that name is a link in the bundle; nothing was written')
        note_text = result.replace('\x00', '')[:MAX_NOTE]
        picture.write_bytes(data)
        note.write_text(note_text, encoding='utf-8')
        (self.bundle / 'manifest.json').unlink(missing_ok=True)
        self.published.append(name)
        return {'path': 'visuals/' + name, 'result': 'visuals/' + name + '.result.md', 'bytes': len(data), 'mime': info['mime'], 'width': info['width'], 'height': info['height'],
                'next': 'record it in the node with bundle_plan ({path, result, elements}), then finish the task'}
