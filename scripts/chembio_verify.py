"""Exact, standard-library checks for chemistry and biology claims, run by ``scientific_verify.py``.

``formula-balance``  atoms and charge conserved in a reaction equation, and (independently) the coefficients that balance it
``molar-mass``       a formula's molar mass from tabulated atomic weights
``stoichiometry``    limiting reagent and theoretical amount from a balanced equation
``sequence-check``   alphabet, reverse complement, transcript, translation, GC content and length of a DNA, RNA or protein sequence

These verify arithmetic and rules, not chemistry or biology: that an equation is *chemically sensible*, that a sequence is the
right gene, or that a yield is achievable in a flask is judgement the reviewer states as not verified.
"""
from __future__ import annotations
from collections import Counter
from fractions import Fraction
import math
import re

PASS, FAIL, INCONCLUSIVE = 'pass', 'fail', 'inconclusive'
ATOMIC_WEIGHT_SOURCE = ('Single values and intervals: CIAAW Standard Atomic Weights 2024 (Atomic Weights 2021 report; Gd, Lu, Zr revised 2024), '
                        'read 2026-10-16. Where CIAAW gives only an interval, the rounded IUPAC conventional value is used; those conventional values '
                        'were not on the page read, and agree with the interval to the digits given (15.999 for oxygen against [15.99903, 15.99977]). '
                        'Elements without a value here have none.')
ELEMENTS = tuple('H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh '
                 'Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn '
                 'Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og'.split())
# Single values as published (the digits in parentheses are the uncertainty and are not kept).
ATOMIC_WEIGHTS = {
    'He': 4.002602, 'Be': 9.0121831, 'F': 18.998403162, 'Ne': 20.1797, 'Na': 22.98976928, 'Al': 26.9815384, 'P': 30.973761998,
    'K': 39.0983, 'Ca': 40.078, 'Sc': 44.955907, 'Ti': 47.867, 'V': 50.9415, 'Cr': 51.9961, 'Mn': 54.938043, 'Fe': 55.845,
    'Co': 58.933194, 'Ni': 58.6934, 'Cu': 63.546, 'Zn': 65.38, 'Ga': 69.723, 'Ge': 72.630, 'As': 74.921595, 'Se': 78.971,
    'Kr': 83.798, 'Rb': 85.4678, 'Sr': 87.62, 'Y': 88.905838, 'Zr': 91.222, 'Nb': 92.90637, 'Mo': 95.95, 'Ru': 101.07,
    'Rh': 102.90549, 'Pd': 106.42, 'Ag': 107.8682, 'Cd': 112.414, 'In': 114.818, 'Sn': 118.710, 'Sb': 121.760, 'Te': 127.60,
    'I': 126.90447, 'Xe': 131.293, 'Cs': 132.90545196, 'Ba': 137.327, 'La': 138.90547, 'Ce': 140.116, 'W': 183.84,
    'Re': 186.207, 'Os': 190.23, 'Ir': 192.217, 'Pt': 195.084, 'Au': 196.966570, 'Hg': 200.592, 'Bi': 208.98040,
    'Th': 232.0377, 'U': 238.02891,
}
# Elements CIAAW gives as intervals: (conventional value used, interval low, interval high).
INTERVAL_WEIGHTS = {
    'H': (1.008, 1.00784, 1.00811), 'Li': (6.94, 6.938, 6.997), 'B': (10.81, 10.806, 10.821), 'C': (12.011, 12.0096, 12.0116),
    'N': (14.007, 14.00643, 14.00728), 'O': (15.999, 15.99903, 15.99977), 'Mg': (24.305, 24.304, 24.307),
    'Si': (28.085, 28.084, 28.086), 'S': (32.06, 32.059, 32.076), 'Cl': (35.45, 35.446, 35.457), 'Ar': (39.95, 39.792, 39.963),
    'Br': (79.904, 79.901, 79.907), 'Tl': (204.383, 204.382, 204.385), 'Pb': (207.2, 206.14, 207.94),
}
WEIGHTS = dict(ATOMIC_WEIGHTS, **{symbol: value[0] for symbol, value in INTERVAL_WEIGHTS.items()})
ARROW = re.compile(r'\s*(?:<->|<=>|->|=>|→|⇌|=)\s*')
DEFAULT_TOLERANCE = {'rel': 1e-3, 'abs': 0.0}


