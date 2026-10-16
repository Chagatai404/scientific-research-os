"""Declarative scientific diagrams: a spec that carries the numbers, renderers that only draw them, and checks that read the same numbers.

A figure is trustworthy only through what it was drawn from, so a diagram here is a *spec* (``diagram_schema: 1``) of coordinates, atoms and
constraints. This module draws it (static SVG, and a self-contained interactive 3D viewer page), registers the result as a visual that starts
at ``rendered`` (never ``verified``), and builds the ``scientific_verify`` checks from the very same spec, so picture and check cannot drift.

Kinds
``geometry2d``       points, segments, polygons, circles, angle marks, constraints (to scale, equal axes)
``geometry3d``       the same in 3D, drawn as four linked views: front, top, side and isometric (orthographic, one common scale)
``molecule``         an explicit atom and bond graph with 2D or 3D coordinates; valence, formula and mass are checkable
``structure-trace``  the C-alpha backbone trace of a PDB-format file (not a ribbon, not a surface); bound to the file by its hash

Standard library only. RDKit, PyVista, Matplotlib, Graphviz and similar tools are optional capabilities: ``capabilities`` reports which exist and
nothing here imports or installs them. Depicting a molecule from a SMILES string needs RDKit and is not done here; give the atom graph.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import importlib.util
import json
import math
import re
import shutil
import sys
from pathlib import Path

import structure_verify as checks
import visual_assets
import visuals

SCHEMA = 1
KINDS = ('geometry2d', 'geometry3d', 'molecule', 'structure-trace')
PANEL, MARGIN = 300, 38
CPK = {'H': '#ffffff', 'C': '#c8c8c8', 'N': '#8f9fff', 'O': '#ff9a9a', 'F': '#90e050', 'Cl': '#6fe06f', 'Br': '#c88a5a', 'I': '#c070c0', 'S': '#ffe070', 'P': '#ffb060'}
DASHES = ('', '8 4', '2 3', '10 3 2 3')
SPEC_FIELDS = {'diagram_schema', 'id', 'title', 'kind', 'units', 'note', 'schematic', 'points', 'segments', 'polygons', 'circles', 'angles', 'constraints',
               'atoms', 'bonds', 'explicit_hydrogens', 'expected_formula', 'expected_charge', 'expected_mass', 'chains', 'source'}


class DiagramError(ValueError):
    pass


def esc(value) -> str:
    return html.escape(str(value), quote=True)


# ------------------------------------------------------------------------------------------------ validation

def _numbers(value, n):
    return isinstance(value, list) and len(value) == n and all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in value)


def _atom_coords(atom):
    coords = atom.get('xyz') if atom.get('xyz') is not None else atom.get('xy')
    return coords if isinstance(coords, list) and len(coords) in (2, 3) and _numbers(coords, len(coords)) else None


def molecule_dim(spec) -> int:
    """2 or 3: the dimension of a molecule spec's coordinates (valid specs only)."""
    return len(_atom_coords(next(iter(spec['atoms'].values()))))


def is_3d(spec) -> bool:
    return spec['kind'] in ('geometry3d', 'structure-trace') or (spec['kind'] == 'molecule' and molecule_dim(spec) == 3)


