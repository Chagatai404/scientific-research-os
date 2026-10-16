"""Animation: spec, scene lint, backend detection and choice, a recorded render, and the registry record. No renderer is needed to run these."""
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import animate as an
import install
import visuals

REAL_WHICH = shutil.which

SCENE = '''try:
    import manimgx as m
except ImportError:
    import manim as m


class Derivation(m.Scene):
    def construct(self):
        self.play(m.Write(m.MathTex("x^2")))
'''
SPEC = {'animation_schema': 1, 'id': 'VIS-complete-square', 'title': 'Completing the square', 'scene': 'scene.py', 'scene_class': 'Derivation',
        'concepts': ['quadratic-formula'], 'basis': 'Each line follows from the last by adding b^2/4 to both sides.', 'predict': 'What completes the square?'}
PROBE = json.dumps({'streams': [{'width': 1280, 'height': 720, 'r_frame_rate': '30/1'}], 'format': {'duration': '9.5'}})


class Fake:
    """Stands in for every program animate.py starts. ``layout`` is what ManimGX's inspect says; ``fail`` makes the render step fail."""

    def __init__(self, layout='layout: no problems in 12 samples', inspect_code=0, fail=False, slides='5.7.0', versions=None, probe=PROBE, raw=None):
        self.calls, self.layout, self.inspect_code, self.fail, self.slides = [], layout, inspect_code, fail, slides
        self.versions, self.probe, self.raw = versions or {}, probe, raw

    def __call__(self, args, cwd=None, timeout=900):
        self.calls.append([str(a) for a in args])
        name = Path(args[0]).stem.lower()
        ok = {'code': 0, 'stdout': '', 'stderr': '', 'seconds': 1.5}
        if '--version' in args:
            return dict(ok, stdout=self.versions.get(str(args[0]), f'{name} 1.0.0'))
        if name.startswith('python') and '-c' in args:
            return dict(ok, stdout=f'{self.slides}\n') if self.slides else dict(ok, code=1)
        if name == 'ffprobe':
            return dict(ok, stdout=self.probe)
        if name == 'ffmpeg':
            Path(args[-1]).write_bytes(self.raw if (self.raw is not None and 'rawvideo' in args) else b'\x89PNG fake')
            return ok
        if name == 'manimgx':
            if args[1] == 'inspect':
                return dict(ok, code=self.inspect_code, stdout=f'scene: Derivation\n{self.layout}\n')
            if self.fail:
                return dict(ok, code=1, stderr='boom: could not typeset')
            Path(args[args.index('-o') + 1]).write_bytes(b'mp4 bytes')
            return ok
        if name == 'manim' and args[1] == 'render':
            if self.fail:
                return dict(ok, code=1, stderr='latex error')
            target = Path(args[args.index('--media_dir') + 1]) / 'videos' / 'scene' / '720p30' / f'{args[-1]}.mp4'
            target.parent.mkdir(parents=True)
            target.write_bytes(b'ce mp4')
            return ok
        if name == 'manim-slides' and args[1] == 'convert':
            Path(args[-1]).write_text('<html>slides</html>', encoding='utf-8')
            return ok
        return dict(ok, code=127, stderr='unexpected ' + ' '.join(map(str, args)))


