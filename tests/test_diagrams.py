"""Diagram specs, renderers, the 3D viewer, registry integration, and the geometry, molecule and structure checks."""
import hashlib
import io
import json
import math
from contextlib import redirect_stdout
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import diagram_spec as ds
import install
import scientific_verify as sv
import structure_verify as st
import visual_assets
import visuals

TRI = {'diagram_schema': 1, 'id': 'VIS-right-triangle', 'title': 'A 3-4-5 right triangle', 'kind': 'geometry2d', 'units': 'cm',
       'points': {'A': [0, 0], 'B': [4, 0], 'C': [0, 3]}, 'segments': [['A', 'B'], ['B', 'C'], ['C', 'A']], 'polygons': [['A', 'B', 'C']],
       'angles': [{'at': 'A', 'from': 'B', 'to': 'C'}, {'at': 'B', 'from': 'A', 'to': 'C'}],
       'constraints': [{'type': 'length', 'between': ['B', 'C'], 'equals': 5}, {'type': 'angle', 'at': 'A', 'from': 'B', 'to': 'C', 'equals_deg': 90},
                       {'type': 'area', 'polygon': ['A', 'B', 'C'], 'equals': 6}, {'type': 'perpendicular', 'a': ['A', 'B'], 'b': ['A', 'C']}]}
CUBE_POINTS = {'a': [0, 0, 0], 'b': [1, 0, 0], 'c': [1, 1, 0], 'd': [0, 1, 0], 'e': [0, 0, 1], 'f': [1, 0, 1], 'g': [1, 1, 1], 'h': [0, 1, 1]}
CUBE = {'diagram_schema': 1, 'id': 'VIS-unit-cube', 'title': 'A unit cube', 'kind': 'geometry3d', 'units': 'm', 'points': CUBE_POINTS,
        'segments': [['a', 'b'], ['b', 'c'], ['c', 'd'], ['d', 'a'], ['e', 'f'], ['f', 'g'], ['g', 'h'], ['h', 'e'], ['a', 'e'], ['b', 'f'], ['c', 'g'], ['d', 'h']],
        'polygons': [['e', 'f', 'g', 'h']],
        'constraints': [{'type': 'length', 'between': ['a', 'g'], 'equals': math.sqrt(3)}, {'type': 'coplanar', 'points': ['a', 'b', 'c', 'd']},
                        {'type': 'perpendicular', 'a': ['a', 'b'], 'b': ['a', 'e']}]}
WATER = {'diagram_schema': 1, 'id': 'VIS-water', 'title': 'Water', 'kind': 'molecule', 'units': 'angstrom', 'expected_formula': 'H2O', 'expected_mass': 18.015,
         'atoms': {'O': {'el': 'O', 'xyz': [0, 0, 0]}, 'H1': {'el': 'H', 'xyz': [0.757, 0.586, 0]}, 'H2': {'el': 'H', 'xyz': [-0.757, 0.586, 0]}},
         'bonds': [['O', 'H1', 1], ['O', 'H2', 1]]}
ETHANOL = {'diagram_schema': 1, 'id': 'VIS-ethanol', 'title': 'Ethanol', 'kind': 'molecule', 'expected_formula': 'C2H6O', 'atoms': {
    'C1': {'el': 'C', 'xy': [0, 0]}, 'C2': {'el': 'C', 'xy': [1.5, 0]}, 'O': {'el': 'O', 'xy': [2.25, 1.3]}, 'Ho': {'el': 'H', 'xy': [3.2, 1.3]},
    'H1': {'el': 'H', 'xy': [-0.5, 0.9]}, 'H2': {'el': 'H', 'xy': [-0.5, -0.9]}, 'H3': {'el': 'H', 'xy': [0, -1]}, 'H4': {'el': 'H', 'xy': [2, -0.9]}, 'H5': {'el': 'H', 'xy': [1.5, -1]}},
    'bonds': [['C1', 'C2', 1], ['C2', 'O', 1], ['O', 'Ho', 1], ['C1', 'H1', 1], ['C1', 'H2', 1], ['C1', 'H3', 1], ['C2', 'H4', 1], ['C2', 'H5', 1]]}