def validate(spec) -> list[str]:
    """Structural problems with a spec. Empty means it can be drawn; it says nothing about whether the numbers are right."""
    if not isinstance(spec, dict):
        return ['a diagram spec is an object']
    out = [f'unknown field {k!r}' for k in sorted(set(spec) - SPEC_FIELDS)]
    if spec.get('diagram_schema') != SCHEMA:
        out.append('diagram_schema must be 1')
    if not isinstance(spec.get('id'), str) or not visuals.VISUAL_ID.fullmatch(spec['id']):
        out.append('id looks like VIS-right-triangle')
    if not isinstance(spec.get('title'), str) or not spec['title'].strip():
        out.append('title is required')
    kind = spec.get('kind')
    if kind not in KINDS:
        return out + ['kind must be one of ' + ', '.join(KINDS)]
    try:
        if kind in ('geometry2d', 'geometry3d'):
            points, dim = checks._points(spec.get('points'))
            if dim != (2 if kind == 'geometry2d' else 3):
                out.append(f'{kind} points have {2 if kind == "geometry2d" else 3} coordinates')
            for pair in spec.get('segments', []):
                checks._pair(points, pair)
            for polygon in spec.get('polygons', []):
                if not isinstance(polygon, list) or len(polygon) < 3:
                    out.append('a polygon lists at least three point names')
                else:
                    for name in polygon:
                        checks._name(points, name)
            for circle in spec.get('circles', []):
                if kind != 'geometry2d' or not isinstance(circle, dict):
                    out.append('circles are 2D objects {center, radius}')
                else:
                    checks._name(points, circle.get('center'))
                    if not isinstance(circle.get('radius'), (int, float)) or circle['radius'] <= 0:
                        out.append('a circle needs a positive radius')
            for angle in spec.get('angles', []):
                for key in ('at', 'from', 'to'):
                    checks._name(points, angle.get(key) if isinstance(angle, dict) else None)
        elif kind == 'molecule':
            checks.molecule_counts(spec.get('atoms'), spec.get('bonds'))
            dims = {len(c) if (c := _atom_coords(a)) else None for a in spec['atoms'].values()}
            if len(dims) != 1 or None in dims:
                out.append('every atom has finite xy (2D) or xyz (3D) coordinates, all in one dimension')
        else:
            chains = spec.get('chains')
            if not isinstance(chains, dict) or not chains:
                out.append('chains is {chain: [[residue number, x, y, z], ...]}')
            else:
                for name, trace in chains.items():
                    good = isinstance(trace, list) and len(trace) >= 2 and all(isinstance(r, list) and len(r) == 4 and type(r[0]) is int and _numbers(r[1:], 3) for r in trace)
                    if not good:
                        out.append(f'chain {name!r} is a list of at least two [residue number, x, y, z]')
    except checks.StructureError as exc:
        out.append(str(exc))
    return out


def require_valid(spec):
    problems = validate(spec)
    if problems:
        raise DiagramError('; '.join(problems))
    return spec


# ------------------------------------------------------------------------------------------------ scenes (what is drawn)

def scene3d(spec) -> dict:
    """points {name: (x, y, z)}, edges [(a, b, order, dash)], polygons, labels: the common form every 3D drawing is made from."""
    kind = spec['kind']
    if kind == 'geometry3d':
        pts = {k: tuple(v) for k, v in spec['points'].items()}
        return {'points': pts, 'edges': [(a, b, 1, 0) for a, b in spec.get('segments', [])], 'polygons': spec.get('polygons', []),
                'labels': {k: k for k in pts}, 'atoms': {}}
    if kind == 'molecule':
        pts = {k: tuple(a['xyz']) for k, a in spec['atoms'].items()}
        return {'points': pts, 'edges': [(a, b, o, 0) for a, b, o in spec['bonds']], 'polygons': [],
                'labels': {k: a['el'] for k, a in spec['atoms'].items()}, 'atoms': dict(spec['atoms'])}
    pts, edges, labels = {}, [], {}
    for index, (chain, trace) in enumerate(sorted(spec['chains'].items())):
        previous = None
        for number, x, y, z in trace:
            name = f'{chain}{number}'
            pts[name] = (x, y, z)
            if number % 20 == 0 or number == trace[0][0] or number == trace[-1][0]:
                labels[name] = name
            if previous and number == previous[0] + 1 and math.dist(previous[1], (x, y, z)) <= 4.5:
                edges.append((f'{chain}{previous[0]}', name, 1, index % len(DASHES)))
            previous = (number, (x, y, z))
    return {'points': pts, 'edges': edges, 'polygons': [], 'labels': labels, 'atoms': {}}


# ------------------------------------------------------------------------------------------------ SVG

def _svg(width, height, title, description, body):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
            f'font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="13"><title>{esc(title)}</title><desc>{esc(description)}</desc>'
            f'<rect width="100%" height="100%" fill="#ffffff"/>{body}</svg>\n')


def _fit2(coords, size, margin):
    xs, ys = [c[0] for c in coords], [c[1] for c in coords]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    scale = (size - 2 * margin) / span
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    return (lambda p: (size / 2 + (p[0] - cx) * scale, size / 2 - (p[1] - cy) * scale)), scale


def _note(spec, width, y):
    if spec.get('schematic'):
        text = 'Schematic, not to scale.'
    else:
        text = 'Drawn to scale from the declared coordinates' + (f" ({spec['units']})" if spec.get('units') else '') + '; rendering is not verification.'
    return f'<text x="{width / 2}" y="{y}" text-anchor="middle" fill="#555" font-size="11">{esc(text)}</text>'


