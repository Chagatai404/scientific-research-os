"""Inline visuals for HTML sessions: safe SVG, Excalidraw sources and exact placement.

A drawing is one visual with two files. The editable source (an Obsidian Excalidraw scene) is
the artifact; the SVG beside it is an export generated from that same scene, linked through the
visual registry, and it is what a lesson shows inline. A registry record states what kind of
evidence the figure is, so a schematic cannot pass for data and a computed plot says whether its
computation was checked. Standard library only; nothing here needs Obsidian or any plugin.

Honest limits: the SVG is drawn from the scene's geometry in a clean style (it is not
byte-identical to the Excalidraw plugin's own export), and a scene saved in the plugin's
``compressed-json`` form is reported, not decoded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import excalidraw_schematic
import html_sessions as hs
import visuals
from research import local_file

SVG_NS = '{http://www.w3.org/2000/svg}'
MAX_BYTES = 1024 * 1024
# Static drawing only: no scripting, embedding, animation or foreign content can come in through a figure.
SVG_ELEMENTS = {'svg', 'g', 'defs', 'title', 'desc', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'path',
                'text', 'tspan', 'marker', 'lineargradient', 'radialgradient', 'stop', 'clippath', 'use', 'style'}
UNSAFE_STYLE = re.compile(r'javascript:|expression\s*\(|@import|behavior\s*:|-moz-binding|url\(\s*(?![\'"]?#)', re.I)
RESOURCE_ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
SCENE_TYPES = {'rectangle', 'ellipse', 'diamond', 'line', 'arrow', 'text'}
FONTS = {1: 'Segoe UI, Helvetica, Arial, sans-serif', 2: 'Helvetica, Arial, sans-serif', 3: 'Consolas, Menlo, monospace'}


class VisualError(ValueError):
    def __init__(self, code, message):
        super().__init__(f'{code}: {message}')
        self.code = code


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_spec(spec) -> str:
    return sha256(json.dumps(spec, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8'))


# ---------------------------------------------------------------- SVG safety

def svg_problems(text: str) -> list[str]:
    """Reasons an SVG must not be shown inline. Empty means it is static, self-contained drawing."""
    if len(text.encode('utf-8')) > MAX_BYTES:
        return ['larger than 1 MiB']
    if re.search(r'<!\s*(doctype|entity)', text, re.I):
        return ['DOCTYPE and ENTITY declarations are not allowed']
    # The XML parser drops processing instructions, so an xml-stylesheet reference would pass unseen; only the declaration is allowed.
    if '<?' in re.sub(r'\A\s*<\?xml\s[^>]*\?>', '', text, count=1):
        return ['processing instructions (such as xml-stylesheet) are not allowed']
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        return [f'not well-formed XML: {exc}']
    problems = []
    if root.tag != SVG_NS + 'svg':
        problems.append('the root element is not an SVG svg element')
    for element in root.iter():
        tag = element.tag if isinstance(element.tag, str) else ''
        if not tag.startswith(SVG_NS):
            problems.append(f'element outside the SVG namespace: {tag or "comment/instruction"}')
            continue
        name = tag[len(SVG_NS):].lower()
        if name not in SVG_ELEMENTS:
            problems.append(f'element not allowed: {name}')
        if name == 'style' and UNSAFE_STYLE.search(element.text or ''):
            problems.append('style sheet reaches outside the figure')
        for key, value in element.attrib.items():
            local = key.rsplit('}', 1)[-1].lower()
            if local.startswith('on'):
                problems.append(f'event handler attribute: {local}')
            elif local == 'href' and not value.startswith('#'):
                problems.append('link to something outside the figure')
            elif UNSAFE_STYLE.search(value):
                problems.append(f'attribute {local} reaches outside the figure')
    return sorted(set(problems))


# ------------------------------------------------------------ Excalidraw scenes

def read_scene(path: Path):
    """The scene (a dict with ``elements``) of a ``.excalidraw`` or ``.excalidraw.md`` file, plus diagnostics."""
    text = path.read_text(encoding='utf-8-sig')
    if path.name.endswith('.excalidraw'):
        payload = text
    else:
        if 'compressed-json' in text.split('## Drawing', 1)[-1][:200]:
            return None, ['compressed-scene-unsupported: this drawing is saved compressed; run "Decompress current Excalidraw file" '
                          'in Obsidian (or turn off compression in the Excalidraw settings), then refresh the export']
        found = re.search(r'## Drawing\s*```json\s*(\{.*?\})\s*```', text, re.S)
        if not found:
            return None, ['no-drawing: the file has no uncompressed "## Drawing" JSON block']
        payload = found[1]
    try:
        scene = json.loads(payload)
    except ValueError as exc:
        return None, [f'drawing-invalid: {exc}']
    if not isinstance(scene, dict) or not isinstance(scene.get('elements'), list):
        return None, ['drawing-invalid: no elements list']
    return scene, []


def _number(value, default=0.0):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else default


def _dash(element):
    return {'dashed': ' stroke-dasharray="8 6"', 'dotted': ' stroke-dasharray="2 5"'}.get(element.get('strokeStyle'), '')


def _color(value, default):
    return value if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{3,8}|transparent', value) else default


def _points(element):
    x, y = _number(element.get('x')), _number(element.get('y'))
    return [(x + _number(p[0]), y + _number(p[1])) for p in element.get('points') or [] if isinstance(p, list) and len(p) == 2]


def _bounds(element):
    if element.get('type') in {'line', 'arrow'}:
        points = _points(element) or [(_number(element.get('x')), _number(element.get('y')))]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        return min(xs), min(ys), max(xs), max(ys)
    x, y = _number(element.get('x')), _number(element.get('y'))
    return x, y, x + _number(element.get('width')), y + _number(element.get('height'))


def svg_from_scene(scene: dict, title: str, note: str = '') -> tuple[str, list[str]]:
    """Static SVG of an Excalidraw scene. Returns the SVG and notes on anything that could not be drawn."""
    live = [e for e in scene['elements'] if isinstance(e, dict) and not e.get('isDeleted')]
    skipped = sorted({str(e.get('type')) for e in live if e.get('type') not in SCENE_TYPES})
    drawn = [e for e in live if e.get('type') in SCENE_TYPES]
    notes = [f'not drawn (unsupported element type): {name}' for name in skipped]
    containers = {e.get('id'): e for e in drawn if e.get('type') != 'text'}
    boxes = [_bounds(e) for e in drawn] or [(0, 0, 100, 40)]
    pad = 20
    left, top = min(b[0] for b in boxes) - pad, min(b[1] for b in boxes) - pad
    width, height = max(b[2] for b in boxes) + pad - left, max(b[3] for b in boxes) + pad - top
    background = _color((scene.get('appState') or {}).get('viewBackgroundColor'), '#ffffff')
    markers, body, words = {}, [], []

    def marker(colour):
        key = 'arrow-' + colour.lstrip('#')
        markers[key] = (f'<marker id="{key}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
                        f'<path d="M0 0 L10 5 L0 10 z" fill="{colour}"/></marker>')
        return key

    for element in drawn:
        kind = element['type']
        x, y, w, h = (_number(element.get(k)) for k in ('x', 'y', 'width', 'height'))
        stroke, fill = _color(element.get('strokeColor'), '#1e1e1e'), _color(element.get('backgroundColor'), 'transparent')
        outline = f' stroke="{stroke}" stroke-width="{_number(element.get("strokeWidth"), 2):g}"{_dash(element)}'
        opacity = _number(element.get('opacity'), 100)
        if opacity < 100:
            outline += f' opacity="{opacity / 100:g}"'
        common = outline + f' fill="{fill}"'
        angle = math.degrees(_number(element.get('angle')))
        turn = f' transform="rotate({angle:g} {x + w / 2:g} {y + h / 2:g})"' if abs(angle) > 1e-9 and kind != 'text' else ''
        if kind == 'rectangle':
            rounded = ' rx="8"' if element.get('roundness') else ''
            body.append(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}"{rounded}{common}{turn}/>')
        elif kind == 'ellipse':
            body.append(f'<ellipse cx="{x + w / 2:g}" cy="{y + h / 2:g}" rx="{w / 2:g}" ry="{h / 2:g}"{common}{turn}/>')
        elif kind == 'diamond':
            body.append(f'<polygon points="{x + w / 2:g},{y:g} {x + w:g},{y + h / 2:g} {x + w / 2:g},{y + h:g} {x:g},{y + h / 2:g}"{common}{turn}/>')
        elif kind in {'line', 'arrow'}:
            points = _points(element)
            if len(points) >= 2:
                ends = f' marker-end="url(#{marker(stroke)})"' if kind == 'arrow' and element.get('endArrowhead') else ''
                coordinates = ' '.join(f'{px:g},{py:g}' for px, py in points)
                body.append(f'<polyline points="{coordinates}"{outline} fill="none"{ends}/>')
        else:
            text = str(element.get('text') or '')
            size, spacing = _number(element.get('fontSize'), 16), _number(element.get('lineHeight'), 1.25)
            lines = text.split('\n')
            home = containers.get(element.get('containerId'))
            if home is not None:
                bx, by, bw, bh = (_number(home.get(k)) for k in ('x', 'y', 'width', 'height'))
                anchor, ax, first = 'middle', bx + bw / 2, by + (bh - len(lines) * size * spacing) / 2 + size
            elif element.get('textAlign') == 'center':
                anchor, ax, first = 'middle', x + w / 2, y + size
            else:
                anchor, ax, first = 'start', x, y + size
            spans = ''.join(f'<tspan x="{ax:g}" y="{first + i * size * spacing:g}">{escape(line)}</tspan>' for i, line in enumerate(lines))
            font = FONTS.get(element.get('fontFamily'), FONTS[2])
            body.append(f'<text font-family="{font}" font-size="{size:g}" text-anchor="{anchor}" fill="{stroke}">{spans}</text>')
            words.append(text.replace('\n', ' '))
    description = escape((note + ' ' + ' / '.join(words))[:600].strip())
    definitions = ''.join(markers[k] for k in sorted(markers))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{left:g} {top:g} {width:g} {height:g}" width="{width:g}" height="{height:g}" '
           f'role="img" aria-labelledby="t d"><title id="t">{escape(title)}</title><desc id="d">{description}</desc><defs>{definitions}</defs>'
           f'<rect x="{left:g}" y="{top:g}" width="{width:g}" height="{height:g}" fill="{background}"/>' + ''.join(body) + '</svg>\n')
    problems = svg_problems(svg)
    if problems:
        raise VisualError('UNSAFE_SVG', '; '.join(problems))
    return svg, notes


def detect_excalidraw(root: Path) -> dict:
    """What can be said about the Excalidraw plugin from files alone. Presence is not proof it works."""
    import obsidian_plugins  # the one place that reads the vault's plugin configuration
    entry = obsidian_plugins.detect(root)['excalidraw']
    return {'plugin_files_present': entry['state'] in ('enabled', 'installed-disabled', 'invalid'), 'version': entry['version'],
            'enabled': entry['listed'], 'checked_in_obsidian': False,
            'note': 'determined from files only; this was not run inside Obsidian'}


# -------------------------------------------------------------------- registry

def _record_file(root: Path, visual_id: str):
    records, _ = visuals.discover(root)
    record = records.get(visual_id)
    if record is None:
        raise VisualError('UNKNOWN_VISUAL', f'no valid registry record {visual_id} under {root}')
    return record, Path(root).resolve() / record['path']


def _write_record(file: Path, record: dict):
    clean = {k: v for k, v in record.items() if k != 'path'}
    file.write_text(json.dumps(clean, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')


def _slug(value: str) -> str:
    return re.sub(r'[^a-z0-9._-]+', '-', value.lower()).strip('-')


def ensure_schematic(root, spec: dict, *, visual_id: str, concepts: list[str], directory: str = 'Visuals') -> dict:
    """The Excalidraw source, its SVG export and a registry record for one schematic; reused when unchanged.

    Never overwrites: asking again for the same visual with the same spec returns what exists, and a changed
    spec for an existing visual is refused so a drawing someone edited by hand is not lost.
    """
    root = Path(root).resolve()
    excalidraw_schematic.validate_spec(spec)
    if not visuals.VISUAL_ID.fullmatch(visual_id):
        raise VisualError('VISUAL_ID', 'a visual id looks like VIS-name')
    if not directory or '\\' in directory or ':' in directory or any(part in {'', '.', '..'} for part in directory.split('/')):
        raise VisualError('DIRECTORY', 'the directory must be a relative path inside the vault')
    base = _slug(visual_id)
    folder = root / directory
    source, export, record_file = folder / f'{base}.excalidraw.md', folder / f'{base}.svg', folder / f'{base}{visuals.SUFFIX}'
    spec_digest = digest_spec(spec)
    if record_file.exists():
        existing = json.loads(record_file.read_text(encoding='utf-8-sig'))
        if existing.get('spec_sha256') == spec_digest and source.exists() and export.exists():
            return {'visual_id': visual_id, 'reused': True, 'artifact': existing['artifact'], 'export': existing['exports'][0]['path'], 'notes': []}
        raise VisualError('SPEC_CHANGED', f'{visual_id} already exists with a different drawing; choose a new visual_id, or edit the drawing '
                                          f'in Excalidraw and run: visual_assets.py refresh {visual_id}')
    if source.exists() or export.exists():
        raise VisualError('FILE_EXISTS', f'{source.name} or {export.name} already exists without a registry record; choose a new visual_id')
    relative = lambda path: path.relative_to(root).as_posix()
    folder.mkdir(parents=True, exist_ok=True)
    source.write_text(excalidraw_schematic.render(spec), encoding='utf-8', newline='\n')
    scene, problems = read_scene(source)
    if scene is None:
        source.unlink()
        raise VisualError('SCENE_UNREADABLE', '; '.join(problems))
    svg, notes = svg_from_scene(scene, spec.get('title', visual_id), spec.get('note', excalidraw_schematic.DEFAULT_NOTE))
    export.write_text(svg, encoding='utf-8', newline='\n')
    record = {'visual_schema': 1, 'visual_id': visual_id, 'title': spec.get('title', visual_id), 'kind': 'conceptual-schematic',
              'concepts': concepts, 'source_type': 'schematic', 'verification_status': 'rendered', 'artifact': relative(source),
              'mode': 'conceptual-schematic', 'quantitative': False, 'exports': [{'path': relative(export), 'format': 'svg'}],
              'spec_sha256': spec_digest, 'source_sha256': sha256(source.read_bytes()), 'generator': 'visual_assets.py'}
    problems = visuals.issues(record, root)
    if problems:
        source.unlink(); export.unlink()
        raise VisualError('RECORD_INVALID', '; '.join(problems))
    _write_record(record_file, record)
    return {'visual_id': visual_id, 'reused': False, 'artifact': record['artifact'], 'export': record['exports'][0]['path'], 'notes': notes}


def refresh_export(root, visual_id: str) -> dict:
    """Regenerate the SVG from the current drawing when the drawing changed (or the export is missing)."""
    root = Path(root).resolve()
    record, file = _record_file(root, visual_id)
    if not record['artifact'].endswith(('.excalidraw.md', '.excalidraw')):
        raise VisualError('NOT_A_DRAWING', f"{visual_id}'s artifact is not an Excalidraw drawing; there is nothing to export")
    artifact = local_file(root, record['artifact'])
    current = sha256(artifact.read_bytes())
    exports = record.get('exports') or []
    if exports and (root / exports[0]['path']).is_file() and record.get('source_sha256') == current:
        return {'visual_id': visual_id, 'refreshed': False, 'export': exports[0]['path'], 'notes': []}
    scene, problems = read_scene(artifact)
    if scene is None:
        raise VisualError('SCENE_UNREADABLE', '; '.join(problems))
    svg, notes = svg_from_scene(scene, record['title'])
    target = (root / exports[0]['path']) if exports else artifact.with_name(re.sub(r'\.excalidraw(\.md)?\Z', '', artifact.name) + '.svg')
    target.write_text(svg, encoding='utf-8', newline='\n')
    record['exports'] = [{'path': target.relative_to(root).as_posix(), 'format': 'svg'}]
    record['source_sha256'] = current
    _write_record(file, record)
    return {'visual_id': visual_id, 'refreshed': True, 'export': record['exports'][0]['path'], 'notes': notes}


def attach_visual(root, session: str, visual_id: str, resource_id: str | None = None) -> dict:
    """Declare a registered visual as an image resource of a session, ready to be placed in the lesson."""
    root = Path(root).resolve()
    record, _ = _record_file(root, visual_id)
    if record['verification_status'] == 'candidate':
        raise VisualError('NOT_RENDERED', f'{visual_id} is only a candidate; render and inspect it before it enters a lesson')
    artifact = record['artifact']
    if artifact.endswith(('.excalidraw.md', '.excalidraw')):
        export = refresh_export(root, visual_id)['export']
        record, _ = _record_file(root, visual_id)
    elif artifact.lower().endswith(('.svg', '.png')):
        export = artifact
    elif record.get('exports'):
        export = record['exports'][0]['path']
    else:
        raise VisualError('NO_INLINE_EXPORT', f'{visual_id} has no SVG or PNG to show inline; register an export for {artifact}')
    source = local_file(root, export)
    data = source.read_bytes()
    suffix = source.suffix.lower()
    if suffix not in {'.svg', '.png'} or len(data) > MAX_BYTES:
        raise VisualError('EXPORT_UNUSABLE', 'an inline export must be an SVG or PNG of at most 1 MiB')
    if suffix == '.svg':
        problems = svg_problems(data.decode('utf-8', errors='replace'))
        if problems:
            raise VisualError('UNSAFE_SVG', '; '.join(problems))
    resource = {'id': resource_id or re.sub(r'[^A-Za-z0-9_-]', '-', visual_id), 'kind': 'image', 'visual_id': visual_id,
                'visual_class': visuals.visual_class(record)}
    if not RESOURCE_ID.match(resource['id']):
        raise VisualError('BAD_RESOURCE_ID', 'a resource id uses letters, digits, hyphen and underscore')
    if record.get('verification_record'):
        import scientific_verify
        try:
            outcome = scientific_verify.validate_record(json.loads(local_file(root, record['verification_record']).read_text(encoding='utf-8')))['outcome']
        except (scientific_verify.VerificationError, ValueError) as exc:
            raise VisualError('VERIFICATION_INVALID', f'{visual_id} cites a verification record that is not valid: {exc}') from None
        resource['verification_outcome'] = outcome
    md, view, _ = hs.paths(root, session)
    (md.parent / (view.stem + '.assets')).mkdir(exist_ok=True)
    resource['path'] = f'{view.stem}.assets/{resource["id"]}{suffix}'
    target = md.parent / resource['path']
    if not target.exists() or target.read_bytes() != data:
        staging = target.with_name(target.name + '.tmp')
        staging.write_bytes(data)
        staging.replace(target)
    state = hs.load_session(root, session)
    hs.update_session(root, session, resources=[r for r in state.get('resources', []) if r.get('id') != resource['id']] + [resource])
    return {'resource': resource, 'next': f'html_sessions.py place {session} --figure {resource["id"]} --alt "..." --after-heading "..."'}


# ------------------------------------------------------------------- placement

def place_visual(root, session: str, *, figure: str | None = None, widget: str | None = None, after_heading: str | None = None,
                 after_text: str | None = None, at_end: bool = False, alt: str | None = None, caption: str | None = None) -> dict:
    """Put one declared figure or widget exactly where the lesson wants it, by editing the lesson's Markdown."""
    if (figure is None) == (widget is None):
        raise VisualError('TARGET', 'give exactly one of figure or widget')
    if sum(1 for chosen in (after_heading is not None, after_text is not None, bool(at_end)) if chosen) != 1:
        raise VisualError('POSITION', 'give exactly one of after_heading, after_text or at_end')
    state = hs.load_session(root, session)
    identifier = figure or widget
    if figure is not None:
        if not any(r.get('id') == figure and r.get('kind') == 'image' for r in state.get('resources', [])):
            raise VisualError('UNDECLARED', f"no image resource '{figure}' is declared; attach it first (html_sessions.py attach-visual)")
        if not alt or re.search(r'[\[\]\n]', alt):
            raise VisualError('ALT_REQUIRED', 'a figure needs alt text (one line, no square brackets) for readers who cannot see it')
        if caption and re.search(r'["\n]', caption):
            raise VisualError('CAPTION', 'a caption is one line without double quotes')
        marker = f'![{alt}](resource:{figure}' + (f' "{caption}")' if caption else ')')
    else:
        if not any(w.get('id') == widget for w in state.get('widgets', [])):
            raise VisualError('UNDECLARED', f"no widget '{widget}' is declared in this session")
        marker = f'<!-- ros-widget: {widget} -->'
    if identifier in hs.placements(state)['figures' if figure else 'widgets']:
        raise VisualError('ALREADY_PLACED', f"'{identifier}' is already placed in the lesson")
    source = state['source_markdown']
    newline = '\r\n' if '\r\n' in source else '\n'
    lines = source.replace('\r\n', '\n').split('\n')
    prose = list(hs.prose_lines(lines))
    if at_end:
        at = len(lines)
        while at and not lines[at - 1].strip():
            at -= 1
    elif after_heading is not None:
        hits = [n for n, heading, text in prose if heading and text == after_heading]
        if len(hits) != 1:
            raise VisualError('HEADING', f"{'no' if not hits else 'more than one'} heading reads exactly {after_heading!r}")
        at = hits[0] + 1
    else:
        hits = [n for n, _, text in prose if after_text in text]
        if len(hits) != 1:
            raise VisualError('TEXT', f"{'no' if not hits else 'more than one'} line contains {after_text!r}; give a more specific phrase")
        at = hits[0] + 1
        while at < len(lines) and lines[at].strip():  # keep the block the phrase sits in whole
            at += 1
    insertion = ([''] if at > 0 and lines[at - 1].strip() else []) + [marker] + ([''] if at < len(lines) and lines[at].strip() else [])
    lines[at:at] = insertion
    hs.update_session(root, session, text=newline.join(lines))
    return {'placed': identifier, 'marker': marker}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--root', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('svg-check', help='say whether an SVG file is safe to show inline').add_argument('file', type=Path)
    schematic = sub.add_parser('schematic', help='create a schematic (Excalidraw source + SVG + registry record) from a spec')
    schematic.add_argument('--spec', type=Path, required=True)
    schematic.add_argument('--id', required=True)
    schematic.add_argument('--concept', action='append', required=True)
    schematic.add_argument('--directory', default='Visuals')
    sub.add_parser('refresh', help='regenerate an SVG from its edited drawing').add_argument('visual_id')
    sub.add_parser('status', help='what the vault files say about the Excalidraw plugin')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        if args.command == 'svg-check':
            problems = svg_problems(args.file.read_text(encoding='utf-8'))
            result = {'safe': not problems, 'problems': problems}
        elif args.command == 'schematic':
            result = ensure_schematic(args.root, json.loads(args.spec.read_text(encoding='utf-8')), visual_id=args.id,
                                      concepts=args.concept, directory=args.directory)
        elif args.command == 'refresh':
            result = refresh_export(args.root, args.visual_id)
        else:
            result = detect_excalidraw(args.root)
    except (VisualError, excalidraw_schematic.SpecError, OSError, ValueError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('safe', True) else 1


if __name__ == '__main__':
    raise SystemExit(main())