class ChemError(ValueError):
    pass


def method(family, status, **detail):
    return {'family': family, 'status': status, **detail}


# ------------------------------------------------------------------------------------------------ formulas

def _split_charge(text):
    text = text.strip()
    if text in ('e-', 'e^-'):
        return 'e', -1, True
    match = re.fullmatch(r'(.*?)(?:\^(\d*)([+-])|([+-]))', text)
    if not match:
        return text, 0, False
    body = match[1]
    if match[3]:
        return body, (int(match[2]) if match[2] else 1) * (1 if match[3] == '+' else -1), False
    return body, 1 if match[4] == '+' else -1, False


def _parse_group(text, pos=0, closer=None):
    counts = Counter()
    while pos < len(text):
        ch = text[pos]
        if closer and ch == closer:
            return counts, pos + 1
        if ch in '([':
            inner, pos = _parse_group(text, pos + 1, ')' if ch == '(' else ']')
            digits = re.match(r'\d+', text[pos:])
            factor = int(digits[0]) if digits else 1
            pos += len(digits[0]) if digits else 0
            for key, value in inner.items():
                counts[key] += value * factor
        elif ch.isupper():
            symbol = re.match(r'[A-Z][a-z]?', text[pos:])[0]
            if symbol not in ELEMENTS and len(symbol) == 2:
                symbol = symbol[0]  # "CO": a following lowercase letter that makes no element is not part of the symbol
            if symbol not in ELEMENTS:
                raise ChemError(f'unknown element {symbol!r}')
            pos += len(symbol)
            digits = re.match(r'\d+', text[pos:])
            counts[symbol] += int(digits[0]) if digits else 1
            pos += len(digits[0]) if digits else 0
        else:
            raise ChemError(f'unexpected {ch!r} in formula {text!r}')
    if closer:
        raise ChemError(f'unclosed bracket in formula {text!r}')
    return counts, pos


def parse_formula(text):
    """(element counts, charge) of one species such as ``Fe^3+``, ``SO4^2-``, ``Ca(OH)2`` or ``CuSO4·5H2O``. ``e-`` is an electron."""
    if not isinstance(text, str) or not text.strip():
        raise ChemError('empty formula')
    body, charge, electron = _split_charge(text.replace(' ', ''))
    if electron:
        return Counter(), charge
    total = Counter()
    for part in re.split(r'[·•*]', body):
        lead = re.match(r'\d+', part)
        factor = int(lead[0]) if lead else 1
        counts, _ = _parse_group(part[len(lead[0]):] if lead else part)
        if not counts and part:
            raise ChemError(f'no elements in {part!r}')
        for key, value in counts.items():
            total[key] += value * factor
    if not total:
        raise ChemError(f'no elements in formula {text!r}')
    return total, charge


def molar_mass(counts):
    missing = sorted(e for e in counts if e not in WEIGHTS)
    if missing:
        raise ChemError('no verified atomic weight for ' + ', '.join(missing))
    return sum(WEIGHTS[e] * n for e, n in counts.items())


def _species(text):
    text = text.strip()
    lead = re.match(r'(\d+/\d+|\d+(?:\.\d+)?)\s*(?=\S)', text)
    coefficient = Fraction(lead[1]) if lead else Fraction(1)
    rest = text[lead.end():] if lead else text
    state = re.search(r'\((s|l|g|aq)\)$', rest)
    if state:
        rest = rest[:state.start()]
    return coefficient, rest.strip()


def parse_equation(text):
    """((coefficient, formula) list for reactants, same for products). Reaction ``+`` needs a space on each side: ``2 H2 + O2 -> 2 H2O``."""
    if not isinstance(text, str):
        raise ChemError('equation must be text')
    sides = ARROW.split(text.strip())
    if len(sides) != 2 or not all(sides):
        raise ChemError('an equation has exactly one arrow (->, =, <=>) with species on both sides')
    result = []
    for side in sides:
        species = [_species(s) for s in re.split(r'\s\+\s', side.strip())]
        if any(not formula for _, formula in species):
            raise ChemError('an empty species in the equation')
        result.append(species)
    return result[0], result[1]