def pdb_text(residues='MET ALA GLY LYS', expdta='X-RAY DIFFRACTION', resolution='1.80', code='1ABC', skip=()):
    names = residues.split()
    lines = ['HEADER    ' + 'HYDROLASE'.ljust(40) + '01-JAN-00' + '   ' + code, f'EXPDTA    {expdta}']
    if resolution:
        lines.append(f'REMARK   2 RESOLUTION.    {resolution} ANGSTROMS.')
    lines.append(f'SEQRES {1:3d} A {len(names):4d}  ' + ' '.join(names))
    serial = 0
    for number, name in enumerate(names, 1):
        if number in skip:
            continue
        serial += 1
        lines.append('ATOM  ' + f'{serial:5d}' + ' ' + ' CA ' + ' ' + f'{name:>3}' + ' ' + 'A' + f'{number:4d}' + ' ' + '   ' + f'{number * 3.8:8.3f}{0.5 * number:8.3f}{1.0:8.3f}' + '  1.00 20.00           C')
    lines.append('END')
    return '\n'.join(lines) + '\n'


def verify(*checks, consequence='routine'):
    return sv.run({'verification_schema': 1, 'verification_id': 'V-D', 'claim': {'id': 'C', 'statement': 'diagram claim', 'consequence': consequence},
                   'checks': [dict(c, id=f'k{i}') for i, c in enumerate(checks)]})


def one(kind, **fields):
    return st.RUNNERS[kind]({}, dict({'id': 'c', 'kind': kind}, **fields))[0]


class Geometry(unittest.TestCase):
    def constraint(self, points, constraint):
        return one('geometry-constraint', points=points, constraints=[constraint])

    def test_every_constraint_type_passes_and_fails_on_the_numbers(self):
        flat = {'A': [0, 0], 'B': [4, 0], 'C': [0, 3], 'D': [4, 3], 'M': [2, 0]}
        cases = [({'type': 'length', 'between': ['A', 'B'], 'equals': 4}, {'type': 'length', 'between': ['A', 'B'], 'equals': 4.1}),
                 ({'type': 'equal-length', 'a': ['A', 'B'], 'b': ['C', 'D']}, {'type': 'equal-length', 'a': ['A', 'B'], 'b': ['A', 'C']}),
                 ({'type': 'angle', 'at': 'A', 'from': 'B', 'to': 'C', 'equals_deg': 90}, {'type': 'angle', 'at': 'A', 'from': 'B', 'to': 'C', 'equals_deg': 60}),
                 ({'type': 'angle-sum', 'angles': [{'at': 'A', 'from': 'B', 'to': 'C'}, {'at': 'B', 'from': 'A', 'to': 'D'}], 'equals_deg': 180},
                  {'type': 'angle-sum', 'angles': [{'at': 'A', 'from': 'B', 'to': 'C'}], 'equals_deg': 180}),
                 ({'type': 'parallel', 'a': ['A', 'B'], 'b': ['C', 'D']}, {'type': 'parallel', 'a': ['A', 'B'], 'b': ['A', 'C']}),
                 ({'type': 'perpendicular', 'a': ['A', 'B'], 'b': ['A', 'C']}, {'type': 'perpendicular', 'a': ['A', 'B'], 'b': ['A', 'D']}),
                 ({'type': 'incident', 'point': 'M', 'on': ['A', 'B']}, {'type': 'incident', 'point': 'C', 'on': ['A', 'B']}),
                 ({'type': 'area', 'polygon': ['A', 'B', 'D', 'C'], 'equals': 12}, {'type': 'area', 'polygon': ['A', 'B', 'D', 'C'], 'equals': 10})]
        for good, bad in cases:
            self.assertEqual(self.constraint(flat, good)['status'], 'pass', good)
            failed = self.constraint(flat, bad)
            self.assertEqual(failed['status'], 'fail', bad)

    def test_incident_within_the_segment_and_3d_coplanarity(self):
        line = {'A': [0, 0], 'B': [4, 0], 'P': [6, 0]}
        self.assertEqual(self.constraint(line, {'type': 'incident', 'point': 'P', 'on': ['A', 'B']})['status'], 'pass', 'on the line')
        self.assertEqual(self.constraint(line, {'type': 'incident', 'point': 'P', 'on': ['A', 'B'], 'within': True})['status'], 'fail', 'but outside the segment')
        bent = dict(CUBE_POINTS, d=[0, 1, 0.5])
        self.assertEqual(self.constraint(CUBE_POINTS, {'type': 'coplanar', 'points': ['a', 'b', 'c', 'd']})['status'], 'pass')
        self.assertEqual(self.constraint(bent, {'type': 'coplanar', 'points': ['a', 'b', 'c', 'd']})['status'], 'fail')

    def test_tolerance_is_explicit_and_changeable(self):
        points = {'A': [0, 0], 'B': [1.0000001, 0]}
        self.assertEqual(one('geometry-constraint', points=points, constraints=[{'type': 'length', 'between': ['A', 'B'], 'equals': 1}])['status'], 'pass')
        tight = one('geometry-constraint', points=points, constraints=[{'type': 'length', 'between': ['A', 'B'], 'equals': 1}], tolerance={'abs': 1e-12, 'rel': 1e-12})
        self.assertEqual(tight['status'], 'fail')

    def test_malformed_input_is_an_error_not_a_falsification(self):
        for points, constraint in (({'A': [0, 0]}, {'type': 'length', 'between': ['A', 'Z'], 'equals': 1}), ({'A': [0, 0], 'B': [1, 2, 3]}, {'type': 'length', 'between': ['A', 'B'], 'equals': 1}),
                                   ({'A': [0, 0], 'B': [1, 0]}, {'type': 'weird'})):
            with self.assertRaises(st.StructureError):
                st.RUNNERS['geometry-constraint']({}, {'points': points, 'constraints': [constraint]})
        record = verify({'kind': 'geometry-constraint', 'points': {'A': [0, 0]}, 'constraints': [{'type': 'length', 'between': ['A', 'Z'], 'equals': 1}]})
        self.assertEqual(record['checks'][0]['status'], 'error')


