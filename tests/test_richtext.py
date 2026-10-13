"""Scientific inline and block rendering: the shared grammar, equations, safety and the golden session."""
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import random
import re
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs
import rich_text as rt

CORPUS = json.loads((ROOT / 'tests/fixtures/richtext-cases.json').read_text(encoding='utf-8'))['cases']
GOLDEN = (ROOT / 'tests/fixtures/html/scientific-v09.md').read_text(encoding='utf-8')
ALLOWED_TAGS = {'span', 'a', 'code', 'em', 'strong', 'del', 'mark', 'sub', 'sup', 'br'}
B = chr(92)
N = chr(10)

# Hand-written, not generated: the CommonMark rules and the scientific cases that motivated Slice 3.
SPEC = {
    '*foo bar*': '<em>foo bar</em>',
    'a * foo bar*': 'a * foo bar*',
    'foo*bar*': 'foo<em>bar</em>',
    '_foo_bar': '_foo_bar',
    '**foo bar**': '<strong>foo bar</strong>',
    '__foo, __bar__, baz__': '<strong>foo, <strong>bar</strong>, baz</strong>',
    '*foo**bar**baz*': '<em>foo<strong>bar</strong>baz</em>',
    '***foo** bar*': '<em><strong>foo</strong> bar</em>',
    '*foo **bar***': '<em>foo <strong>bar</strong></em>',
    'foo***bar***baz': 'foo<em><strong>bar</strong></em>baz',
    '*foo**bar***': '<em>foo<strong>bar</strong></em>',
    '**bold *italic***': '<strong>bold <em>italic</em></strong>',
    '*(*foo*)*': '<em>(<em>foo</em>)</em>',
    '2 * 3 * 4': '2 * 3 * 4',
    '5*3*2': '5<em>3</em>2',
    'snake_case_name': 'snake_case_name',
    '`a*b*c` and *d*': '<code>a*b*c</code> and <em>d</em>',
    B + '*not em' + B + '*': '*not em*',
    'costs $5 and $6 total': 'costs $5 and $6 total',
    'price ' + B + '$5': 'price $5',
    'H<sub>2</sub>O': 'H<sub>2</sub>O',
    '~~gone~~': '<del>gone</del>',
    'a<b': 'a&lt;b',
    '**bold': '**bold',
}


class Conformance(unittest.TestCase):
    def test_every_corpus_case_renders_to_its_recorded_html(self):
        self.assertGreaterEqual(len(CORPUS), 55)
        for case in CORPUS:
            with self.subTest(case=case['id']):
                self.assertEqual(rt.render_inline(case['input'], case['labels']), case['html'])

    def test_hand_written_commonmark_and_scientific_expectations(self):
        for text, expected in SPEC.items():
            with self.subTest(text=text):
                self.assertEqual(rt.render_inline(text), expected)

    def test_math_survives_every_delimiter_and_is_never_emphasis(self):
        for text, tex in (('$x_i^2$', 'x_i^2'), (B + '(E_i' + B + ')', 'E_i'), ('$$a*b$$', 'a*b'), (B + '[a_b' + B + ']', 'a_b'),
                          ('$a * b * c$', 'a * b * c'), ('$_x_$', '_x_')):
            with self.subTest(text=text):
                nodes = rt.parse_inline(text)
                self.assertEqual([n['t'] for n in nodes], ['math'], nodes)
                self.assertEqual(nodes[0]['v'], tex)
                self.assertEqual(nodes[0]['src'], text)

    def test_unsupported_syntax_stays_visible_with_a_diagnostic(self):
        out = rt.render_inline('open ' + B + '(never closed *and* more')
        self.assertIn('data-code="unclosed-math"', out)
        self.assertIn(html.escape(B + '('), out)
        self.assertIn('<em>and</em>', out)
        self.assertEqual(rt.diagnostics(rt.parse_inline('x ' + B + '(')), [{'code': 'unclosed-math', 'text': B + '('}])
        self.assertIn('data-code="unresolved-reference"', rt.render_inline(B + 'eqref{nowhere}'))