def make_env(base: Path, name: str, tools=('manimgx',)) -> Path:
    env = base / name
    (env / 'Scripts').mkdir(parents=True)
    for tool in (*tools, 'python'):
        (env / 'Scripts' / f'{tool}.exe').write_bytes(b'')
    return env


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.vault = self.dir / 'vault'
        self.vault.mkdir()
        self.work = self.dir / 'work'
        self.work.mkdir()
        (self.work / 'scene.py').write_text(SCENE, encoding='utf-8')
        self.spec_file = self.work / 'spec.json'
        self.write_spec(SPEC)
        for patcher in (mock.patch.object(an.shutil, 'which', lambda t: f'/bin/{t}' if t in ('ffmpeg', 'ffprobe') else None),
                        mock.patch.dict(os.environ, {an.ENV_VARIABLE: ''})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_spec(self, spec):
        self.spec_file.write_text(json.dumps(spec), encoding='utf-8')

    def run_render(self, fake, envs, spec=None, **kwargs):
        if spec is not None:
            self.write_spec(spec)
        with mock.patch.object(an, 'run_command', fake):
            return an.render(self.spec_file, self.vault, envs=[str(e) for e in envs], **kwargs)


class Spec(unittest.TestCase):
    def test_a_good_spec_has_no_problems(self):
        self.assertEqual(an.validate(SPEC), [])

    def test_basis_is_required_unless_the_animation_is_a_schematic(self):
        without = {k: v for k, v in SPEC.items() if k != 'basis'}
        self.assertTrue(any('basis is required' in p for p in an.validate(without)))
        self.assertEqual(an.validate(dict(without, schematic=True)), [])

    def test_bad_specs_say_what_is_wrong(self):
        cases = [(dict(SPEC, animation_schema=2), 'animation_schema'), (dict(SPEC, id='nope'), 'id looks like'), (dict(SPEC, mood='x'), 'unknown field'),
                 (dict(SPEC, scene='../evil.py'), 'inside the project'), (dict(SPEC, scene='/abs.py'), 'inside the project'), (dict(SPEC, scene_class='not a name'), 'class name'),
                 (dict(SPEC, concepts=[]), 'concepts'), (dict(SPEC, backend='blender'), 'backend'), (dict(SPEC, resolution='big'), 'resolution'), (dict(SPEC, fps=0), 'fps'),
                 (dict(SPEC, fps=True), 'fps'), (dict(SPEC, seed='x'), 'seed'), (dict(SPEC, slides='yes'), 'slides'), (dict(SPEC, pauses=[{'at': -1, 'note': 'x'}]), 'pauses'),
                 (dict(SPEC, pauses=[{'at': 'end'}]), 'pauses'), ({'animation_schema': 1}, 'missing field')]
        for spec, expect in cases:
            self.assertTrue(any(expect in p for p in an.validate(spec)), (expect, an.validate(spec)))
        self.assertEqual(an.validate(dict(SPEC, pauses=[{'at': 2.5, 'note': 'ask'}, {'at': 'end', 'note': 'recap'}], seed=7, fps=60, resolution='1920x1080')), [])
        self.assertEqual(an.validate([]), ['spec must be a JSON object'])


class Lint(unittest.TestCase):
    def test_a_clean_scene_passes_and_lists_its_classes(self):
        result = an.lint_source(SCENE, SPEC)
        self.assertEqual((result['errors'], result['warnings'], result['classes']), ([], [], ['Derivation']))

    def test_obvious_escapes_are_refused(self):
        for line, expect in (('import subprocess', 'subprocess'), ('import requests', 'requests'), ('from urllib.request import urlopen', 'urllib'),
                             ('import socket', 'socket'), ('eval("1")', 'eval'), ('exec("x=1")', 'exec'), ('import os\nos.system("dir")', 'os.system'),
                             ('import os\nos.remove("x")', 'os.remove'), ('__import__("os")', '__import__')):
            result = an.lint_source(SCENE + '\n' + line + '\n')
            self.assertTrue(any(expect in e for e in result['errors']), (line, result['errors']))

    def test_a_scene_must_import_a_library_and_define_its_class(self):
        self.assertTrue(any('imports none' in e for e in an.lint_source('class Derivation: pass\n')['errors']))
        self.assertTrue(any('not defined' in e for e in an.lint_source(SCENE, dict(SPEC, scene_class='Other'))['errors']))
        self.assertTrue(any('syntax error' in e for e in an.lint_source('def (:\n')['errors']))

    def test_unseeded_randomness_warns_and_a_seed_silences_it(self):
        random_scene = SCENE + '\nimport numpy as np\nx = np.random.rand(3)\n'
        self.assertTrue(any('seed' in w for w in an.lint_source(random_scene)['warnings']))
        self.assertEqual([w for w in an.lint_source(random_scene, dict(SPEC, seed=3))['warnings'] if 'seed' in w], [])
        self.assertEqual([w for w in an.lint_source(random_scene + 'np.random.seed(1)\n')['warnings'] if 'seed' in w], [])
        self.assertTrue(any('seed' in w for w in an.lint_source(SCENE + '\nimport random\n')['warnings']))

    def test_a_matrix_without_row_breaks_is_flagged_because_the_backslashes_may_have_been_lost(self):
        good = SCENE + '\nA = m.MathTex(r"\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}")\n'
        lost = SCENE + '\nA = m.MathTex(r"\\begin{pmatrix} a & b \\ c & d \\end{pmatrix}")\n'
        self.assertEqual([w for w in an.lint_source(good)['warnings'] if 'row break' in w], [])
        self.assertEqual(len([w for w in an.lint_source(lost)['warnings'] if 'row break' in w]), 1)
        flat = SCENE + '\nB = m.MathTex(r"\\begin{aligned} x &= 1 y &= 2 \\end{aligned}")\n'
        self.assertEqual(len([w for w in an.lint_source(flat)['warnings'] if 'row break' in w]), 1)
        single = SCENE + '\nC = m.MathTex(r"\\begin{pmatrix} 1 \\end{pmatrix}")\n'
        self.assertEqual([w for w in an.lint_source(single)['warnings'] if 'row break' in w], [], 'no & means one column; nothing to flag')

    def test_teaching_warnings_name_the_missing_prompt_and_slides(self):
        no_predict = {k: v for k, v in SPEC.items() if k != 'predict'}
        self.assertTrue(any('predict' in w for w in an.lint_source(SCENE, no_predict)['warnings']))
        self.assertTrue(any('one slide' in w for w in an.lint_source(SCENE, dict(SPEC, slides=True))['warnings']))
        sectioned = SCENE + '\n        self.next_section()\n'
        self.assertEqual(an.lint_source(sectioned, dict(SPEC, slides=True))['sections'], 1)


class Detection(Base):
    def test_backends_are_found_with_versions_and_the_known_bad_pairing_is_flagged(self):
        gx, ce = make_env(self.dir, 'gx'), make_env(self.dir, 'ce', ('manim',))
        fake = Fake(versions={str(gx / 'Scripts' / 'manimgx.exe'): 'manimgx, version 0.1.1', str(ce / 'Scripts' / 'manim.exe'): 'Manim Community v0.22.0'})
        with mock.patch.object(an, 'run_command', fake):
            found = an.capabilities([str(gx), str(ce)])
        self.assertEqual([(b['backend'], b['version']) for b in found['backends']], [('manimgx', '0.1.1'), ('manim', '0.22.0')])
        self.assertTrue(found['tools']['ffmpeg'])
        self.assertTrue(any('write_to_movie' in n for n in found['notes']))

    def test_nothing_found_says_so_and_never_installs(self):
        with mock.patch.object(an, 'run_command', Fake()):
            found = an.capabilities([])
        self.assertEqual(found['backends'], [])
        self.assertTrue(any('no animation backend' in n for n in found['notes']))

    def test_environments_come_from_the_variable_when_none_are_named(self):
        gx = make_env(self.dir, 'gx')
        with mock.patch.dict(os.environ, {an.ENV_VARIABLE: str(gx)}), mock.patch.object(an, 'run_command', Fake()):
            self.assertEqual([b['backend'] for b in an.capabilities()['backends']], ['manimgx'])

    def test_manimgx_is_preferred_and_slides_select_manim_community(self):
        gx, ce = make_env(self.dir, 'gx'), make_env(self.dir, 'ce', ('manim', 'manim-slides'))
        with mock.patch.object(an, 'run_command', Fake()):
            envs = [str(ce), str(gx)]
            self.assertEqual(an.choose(SPEC, envs)['backend'], 'manimgx')
            self.assertEqual(an.choose(dict(SPEC, backend='manim'), envs)['backend'], 'manim')
            self.assertEqual(an.choose(dict(SPEC, slides=True), envs)['backend'], 'manim')
            self.assertEqual(an.choose(SPEC, envs, backend='manim')['backend'], 'manim')
            self.assertIsNone(an.choose(dict(SPEC, backend='manim'), [str(gx)]))


class Rendering(Base):
    def test_a_render_keeps_the_files_a_record_and_a_registry_entry_at_rendered(self):
        gx = make_env(self.dir, 'gx')
        result = self.run_render(Fake(), [gx])
        self.assertTrue(result['rendered'])
        self.assertEqual((result['backend'], result['layout']['checked']), ('manimgx', True))
        folder = self.vault / 'Visuals' / 'vis-complete-square'
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ['vis-complete-square.animation.json', 'vis-complete-square.keyframes.png', 'vis-complete-square.mp4',
                                                                     'vis-complete-square.poster.png', 'vis-complete-square.render.json', 'vis-complete-square.scene.py',
                                                                     'vis-complete-square.visual.json'])
        records, diagnostics = visuals.discover(self.vault)
        self.assertEqual(diagnostics, [])
        record = records['VIS-complete-square']
        self.assertEqual((record['kind'], record['mode'], record['verification_status'], record['quantitative'], record['source_type']),
                         ('animation', 'animation', 'rendered', True, 'generated'))
        self.assertIn('Rendering is not verification', record['basis'])
        self.assertEqual([e['format'] for e in record['exports']], ['png', 'png'])
        self.assertEqual(visuals.reusable(records, 'quadratic-formula'), [], 'a rendered visual is not reusable automatically')
        report = json.loads((folder / 'vis-complete-square.render.json').read_text(encoding='utf-8'))
        self.assertEqual((report['backend']['env'], report['video']['duration'], report['video']['width']), ('gx', 9.5, 1280))
        self.assertNotIn(str(self.dir), json.dumps(report), 'no local path leaks into the vault')
        self.assertEqual([c['argv'][1] for c in report['commands']], ['inspect', 'render'])
        self.assertEqual(report['commands'][0]['argv'][2], 'scene.py', 'commands are recorded without absolute paths')

    def test_the_same_spec_is_reused_and_a_changed_one_is_refused(self):
        gx = make_env(self.dir, 'gx')
        self.run_render(Fake(), [gx])
        again = self.run_render(Fake(), [gx])
        self.assertEqual((again['reused'], again['rendered']), (True, True))
        with self.assertRaisesRegex(an.AnimationError, 'different spec or scene'):
            self.run_render(Fake(), [gx], dict(SPEC, title='Another title'))
        (self.work / 'scene.py').write_text(SCENE + '\n# edited\n', encoding='utf-8')
        with self.assertRaisesRegex(an.AnimationError, 'different spec or scene'):
            self.run_render(Fake(), [gx], SPEC)

    def test_layout_problems_stop_the_render_unless_allowed_and_are_then_recorded(self):
        gx = make_env(self.dir, 'gx')
        fake = Fake(layout='layout: 1 problem\n  [1] t=2s (scene.py:9) label: 0.15 past the bottom edge', inspect_code=1)
        with self.assertRaises(an.LayoutProblems) as caught:
            self.run_render(fake, [gx])
        self.assertIn('past the bottom edge', str(caught.exception))
        self.assertFalse((self.vault / 'Visuals').exists(), 'a stopped render leaves nothing behind')
        self.assertNotIn('render', [c[1] for c in fake.calls if Path(c[0]).stem == 'manimgx'])
        result = self.run_render(Fake(layout='layout: 1 problem\n  [1] t=2s label: clipped', inspect_code=1), [gx], allow_layout_problems=True)
        self.assertEqual(len(result['layout']['problems']), 1)

    def test_a_3d_scene_is_recorded_as_not_layout_checked(self):
        result = self.run_render(Fake(layout='layout: not checked (a 3D scene)'), [make_env(self.dir, 'gx')])
        self.assertEqual(result['layout']['checked'], False)

    def test_a_failed_render_leaves_no_folder_and_reports_the_reason(self):
        with self.assertRaisesRegex(an.AnimationError, 'could not typeset'):
            self.run_render(Fake(fail=True), [make_env(self.dir, 'gx')])
        self.assertFalse((self.vault / 'Visuals' / 'vis-complete-square').exists())

    def test_no_backend_is_an_honest_unrendered_result_that_writes_nothing(self):
        result = self.run_render(Fake(), [])
        self.assertFalse(result['rendered'])
        self.assertIn('nothing was rendered', result['fallback'])
        self.assertFalse((self.vault / 'Visuals').exists())

    def test_manim_community_output_is_found_in_its_media_tree(self):
        ce = make_env(self.dir, 'ce', ('manim',))
        result = self.run_render(Fake(), [ce], dict(SPEC, backend='manim'))
        self.assertEqual((result['backend'], result['layout']['checked']), ('manim', False))
        self.assertEqual((self.vault / 'Visuals/vis-complete-square/vis-complete-square.mp4').read_bytes(), b'ce mp4')

    def test_a_schematic_animation_is_registered_without_quantitative_claims(self):
        spec = {k: v for k, v in SPEC.items() if k != 'basis'}
        self.run_render(Fake(), [make_env(self.dir, 'gx')], dict(spec, schematic=True))
        record = visuals.discover(self.vault)[0]['VIS-complete-square']
        self.assertEqual((record['source_type'], record['quantitative']), ('schematic', False))
        self.assertNotIn('basis', record)

    def test_unsafe_scenes_missing_files_and_bad_places_are_refused_before_anything_runs(self):
        gx = make_env(self.dir, 'gx')
        fake = Fake()
        (self.work / 'scene.py').write_text(SCENE + '\nimport subprocess\n', encoding='utf-8')
        with self.assertRaisesRegex(an.AnimationError, 'scene refused'):
            self.run_render(fake, [gx])
        (self.work / 'scene.py').write_text(SCENE, encoding='utf-8')
        with self.assertRaisesRegex(an.AnimationError, 'scene file not found'):
            self.run_render(fake, [gx], dict(SPEC, scene='missing.py'))
        for bad in ('../out', 'a/../b', 'C:/x', ''):
            with self.assertRaisesRegex(an.AnimationError, 'relative path inside the vault'):
                self.run_render(fake, [gx], SPEC, directory=bad)
        with self.assertRaisesRegex(an.AnimationError, 'invalid spec'):
            self.run_render(fake, [gx], dict(SPEC, fps=0))
        self.assertEqual(fake.calls, [], 'no program was started for a refused scene')

    def test_a_scene_in_a_subfolder_of_the_spec_folder_is_allowed(self):
        sub = self.work / 'sub'
        sub.mkdir()
        (sub / 'scene.py').write_text(SCENE, encoding='utf-8')
        result = self.run_render(Fake(), [make_env(self.dir, 'gx')], dict(SPEC, scene='sub/scene.py'))
        self.assertTrue(result['rendered'])

    def test_slides_make_a_single_offline_html_with_manim_community_and_a_note_with_manimgx(self):
        ce = make_env(self.dir, 'ce', ('manim', 'manim-slides'))
        done = self.run_render(Fake(), [ce], dict(SPEC, slides=True))
        self.assertEqual(done['slides'], 'vis-complete-square.slides.html')
        self.assertTrue((self.vault / 'Visuals/vis-complete-square/vis-complete-square.slides.html').exists())
        report = json.loads((self.vault / 'Visuals/vis-complete-square/vis-complete-square.render.json').read_text(encoding='utf-8'))
        convert = [c for c in report['commands'] if c['argv'][0] == 'manim-slides'][0]['argv']
        self.assertIn('--one-file', convert)
        self.assertIn('--offline', convert)
        gx = make_env(self.dir, 'gx2')
        note = self.run_render(Fake(), [gx], dict(SPEC, id='VIS-gx-slides', slides=True, backend='manimgx'))
        self.assertIn('present', note['slides'])

    def test_slides_without_manim_slides_say_so(self):
        ce = make_env(self.dir, 'ce', ('manim',))
        result = self.run_render(Fake(), [ce], dict(SPEC, slides=True))
        self.assertIn('not installed', result['slides'])

    def test_missing_ffmpeg_means_no_key_frames_and_a_reason_not_a_failure(self):
        with mock.patch.object(an.shutil, 'which', lambda t: None):
            result = self.run_render(Fake(), [make_env(self.dir, 'gx')])
        self.assertEqual(result['exports'], [])
        report = json.loads((self.vault / 'Visuals/vis-complete-square/vis-complete-square.render.json').read_text(encoding='utf-8'))
        self.assertEqual(report['keyframes']['reason'], 'ffmpeg not found')

    def test_present_prints_a_command_and_runs_nothing(self):
        gx, ce = {'backend': 'manimgx', 'command': '/x/manimgx.exe'}, {'backend': 'manim', 'command': '/x/manim'}
        self.assertEqual(an.present_command(SPEC, gx), ['manimgx.exe', 'present', 'scene.py', 'Derivation'])
        self.assertEqual(an.present_command(SPEC, ce), ['manim-slides', 'present', 'Derivation'])