def render_2d(spec) -> str:
    points = {k: tuple(v) for k, v in spec['points'].items()}
    extent = list(points.values())
    for circle in spec.get('circles', []):
        cx, cy = points[circle['center']]
        extent += [(cx - circle['radius'], cy - circle['radius']), (cx + circle['radius'], cy + circle['radius'])]
    size = 480
    to, scale = _fit2(extent, size, 56)
    body = []
    for polygon in spec.get('polygons', []):
        body.append('<polygon points="' + ' '.join('%.2f,%.2f' % to(points[n]) for n in polygon) + '" fill="#eef3fb" stroke="none"/>')
    for circle in spec.get('circles', []):
        x, y = to(points[circle['center']])
        body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{circle["radius"] * scale:.2f}" fill="none" stroke="#335" stroke-width="1.5"/>')
    for a, b in spec.get('segments', []):
        (x1, y1), (x2, y2) = to(points[a]), to(points[b])
        body.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="#222" stroke-width="2"/>')
    for angle in spec.get('angles', []):
        at, a, b = angle['at'], angle['from'], angle['to']
        degrees = checks.angle_deg(points, at, a, b)
        (vx, vy), (ax, ay), (bx, by) = to(points[at]), to(points[a]), to(points[b])
        a1, a2 = math.atan2(ay - vy, ax - vx), math.atan2(by - vy, bx - vx)
        delta = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
        if abs(degrees - 90) <= 0.5:
            u, w = (math.cos(a1) * 16, math.sin(a1) * 16), (math.cos(a2) * 16, math.sin(a2) * 16)
            body.append(f'<path d="M {vx + u[0]:.2f} {vy + u[1]:.2f} L {vx + u[0] + w[0]:.2f} {vy + u[1] + w[1]:.2f} L {vx + w[0]:.2f} {vy + w[1]:.2f}" fill="none" stroke="#a33" stroke-width="1.5"/>')
            label = '90°'
        else:
            r = 24
            body.append(f'<path d="M {vx + r * math.cos(a1):.2f} {vy + r * math.sin(a1):.2f} A {r} {r} 0 0 {1 if delta > 0 else 0} '
                        f'{vx + r * math.cos(a2):.2f} {vy + r * math.sin(a2):.2f}" fill="none" stroke="#a33" stroke-width="1.5"/>')
            label = f'{degrees:.1f}°'
        mid = a1 + delta / 2
        body.append(f'<text x="{vx + 40 * math.cos(mid):.2f}" y="{vy + 40 * math.sin(mid) + 4:.2f}" text-anchor="middle" fill="#a33" font-size="12">{esc(label)}</text>')
    for name, point in points.items():
        x, y = to(point)
        body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.5" fill="#222"/><text x="{x + 7:.2f}" y="{y - 7:.2f}" font-weight="600">{esc(name)}</text>')
    body.append(_note(spec, size, size - 12))
    return _svg(size, size, spec['title'], f'{len(points)} points, {len(spec.get("segments", []))} segments, {len(spec.get("constraints", []))} declared constraints.', ''.join(body))


def render_molecule_2d(spec) -> str:
    coords = {k: tuple(a['xy']) for k, a in spec['atoms'].items()}
    size = 480
    to, _ = _fit2(list(coords.values()), size, 70)
    body, radius = [], 12
    for a, b, order in spec['bonds']:
        (x1, y1), (x2, y2) = to(coords[a]), to(coords[b])
        length = math.hypot(x2 - x1, y2 - y1) or 1.0
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        nx, ny = -uy, ux
        for k in range(order):
            shift = (k - (order - 1) / 2) * 5
            body.append(f'<line x1="{x1 + ux * radius + nx * shift:.2f}" y1="{y1 + uy * radius + ny * shift:.2f}" x2="{x2 - ux * radius + nx * shift:.2f}" '
                        f'y2="{y2 - uy * radius + ny * shift:.2f}" stroke="#222" stroke-width="2"/>')
    for key, atom in spec['atoms'].items():
        x, y = to(coords[key])
        charge = int(atom.get('charge', 0))
        mark = (('+' if charge > 0 else '−') + (str(abs(charge)) if abs(charge) > 1 else '')) if charge else ''
        body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius}" fill="{CPK.get(atom["el"], "#dddddd")}" stroke="#222" stroke-width="1"/>'
                    f'<text x="{x:.2f}" y="{y + 4.5:.2f}" text-anchor="middle" font-weight="600">{esc(atom["el"])}</text>'
                    + (f'<text x="{x + 12:.2f}" y="{y - 10:.2f}" font-size="11">{esc(mark)}</text>' if mark else ''))
    counts, _, _ = checks.molecule_counts(spec['atoms'], spec['bonds'])
    body.append(f'<text x="{size / 2}" y="26" text-anchor="middle" font-weight="600">{esc(checks.hill_formula(counts))}</text>')
    body.append(_note(spec, size, size - 12))
    return _svg(size, size, spec['title'], f'Molecule {checks.hill_formula(counts)} with {len(spec["atoms"])} atoms and {len(spec["bonds"])} bonds; layout as declared.', ''.join(body))