class BlockLevel(unittest.TestCase):
    def render(self, source, **kwargs):
        return hs.markdown_html(source, **kwargs)

    def test_all_display_forms_produce_display_equations_with_the_source_intact(self):
        source = ('$$' + N + 'x_i^2' + N + '$$' + N * 2 + B + '[' + N + 'y' + B + B + 'z' + N + B + ']' + N * 2
                  + B + 'begin{aligned}a&=b' + B + B + 'c&=d' + B + 'end{aligned}' + N * 2 + '$$u+v$$')
        rendered = self.render(source)
        tex = [html.unescape(t) for _, t in re.findall(r'<div class="ros-formula ros-math"([^>]*?)data-tex="([^"]*)"', rendered)]
        self.assertEqual(tex, ['x_i^2', 'y' + B + B + 'z', B + 'begin{aligned}a&=b' + B + B + 'c&=d' + B + 'end{aligned}', 'u+v'])
        self.assertEqual(rendered.count('data-display="true"'), 4)

    def test_labelled_equations_are_numbered_in_document_order_and_forward_references_resolve(self):
        source = ('See ' + B + 'eqref{b} and [@eq:a] before either.' + N * 2 + '$$' + N + 'a=1' + N + '$$ {#eq:a}' + N * 2
                  + B + 'begin{align}x&=1' + B + 'label{b}' + B + B + 'y&=2' + B + 'end{align}' + N * 2
                  + 'Later: ' + B + 'eqref{a}, ' + B + 'eqref{missing}.')
        rendered = self.render(source)
        text = html.unescape(rendered)
        self.assertIn('id="eq-a" data-eq-label="a" data-eq-number="1"', rendered)
        self.assertIn('id="eq-b" data-eq-label="b" data-eq-number="2"', rendered)
        self.assertIn('a=1 ' + B + 'tag{1}', text)
        self.assertIn(B + 'tag{2}', text)
        self.assertNotIn('label{b}', html.unescape(re.search(r'data-eq-number="2"[^>]*data-tex="([^"]*)"', rendered)[1]))
        self.assertIn('<a class="ros-eqref" href="#eq-b" data-ros-ref="b">(2)</a>', rendered)
        self.assertEqual(rendered.count('data-ros-ref="a"'), 2)
        self.assertIn('data-code="unresolved-reference"', rendered)

    def test_a_duplicate_label_is_not_numbered_twice(self):
        rendered = self.render('$$a$$ {#eq:same}' + N * 2 + '$$b$$ {#eq:same}')
        self.assertEqual(rendered.count('id="eq-same"'), 1)
        self.assertEqual(rendered.count('data-eq-number='), 1)

    def test_a_malformed_display_never_swallows_the_document(self):
        rendered = self.render('$$ x and trailing prose' + N * 2 + 'The rest stays here.' + N * 2 + '## Heading')
        self.assertIn('<p>The rest stays here.</p>', rendered)
        self.assertIn('Heading</h2>', rendered)
        self.assertNotIn('legacy', rendered)

    def test_pipes_inside_math_do_not_split_table_cells(self):
        rendered = self.render('| Quantity | Value |' + N + '| --- | --- |' + N + '| $|x|$ and $a$ | 2 |')
        self.assertEqual(rendered.count('<td'), 2)
        self.assertIn('data-tex="|x|"', rendered)

    def test_emphasis_links_and_math_span_soft_line_breaks_within_a_paragraph(self):
        self.assertEqual(self.render('*a' + N + 'b*'), '<p><em>a b</em></p>')
        self.assertIn('data-tex="a' + N + 'b"', self.render('x $a' + N + 'b$ y'))
        self.assertEqual(self.render('one  ' + N + 'two'), '<p>one<br>two</p>')
        self.assertEqual(self.render('one' + B + N + 'two'), '<p>one<br>two</p>')

    def test_headings_callouts_lists_and_quotes_use_the_same_grammar(self):
        rendered = self.render('## The **depth** $t_0$' + N * 2 + '> [!note] About ' + B + '(E' + B + ')' + N + '> Body with *em*.' + N * 2
                               + '- item $a_1$' + N + '  - nested **strong**' + N * 2 + '> quoted ~~old~~')
        for fragment in ('<strong>depth</strong>', 'data-tex="t_0"', 'data-tex="E"', '<em>em</em>', 'data-tex="a_1"', '<strong>strong</strong>', '<del>old</del>'):
            self.assertIn(fragment, rendered)

    def test_static_question_surfaces_all_render_scientific_markup(self):
        rendered = hs._question_html({'id': 'q', 'kind': 'mcq', 'prompt': 'Value of **$x$**?', 'options': ['$x^2$', {'value': 'b', 'label': '*b*'}],
                                      'hints': ['Use *units*'], 'solution': 'See ' + B + '(E=mc^2' + B + ')'})
        for fragment in ('<strong><span data-ros="equation"', 'data-tex="x^2"', '<em>b</em>', '<em>units</em>', 'data-tex="E=mc^2"'):
            self.assertIn(fragment, rendered)


class GoldenSession(unittest.TestCase):
    def test_the_advanced_physics_session_renders_every_construct_in_place(self):
        rendered = hs.markdown_html(GOLDEN, page_title='Scientific rendering regression',
                                    questions={'normalization': {'id': 'normalization', 'kind': 'free-response', 'prompt': 'Why is $b$ an inverse scale?'}},
                                    placed=set())
        text = html.unescape(rendered)
        self.assertIn('<strong>A bold statement with <em>nested emphasis</em></strong>', rendered)
        self.assertIn('data-tex="x_i^2"', rendered)
        self.assertIn('data-tex="E_{' + B + 'mathrm{vis}}"', text)
        self.assertIn('<code>x_i ** 2</code>', rendered)
        self.assertIn(B + 'begin{aligned}', text)
        self.assertIn('f(t)&=' + B + 'frac{b(bt)^{a-1}e^{-bt}}{' + B + 'Gamma(a)},' + B + B, text)
        self.assertIn(B + 'begin{pmatrix}', text)
        self.assertEqual(rendered.count('data-display="true"'), 2)
        self.assertIn('data-ros="formula"', rendered)  # the callout
        self.assertIn('data-ros-target="Radiation length"', rendered)
        self.assertIn('<th scope="col"', rendered)
        self.assertEqual(len(re.findall(r'<td class="ros-align-left">.*?</td>', rendered)), 4)
        self.assertIn('data-resource-id="profile"', rendered)
        self.assertLess(rendered.index('Normalized shower profile'), rendered.index('data-question-id="normalization"'))
        self.assertLess(rendered.index('data-question-id="normalization"'), rendered.index('Return checkpoint'))
        # Unsupported TeX is not repaired, dropped or rewritten: the macro survives verbatim in both the source attribute and the text.
        self.assertIn('data-tex="' + B + 'unknownmacro{x}"', text)
        self.assertRegex(text, r'>\$' + re.escape(B) + r'unknownmacro\{x\}\$<')

    def test_rendering_never_mutates_the_authored_source_and_is_deterministic(self):
        before = GOLDEN[:]
        first, second = hs.markdown_html(GOLDEN), hs.markdown_html(GOLDEN)
        self.assertEqual(GOLDEN, before)
        self.assertEqual(first, second)