class Molecules(unittest.TestCase):
    def test_water_and_ethanol_are_consistent_graphs(self):
        for spec in (WATER, ETHANOL):
            result = sv.run(ds.verification_spec(spec))
            self.assertEqual(result['outcome'], 'verified-in-scope', spec['id'])

    def test_valence_charge_and_formula_failures(self):
        over = {'C': {'el': 'C'}, **{f'H{i}': {'el': 'H'} for i in range(5)}}
        result = one('molecule-graph', atoms=over, bonds=[['C', f'H{i}', 1] for i in range(5)])
        self.assertEqual(result['status'], 'fail')
        self.assertIn('C', result['reason'])
        ammonium = {'N': {'el': 'N', 'charge': 1}, **{f'H{i}': {'el': 'H'} for i in range(4)}}
        good = one('molecule-graph', atoms=ammonium, bonds=[['N', f'H{i}', 1] for i in range(4)], expected_charge=1, expected_formula='H4N')
        self.assertEqual(good['status'], 'pass', good.get('reason'))
        wrong = one('molecule-graph', atoms=WATER['atoms'], bonds=WATER['bonds'], expected_formula='H2O2')
        self.assertEqual(wrong['status'], 'fail')

    def test_implicit_hydrogen_mode_only_bounds_the_valence(self):
        skeleton = {'C1': {'el': 'C'}, 'C2': {'el': 'C'}, 'O': {'el': 'O'}}
        bonds = [['C1', 'C2', 1], ['C2', 'O', 1]]
        self.assertEqual(one('molecule-graph', atoms=skeleton, bonds=bonds, explicit_hydrogens=False)['status'], 'pass')
        self.assertEqual(one('molecule-graph', atoms=skeleton, bonds=bonds)['status'], 'fail', 'explicit hydrogens are the default')

    def test_bad_graphs_are_errors(self):
        for atoms, bonds in (({'A': {'el': 'Qq'}}, []), ({'A': {'el': 'C'}}, [['A', 'B', 1]]), ({'A': {'el': 'C'}, 'B': {'el': 'C'}}, [['A', 'B', 4]]),
                             ({'A': {'el': 'C'}}, [['A', 'A', 1]])):
            with self.assertRaises(st.StructureError):
                st.RUNNERS['molecule-graph']({}, {'atoms': atoms, 'bonds': bonds})


