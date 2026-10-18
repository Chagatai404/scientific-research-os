"""The handout builder: lint, template in step with the style, a full build into a temporary vault (real xelatex when present), library safety, versions, plan status."""
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import handout as ho
import html_sessions as hs
import session_plan as sp

EXAMPLE = (ROOT / 'examples' / 'handout' / 'variance-and-rescaling.tex').read_text(encoding='utf-8')
PLAN = json.loads((ROOT / 'examples' / 'session-plan-variance.json').read_text(encoding='utf-8'))
SESSION = '01 Projects/Stats/Sessions/variance.md'
STY = (ROOT / 'assets' / 'handout' / 'roshandout.sty').read_text(encoding='utf-8')


def fake_compiler(log='Output written on main.pdf (3 pages, 20000 bytes).'):
    def compile_(folder, main='main.tex', timeout=0, allow_install=False):
        pdf = Path(folder) / 'main.pdf'
        pdf.write_bytes(b'%PDF-1.5\n' + b'x' * 2000)
        return {'ok': True, 'pdf': pdf, 'log': log, 'tool': 'fake', 'timed_out': False, 'seconds': 0.1, 'output': ''}
    return compile_


def make_vault(root, with_plan=True):
    root = Path(root)
    (root / '01 Projects/Stats/Sessions').mkdir(parents=True)
    (root / '01 Projects/Stats/Stats.md').write_text('---\ntype: project\n---\n# Stats\n', encoding='utf-8')
    hs.install_runtime(root)
    hs.create_session(root, SESSION, '# Variance\n\nBody.\n', title='Variance')
    if with_plan:
        hs.update_session(root, SESSION, plan=PLAN)


class Lint(unittest.TestCase):
    def test_the_example_passes(self):
        report = ho.lint(EXAMPLE, PLAN['handout']['sections'])
        self.assertEqual(report['errors'], [])
        self.assertGreaterEqual(report['stats']['examples'], 3)

    def errors(self, body, **kw):
        return '\n'.join(ho.lint(body, **kw)['errors'])

    def test_forbidden_commands_are_named_with_their_line(self):
        for bad in (r'\input{/etc/passwd}', r'\write18{ls}', r'\usepackage{x}', r'\immediate\openout3=a', r'\catcode`\%=12', r'\csname x\endcsname', r'\def\x{^^5cinput}'):
            self.assertIn('line 1', self.errors(bad + '\n' + EXAMPLE), bad)

    def test_a_comment_hides_nothing_dangerous_but_is_not_flagged(self):
        self.assertEqual(ho.lint('% \\input{x}\n' + EXAMPLE)['errors'], [])

    def test_the_document_environment_and_paths_are_refused(self):
        self.assertIn('document', self.errors('\\begin{document}\n' + EXAMPLE))
        self.assertIn('absolute drive path', self.errors('C:/Users/x\n' + EXAMPLE))
        self.assertIn("'..'", self.errors('see ../secret\n' + EXAMPLE))

    def test_unfinished_work_is_refused(self):
        self.assertIn('unfinished', self.errors('TODO fix this\n' + EXAMPLE))
        self.assertIn('unfilled slot', self.errors('Explain [Name the concept] here.\n' + EXAMPLE))

    def test_mathematics_with_brackets_is_not_a_slot(self):
        self.assertNotIn('unfilled slot', self.errors('We have $E[X^2]$ and $[a, b)$ and \\[ E[X Y] \\].\n' + EXAMPLE))

    def test_structure_is_required(self):
        self.assertIn('words', self.errors('\\section{A}\nShort.\n\\begin{sources}\\bibitem{a} A.\\end{sources}'))
        self.assertIn('no sources', self.errors(re.sub(r'\\begin\{sources\}.*?\\end\{sources\}', '', EXAMPLE, flags=re.S)))
        self.assertIn('no \\section', self.errors('plain text only ' * 100))

    def test_exercises_need_solutions_cites_need_sources_refs_need_labels(self):
        self.assertIn('printsolutions', self.errors(EXAMPLE.replace('\\printsolutions', '')))
        self.assertIn('no \\bibitem', self.errors(EXAMPLE + '\n\\cite{nobody}'))
        self.assertIn('never defined', self.errors(EXAMPLE + '\n\\ref{nowhere}'))
        self.assertIn('empty solution', self.errors(EXAMPLE + '\n\\exercise{Why?}{}'))

    def test_the_plan_sections_must_be_present(self):
        self.assertIn('missing section', self.errors(EXAMPLE, plan_sections=['Quantum gravity']))

    def test_figures_are_checked(self):
        body = EXAMPLE + '\n\\includegraphics{figures/nothing.pdf}'
        self.assertIn('figure', self.errors(body, check_figures=True))
        self.assertIn('relative file name', self.errors(EXAMPLE + '\n\\includegraphics{/etc/x.png}', check_figures=True))