class Robustness(unittest.TestCase):
    ALPHABET = ['*', '_', '$', B, '`', '[', ']', '(', ')', '<', '>', '~', '=', '|', 'a', 'b', ' ', N, '{', '}', '^', '#', '!', 'sub', '/',
                'α', '1', '$$', '**', '"', "'", '@', 'eqref', 'sup', ':']

    def test_arbitrary_text_never_raises_and_only_ever_emits_whitelisted_markup(self):
        rng = random.Random(20261013)
        for _ in range(4000):
            text = ''.join(rng.choice(self.ALPHABET) for _ in range(rng.randint(0, 48)))
            out = rt.render_inline(text, {'a': 1})
            self.assertLessEqual(set(re.findall(r'</?([a-z0-9]+)', out)), ALLOWED_TAGS, text)
            self.assertNotIn('<script', out.lower())
            rt.plain_text(rt.parse_inline(text))

    def test_hostile_input_cannot_inject_attributes_or_scripts(self):
        hostile = ['[x](#a" onclick="alert(1))', '[[a" onmouseover="x]]', '<img src=x onerror=alert(1)>', '<sub onclick=alert(1)>x</sub>',
                   '[x](javascript:alert(1))', '$" onfocus="a$', B + 'eqref{a" x="y}', '[link](https://x.org/"><script>alert(1)</script>)']
        for text in hostile:
            out = rt.render_inline(text)
            with self.subTest(text=text):
                tags, names, hrefs = [], set(), []

                class Collect(HTMLParser):
                    def handle_starttag(self, tag, attrs):
                        tags.append(tag)
                        names.update(name for name, _ in attrs)
                        hrefs.extend(value for name, value in attrs if name == 'href')
                Collect().feed(out)
                self.assertLessEqual(set(tags), ALLOWED_TAGS)
                self.assertFalse([n for n in names if n.startswith('on') or n in {'src', 'style', 'srcdoc'}], names)
                self.assertTrue(all(h.startswith('#') for h in hrefs), hrefs)

    def test_pathological_inputs_finish_quickly(self):
        cases = ['*a ' * 4000, '*' * 5000, '_' * 5000, '[' * 3000, '[[' * 2000, '$' * 5000, '$a ' * 3000, B + '(' * 3000, '`' * 4000,
                 '<sub>' * 600, '*a [b ' * 1500, '**' + '*' * 3000 + 'x' + '*' * 3000, '~~a ' * 2000, 'a  ' + N + 'b' + N * 5]
        for text in cases:
            # CPU time, not wall-clock: a slow or busy machine must not fail this, a quadratic blow-up still must.
            started = time.process_time()
            rt.render_inline(text)
            self.assertLess(time.process_time() - started, 6.0, text[:30])

    def test_note_target_syntax_matches_the_shared_fixture(self):
        fixture = json.loads((ROOT / 'tests/fixtures/note-targets.json').read_text(encoding='utf-8'))
        for target in fixture['valid']:
            self.assertTrue(rt.valid_note_target(target), repr(target))
            self.assertIn('<a class="ros-note-link"', rt.render_inline('[[' + target + ']]'))
        for target in fixture['invalid']:
            self.assertFalse(rt.valid_note_target(target), repr(target))
        self.assertFalse(rt.valid_note_target(None))
        self.assertFalse(rt.valid_note_target(7))

    def test_unnavigable_wikilinks_stay_visible_but_inert(self):
        for text in ('[[https://example.org/x|site]]', '[[../secret]]', '[[.obsidian/app]]', '[[C:/x]]'):
            out = rt.render_inline(text)
            self.assertIn('ros-note-link-invalid', out, text)
            self.assertNotIn('<a ', out, text)

    def test_recursion_is_bounded(self):
        rt.render_inline('<sub>' * 200 + 'x' + '</sub>' * 200)
        rt.render_inline('[' * 100 + 'x' + '](#a)' * 100)
        rt.render_inline('~~' + '~~a' * 100)


if __name__ == '__main__':
    unittest.main()