class Structures(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def file(self, text=None, name='model.pdb'):
        path = self.dir / name
        path.write_text(text if text is not None else pdb_text(), encoding='utf-8')
        return path

    def check(self, path, claims, digest=None):
        return one('structure-source', path=str(path), sha256=digest or hashlib.sha256(path.read_bytes()).hexdigest(), claims=claims)

    def test_true_claims_about_a_file_pass(self):
        result = self.check(self.file(), {'accession': '1abc', 'method': 'x-ray', 'resolution_max': 2.0, 'chains': ['A'],
                                          'residue_range': {'chain': 'A', 'start': 1, 'end': 4}, 'sequence': {'chain': 'A', 'expected': 'MAGK'},
                                          'residue': {'chain': 'A', 'number': 3, 'name': 'GLY'}})
        self.assertEqual(result['status'], 'pass', result.get('reason'))

    def test_false_claims_fail(self):
        path = self.file()
        for claims in ({'accession': '2XYZ'}, {'method': 'NMR'}, {'resolution_max': 1.5}, {'chains': ['B']}, {'sequence': {'chain': 'A', 'expected': 'MAGA'}},
                       {'residue': {'chain': 'A', 'number': 3, 'name': 'LYS'}}, {'residue': {'chain': 'A', 'number': 99, 'name': 'GLY'}}):
            result = self.check(path, claims)
            self.assertEqual(result['status'], 'fail', claims)

    def test_gaps_in_a_residue_range_are_reported_and_allowed_on_request(self):
        path = self.file(pdb_text(skip=(2,)))
        gap = self.check(path, {'residue_range': {'chain': 'A', 'start': 1, 'end': 4}})
        self.assertEqual(gap['status'], 'fail')
        self.assertIn('2', gap['reason'])
        self.assertEqual(self.check(path, {'residue_range': {'chain': 'A', 'start': 1, 'end': 4, 'allow_gaps': True}})['status'], 'pass')

    def test_a_changed_file_fails_its_hash_and_unstated_things_are_inconclusive(self):
        path = self.file()
        recorded = hashlib.sha256(path.read_bytes()).hexdigest()
        path.write_text(pdb_text(code='9ZZZ'), encoding='utf-8')
        changed = self.check(path, {'chains': ['A']}, digest=recorded)
        self.assertEqual(changed['status'], 'fail')
        self.assertIn('hash', changed['reason'])
        nmr = self.file(pdb_text(expdta='SOLUTION NMR', resolution=''), 'nmr.pdb')
        self.assertEqual(self.check(nmr, {'resolution_max': 2.0})['status'], 'inconclusive')

    def test_mmcif_missing_files_and_unknown_claims_are_errors(self):
        cif = self.file('data_1ABC\nloop_\n_atom_site.group_PDB\nATOM 1 N N\n', 'm.cif')
        with self.assertRaises(st.StructureError):
            self.check(cif, {'chains': ['A']})
        with self.assertRaises(st.StructureError):
            one('structure-source', path=str(self.dir / 'nothing.pdb'), sha256='0' * 64, claims={'chains': ['A']})
        with self.assertRaises(st.StructureError):
            self.check(self.file(), {'mood': 'good'})


class Rendering(unittest.TestCase):
    def test_every_kind_renders_a_static_svg(self):
        trace = {'diagram_schema': 1, 'id': 'VIS-trace', 'title': 'Trace', 'kind': 'structure-trace',
                 'chains': {'A': [[i, i * 3.8, math.sin(i), 0.5 * i] for i in range(1, 8)], 'B': [[i, i * 3.8, 5, math.cos(i)] for i in range(1, 6)]}}
        for spec in (TRI, CUBE, WATER, ETHANOL, trace):
            self.assertEqual(ds.validate(spec), [], spec['id'])
            svg = ds.render_svg(spec)
            self.assertEqual(visual_assets.svg_problems(svg), [], spec['id'])
            self.assertIn(spec['title'], svg)

    def test_a_2d_drawing_marks_right_angles_and_computes_other_angles(self):
        svg = ds.render_svg(TRI)
        self.assertIn('36.9', svg)
        self.assertRegex(svg, r'to scale|Drawn to scale')

    def test_schematics_say_so_and_never_claim_scale(self):
        svg = ds.render_svg(dict(TRI, schematic=True))
        self.assertIn('not to scale', svg)
        self.assertNotIn('Drawn to scale', svg)

    def test_the_3d_views_share_one_scale(self):
        svg = ds.render_svg(CUBE)
        for word in ('Front', 'Top', 'Side', 'Isometric'):
            self.assertIn(word, svg)
        self.assertIn('common scale', svg)

    def test_text_in_a_spec_cannot_inject_markup(self):
        nasty = dict(TRI, title='</title><script>alert(1)</script>', points={'A<x>': [0, 0], 'B': [4, 0], 'C': [0, 3]}, segments=[['A<x>', 'B']], polygons=[], angles=[], constraints=[])
        svg = ds.render_svg(nasty)
        self.assertNotIn('<script', svg)
        self.assertEqual(visual_assets.svg_problems(svg), [])


class Validation(unittest.TestCase):
    def test_bad_specs_are_reported(self):
        for spec in ({'kind': 'sculpture'}, dict(TRI, diagram_schema=2), dict(TRI, id='triangle'), dict(TRI, mood='x'), dict(TRI, segments=[['A', 'Z']]),
                     dict(TRI, points={'A': [0, 0, 0], 'B': [1, 0, 0]}), dict(CUBE, points={'a': [0, 0], 'b': [1, 0]}), dict(TRI, polygons=[['A', 'B']])):
            self.assertTrue(ds.validate(spec), spec)
        with self.assertRaises(ds.DiagramError):
            ds.render_svg({'kind': 'sculpture'})


class Viewer(unittest.TestCase):
    def test_the_viewer_is_self_contained_and_restricted(self):
        page = ds.viewer_html(CUBE)
        self.assertIn("default-src 'none'", page)
        self.assertNotRegex(page, r'(?:src|href)=["\']https?:')
        self.assertNotRegex(page, r'\b(?:fetch|XMLHttpRequest)\b')
        for view in ('front', 'top', 'side', 'isometric'):
            self.assertIn(view, page)

    def test_markup_in_a_title_is_escaped(self):
        page = ds.viewer_html(dict(WATER, title='<img src=x onerror=alert(1)>'))
        self.assertNotIn('<img src=x', page)

    def test_two_dimensional_diagrams_have_no_viewer(self):
        for spec in (TRI, ETHANOL):
            with self.assertRaises(ds.DiagramError):
                ds.viewer_html(spec)


class Files(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_render_writes_files_and_never_overwrites(self):
        flat = ds.render_files(TRI, self.dir / 'flat')
        self.assertEqual(sorted(flat), ['spec', 'svg'])
        solid = ds.render_files(CUBE, self.dir / 'solid')
        self.assertEqual(sorted(solid), ['spec', 'svg', 'viewer'])
        with self.assertRaises(ds.DiagramError):
            ds.render_files(CUBE, self.dir / 'solid')

    def test_register_adds_a_valid_record_at_rendered_and_refuses_a_changed_spec(self):
        first = ds.register(self.dir, CUBE, concepts=['solid-geometry'])
        self.assertFalse(first['reused'])
        records, diagnostics = visuals.discover(self.dir)
        self.assertEqual(diagnostics, [])
        record = records['VIS-unit-cube']
        self.assertEqual((record['verification_status'], record['quantitative'], record['kind']), ('rendered', True, 'model-driven-plot'))
        self.assertTrue(ds.register(self.dir, CUBE, concepts=['solid-geometry'])['reused'])
        with self.assertRaises(ds.DiagramError):
            ds.register(self.dir, dict(CUBE, title='Another cube'), concepts=['solid-geometry'])

    def test_a_schematic_is_registered_as_not_quantitative(self):
        ds.register(self.dir, dict(TRI, id='VIS-sketch', schematic=True), concepts=['triangle'])
        record = visuals.discover(self.dir)[0]['VIS-sketch']
        self.assertFalse(record['quantitative'])


class FromTheSameNumbers(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_the_spec_a_picture_was_drawn_from_is_the_spec_that_gets_checked(self):
        self.assertEqual(sv.run(ds.verification_spec(TRI))['outcome'], 'verified-in-scope')
        bent = dict(TRI, points={'A': [0, 0], 'B': [4, 0], 'C': [0.5, 3]})
        self.assertEqual(sv.run(ds.verification_spec(bent))['outcome'], 'invalidated')
        self.assertEqual(sv.run(ds.verification_spec(dict(WATER, expected_formula='H2O2')))['outcome'], 'invalidated')

    def test_a_structure_trace_from_a_pdb_file_is_bound_to_that_file(self):
        pdb = self.dir / 'model.pdb'
        pdb.write_text(pdb_text(), encoding='utf-8')
        spec = ds.spec_from_pdb(pdb, None, 'VIS-model', 'A short model')
        self.assertEqual(ds.validate(spec), [])
        self.assertEqual(sorted(spec['chains']), ['A'])
        self.assertEqual(len(spec['chains']['A']), 4)
        self.assertEqual(sv.run(ds.verification_spec(spec))['outcome'], 'verified-in-scope')
        pdb.write_text(pdb_text(code='9ZZZ'), encoding='utf-8')
        self.assertEqual(sv.run(ds.verification_spec(spec))['outcome'], 'invalidated')


class CommandLine(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.script = str(ROOT / 'scripts/diagram_spec.py')

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-S', '-B', self.script, *args], capture_output=True, text=True, encoding='utf-8')

    def test_validate_render_register_and_capabilities(self):
        spec = self.dir / 'cube.json'
        spec.write_text(json.dumps(CUBE), encoding='utf-8')
        bad = self.dir / 'bad.json'
        bad.write_text(json.dumps(dict(CUBE, kind='sculpture')), encoding='utf-8')
        self.assertEqual(self.run_cli('validate', str(spec)).returncode, 0)
        self.assertNotEqual(self.run_cli('validate', str(bad)).returncode, 0)
        out = self.dir / 'out'
        done = self.run_cli('render', str(spec), '--out', str(out))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotEqual(self.run_cli('render', str(spec), '--out', str(out)).returncode, 0, 'it never overwrites')
        vault = self.dir / 'vault'
        vault.mkdir()
        registered = self.run_cli('register', str(spec), '--root', str(vault), '--concept', 'solid-geometry')
        self.assertEqual(registered.returncode, 0, registered.stdout + registered.stderr)
        verification = json.loads(self.run_cli('verification-spec', str(spec)).stdout)
        self.assertEqual(verification['checks'][0]['kind'], 'geometry-constraint')
        self.assertEqual(self.run_cli('capabilities').returncode, 0)


class Wiring(unittest.TestCase):
    def test_the_kinds_are_registered_documented_and_classified(self):
        protocol = (ROOT / 'references/VERIFICATION_PROTOCOL.md').read_text(encoding='utf-8')
        for kind in st.RUNNERS:
            self.assertIn(kind, sv.DISCRETE)
            self.assertIn(kind, sv.FIELDS)
            self.assertIn(f'`{kind}`', protocol)
        record = verify({'kind': 'geometry-constraint', 'points': {'A': [0, 0], 'B': [3, 4]}, 'constraints': [{'type': 'length', 'between': ['A', 'B'], 'equals': 5}]})
        self.assertEqual(record['independent_classes'], ['coordinate-geometry'])

    def test_the_tools_and_protocol_reach_the_visualization_skill(self):
        text = (ROOT / 'skills/science-visualize/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('references/DIAGRAM_PROTOCOL.md', text)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with redirect_stdout(io.StringIO()):
                install.install_skills(tmp / 'claude', False)
            scripts = tmp / 'claude' / 'science-visualize/scripts'
            for name in ('diagram_spec.py', 'structure_verify.py', 'chembio_verify.py', 'scientific_verify.py'):
                self.assertEqual((scripts / name).read_bytes(), (ROOT / 'scripts' / name).read_bytes(), name)
            done = subprocess.run([sys.executable, '-S', '-B', str(scripts / 'diagram_spec.py'), 'capabilities'], cwd=tmp, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


if __name__ == '__main__':
    unittest.main()