def side_totals(species):
    atoms, charge = Counter(), Fraction(0)
    for coefficient, formula in species:
        counts, z = parse_formula(formula)
        for element, n in counts.items():
            atoms[element] += coefficient * n
        charge += coefficient * z
    return atoms, charge


def balance_solve(reactants, products):
    """Coefficients that balance the equation, found by linear algebra instead of counting: the null space of the element-and-charge
    matrix (products negated). Returns ``('unique', [coefficients])``, ``('none', None)`` or ``('underdetermined', dimension)``."""
    columns = [(f, 1) for _, f in reactants] + [(f, -1) for _, f in products]
    parsed = [(parse_formula(f), sign) for f, sign in columns]
    elements = sorted({e for (counts, _), _ in parsed for e in counts})
    rows = [[Fraction(sign * counts.get(e, 0)) for (counts, _), sign in parsed] for e in elements]
    rows.append([Fraction(sign * z) for (_, z), sign in parsed])
    width, pivots, row = len(columns), [], 0
    for col in range(width):
        pivot = next((r for r in range(row, len(rows)) if rows[r][col] != 0), None)
        if pivot is None:
            continue
        rows[row], rows[pivot] = rows[pivot], rows[row]
        rows[row] = [v / rows[row][col] for v in rows[row]]
        for r in range(len(rows)):
            if r != row and rows[r][col] != 0:
                factor = rows[r][col]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[row])]
        pivots.append(col)
        row += 1
    free = [c for c in range(width) if c not in pivots]
    if not free:
        return 'none', None
    if len(free) > 1:
        return 'underdetermined', len(free)
    vector = [Fraction(0)] * width
    vector[free[0]] = Fraction(1)
    for r, col in enumerate(pivots):
        vector[col] = -rows[r][free[0]]
    denominator = math.lcm(*[v.denominator for v in vector])
    integers = [int(v * denominator) for v in vector]
    divisor = math.gcd(*integers) or 1
    integers = [v // divisor for v in integers]
    if all(v <= 0 for v in integers):
        integers = [-v for v in integers]
    if any(v <= 0 for v in integers):
        return 'none', None  # a null vector with mixed signs is not a reaction in this direction
    return 'unique', integers


def _close(a, b, tolerance):
    tolerance = dict(DEFAULT_TOLERANCE, **(tolerance or {}))
    return abs(a - b) <= max(tolerance['abs'], tolerance['rel'] * max(abs(a), abs(b)))


# ------------------------------------------------------------------------------------------------ check runners

def run_formula_balance(spec, check):
    reactants, products = parse_equation(check['equation'])  # unreadable input raises ChemError: an error, not a falsification
    left, lz = side_totals(reactants)
    right, rz = side_totals(products)
    problems = [f'{e}: {left.get(e, 0)} on the left, {right.get(e, 0)} on the right' for e in sorted(set(left) | set(right)) if left.get(e, 0) != right.get(e, 0)]
    if lz != rz:
        problems.append(f'charge: {lz} on the left, {rz} on the right')
    methods = [method('atom-count', FAIL, reason='not conserved: ' + '; '.join(problems), problems=problems) if problems
               else method('atom-count', PASS, atoms={e: str(n) for e, n in sorted(left.items())}, charge=str(lz))]
    kind, value = balance_solve(reactants, products)
    claimed = [c for c, _ in reactants] + [c for c, _ in products]
    if kind == 'unique':
        ratio = {c / v for c, v in zip(claimed, value)}
        agrees = len(ratio) == 1 and all(c > 0 for c in claimed)
        methods.append(method('nullspace', PASS if agrees else FAIL, balancing_coefficients=value,
                              **({} if agrees else {'reason': f'the coefficients that balance these species are {value}, not the claimed {[str(c) for c in claimed]}'})))
    elif kind == 'none':
        methods.append(method('nullspace', FAIL, reason='no positive coefficients balance these species, so no balanced reaction exists with them'))
    else:
        methods.append(method('nullspace', INCONCLUSIVE, reason=f'the species allow {value} independent balanced reactions; the coefficients are not unique'))
    return methods


def run_molar_mass(spec, check):
    counts, _ = parse_formula(check['formula'])
    try:
        value = molar_mass(counts)
    except ChemError as exc:
        return [method('tabulated-weights', INCONCLUSIVE, reason=str(exc))]
    expected = check['expected']
    ok = _close(value, float(expected), check.get('tolerance'))
    return [method('tabulated-weights', PASS if ok else FAIL, value=value, expected=expected, unit='g/mol', source=ATOMIC_WEIGHT_SOURCE,
                   **({} if ok else {'reason': f'molar mass of {check["formula"]} is {value:.6g} g/mol, not {expected}'}))]


def _amount_mol(formula, amount):
    if isinstance(amount, dict) and set(amount) == {'mol'}:
        return Fraction(str(amount['mol']))
    if isinstance(amount, dict) and set(amount) == {'g'}:
        counts, _ = parse_formula(formula)
        return Fraction(str(amount['g'])) / Fraction(str(molar_mass(counts)))
    raise ChemError('each amount is {"mol": x} or {"g": x}')


def run_stoichiometry(spec, check):
    try:
        reactants, products = parse_equation(check['equation'])
        left, lz = side_totals(reactants)
        right, rz = side_totals(products)
        if left != right or lz != rz:
            return [method('mole-ratio', FAIL, reason='the equation is not balanced, so mole ratios are meaningless; check it with formula-balance')]
        names = {formula.replace(' ', ''): (coefficient, formula) for coefficient, formula in reactants}
        extents = {}
        for formula, amount in check['amounts'].items():
            key = formula.replace(' ', '')
            if key not in names:
                raise ChemError(f'{formula!r} is not a reactant of this equation')
            extents[key] = _amount_mol(names[key][1], amount) / names[key][0]
        if set(extents) != set(names):
            raise ChemError('an amount is needed for every reactant: missing ' + ', '.join(sorted(set(names) - set(extents))))
        extent = min(extents.values())
        limiting = sorted(k for k, v in extents.items() if v == extent)
        want = check['expected']
        found = {}
        if 'limiting' in want:
            normal = sorted(x.replace(' ', '') for x in (want['limiting'] if isinstance(want['limiting'], list) else [want['limiting']]))
            found['limiting'] = (limiting, normal, limiting == normal)
        if 'product' in want:
            table = {formula.replace(' ', ''): (coefficient, formula) for coefficient, formula in products}
            key = want['product'].replace(' ', '')
            if key not in table:
                raise ChemError(f'{want["product"]!r} is not a product of this equation')
            moles = table[key][0] * extent
            if 'mol' in want:
                found['mol'] = (float(moles), want['mol'], _close(float(moles), float(want['mol']), check.get('tolerance')))
            if 'g' in want:
                grams = float(moles) * molar_mass(parse_formula(table[key][1])[0])
                found['g'] = (grams, want['g'], _close(grams, float(want['g']), check.get('tolerance')))
        if not found:
            raise ChemError('expected needs "limiting", or "product" with "mol" or "g"')
    except ChemError as exc:
        if 'no verified atomic weight' in str(exc):
            return [method('mole-ratio', INCONCLUSIVE, reason=str(exc))]
        raise
    wrong = [f'{k}: computed {v[0]}, expected {v[1]}' for k, v in found.items() if not v[2]]
    detail = {'extent_mol': float(extent), 'limiting': limiting, 'computed': {k: v[0] for k, v in found.items()}}
    return [method('mole-ratio', FAIL, reason='; '.join(wrong), **detail) if wrong else method('mole-ratio', PASS, **detail)]


# ------------------------------------------------------------------------------------------------ sequences

ALPHABETS = {'dna': 'ACGT', 'rna': 'ACGU', 'protein': 'ACDEFGHIKLMNPQRSTVWY'}
AMBIGUOUS = {'dna': 'RYKMSWBDHVN', 'rna': 'RYKMSWBDHVN', 'protein': 'BZXJUO*'}
COMPLEMENT = {'A': 'T', 'C': 'G', 'G': 'C', 'T': 'A', 'R': 'Y', 'Y': 'R', 'K': 'M', 'M': 'K', 'S': 'S', 'W': 'W', 'B': 'V', 'V': 'B', 'D': 'H', 'H': 'D', 'N': 'N'}
_BASES = 'TCAG'
_AMINO = 'FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG'
CODONS = {a + b + c: _AMINO[16 * i + 4 * j + k] for i, a in enumerate(_BASES) for j, b in enumerate(_BASES) for k, c in enumerate(_BASES)}


def _clean_sequence(text, alphabet, ambiguous):
    sequence = re.sub(r'\s+', '', str(text)).upper()
    allowed = set(ALPHABETS[alphabet]) | (set(AMBIGUOUS[alphabet]) if ambiguous else set())
    bad = [(i + 1, c) for i, c in enumerate(sequence) if c not in allowed]
    return sequence, bad


def translate(dna, frame=1, to_stop=False):
    out = []
    for i in range(frame - 1, len(dna) - 2, 3):
        amino = CODONS.get(dna[i:i + 3], 'X')
        if amino == '*' and to_stop:
            break
        out.append(amino)
    return ''.join(out)


def run_sequence_check(spec, check):
    alphabet, ambiguous = check['alphabet'], bool(check.get('allow_ambiguous', False))
    if alphabet not in ALPHABETS:
        return [method('sequence-rules', FAIL, reason='alphabet is dna, rna or protein')]
    sequence, bad = _clean_sequence(check['sequence'], alphabet, ambiguous)
    if bad:
        shown = ', '.join(f'{c!r} at {i}' for i, c in bad[:5])
        return [method('sequence-rules', FAIL, reason=f'not a valid {alphabet} sequence: {shown}')]
    problems, notes = [], {'length': len(sequence)}
    if 'expected_length' in check and len(sequence) != check['expected_length']:
        problems.append(f'length is {len(sequence)}, not {check["expected_length"]}')
    nucleotide = sequence.replace('U', 'T') if alphabet == 'rna' else sequence
    if alphabet != 'protein':
        if 'reverse_complement' in check:
            actual = ''.join(COMPLEMENT[c] for c in reversed(nucleotide))
            if alphabet == 'rna':
                actual = actual.replace('T', 'U')
            notes['reverse_complement'] = actual
            if actual != str(check['reverse_complement']).upper():
                problems.append(f'reverse complement is {actual}')
        if 'gc_content' in check:
            known = [c for c in nucleotide if c in 'ACGT']
            if not known:
                problems.append('no unambiguous bases to compute GC content from')
            else:
                gc = sum(c in 'GC' for c in known) / len(known)
                notes['gc_content'] = gc
                if not _close(gc, float(check['gc_content']), check.get('tolerance') or {'rel': 1e-6}):
                    problems.append(f'GC content is {gc:.6g}, not {check["gc_content"]}')
        if 'transcript' in check:
            if alphabet != 'dna':
                problems.append('a transcript is computed from DNA')
            else:
                notes['transcript'] = sequence.replace('T', 'U')
                if notes['transcript'] != str(check['transcript']).upper():
                    problems.append(f'transcript is {notes["transcript"]}')
        if 'translation' in check:
            frame = int(check.get('frame', 1))
            if frame not in (1, 2, 3):
                problems.append('frame is 1, 2 or 3')
            else:
                protein = translate(nucleotide, frame, bool(check.get('to_stop', False)))
                notes['translation'] = protein
                if protein != str(check['translation']).upper():
                    problems.append(f'translation (standard code, frame {frame}) is {protein}')
    elif any(k in check for k in ('reverse_complement', 'gc_content', 'transcript', 'translation')):
        problems.append('nucleotide properties do not apply to a protein sequence')
    return [method('sequence-rules', FAIL, reason='; '.join(problems), **notes) if problems else method('sequence-rules', PASS, **notes)]


RUNNERS = {'formula-balance': run_formula_balance, 'molar-mass': run_molar_mass, 'stoichiometry': run_stoichiometry, 'sequence-check': run_sequence_check}
FIELDS = {
    'formula-balance': ({'equation'}, set()),
    'molar-mass': ({'formula', 'expected'}, {'tolerance'}),
    'stoichiometry': ({'equation', 'amounts', 'expected'}, {'tolerance'}),
    'sequence-check': ({'sequence', 'alphabet'}, {'expected_length', 'reverse_complement', 'gc_content', 'transcript', 'translation', 'frame',
                                                   'to_stop', 'allow_ambiguous', 'tolerance'}),
}
CLASS = {'atom-count': 'discrete-counting', 'nullspace': 'linear-algebra', 'tabulated-weights': 'tabulated-constants',
         'mole-ratio': 'mole-ratio', 'sequence-rules': 'sequence-rules'}