# (title, projection to (screen x, screen y up, depth)); right-handed axes, z up.
VIEWS = {'front': ('Front (x right, z up)', lambda p: (p[0], p[2], p[1])), 'top': ('Top (x right, y up)', lambda p: (p[0], p[1], -p[2])),
         'side': ('Side (y right, z up)', lambda p: (p[1], p[2], -p[0])),
         'isometric': ('Isometric (z up)', lambda p: ((p[0] - p[1]) * math.cos(math.pi / 6), p[2] + (p[0] + p[1]) * math.sin(math.pi / 6), p[0] + p[1]))}
AXES = {'front': ('x', 'z'), 'top': ('x', 'y'), 'side': ('y', 'z'), 'isometric': ('x', 'y', 'z')}
UNIT = {'x': (1, 0, 0), 'y': (0, 1, 0), 'z': (0, 0, 1)}


def render_3d(spec) -> str:
    """Four orthographic views of one scene on one common scale, so lengths in different panels can be compared."""
    scene = scene3d(spec)
    projected = {v: {k: fn(p) for k, p in scene['points'].items()} for v, (_, fn) in VIEWS.items()}
    span = max(max(max(q[0] for q in pts.values()) - min(q[0] for q in pts.values()), max(q[1] for q in pts.values()) - min(q[1] for q in pts.values()))
               for pts in projected.values()) or 1.0
    scale = (PANEL - 2 * MARGIN) / span
    body = []
    for index, (view, (title, fn)) in enumerate(VIEWS.items()):
        ox, oy = (index % 2) * PANEL, (index // 2) * (PANEL + 8)
        pts = projected[view]
        cx = (max(q[0] for q in pts.values()) + min(q[0] for q in pts.values())) / 2
        cy = (max(q[1] for q in pts.values()) + min(q[1] for q in pts.values())) / 2

        def to(q, ox=ox, oy=oy, cx=cx, cy=cy):
            return ox + PANEL / 2 + (q[0] - cx) * scale, oy + PANEL / 2 + 6 - (q[1] - cy) * scale

        body.append(f'<g><rect x="{ox + 2}" y="{oy + 2}" width="{PANEL - 4}" height="{PANEL - 4}" fill="none" stroke="#bbb"/>'
                    f'<text x="{ox + 10}" y="{oy + 18}" font-size="12" font-weight="600">{esc(title)}</text>')
        for polygon in scene['polygons']:
            body.append('<polygon points="' + ' '.join('%.2f,%.2f' % to(pts[n]) for n in polygon) + '" fill="#eef3fb" fill-opacity="0.7" stroke="none"/>')
        for a, b, order, dash in sorted(scene['edges'], key=lambda e: pts[e[0]][2] + pts[e[1]][2]):
            (x1, y1), (x2, y2) = to(pts[a]), to(pts[b])
            body.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="#222" stroke-width="{1.5 + (order - 1) * 1.2:.1f}"'
                        + (f' stroke-dasharray="{DASHES[dash]}"' if DASHES[dash] else '') + '/>')
        for name, q in pts.items():
            x, y = to(q)
            atom = scene['atoms'].get(name)
            body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{7 if atom else 3}" fill="{CPK.get(atom["el"], "#ddd") if atom else "#222"}" stroke="#222"/>')
            if name in scene['labels']:
                body.append(f'<text x="{x + 6:.2f}" y="{y - 6:.2f}" font-size="11">{esc(scene["labels"][name])}</text>')
        tx, ty = ox + 30, oy + PANEL - 30
        for letter in AXES[view]:
            a0, a1 = fn((0, 0, 0)), fn(UNIT[letter])
            dx, dy = (a1[0] - a0[0]) * 22, -(a1[1] - a0[1]) * 22
            body.append(f'<line x1="{tx}" y1="{ty}" x2="{tx + dx:.1f}" y2="{ty + dy:.1f}" stroke="#a33" stroke-width="1.2"/>'
                        f'<text x="{tx + dx * 1.35:.1f}" y="{ty + dy * 1.35 + 4:.1f}" font-size="11" fill="#a33">{letter}</text>')
        body.append('</g>')
    width, height = PANEL * 2, PANEL * 2 + 34
    body.append(_note(spec, width, height - 8))
    noun = {'geometry3d': 'solid', 'molecule': 'molecule', 'structure-trace': 'C-alpha backbone trace'}[spec['kind']]
    return _svg(width, height, spec['title'], f'Four orthographic views of a {noun} with {len(scene["points"])} points; right-handed axes, one common scale.', ''.join(body))