SMALL = json.dumps({'streams': [{'width': 64, 'height': 36, 'r_frame_rate': '30/1'}], 'format': {'duration': '6.0'}})
AREA = 64 * 36


def frame(bottom=False, top=False, left=False, specks=0):
    pixels = bytearray(AREA)
    if bottom:
        pixels[AREA - 128:] = b'\xff' * 128
    if top:
        pixels[:128] = b'\xff' * 128
    if left:
        for y in range(36):
            pixels[y * 64:y * 64 + 2] = b'\xff\xff'
    for i in range(specks):
        pixels[i] = 255
    return bytes(pixels)


class EdgeContact(Base):
    INFO = {'duration': 6.0, 'width': 64, 'height': 36}

    def check(self, raw, **kwargs):
        with mock.patch.object(an, 'run_command', Fake(raw=raw, probe=SMALL)):
            return an.edge_contact(Path('v.mp4'), self.INFO, **kwargs)

    def test_clean_frames_report_nothing(self):
        found = self.check(frame() * 3)
        self.assertEqual((found['checked'], found['frames'], found['touching']), (True, 3, []))

    def test_content_on_the_edge_is_reported_by_side_and_time(self):
        found = self.check(frame() + frame(bottom=True) + frame(top=True, left=True))
        self.assertEqual([(h['t'], sorted(h['sides'])) for h in found['touching']], [(2.0, ['bottom']), (4.0, ['left', 'top'])])

    def test_a_full_bleed_background_and_a_few_stray_pixels_are_not_cropping(self):
        self.assertEqual(self.check(b'\xff' * AREA * 2)['touching'], [], 'the background is read from the first frame')
        self.assertEqual(self.check(frame(specks=5) * 2)['touching'], [])

    def test_unreadable_output_says_why_instead_of_passing(self):
        self.assertEqual(self.check(b'')['checked'], False)
        with mock.patch.object(an.shutil, 'which', lambda t: None):
            self.assertIn('ffmpeg', an.edge_contact(Path('v.mp4'), self.INFO)['reason'])

    def test_a_3d_render_with_cropped_frames_is_stopped_unless_allowed_and_then_recorded(self):
        gx = make_env(self.dir, 'gx')
        cropped = frame() + frame(bottom=True)
        fake = Fake(layout='layout: not checked (a 3D scene)', probe=SMALL, raw=cropped)
        with self.assertRaises(an.LayoutProblems) as caught:
            self.run_render(fake, [gx])
        self.assertIn('touches the bottom edge', str(caught.exception))
        self.assertFalse((self.vault / 'Visuals').exists())
        allowed = self.run_render(Fake(layout='layout: not checked (a 3D scene)', probe=SMALL, raw=cropped), [gx], allow_layout_problems=True)
        self.assertEqual(len(allowed['layout']['problems']), 1)
        report = json.loads((self.vault / 'Visuals/vis-complete-square/vis-complete-square.render.json').read_text(encoding='utf-8'))
        self.assertEqual(report['layout']['edge_contact']['touching'][0]['sides'], {'bottom': 128})

    def test_a_clean_3d_render_records_that_the_edges_were_checked(self):
        result = self.run_render(Fake(layout='layout: not checked (a 3D scene)', probe=SMALL, raw=frame() * 3), [make_env(self.dir, 'gx')])
        self.assertEqual((result['layout']['checked'], result['layout']['edge_contact']['checked']), (False, True))

    def test_a_scene_inspect_already_checked_is_not_frame_scanned(self):
        fake = Fake(probe=SMALL, raw=frame(bottom=True))
        self.run_render(fake, [make_env(self.dir, 'gx')])
        self.assertFalse(any('rawvideo' in call for call in fake.calls))