class LogAnalysis(unittest.TestCase):
    def test_a_clean_log(self):
        self.assertEqual(ho.analyze_log('Output written on main.pdf (7 pages, 90000 bytes).'), {'problems': [], 'pages': 7})

    def test_each_kind_of_problem(self):
        log = ('! Undefined control sequence.\nl.12 \\foo\n'
               "LaTeX Warning: Reference `x' on page 2 undefined on input line 4.\n"
               'Overfull \\hbox (40.0pt too wide) in paragraph\n'
               'Overfull \\hbox (2.0pt too wide) in paragraph\n'
               'Missing character: There is no ğ in font lmroman10\n')
        problems = '\n'.join(ho.analyze_log(log)['problems'])
        for needle in ('compile error', "undefined reference 'x'", 'Overfull \\hbox 40.0pt', 'missing glyph'):
            self.assertIn(needle, problems)
        self.assertNotIn('2.0pt', problems)


class Template(unittest.TestCase):
    def test_every_environment_and_macro_is_defined_by_the_style(self):
        for name in ho.ENVIRONMENTS:
            if name in ('proof', 'figure'):
                continue
            self.assertRegex(STY, r'(newtcolorbox|newenvironment|newtheorem\*?|NewDocumentEnvironment|newtcbtheorem)(\[[^\]]*\])?\{' + name + r'\}|\{' + name + r'\}', name)
        for macro in (r'\exercise', r'\printsolutions', r'\margin', r'\sourcenote', r'\Var', r'\Cov', r'\E', r'\Pr', r'\iid'):
            self.assertIn(macro.lstrip('\\'), STY, macro)

    def test_the_template_command_runs(self):
        out = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'handout.py'), 'template'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(out.returncode, 0)
        self.assertIn('workedexample', out.stdout)

    def test_metadata_is_escaped(self):
        text = ho.assemble('\\section{A}', {'title': 'Cost & $ 50% {x}', 'subtitle': '', 'course': '', 'date': '', 'line': ''})
        self.assertIn(r'Cost \& \$ 50\% \{x\}', text)


