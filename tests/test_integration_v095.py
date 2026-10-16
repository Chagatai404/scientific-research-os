"""v0.9.5 end to end: one chemistry lesson and one biology lesson, each through checks, a diagram, a spoken script, a recording, a card, a lint and the page.

Only the speech engine is faked. Everything else is the real tool, so a break between two v0.9.5 pieces shows up here and not in a unit test.
"""
import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import diagram_spec as ds
import html_sessions as hs
import scientific_verify as sv
import teaching_lint as tl
import visual_assets as va
import visuals
import voice as vc
from test_diagrams import WATER, pdb_text
from test_tutor_gate import Base
from test_voice import FakeAdapter, make_env

CHEMISTRY = '''# Burning methane

## Balancing the equation

Methane burns in oxygen to give carbon dioxide and water. Every atom on the left must appear on the right.

## The water molecule

Water has two hydrogen atoms bonded to one oxygen atom.
'''
BIOLOGY = '''# From gene to protein

## Reading the code

A gene is read three bases at a time. Each triplet names one amino acid.

## A folded backbone

The chain folds into a shape that the file records atom by atom.
'''


def check(kind, **fields):
    return dict({'kind': kind}, **fields)


def verify(*checks, consequence='routine'):
    return sv.run({'verification_schema': 1, 'verification_id': 'V-INT', 'claim': {'id': 'C', 'statement': 'lesson claim', 'consequence': consequence},
                   'checks': [dict(c, id=f'k{i}') for i, c in enumerate(checks)]})


def page_state(html):
    return json.loads(re.search(r'<script type="application/json" id="ros-session-data">(.*?)</script>', html, re.S)[1].replace('\\u003c', '<').replace('\\u0026', '&'))


class Lesson(Base):
    """Shared steps: speak a script with the fake engine, then declare a card that carries the recording."""

    def setUp(self):
        super().setUp()
        self.env = make_env(self.root, 'engine-env')
        self.voices = {'en': str(self.root / 'en.onnx'), 'tr': str(self.root / 'tr.onnx')}

    def record(self, script, lang):
        with mock.patch.object(vc, 'run_command', FakeAdapter()):
            return vc.speak(self.root, script, lang, 'piper', [str(self.env)], self.voices)

    def assertNothingVerifiedBySideEffect(self):
        records, diagnostics = visuals.discover(self.root)
        self.assertEqual(diagnostics, [])
        self.assertTrue(records)
        self.assertEqual({r['verification_status'] for r in records.values()}, {'rendered'}, 'rendering and registering never promote a visual')


class ChemistryLesson(Lesson):
    def test_a_chemistry_lesson_from_checked_claims_to_a_page_with_a_recording(self):
        # 1. The claims the lesson relies on are checked by executed methods, and a wrong one is caught.
        good = verify(check('formula-balance', equation='CH4 + 2 O2 -> CO2 + 2 H2O'), check('molar-mass', formula='H2O', expected=18.015),
                      check('stoichiometry', equation='2 H2 + O2 -> 2 H2O', amounts={'H2': {'g': 4.0}, 'O2': {'g': 40.0}}, expected={'limiting': 'H2'}))
        self.assertEqual(good['outcome'], 'verified-in-scope', good.get('findings'))
        self.assertEqual(verify(check('formula-balance', equation='CH4 + O2 -> CO2 + H2O'))['outcome'], 'invalidated')

        # 2. The water molecule is drawn from numbers that are themselves checked, then registered at rendered.
        registered = ds.register(self.root, WATER, concepts=['water-molecule'])
        self.assertFalse(registered['reused'])
        self.assertEqual(sv.run(ds.verification_spec(WATER))['outcome'], 'verified-in-scope')
        self.assertEqual(sv.run(ds.verification_spec(dict(WATER, expected_formula='H2O2')))['outcome'], 'invalidated')

        # 3. The script is written to be heard: a formula span and a language span, said by the rules and recorded.
        script = {'en': 'Water weighs {{math: M = 2 \\times 1.008 + 15.999}} grams per mole, a number we call the {{tr: mol kütlesi}}.',
                  'tr': 'Suyun mol kütlesi {{math: M = 2 \\times 1.008 + 15.999}} gram bölü mol olur.'}
        for lang, text in script.items():
            self.assertEqual(vc.speech_text.prepare(text, lang)['problems'], [], lang)
        english = self.record(script['en'], 'en')
        self.assertTrue((self.root / english['audio']).is_file())
        self.assertEqual(self.record(script['en'], 'en')['reused'], True)

        # 4. The lesson, its card, the diagram and the recording.
        name = self.make(CHEMISTRY, name='Sessions/chem.md')
        va.attach_visual(self.root, name, 'VIS-water')
        va.place_visual(self.root, name, figure='VIS-water', after_heading='The water molecule', alt='Water: one oxygen bonded to two hydrogens', caption='Water, drawn to scale from its coordinates')
        block = {'id': 'balance', 'heading': 'Balancing the equation', 'kind': 'concept', 'target': 'chemical-equation',
                 'introduces': {'stoichiometry': 'The counting of atoms and moles in a reaction.'},
                 'card': {'core_idea': 'A balanced equation keeps every kind of atom the same on both sides.', 'predict': 'How many oxygen molecules does one methane need?',
                          'retrieve': 'Why must the atoms balance?', 'no_visual_reason': 'The equation is the picture.',
                          'spoken': script, 'audio': {'en': english['audio']}}}
        self.declare(name, block)
        state = self.state(name)

        # 5. The mechanical lint finds nothing in the spoken scripts, and the page carries every piece.
        found = tl.lint_blocks(state)
        self.assertEqual([f['code'] for f in found['issues'] if f['code'].startswith(('SPOKEN', 'CARD'))], [], found['issues'])
        page = hs.render_html(state)
        for needle in ('ros-callout-concept', 'ros-callout-predict', 'ros-callout-glossary', 'ros-callout-listen', 'data-resource-id="VIS-water"'):
            self.assertIn(needle, page, needle)
        self.assertIn("media-src 'self'", page)
        self.assertNotIn('frame-src', page)
        self.assertEqual(page_state(page)['audio_urls']['balance']['en'], english['audio'])

        # 6. A standalone copy embeds the recording and still carries the figure.
        out = self.root / 'chem-export.html'
        hs.export_session(self.root, name, out)
        exported = out.read_text(encoding='utf-8')
        self.assertTrue(page_state(exported)['audio_urls']['balance']['en'].startswith('data:audio/wav;base64,'))
        self.assertIn('media-src data:', exported)
        self.assertNothingVerifiedBySideEffect()