class SlidesEnvironment(Base):
    def setUp(self):
        super().setUp()
        self.new = make_env(self.dir, 'ce22', ('manim', 'manim-slides'))
        self.old = make_env(self.dir, 'ce19', ('manim', 'manim-slides'))
        self.fake = Fake(versions={str(self.new / 'Scripts' / 'manim.exe'): 'Manim Community v0.22.0', str(self.old / 'Scripts' / 'manim.exe'): 'Manim Community v0.19.0'})

    def test_the_environment_with_the_known_bad_pairing_is_skipped_whichever_order(self):
        slides = dict(SPEC, slides=True)
        with mock.patch.object(an, 'run_command', self.fake):
            for envs in ([self.new, self.old], [self.old, self.new]):
                self.assertEqual(Path(an.choose(slides, [str(e) for e in envs])['env']).name, 'ce19')
            self.assertEqual(Path(an.choose(dict(SPEC, backend='manim'), [str(self.new)])['env']).name, 'ce22', 'a plain animation may still use it')

    def test_only_the_bad_pairing_means_no_slides_and_the_reason_is_returned(self):
        result = self.run_render(self.fake, [self.new], dict(SPEC, slides=True))
        self.assertFalse(result['rendered'])
        self.assertTrue(any('write_to_movie' in n for n in result['notes']))
        self.assertFalse((self.vault / 'Visuals').exists())

    def test_the_working_environment_renders_the_deck(self):
        result = self.run_render(self.fake, [self.new, self.old], dict(SPEC, slides=True))
        self.assertEqual((result['version'], result['slides']), ('0.19.0', 'vis-complete-square.slides.html'))