def render_svg(spec) -> str:
    require_valid(spec)
    kind = spec['kind']
    if kind == 'geometry2d':
        text = render_2d(spec)
    elif kind == 'molecule' and molecule_dim(spec) == 2:
        text = render_molecule_2d(spec)
    else:
        text = render_3d(spec)
    problems = visual_assets.svg_problems(text)
    if problems:
        raise DiagramError('the drawing is not a static SVG: ' + '; '.join(problems))
    return text


# ------------------------------------------------------------------------------------------------ interactive 3D viewer (standalone page)

VIEWER = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
<title>__TITLE__</title>
<style>body{margin:0;font:14px system-ui,sans-serif;background:#fff;color:#222}main{max-width:760px;margin:0 auto;padding:12px 16px}
canvas{width:100%;max-width:720px;aspect-ratio:1/1;border:1px solid #bbb;border-radius:6px;touch-action:none;cursor:grab;background:#fafcff}
button{font:inherit;padding:4px 10px;margin:2px;border:1px solid #888;border-radius:5px;background:#f4f4f4;cursor:pointer}p.note{color:#555;font-size:12px}</style></head>
<body><main><h1 style="font-size:18px">__TITLE__</h1>
<p>__DESCRIPTION__</p>
<canvas id="c" width="720" height="720" role="img" aria-label="__TITLE__: drag to rotate, scroll to zoom"></canvas>
<div role="group" aria-label="Views"><button data-v="front">Front</button><button data-v="top">Top</button><button data-v="side">Side</button><button data-v="isometric">Isometric</button><button id="reset">Reset</button></div>
<p class="note">Drag to rotate, scroll to zoom, arrow keys to turn. Orthographic projection of the declared coordinates (__UNITS__); right-handed axes, z up. __NOTE__</p>
<script type="application/json" id="scene">__SCENE__</script>
<script>
(function () {
  var S = JSON.parse(document.getElementById('scene').textContent), cv = document.getElementById('c'), g = cv.getContext('2d');
  var P = S.points, C = [0, 0, 0], R = 0, i, k;
  // R is the diagonal of the bounding box, so the scene stays inside the canvas in every orientation.
  for (k = 0; k < 3; k++) { var lo = Infinity, hi = -Infinity; for (i = 0; i < P.length; i++) { lo = Math.min(lo, P[i][k]); hi = Math.max(hi, P[i][k]); } C[k] = (lo + hi) / 2; R += (hi - lo) * (hi - lo); }
  R = Math.sqrt(R); if (R <= 1e-9) R = 1;
  // yaw turns about z, pitch tilts about x. Looking along +y with yaw 0 and pitch 0 gives the front view (x right, z up).
  var V = {front: [0, 0], top: [0, Math.PI / 2], side: [-Math.PI / 2, 0], isometric: [Math.PI / 4, 0.6155]};
  var st = {yaw: 0.6, pitch: 0.5, zoom: 1}, drag = null;
  function rot(p) {
    var x = p[0] - C[0], y = p[1] - C[1], z = p[2] - C[2], cy = Math.cos(st.yaw), sy = Math.sin(st.yaw), cp = Math.cos(st.pitch), sp = Math.sin(st.pitch);
    var x1 = x * cy - y * sy, y1 = x * sy + y * cy;
    return [x1, z * cp + y1 * sp, y1 * cp - z * sp];
  }
  function scale() { return 600 / (R * 1.25) * st.zoom; }
  function proj(p) { var q = rot(p), s = scale(); return [360 + q[0] * s, 360 - q[1] * s, q[2]]; }
  function draw() {
    g.clearRect(0, 0, 720, 720); var Q = P.map(proj), order = S.edges.slice().sort(function (a, b) { return (Q[b[0]][2] + Q[b[1]][2]) - (Q[a[0]][2] + Q[a[1]][2]); });
    order.forEach(function (e) { g.beginPath(); g.moveTo(Q[e[0]][0], Q[e[0]][1]); g.lineTo(Q[e[1]][0], Q[e[1]][1]); g.lineWidth = 1.5 + (e[2] - 1) * 1.2; g.setLineDash(e[3] ? [8, 4] : []); g.strokeStyle = '#222'; g.stroke(); });
    g.setLineDash([]);
    Q.forEach(function (q, j) { var a = S.colors[j]; g.beginPath(); g.arc(q[0], q[1], a ? 9 : 3.5, 0, 6.2832); g.fillStyle = a || '#222'; g.fill(); g.lineWidth = 1; g.strokeStyle = '#222'; g.stroke();
      if (S.labels[j]) { g.fillStyle = '#222'; g.font = '13px system-ui'; g.fillText(S.labels[j], q[0] + 8, q[1] - 8); } });
    [['x', [1, 0, 0]], ['y', [0, 1, 0]], ['z', [0, 0, 1]]].forEach(function (a) {
      var o = rot(C), t = rot([C[0] + a[1][0] * R / 4, C[1] + a[1][1] * R / 4, C[2] + a[1][2] * R / 4]), s = scale(), dx = (t[0] - o[0]) * s, dy = -(t[1] - o[1]) * s;
      g.beginPath(); g.moveTo(50, 670); g.lineTo(50 + dx, 670 + dy); g.strokeStyle = '#a33'; g.lineWidth = 1.5; g.stroke(); g.fillStyle = '#a33'; g.font = '13px system-ui'; g.fillText(a[0], 50 + dx * 1.2, 670 + dy * 1.2 + 4); });
  }
  function set(yaw, pitch) { st.yaw = yaw; st.pitch = pitch; draw(); }
  cv.addEventListener('pointerdown', function (e) { drag = [e.clientX, e.clientY]; cv.setPointerCapture(e.pointerId); cv.style.cursor = 'grabbing'; });
  cv.addEventListener('pointermove', function (e) { if (!drag) return; st.yaw += (e.clientX - drag[0]) * 0.01; st.pitch = Math.max(-1.5708, Math.min(1.5708, st.pitch + (e.clientY - drag[1]) * 0.01)); drag = [e.clientX, e.clientY]; draw(); });
  cv.addEventListener('pointerup', function () { drag = null; cv.style.cursor = 'grab'; });
  cv.addEventListener('wheel', function (e) { e.preventDefault(); st.zoom = Math.max(0.3, Math.min(6, st.zoom * (e.deltaY < 0 ? 1.1 : 0.9))); draw(); }, {passive: false});
  document.addEventListener('keydown', function (e) { var d = {ArrowLeft: [-0.1, 0], ArrowRight: [0.1, 0], ArrowUp: [0, 0.1], ArrowDown: [0, -0.1]}[e.key]; if (d) { e.preventDefault(); set(st.yaw + d[0], Math.max(-1.5708, Math.min(1.5708, st.pitch + d[1]))); } });
  Array.prototype.forEach.call(document.querySelectorAll('button[data-v]'), function (b) { b.addEventListener('click', function () { var v = V[b.getAttribute('data-v')]; st.zoom = 1; set(v[0], v[1]); }); });
  document.getElementById('reset').addEventListener('click', function () { st.zoom = 1; set(0.6, 0.5); });
  window.__viewer = st; draw();
})();
</script></main></body></html>
'''


def viewer_html(spec) -> str:
    """A self-contained page (no network, no libraries) to rotate and zoom a 3D scene. Opens in a browser; sessions embed the static SVG views."""
    require_valid(spec)
    if not is_3d(spec):
        raise DiagramError('the viewer is for 3D scenes: geometry3d, a molecule with xyz coordinates, or a structure trace')
    scene = scene3d(spec)
    names = list(scene['points'])
    index = {n: i for i, n in enumerate(names)}
    payload = {'points': [list(scene['points'][n]) for n in names], 'edges': [[index[a], index[b], o, d] for a, b, o, d in scene['edges']],
               'labels': [scene['labels'].get(n, '') for n in names], 'colors': [CPK.get(scene['atoms'][n]['el'], '#dddddd') if n in scene['atoms'] else '' for n in names]}
    data = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026')
    note = 'Schematic, not to scale.' if spec.get('schematic') else 'Rendering is not verification.'
    return (VIEWER.replace('__TITLE__', esc(spec['title'])).replace('__SCENE__', data).replace('__UNITS__', esc(spec.get('units') or 'declared units'))
            .replace('__DESCRIPTION__', esc(f'{len(names)} points and {len(payload["edges"])} edges. Four fixed views are available as buttons.')).replace('__NOTE__', esc(note)))


# ------------------------------------------------------------------------------------------------ checks from the same spec

def verification_spec(spec) -> dict:
    """A ``scientific_verify`` spec that checks the numbers this diagram was drawn from. Run it with ``scientific_verify.py run``."""
    require_valid(spec)
    kind, checklist = spec['kind'], []
    if kind in ('geometry2d', 'geometry3d') and spec.get('constraints'):
        checklist.append({'id': 'geometry', 'kind': 'geometry-constraint', 'points': spec['points'], 'constraints': spec['constraints']})
    if kind == 'molecule':
        check = {'id': 'molecule', 'kind': 'molecule-graph', 'bonds': spec['bonds'],
                 'atoms': {k: {'el': a['el'], **({'charge': a['charge']} if a.get('charge') else {})} for k, a in spec['atoms'].items()}}
        for key in ('explicit_hydrogens', 'expected_formula', 'expected_charge', 'expected_mass'):
            if key in spec:
                check[key] = spec[key]
        checklist.append(check)
    source = spec.get('source') or {}
    if kind == 'structure-trace' and source.get('path') and source.get('sha256'):
        claims = {k: source[k] for k in ('accession', 'method', 'resolution_max') if k in source}
        claims['chains'] = sorted(spec['chains'])
        checklist.append({'id': 'structure-source', 'kind': 'structure-source', 'path': source['path'], 'sha256': source['sha256'], 'claims': claims})
    return {'verification_schema': 1, 'verification_id': 'VER-' + spec['id'].removeprefix('VIS-'),
            'claim': {'id': spec['id'], 'statement': f"The diagram {spec['id']} is consistent with the constraints and source it declares", 'consequence': 'routine'},
            'checks': checklist}


# ------------------------------------------------------------------------------------------------ files and registry

def _slug(value):
    return re.sub(r'[^a-z0-9._-]+', '-', value.lower()).strip('-')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_new(path: Path, text: str):
    if path.exists():
        raise DiagramError(f'{path.name} already exists; choose a new id or output directory')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')


def render_files(spec, directory: Path, viewer: bool = True) -> dict:
    """Write ``<id>.diagram.json``, ``.svg`` and, for 3D scenes, ``.viewer.html`` into a directory. Never overwrites."""
    require_valid(spec)
    directory, base = Path(directory), _slug(spec['id'])
    out = {'spec': directory / f'{base}.diagram.json', 'svg': directory / f'{base}.svg'}
    texts = {'spec': json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True) + '\n', 'svg': render_svg(spec)}
    if viewer and is_3d(spec):
        out['viewer'] = directory / f'{base}.viewer.html'
        texts['viewer'] = viewer_html(spec)
    for path in out.values():
        if path.exists():
            raise DiagramError(f'{path.name} already exists; choose a new id or output directory')
    for key, path in out.items():
        write_new(path, texts[key])
    return out


def register(root, spec, *, concepts: list[str], directory: str = 'Visuals') -> dict:
    """Render into the vault and add a registry record at ``rendered``. Rendering never promotes a visual: ``verified`` is attested elsewhere."""
    root = Path(root).resolve()
    require_valid(spec)
    if not directory or '\\' in directory or ':' in directory or any(p in {'', '.', '..'} for p in directory.split('/')):
        raise DiagramError('the directory is a relative path inside the vault')
    base, folder = _slug(spec['id']), root / directory
    record_file = folder / f'{base}{visuals.SUFFIX}'
    digest = visual_assets.digest_spec(spec)
    if record_file.exists():
        existing = json.loads(record_file.read_text(encoding='utf-8-sig'))
        if existing.get('spec_sha256') == digest:
            return {'visual_id': spec['id'], 'reused': True, 'artifact': existing['artifact'], 'export': existing['exports'][0]['path']}
        raise DiagramError(f'{spec["id"]} already exists with a different spec; choose a new id')
    files = render_files(spec, folder)

    def relative(path):
        return path.relative_to(root).as_posix()

    schematic = bool(spec.get('schematic'))
    record = {'visual_schema': 1, 'visual_id': spec['id'], 'title': spec['title'], 'concepts': concepts,
              'kind': 'conceptual-schematic' if schematic else 'model-driven-plot', 'source_type': 'schematic' if schematic else 'generated',
              'verification_status': 'rendered', 'artifact': relative(files['spec']), 'quantitative': not schematic,
              'mode': 'geometric-construction' if spec['kind'] in ('geometry2d', 'geometry3d') else 'scientific-illustration',
              'exports': [{'path': relative(files['svg']), 'format': 'svg'}], 'spec_sha256': digest, 'source_sha256': sha(files['spec'].read_bytes()),
              'generator': 'diagram_spec.py'}
    if not schematic:
        record['basis'] = (f'Drawn from the coordinates declared in {relative(files["spec"])} (sha256 {digest[:12]}…). Constraints and structure claims are '
                           f'checked separately (diagram_spec.py verification-spec, scientific_verify.py); rendering is not verification.')
    problems = visuals.issues(record, root)
    if problems:
        for path in files.values():
            path.unlink(missing_ok=True)
        raise DiagramError('record invalid: ' + '; '.join(problems))
    visual_assets._write_record(record_file, record)
    return {'visual_id': spec['id'], 'reused': False, 'artifact': record['artifact'], 'export': record['exports'][0]['path'],
            'viewer': relative(files['viewer']) if 'viewer' in files else None}


def spec_from_pdb(path: Path, chains: list[str] | None, visual_id: str, title: str) -> dict:
    """A structure-trace spec from a PDB-format file's C-alpha atoms, bound to the file by its SHA-256."""
    raw = Path(path).read_bytes()
    info = checks.parse_pdb(raw.decode('utf-8', 'replace'))
    trace = {}
    for chain in chains or info['chains']:
        residues = [(n, v['ca']) for (n, _), v in sorted(info['residues'].get(chain, {}).items()) if v['ca']]
        if len(residues) < 2:
            raise DiagramError(f'chain {chain} has fewer than two C-alpha atoms in {Path(path).name}')
        trace[chain] = [[n, *xyz] for n, xyz in residues]
    source = {'path': str(path).replace('\\', '/'), 'sha256': sha(raw)}
    if info['id']:
        source['accession'] = info['id']
    if info['expdta']:
        source['method'] = info['expdta']
    return {'diagram_schema': SCHEMA, 'id': visual_id, 'title': title, 'kind': 'structure-trace', 'units': 'angstrom', 'chains': trace, 'source': source,
            'note': 'C-alpha backbone trace only; PDB residue numbering.'}


def capabilities() -> dict:
    """Which optional renderers exist on this machine. Reports only; nothing is imported, run or installed."""
    modules = {m: importlib.util.find_spec(m) is not None for m in ('rdkit', 'pyvista', 'matplotlib', 'plotly', 'py3Dmol', 'Bio', 'numpy', 'trimesh')}
    tools = {t: shutil.which(t) is not None for t in ('dot', 'mmdc', 'inkscape', 'blender', 'node')}
    return {'builtin': ['svg (stdlib)', 'interactive 3D viewer page (stdlib)'], 'python_modules': modules, 'tools': tools,
            'note': 'SMILES depiction needs rdkit and is not done by diagram_spec.py; give an explicit atom graph. Optional tools are used only when a lesson asks for them.'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('validate', help='structural problems with a spec (exit 1 if any)')
    p.add_argument('spec', type=Path)
    p = sub.add_parser('render', help='write the spec, SVG and (3D) viewer page into a new directory')
    p.add_argument('spec', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--no-viewer', action='store_true')
    p = sub.add_parser('register', help='render into a vault and add a registry record at "rendered"')
    p.add_argument('spec', type=Path)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--concept', action='append', required=True)
    p.add_argument('--directory', default='Visuals')
    p = sub.add_parser('verification-spec', help='print the scientific_verify spec for the numbers this diagram was drawn from')
    p.add_argument('spec', type=Path)
    p = sub.add_parser('from-pdb', help='write a structure-trace spec from a PDB-format file (new file only)')
    p.add_argument('pdb', type=Path)
    p.add_argument('--id', required=True)
    p.add_argument('--title', required=True)
    p.add_argument('--chain', action='append')
    p.add_argument('--out', type=Path, required=True)
    sub.add_parser('capabilities', help='which optional renderers exist here')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        if args.command == 'capabilities':
            result = capabilities()
        elif args.command == 'from-pdb':
            made = spec_from_pdb(args.pdb, args.chain, args.id, args.title)
            write_new(args.out, json.dumps(made, indent=2, ensure_ascii=False) + '\n')
            result = {'written': str(args.out), 'chains': sorted(made['chains'])}
        else:
            spec = json.loads(args.spec.read_text(encoding='utf-8'))
            if args.command == 'validate':
                problems = validate(spec)
                print(json.dumps({'valid': not problems, 'problems': problems}, indent=2, ensure_ascii=False))
                return 1 if problems else 0
            if args.command == 'render':
                result = {k: str(v) for k, v in render_files(spec, args.out, not args.no_viewer).items()}
            elif args.command == 'register':
                result = register(args.root, spec, concepts=args.concept, directory=args.directory)
            else:
                result = verification_spec(spec)
    except (DiagramError, checks.StructureError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
