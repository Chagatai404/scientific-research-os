"""Choose a scientific representation from declared intent; never verify a claim."""
import argparse
import json
from pathlib import Path
from visuals import MODES

NEEDS = {'dependence': 'plot', 'geometry': 'diagram', 'scale': 'geometric-construction',
         'relations': 'conceptual-schematic', 'mechanism': 'scientific-illustration',
         'evolution': 'diagram'}


def choose(spec):
    if not isinstance(spec, dict) or not isinstance(spec.get('need'), str) or spec['need'] not in set(NEEDS) | {'none'}:
        raise ValueError('declare dependence, geometry, scale, relations, mechanism, evolution or none')
    if not isinstance(spec.get('goal'), str) or not spec['goal'].strip():
        raise ValueError('a concrete teaching goal is required')
    for key in ('material', 'motion_material', 'interaction_material'):
        if key in spec and type(spec[key]) is not bool:
            raise ValueError(key + ' must be boolean')
    for key in ('basis', 'provenance'):
        if key in spec and (not isinstance(spec[key], str) or not spec[key].strip()):
            raise ValueError(key + ' must be a nonempty string')
    available = spec.get('available', sorted(MODES))
    if not isinstance(available, list) or any(not isinstance(x, str) or x not in MODES for x in available):
        raise ValueError('available must list supported modes')
    if spec['need'] == 'none' or spec.get('material') is False:
        return {'mode': None, 'reason': 'No material visual benefit; use a short explanation.', 'verification_status': 'candidate'}
    preferred = NEEDS[spec['need']]
    if spec.get('motion_material') and spec['need'] == 'evolution':
        preferred = 'simulation' if spec.get('interaction_material') and spec.get('basis') else 'animation'
    if preferred in {'animation', 'simulation'} and not spec.get('basis'):
        preferred = 'diagram'  # Never invent motion from an unsupported model.
    options = [preferred]
    if preferred in {'animation', 'simulation', 'geometric-construction', 'scientific-illustration'}:
        options += ['diagram', 'conceptual-schematic']
    elif preferred == 'plot':
        options += ['diagram']
    else:
        options += ['conceptual-schematic']
    mode = next((x for x in options if x in available), None)
    return {'mode': mode, 'preferred': preferred, 'goal': spec['goal'],
            'reason': 'simplest adequate representation' if mode == preferred else 'static fallback' if mode else 'no available renderer; unrendered draft',
            'basis': spec.get('basis'), 'provenance': spec.get('provenance'),
            'verification_status': 'candidate', 'source_first': True}


def box_grid(object_kind='square', divisions=(2, 4, 8)):
    """Exact unit-line/unit-square counting panels, not detector data or estimated D."""
    if object_kind not in {'line', 'square'} or not divisions or any(type(n) is not int or not 1 <= n <= 32 for n in divisions):
        raise ValueError('use line/square and integer grid divisions from 1 to 32')
    width = 200 * len(divisions)
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="230" viewBox="0 0 {width} 230">',
                '<rect width="100%" height="100%" fill="white"/>']
    counts = []
    for panel, n in enumerate(divisions):
        x, y, side = panel * 200 + 20, 25, 150
        counts.append(n if object_kind == 'line' else n * n)
        elements.append(f'<rect x="{x}" y="{y}" width="{side}" height="{side}" fill="#e0f2fe" stroke="black"/>')
        if object_kind == 'line':
            elements.append(f'<rect x="{x}" y="{y + side/n}" width="{side}" height="{side - side/n}" fill="white"/>')
            elements.append(f'<path d="M {x} {y} h {side}" stroke="black" stroke-width="3"/>')
        for i in range(n + 1):
            pos = side * i / n
            elements += [f'<path d="M {x+pos} {y} v {side}" stroke="#555"/>', f'<path d="M {x} {y+pos} h {side}" stroke="#555"/>']
        elements.append(f'<text x="{x}" y="200" font-size="14">1/epsilon={n}; N={counts[-1]}</text>')
    elements += ['<text x="20" y="223" font-size="12">Exact ideal geometric example; not finite-resolution detector inference.</text>', '</svg>']
    return '\n'.join(elements), counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(choose(json.loads(args.spec.read_text(encoding='utf-8'))), indent=2, sort_keys=True))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