class CommandLine(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        (self.dir / 'scene.py').write_text(SCENE, encoding='utf-8')
        (self.dir / 'spec.json').write_text(json.dumps(SPEC), encoding='utf-8')
        self.script = str(ROOT / 'scripts/animate.py')
        self.env = dict(os.environ, PATH=str(self.dir), **{an.ENV_VARIABLE: ''})

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-S', '-B', self.script, *args], capture_output=True, text=True, encoding='utf-8', env=self.env)

    def test_validate_and_lint_exit_codes(self):
        self.assertEqual(self.run_cli('validate', str(self.dir / 'spec.json')).returncode, 0)
        (self.dir / 'bad.json').write_text(json.dumps(dict(SPEC, fps=0)), encoding='utf-8')
        self.assertEqual(self.run_cli('validate', str(self.dir / 'bad.json')).returncode, 1)
        self.assertEqual(self.run_cli('lint', str(self.dir / 'scene.py'), '--spec', str(self.dir / 'spec.json')).returncode, 0)
        (self.dir / 'evil.py').write_text(SCENE + '\nimport subprocess\n', encoding='utf-8')
        self.assertEqual(self.run_cli('lint', str(self.dir / 'evil.py')).returncode, 1)

    def test_capabilities_and_a_render_with_no_backend_exit_with_the_unrendered_code(self):
        found = json.loads(self.run_cli('capabilities').stdout)
        self.assertEqual(found['backends'], [])
        vault = self.dir / 'vault'
        vault.mkdir()
        done = self.run_cli('render', str(self.dir / 'spec.json'), '--root', str(vault))
        self.assertEqual(done.returncode, 3, done.stdout + done.stderr)
        self.assertFalse(json.loads(done.stdout)['rendered'])
        self.assertEqual(list(vault.iterdir()), [])
        self.assertEqual(self.run_cli('present', str(self.dir / 'spec.json')).returncode, 3)

    def test_errors_exit_two(self):
        self.assertEqual(self.run_cli('validate', str(self.dir / 'nothing.json')).returncode, 2)
        self.assertEqual(self.run_cli('render', str(self.dir / 'spec.json'), '--root', str(self.dir / 'vault'), '--directory', '../x').returncode, 2)


class Installed(unittest.TestCase):
    def test_the_tool_and_protocol_reach_the_visualization_skill(self):
        text = (ROOT / 'skills/science-visualize/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('references/ANIMATION_PROTOCOL.md', text)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with redirect_stdout(io.StringIO()):
                install.install_skills(tmp / 'claude', False)
            skill = tmp / 'claude' / 'science-visualize'
            self.assertEqual((skill / 'scripts/animate.py').read_bytes(), (ROOT / 'scripts/animate.py').read_bytes())
            self.assertTrue((skill / 'references/ANIMATION_PROTOCOL.md').exists())
            done = subprocess.run([sys.executable, '-S', '-B', str(skill / 'scripts/animate.py'), 'validate', str(ROOT / 'tests/fixtures/animation-spec.json')],
                                  capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_the_protocol_states_what_was_measured_and_what_was_not(self):
        text = (ROOT / 'references/ANIMATION_PROTOCOL.md').read_text(encoding='utf-8')
        for needle in ('Measured here', 'does not test the vendor', 'write_to_movie', 'not a sandbox', 'Not done', 'one-file'):
            self.assertIn(needle, text)


@unittest.skipUnless(os.environ.get('RESEARCH_OS_TEST_MANIMGX_ENV') and REAL_WHICH('ffmpeg'), 'set RESEARCH_OS_TEST_MANIMGX_ENV to a ManimGX virtual environment to render for real')
class RealManimGX(Base):
    def test_a_real_scene_renders_and_registers(self):
        which = mock.patch.object(an.shutil, 'which', REAL_WHICH)
        which.start()
        self.addCleanup(which.stop)
        result = an.render(self.spec_file, self.vault, envs=[os.environ['RESEARCH_OS_TEST_MANIMGX_ENV']])
        self.assertTrue(result['rendered'], result)
        video = self.vault / result['artifact']
        self.assertGreater(video.stat().st_size, 1000)
        self.assertEqual(visuals.discover(self.vault)[1], [])
        self.assertTrue(an.probe(video)['duration'] > 0)


if __name__ == '__main__':
    unittest.main()