class BiologyLesson(Lesson):
    def test_a_biology_lesson_from_a_structure_file_to_a_page_with_a_code_switched_recording(self):
        # 1. Sequence claims are recomputed; a wrong translation is caught.
        dna = 'ATGGCCATTGTAATGGGCCGCTGA'
        right = verify(check('sequence-check', sequence=dna, alphabet='dna', expected_length=24, translation='MAIVMGR*'))
        self.assertEqual(right['outcome'], 'verified-in-scope', right.get('findings'))
        self.assertEqual(verify(check('sequence-check', sequence=dna, alphabet='dna', translation='MAIVMGA*'))['outcome'], 'invalidated')

        # 2. A structure file becomes a backbone trace bound to its hash, is checked against what the lesson says about it, and is registered.
        pdb = self.root / 'models' / 'tiny.pdb'
        pdb.parent.mkdir()
        pdb.write_text(pdb_text(), encoding='utf-8')
        spec = ds.spec_from_pdb(pdb, None, 'VIS-tiny-chain', 'A four-residue chain')
        self.assertEqual(sv.run(ds.verification_spec(spec))['outcome'], 'verified-in-scope')
        ds.register(self.root, spec, concepts=['protein-backbone'])
        pdb.write_text(pdb_text(code='9ZZZ'), encoding='utf-8')
        self.assertEqual(sv.run(ds.verification_spec(spec))['outcome'], 'invalidated', 'the file changed after the figure was drawn from it')

        # 3. A Turkish script with an English term in its own voice and a formula in words.
        script = {'tr': 'Her üç baz bir amino asidi adlandırır; buna {{en: codon}} denir. Zincirin uzunluğu {{math: n = 3 k}} olur.'}
        prepared = vc.speech_text.prepare(script['tr'], 'tr')
        self.assertEqual([s['lang'] for s in prepared['segments']], ['tr', 'en', 'tr'])
        recording = self.record(script['tr'], 'tr')
        self.assertEqual(recording['reused'], False)

        # 4. Lesson, card and page.
        name = self.make(BIOLOGY, name='Sessions/bio.md')
        va.attach_visual(self.root, name, 'VIS-tiny-chain')
        va.place_visual(self.root, name, figure='VIS-tiny-chain', after_heading='A folded backbone', alt='The C-alpha trace of a four-residue chain', caption='Backbone trace from the structure file')
        block = {'id': 'code', 'heading': 'Reading the code', 'kind': 'concept', 'target': 'genetic-code',
                 'introduces': {'codon': 'A group of three bases that names one amino acid.'},
                 'card': {'core_idea': 'Three bases name one amino acid.', 'predict': 'How many amino acids does a 24-base gene with a stop codon encode?',
                          'no_visual_reason': 'The words carry the idea.', 'spoken': script, 'audio': {'tr': recording['audio']}}}
        self.declare(name, block)
        state = self.state(name)
        self.assertEqual([f['code'] for f in tl.lint_blocks(state)['issues'] if f['code'].startswith(('SPOKEN', 'CARD'))], [])
        page = hs.render_html(state)
        self.assertIn('ros-callout-listen', page)
        self.assertEqual(page_state(page)['audio_urls']['code']['tr'], recording['audio'])
        # The recording registry holds only the voice file names and the segments, never a local path.
        record = json.loads(next((self.root / 'Narration').glob('*.narration.json')).read_text(encoding='utf-8'))
        self.assertEqual(sorted(record['voices']), ['en', 'tr'])
        self.assertNotIn(str(self.root), json.dumps(record))
        self.assertNothingVerifiedBySideEffect()


class WhatTheReleaseDoesNotDo(Lesson):
    def test_a_spoken_script_with_a_formula_the_rules_cannot_say_is_stopped_before_any_engine_runs(self):
        fake = FakeAdapter()
        with mock.patch.object(vc, 'run_command', fake), self.assertRaisesRegex(vc.VoiceError, 'cannot be spoken yet'):
            vc.speak(self.root, r'See {{math: \begin{pmatrix} a & b \\ c & d \end{pmatrix}}}.', 'en', 'piper', [str(self.env)], self.voices)
        self.assertEqual([c for c in fake.calls if len(c) > 2 and c[2] == 'synth'], [])

    def test_a_diagram_whose_numbers_are_wrong_never_reaches_a_verified_record(self):
        bent = dict(WATER, expected_formula='H2O2')
        self.assertEqual(sv.run(ds.verification_spec(bent))['outcome'], 'invalidated')
        ds.register(self.root, bent, concepts=['water-molecule'])
        records, _ = visuals.discover(self.root)
        self.assertEqual(records['VIS-water']['verification_status'], 'rendered', 'registering is not checking; the check above is what caught it')


if __name__ == '__main__':
    unittest.main()
