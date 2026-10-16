"""Exact, standard-library checks for what a diagram or a structure claims, run by ``scientific_verify.py``.

``geometry-constraint``  lengths, angles, parallel, perpendicular, incidence, coplanarity and area recomputed from the coordinates
``molecule-graph``       valence, formula, charge and molar mass recomputed from an explicit atom and bond graph
``structure-source``     a PDB-format file bound by hash: method, resolution, chains, residue ranges, sequence, residue identity

A drawing is only as true as the numbers it was drawn from, so these checks read the *numbers* (the diagram spec's coordinates, the molecule
graph, the structure file), never the picture. They verify that the declared coordinates satisfy the declared constraints and that a
structure file says what is claimed about it; whether a geometry is the right model of the physical object, whether a structure is the
right protein, or whether a PDB entry is current is judgement the reviewer states as not verified. mmCIF files are not read: say so
instead of guessing.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import math
from pathlib import Path
import re

from chembio_verify import ChemError, ELEMENTS, WEIGHTS, molar_mass

PASS, FAIL, INCONCLUSIVE = 'pass', 'fail', 'inconclusive'
DEFAULT_TOLERANCE = {'abs': 1e-6, 'rel': 1e-9, 'deg': 1e-6}
MASS_TOLERANCE = {'abs': 0.0, 'rel': 1e-3}
MAX_CONSTRAINTS = 100
MAX_POINTS = 2000
THREE = {'ALA': 'A', 'ARG': 'R', 'ASN': 'N', 'ASP': 'D', 'CYS': 'C', 'GLN': 'Q', 'GLU': 'E', 'GLY': 'G', 'HIS': 'H', 'ILE': 'I', 'LEU': 'L',
         'LYS': 'K', 'MET': 'M', 'PHE': 'F', 'PRO': 'P', 'SER': 'S', 'THR': 'T', 'TRP': 'W', 'TYR': 'Y', 'VAL': 'V'}
VALENCES = {'H': {1}, 'C': {4}, 'N': {3}, 'O': {2}, 'F': {1}, 'Cl': {1}, 'Br': {1}, 'I': {1}, 'S': {2, 4, 6}, 'P': {3, 5}, 'B': {3}}
CHARGE_SHIFT = {'N': {1: {4}, -1: {2}}, 'O': {1: {3}, -1: {1}}, 'C': {1: {3}, -1: {3}}, 'B': {-1: {4}}}


class StructureError(ChemError):
    """Malformed input: an error for the engine, not a falsification of the claim."""


def method(family, status, **detail):
    return {'family': family, 'status': status, **detail}


def _tolerance(check, base=DEFAULT_TOLERANCE):
    return dict(base, **(check.get('tolerance') or {}))


def _close(a, b, tolerance):
    return abs(a - b) <= max(tolerance['abs'], tolerance['rel'] * max(abs(a), abs(b)))


# ------------------------------------------------------------------------------------------------ geometry

def _points(raw):
    if not isinstance(raw, dict) or not raw or len(raw) > MAX_POINTS:
        raise StructureError(f'points is a non-empty object of at most {MAX_POINTS} named points')
    points, dim = {}, None
    for name, coords in raw.items():
        if (not isinstance(coords, list) or len(coords) not in (2, 3) or any(isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) for c in coords)):
            raise StructureError(f'point {name!r} is a list of 2 or 3 finite numbers')
        if dim is not None and len(coords) != dim:
            raise StructureError('all points share one dimension (2 or 3)')
        dim = len(coords)
        points[name] = tuple(float(c) for c in coords)
    return points, dim


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _norm(a):
    return math.sqrt(_dot(a, a))


def _cross(a, b):
    if len(a) == 2:
        return a[0] * b[1] - a[1] * b[0]
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def angle_deg(points, at, a, b):
    u, v = _sub(points[a], points[at]), _sub(points[b], points[at])
    if _norm(u) == 0 or _norm(v) == 0:
        raise StructureError(f'angle at {at}: a vertex coincides with an end point')
    return math.degrees(math.acos(max(-1.0, min(1.0, _dot(u, v) / (_norm(u) * _norm(v))))))


def _name(points, value):
    if not isinstance(value, str) or value not in points:
        raise StructureError(f'unknown point {value!r}')
    return value


def _pair(points, value):
    if not isinstance(value, list) or len(value) != 2:
        raise StructureError('a segment is a list of two point names')
    return _name(points, value[0]), _name(points, value[1])


def _length(points, pair):
    a, b = _pair(points, pair)
    return _norm(_sub(points[a], points[b]))


def evaluate_constraint(points, dim, constraint, tolerance):
    """(ok, description) for one constraint, recomputed from the coordinates."""
    if not isinstance(constraint, dict) or 'type' not in constraint:
        raise StructureError('a constraint is an object with a type')
    kind = constraint['type']
    if kind == 'length':
        measured = _length(points, constraint['between'])
        return _close(measured, float(constraint['equals']), tolerance), f"length {constraint['between']} is {measured:.9g}, not {constraint['equals']}"
    if kind == 'equal-length':
        a, b = _length(points, constraint['a']), _length(points, constraint['b'])
        return _close(a, b, tolerance), f"{constraint['a']} is {a:.9g} long and {constraint['b']} is {b:.9g}"
    if kind == 'angle':
        at, a, b = (_name(points, constraint[k]) for k in ('at', 'from', 'to'))
        measured = angle_deg(points, at, a, b)
        return abs(measured - float(constraint['equals_deg'])) <= tolerance['deg'], f"angle {a}-{at}-{b} is {measured:.9g} degrees, not {constraint['equals_deg']}"
    if kind == 'angle-sum':
        total = sum(angle_deg(points, _name(points, e['at']), _name(points, e['from']), _name(points, e['to'])) for e in constraint['angles'])
        return abs(total - float(constraint['equals_deg'])) <= tolerance['deg'], f"the angles sum to {total:.9g} degrees, not {constraint['equals_deg']}"
    if kind in ('parallel', 'perpendicular'):
        a, b = _pair(points, constraint['a']), _pair(points, constraint['b'])
        u, v = _sub(points[a[1]], points[a[0]]), _sub(points[b[1]], points[b[0]])
        if _norm(u) == 0 or _norm(v) == 0:
            raise StructureError('a degenerate segment has no direction')
        c = _dot(u, v) / (_norm(u) * _norm(v))
        if kind == 'perpendicular':
            return abs(c) <= tolerance['abs'], f"the segments' direction cosine is {c:.9g}, not 0"
        return abs(abs(c) - 1.0) <= tolerance['abs'], f"the segments' direction cosine is {c:.9g}, not +-1"
    if kind == 'incident':
        p, (a, b) = _name(points, constraint['point']), _pair(points, constraint['on'])
        u, w = _sub(points[b], points[a]), _sub(points[p], points[a])
        if _norm(u) == 0:
            raise StructureError('a degenerate segment has no line')
        off = abs(_cross(u, w)) if dim == 2 else _norm(_cross(u, w))
        offset = off / _norm(u)
        within = True
        if constraint.get('within'):
            t = _dot(w, u) / _dot(u, u)
            within = -tolerance['abs'] <= t <= 1 + tolerance['abs']
        return offset <= tolerance['abs'] and within, f"{p} is {offset:.9g} from the line {a}{b}" + ('' if within else ' and outside the segment')
    if kind == 'coplanar':
        if dim != 3:
            raise StructureError('coplanar needs 3D points')
        names = [_name(points, n) for n in constraint['points']]
        if len(names) < 4:
            raise StructureError('coplanar needs at least four points')
        base, u, v = points[names[0]], _sub(points[names[1]], points[names[0]]), _sub(points[names[2]], points[names[0]])
        normal = _cross(u, v)
        if _norm(normal) == 0:
            raise StructureError('the first three points are collinear, so they do not fix a plane')
        worst = max(abs(_dot(_sub(points[n], base), normal)) / _norm(normal) for n in names[3:])
        return worst <= tolerance['abs'], f'the furthest point is {worst:.9g} from the plane of the first three'
    if kind == 'area':
        if dim != 2:
            raise StructureError('area is for 2D polygons')
        names = [_name(points, n) for n in constraint['polygon']]
        area = abs(sum(points[names[i]][0] * points[names[(i + 1) % len(names)]][1] - points[names[(i + 1) % len(names)]][0] * points[names[i]][1]
                       for i in range(len(names)))) / 2
        return _close(area, float(constraint['equals']), tolerance), f"the area is {area:.9g}, not {constraint['equals']}"
    raise StructureError(f'unknown constraint type {kind!r}')


def run_geometry_constraint(spec, check):
    points, dim = _points(check['points'])
    constraints = check['constraints']
    if not isinstance(constraints, list) or not constraints or len(constraints) > MAX_CONSTRAINTS:
        raise StructureError(f'constraints is a list of 1 to {MAX_CONSTRAINTS}')
    tolerance, failures, ok = _tolerance(check), [], 0
    for index, constraint in enumerate(constraints):
        passed, message = evaluate_constraint(points, dim, constraint, tolerance)
        if passed:
            ok += 1
        else:
            failures.append(f"constraint {index + 1} ({constraint['type']}): {message}")
    if failures:
        return [method('coordinate-recompute', FAIL, reason='; '.join(failures), failed=len(failures), passed=ok)]
    return [method('coordinate-recompute', PASS, passed=ok, dimension=dim, tolerance=tolerance)]


# ------------------------------------------------------------------------------------------------ molecules

def hill_formula(counts: Counter) -> str:
    rest = sorted(e for e in counts if not ('C' in counts and e in ('C', 'H')))
    order = (['C', 'H'] if 'C' in counts and 'H' in counts else ['C'] if 'C' in counts else []) + rest
    return ''.join(e + (str(counts[e]) if counts[e] > 1 else '') for e in order)


def molecule_counts(atoms, bonds):
    if not isinstance(atoms, dict) or not atoms or len(atoms) > MAX_POINTS:
        raise StructureError('atoms is a non-empty object: id -> {el, charge?}')
    if not isinstance(bonds, list) or len(bonds) > MAX_POINTS:
        raise StructureError('bonds is a list of [a, b, order]')
    counts, charge = Counter(), 0
    for key, atom in atoms.items():
        if not isinstance(atom, dict) or atom.get('el') not in ELEMENTS:
            raise StructureError(f'atom {key!r} needs an element symbol such as C or Cl')
        counts[atom['el']] += 1
        charge += int(atom.get('charge', 0))
    valence = Counter()
    for bond in bonds:
        if not isinstance(bond, list) or len(bond) != 3 or bond[0] not in atoms or bond[1] not in atoms or bond[0] == bond[1] or bond[2] not in (1, 2, 3):
            raise StructureError(f'a bond is [atom, atom, 1|2|3] between two different known atoms: {bond!r}')
        valence[bond[0]] += bond[2]
        valence[bond[1]] += bond[2]
    return counts, charge, valence


def run_molecule_graph(spec, check):
    counts, charge, valence = molecule_counts(check['atoms'], check['bonds'])
    explicit, problems, unresolved = bool(check.get('explicit_hydrogens', True)), [], []
    for key, atom in check['atoms'].items():
        element, shift = atom['el'], int(atom.get('charge', 0))
        allowed = CHARGE_SHIFT.get(element, {}).get(shift) if shift else VALENCES.get(element)
        if allowed is None:
            unresolved.append(f'{key} ({element}{"%+d" % shift if shift else ""}): no valence rule')
            continue
        got = valence[key]
        if (explicit and got not in allowed) or (not explicit and got > max(allowed)):
            problems.append(f'{key} ({element}) has bond order sum {got}, allowed {sorted(allowed)}')
    notes = {'formula': hill_formula(counts), 'charge': charge}
    if 'expected_formula' in check and check['expected_formula'] != notes['formula']:
        problems.append(f"the graph's formula is {notes['formula']}, not {check['expected_formula']}")
    if 'expected_charge' in check and check['expected_charge'] != charge:
        problems.append(f'the net charge is {charge}, not {check["expected_charge"]}')
    if 'expected_mass' in check:
        try:
            mass = molar_mass(counts)
            notes['molar_mass'] = mass
            if not _close(mass, float(check['expected_mass']), _tolerance(check, MASS_TOLERANCE)):
                problems.append(f'molar mass is {mass:.6g} g/mol, not {check["expected_mass"]}')
        except ChemError as exc:
            unresolved.append(str(exc))
    if problems:
        return [method('graph-recompute', FAIL, reason='; '.join(problems), **notes)]
    if unresolved:
        return [method('graph-recompute', INCONCLUSIVE, reason='; '.join(unresolved), **notes)]
    return [method('graph-recompute', PASS, **notes)]


# ------------------------------------------------------------------------------------------------ PDB files

def parse_pdb(text: str) -> dict:
    """The parts of a PDB-format file the checks need (first model only). Fixed-column parsing per the PDB format."""
    if re.search(r'^_atom_site\.', text, re.M) or re.search(r'^data_\S', text, re.M):
        raise StructureError('this looks like mmCIF; only PDB-format files are read (convert it, or check it by another route)')
    info = {'id': None, 'expdta': None, 'resolution': None, 'seqres': {}, 'residues': {}, 'atoms': 0, 'chains': []}
    for line in text.splitlines():
        record = line[:6].strip()
        if record == 'HEADER' and len(line) >= 66:
            info['id'] = line[62:66].strip() or None
        elif record == 'EXPDTA':
            info['expdta'] = ((info['expdta'] or '') + ' ' + line[10:].strip()).strip()
        elif record == 'REMARK' and line[7:10].strip() == '2':
            match = re.search(r'RESOLUTION\.\s+([\d.]+)\s+ANGSTROMS', line)
            if match:
                info['resolution'] = float(match[1])
        elif record == 'SEQRES':
            info['seqres'].setdefault(line[11:12], []).extend(line[19:].split())
        elif record == 'ENDMDL':
            break
        elif record == 'ATOM':
            try:
                chain, number, icode, name = line[21:22], int(line[22:26]), line[26:27].strip(), line[17:20].strip()
                coords = (float(line[30:38]), float(line[38:46]), float(line[46:54])) if line[12:16].strip() == 'CA' else None
            except ValueError:
                raise StructureError('a malformed ATOM record (fixed columns expected)') from None
            info['atoms'] += 1
            residue = info['residues'].setdefault(chain, {}).setdefault((number, icode), {'name': name, 'ca': None})
            if coords:
                residue['ca'] = coords
    info['chains'] = sorted(info['residues'])
    return info


def _one(name):
    name = str(name).upper()
    return THREE.get(name, name if len(name) == 1 else 'X')


def run_structure_source(spec, check):
    path = Path(check['path'])
    if not path.is_file():
        raise StructureError(f'structure file not found: {path}')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != check['sha256']:
        return [method('pdb-records', FAIL, reason=f'the file differs from the recorded hash (is {digest[:12]}…): the structure changed, or the claim was written about another file',
                       sha256=digest)]
    info = parse_pdb(raw.decode('utf-8', 'replace'))
    claims, problems, unresolved = check['claims'], [], []
    if not isinstance(claims, dict) or not claims:
        raise StructureError('claims is a non-empty object')
    unknown = set(claims) - {'accession', 'method', 'resolution_max', 'chains', 'residue_range', 'sequence', 'residue'}
    if unknown:
        raise StructureError('unknown claims: ' + ', '.join(sorted(unknown)))
    if 'accession' in claims:
        if not info['id']:
            unresolved.append('the file has no HEADER identifier to compare the accession with')
        elif info['id'].upper() != str(claims['accession']).upper():
            problems.append(f"the file's identifier is {info['id']}, not {claims['accession']}")
    if 'method' in claims:
        if not info['expdta']:
            unresolved.append('the file has no EXPDTA record')
        elif str(claims['method']).upper() not in info['expdta'].upper():
            problems.append(f"the experimental method is {info['expdta']}, not {claims['method']}")
    if 'resolution_max' in claims:
        if info['resolution'] is None:
            unresolved.append('the file states no resolution (REMARK 2), as for NMR or a model')
        elif info['resolution'] > float(claims['resolution_max']):
            problems.append(f"the resolution is {info['resolution']} A, worse than {claims['resolution_max']} A")
    for chain in claims.get('chains', []):
        if chain not in info['residues']:
            problems.append(f'chain {chain} has no ATOM records (chains present: {", ".join(info["chains"]) or "none"})')
    if 'residue_range' in claims:
        r = claims['residue_range']
        observed = {n for (n, _) in info['residues'].get(r['chain'], {})}
        missing = [n for n in range(r['start'], r['end'] + 1) if n not in observed]
        if not observed:
            problems.append(f"chain {r['chain']} has no residues")
        elif missing and not r.get('allow_gaps'):
            problems.append(f"chain {r['chain']} lacks residues {missing[:10]}{'…' if len(missing) > 10 else ''} of {r['start']}-{r['end']} (PDB numbering, which may differ from the reference sequence)")
    if 'sequence' in claims:
        s = claims['sequence']
        source = s.get('source', 'seqres')
        if source == 'seqres':
            actual = ''.join(_one(n) for n in info['seqres'].get(s['chain'], []))
        else:
            actual = ''.join(_one(v['name']) for _, v in sorted(info['residues'].get(s['chain'], {}).items()))
        if not actual:
            unresolved.append(f"no {source} sequence for chain {s['chain']}")
        elif actual != str(s['expected']).upper():
            problems.append(f"chain {s['chain']} {source} sequence is {actual[:40]}{'…' if len(actual) > 40 else ''}, not the claimed one")
    if 'residue' in claims:
        r = claims['residue']
        found = [v['name'] for (n, _), v in info['residues'].get(r['chain'], {}).items() if n == r['number']]
        if not found:
            problems.append(f"chain {r['chain']} has no residue numbered {r['number']} in the file (PDB numbering)")
        elif _one(found[0]) != _one(r['name']):
            problems.append(f"residue {r['number']} of chain {r['chain']} is {found[0]}, not {r['name']}")
    notes = {'sha256': digest, 'id': info['id'], 'expdta': info['expdta'], 'resolution': info['resolution'], 'chains': info['chains'], 'atoms': info['atoms']}
    if problems:
        return [method('pdb-records', FAIL, reason='; '.join(problems), **notes)]
    if unresolved:
        return [method('pdb-records', INCONCLUSIVE, reason='; '.join(unresolved), **notes)]
    return [method('pdb-records', PASS, **notes)]


RUNNERS = {'geometry-constraint': run_geometry_constraint, 'molecule-graph': run_molecule_graph, 'structure-source': run_structure_source}
FIELDS = {
    'geometry-constraint': ({'points', 'constraints'}, {'tolerance'}),
    'molecule-graph': ({'atoms', 'bonds'}, {'explicit_hydrogens', 'expected_formula', 'expected_charge', 'expected_mass', 'tolerance'}),
    'structure-source': ({'path', 'sha256', 'claims'}, set()),
}
CLASS = {'coordinate-recompute': 'coordinate-geometry', 'graph-recompute': 'graph-recompute', 'pdb-records': 'structure-file'}