class Build(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'vault'
        make_vault(self.root)
        self.body = Path(self.temp.name) / 'body.tex'
        self.body.write_text(EXAMPLE, encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def build(self, **kw):
        kw.setdefault('compiler', fake_compiler())
        return ho.build(self.root, SESSION, self.body, library='01 Projects/Stats', **kw)

    def test_a_build_saves_files_note_and_status(self):
        result = self.build()
        directory = self.root / result['directory']
        for name in ('.tex', '.pdf', '.md'):
            self.assertTrue((self.root / result['pdf']).with_suffix(name).is_file(), name)
        self.assertTrue((directory / 'roshandout.sty').is_file())
        note = (self.root / result['note']).read_text(encoding='utf-8')
        self.assertIn('type: handout', note)
        self.assertIn('[[01 Projects/Stats/Sessions/variance]]', note)
        self.assertEqual(ho.locate(self.root, SESSION)['status'], 'built')
        self.assertEqual(hs.load_session(self.root, SESSION)['plan']['handout']['status'], 'built')
        self.assertEqual(sp.validate(hs.load_session(self.root, SESSION)['plan']), [])

    def test_the_directory_is_the_plans(self):
        result = self.build()
        self.assertTrue(result['directory'].endswith(PLAN['handout']['directory']))

    def test_a_rebuild_replaces_its_own_unchanged_files_and_never_an_edited_one(self):
        first = self.build()
        again = self.build(stage='built')
        self.assertEqual(first['pdf'], again['pdf'])
        self.assertTrue(again['replaced_unchanged_earlier_build'])
        (self.root / first['tex']).write_text('edited by the learner', encoding='utf-8')
        third = self.build()
        self.assertTrue(third['pdf'].endswith('-v2.pdf'))
        self.assertEqual((self.root / first['tex']).read_text(encoding='utf-8'), 'edited by the learner')
        with self.assertRaises(ho.HandoutError):
            self.build(on_conflict='refuse')

    def test_status_never_moves_back(self):
        self.build(stage='built')
        with self.assertRaises(ho.HandoutError):
            self.build(stage='draft')

    def test_a_draft_then_built(self):
        self.build(stage='draft')
        self.assertEqual(hs.load_session(self.root, SESSION)['plan']['handout']['status'], 'draft')
        self.build(stage='built')
        self.assertEqual(hs.load_session(self.root, SESSION)['plan']['handout']['status'], 'built')

    def test_nothing_is_saved_when_a_check_fails(self):
        for log, needle in (('! Emergency stop.\nl.1 x', 'compile error'), ("Reference `a' on page 1 undefined\nOutput written on main.pdf (1 page, 9 bytes).", 'undefined')):
            with self.assertRaises(ho.HandoutError) as caught:
                self.build(compiler=fake_compiler(log))
            self.assertIn(needle, '\n'.join(caught.exception.problems))
        self.assertFalse((self.root / '01 Projects/Stats/Tutor Handouts').exists())
        self.assertEqual(hs.load_session(self.root, SESSION)['plan']['handout']['status'], 'planned')

    def test_a_dangerous_body_is_refused_before_compiling(self):
        self.body.write_text(EXAMPLE + '\n\\input{/etc/passwd}\n', encoding='utf-8')
        called = []
        with self.assertRaises(ho.HandoutError):
            self.build(compiler=lambda *a, **k: called.append(1))
        self.assertEqual(called, [])

    def test_unsafe_directories_and_libraries_are_refused(self):
        for directory in ('../../outside', '/abs', 'a/../../b', '.hidden/x'):
            plan = json.loads(json.dumps(PLAN))
            plan['handout']['directory'] = directory
            if sp.validate(plan):
                continue
            hs.update_session(self.root, SESSION, plan=plan)
            with self.assertRaises(ho.HandoutError):
                self.build()
        with self.assertRaises(ho.HandoutError):
            ho.build(self.root, SESSION, self.body, library='../elsewhere', compiler=fake_compiler())

    def test_a_session_outside_a_project_needs_a_library(self):
        with self.assertRaises(ho.HandoutError):
            ho.library_of(self.root, 'Sessions/x.md', None)
        with self.assertRaises(ho.HandoutError):
            ho.library_of(self.root, SESSION, '01 Projects/Missing')

    def test_a_course_library_uses_the_course_directory(self):
        (self.root / '01 Projects/Stats/Stats.md').write_text('---\ntype: course\n---\n# Stats\n', encoding='utf-8')
        lib = ho.library_of(self.root, SESSION, None)
        self.assertEqual(lib['kind'], 'course')
        self.assertEqual(ho.default_directory('course', 'Variance', '2026-10-18'), 'Tutor Handouts/2026-10-18 Variance')
        self.assertEqual(ho.default_directory('project', 'Variance', '2026-10-18'), 'Library/Variance')

    def test_cli_check_and_missing_body(self):
        out = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'handout.py'), 'check', str(ROOT / 'examples/handout/variance-and-rescaling.tex'), '--plan', str(ROOT / 'examples/session-plan-variance.json')],
                             capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(json.loads(out.stdout)['ok'])


@unittest.skipUnless(ho.have_latex(), 'xelatex is not installed')
class RealCompile(unittest.TestCase):
    def test_the_example_builds_a_pdf_without_problems_and_with_turkish_letters(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'vault'
            make_vault(root)
            body = Path(temp) / 'body.tex'
            body.write_text(EXAMPLE.replace('\\section{What variance measures}', '\\section{What variance measures}\nTürkçe: çğıöşü ÇĞİÖŞÜ.\n', 1), encoding='utf-8')
            result = ho.build(root, SESSION, body, library='01 Projects/Stats', timeout=240)
            pdf = (root / result['pdf']).read_bytes()
            self.assertTrue(pdf.startswith(b'%PDF'))
            self.assertGreaterEqual(result['pages'], 5)

    def test_shell_escape_is_off(self):
        with tempfile.TemporaryDirectory() as temp:
            scratch = Path(temp)
            ho.build_scratch('\\section{A}\n' + 'word ' * 400, {'title': 'T', 'subtitle': '', 'course': '', 'date': '', 'line': ''}, None, scratch)
            main = scratch / 'main.tex'
            main.write_text(main.read_text(encoding='utf-8').replace('\\makehandouttitle', '\\immediate\\write18{echo pwned > pwned.txt}'), encoding='utf-8')
            ho.compile_document(scratch, timeout=120)
            self.assertFalse((scratch / 'pwned.txt').exists())


if __name__ == '__main__':
    unittest.main()
