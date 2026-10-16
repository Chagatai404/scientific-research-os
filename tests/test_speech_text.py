"""Speech text: numbers, formulas in words (English and Turkish), spans, the lexicon, and what is refused rather than guessed."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import speech_text as st


class Numbers(unittest.TestCase):
    def test_english(self):
        for n, words in ((0, 'zero'), (7, 'seven'), (13, 'thirteen'), (21, 'twenty-one'), (100, 'one hundred'), (101, 'one hundred one'), (1000, 'one thousand'),
                         (2024, 'two thousand twenty-four'), (1000000, 'one million'), (-5, 'minus five'), (1234567, 'one million two hundred thirty-four thousand five hundred sixty-seven')):
            self.assertEqual(st.integer_words(n, 'en'), words, n)

    def test_turkish(self):
        for n, words in ((0, 'sıfır'), (7, 'yedi'), (10, 'on'), (21, 'yirmi bir'), (100, 'yüz'), (101, 'yüz bir'), (200, 'iki yüz'), (1000, 'bin'), (1001, 'bin bir'),
                         (2000, 'iki bin'), (2024, 'iki bin yirmi dört'), (1000000, 'bir milyon'), (-5, 'eksi beş'), (1500000, 'bir milyon beş yüz bin')):
            self.assertEqual(st.integer_words(n, 'tr'), words, n)

    def test_decimals_are_read_digit_by_digit_and_bad_input_is_refused(self):
        self.assertEqual(st.number_words('3.14', 'en'), 'three point one four')
        self.assertEqual(st.number_words('3.14', 'tr'), 'üç virgül bir dört')
        for bad in ('1e5', '-3', '', '1.2.3'):
            with self.assertRaises(st.Unspeakable):
                st.number_words(bad, 'en')
        with self.assertRaises(st.Unspeakable):
            st.integer_words(10 ** 15, 'en')
        with self.assertRaises(st.Unspeakable):
            st.integer_words(3, 'de')


ENGLISH = [
    (r'x^2 + y^2 = r^2', 'x squared plus y squared equals r squared'),
    (r'x^3', 'x cubed'), (r'x^n', 'x to the n'), (r'x^{-1}', 'x to the minus one'),
    (r'e^{-x^2}', 'e to the power of minus x squared, end of power'),
    (r'\frac{a}{b}', 'ay over b'), (r'\frac{1}{2}', 'one over two'),
    (r'\frac{x+1}{x-1}', 'the fraction with numerator x plus one and denominator x minus one, end fraction'),
    (r'x_1', 'x sub one'), (r'x_{ij}', 'x sub i j, end sub'),
    (r'\sqrt{x}', 'the square root of x'), (r'\sqrt{x+1}', 'the square root of x plus one, end root'), (r'\sqrt[3]{x}', 'the cube root of x'),
    (r'\sqrt[n]{x}', 'the n-th root of x'),
    (r'\sum_{n=1}^{\infty} \frac{1}{n^2}', 'the sum from n equals one to infinity of one over n squared'),
    (r'\int_0^1 f(x)\,dx', 'the integral from zero to one of f of x d x'),
    (r'\lim_{x \to 0} x', 'the limit as x tends to zero of x'),
    (r'\alpha + \beta', 'alpha plus beta'), (r'\Delta E', 'capital delta E'), (r'\vec{v}', 'vector v'), (r'\mathbf{F} = m\mathbf{a}', 'vector F equals m vector ay'),
    (r'|x|', 'the absolute value of x, end absolute value'), (r'\left| x \right|', 'the absolute value of x, end absolute value'),
    (r'f(x)', 'f of x'), (r'\sin^2 \theta + \cos^2 \theta = 1', 'sine squared of theta plus cosine squared of theta equals one'),
    (r'\text{speed} = \frac{d}{t}', 'speed equals d over t'), (r'\text{is equal to}', 'is equal to'), (r'n!', 'n factorial'), (r'3.14', 'three point one four'),
    (r'a \leq b', 'ay is less than or equal to b'), (r'E = mc^2', 'E equals m c squared'), (r'\hat{x}', 'x hat'), (r'(a+b)^2', 'open parenthesis ay plus b close parenthesis squared'),
    (r'\mathbb{R}', 'the real numbers'), (r'x \in \mathbb{R}', 'x is an element of the real numbers'), (r'\pm 1', 'plus or minus one'),
    (r'\frac{\partial f}{\partial x}', 'the fraction with numerator partial f and denominator partial x, end fraction'),
]
TURKISH = [
    (r'x^2 + y^2 = r^2', 'iks kare artı ye kare eşittir re kare'), (r'x^3', 'iks küp'), (r'x^n', 'iks üzeri ne'), (r'x^{-1}', 'iks üzeri eksi bir'),
    (r'e^{-x^2}', 'e üzeri eksi iks kare, üs sonu'), (r'\frac{a}{b}', 'a bölü be'),
    (r'\frac{x+1}{x-1}', 'payı iks artı bir, paydası iks eksi bir olan kesir, kesir sonu'), (r'x_1', 'iks indis bir'),
    (r'\sqrt{x}', 'karekök iks'), (r'\sqrt{x+1}', 'karekök iks artı bir, kök sonu'), (r'\sqrt[3]{x}', 'küpkök iks'),
    (r'\sum_{n=1}^{\infty} \frac{1}{n^2}', 'toplam, ne eşittir bir ile sonsuz arasında, bir bölü ne kare'),
    (r'\lim_{x \to 0} x', 'iks, sıfır değerine yaklaşırken, limit iks'),
    (r'\alpha + \beta', 'alfa artı beta'), (r'\Delta', 'büyük delta'), (r'|x|', 'iks sayısının mutlak değeri'), (r'f(x)', 'fe iks'),
    (r'\sin^2 \theta + \cos^2 \theta = 1', 'sinüs kare teta artı kosinüs kare teta eşittir bir'), (r'a \leq b', 'a küçük eşittir be'), (r'\mathbb{R}', 'gerçel sayılar'),
]


class Formulas(unittest.TestCase):
    def test_english_formulas(self):
        for tex, expect in ENGLISH:
            self.assertEqual(st.verbalize(tex, 'en'), expect, tex)

    def test_turkish_formulas(self):
        for tex, expect in TURKISH:
            self.assertEqual(st.verbalize(tex, 'tr'), expect, tex)

    def test_whitespace_in_the_source_does_not_change_the_words(self):
        self.assertEqual(st.verbalize('x ^ 2   +  y', 'en'), st.verbalize('x^2+y', 'en'))
        self.assertEqual(st.verbalize(r'\text{ a b }', 'en'), 'a b')

    def test_what_the_rules_cannot_say_is_refused_with_a_reason(self):
        cases = [(r'\begin{pmatrix} a & b \\ c & d \end{pmatrix}', 'environments'), (r'a & b', 'alignment'), (r'a \\ b', 'line breaks'), (r'\forall x', 'more than one reading'),
                 (r'f: A', 'is not spoken'), (r'a \to b', 'arrow outside a limit'), (r"x'", 'prime'), (r'|x', 'unpaired'), (r'\unknowncmd', 'not in the set'), (r'x^2^3', 'two superscripts'),
                 (r'x_1_2', 'two subscripts'), (r'', 'empty'), (r'\frac{a}', 'ends in the middle'), (r'\mathbb{X}', 'not a set'), (r'\lim x', 'needs to say'),
                 (r'\lim_{x} y', 'needs an arrow'), (r'\sin_1 x', 'subscript on a function'), (r'}', 'unexpected'),
                 (r'\left\{ x \right\}', 'not in the set'), ('{' * 12 + 'x' + '}' * 12, 'nested too deeply'), (r'?', 'not spoken')]
        for tex, reason in cases:
            with self.assertRaises(st.Unspeakable, msg=tex) as caught:
                st.verbalize(tex, 'en')
            self.assertIn(reason, str(caught.exception), tex)

    def test_an_unknown_language_is_refused_not_defaulted(self):
        with self.assertRaisesRegex(st.Unspeakable, 'no formula rules'):
            st.verbalize('x', 'de')


class Spans(unittest.TestCase):
    def test_braces_inside_a_span_are_balanced(self):
        pieces = st.scan(r'Rate is {{math: \frac{a}{b}}} per second')
        self.assertEqual(pieces, [('plain', 'Rate is '), ('math', r'\frac{a}{b}'), ('plain', ' per second')])
        self.assertEqual(st.scan('no spans here'), [('plain', 'no spans here')])
        self.assertEqual(st.scan('{{m: x}}'), [('math', 'x')])
        self.assertEqual(st.scan('{{other: x}}'), [('plain', '{{other: x}}')], 'an unknown kind is plain text')
        with self.assertRaisesRegex(st.Unspeakable, 'unclosed'):
            st.scan('{{math: x')

    def test_language_spans_become_segments_for_the_right_voice(self):
        prepared = st.prepare('Gradyan {{en: gradient descent}} yöntemi {{math: x^2}} olur', 'tr')
        self.assertEqual([(s['lang'], s['text']) for s in prepared['segments']],
                         [('tr', 'Gradyan'), ('en', 'gradient descent'), ('tr', 'yöntemi iks kare olur')])
        self.assertEqual(prepared['problems'], [])
        self.assertEqual(prepared['text'], 'Gradyan gradient descent yöntemi iks kare olur')

    def test_punctuation_after_a_span_attaches_to_the_word_before_it(self):
        prepared = st.prepare(r'The area is {{math: \pi r^2}}. Then {{math: x}}, and {{math: y}}!', 'en')
        self.assertEqual(prepared['text'], 'The area is pi r squared. Then x, and y!')
        self.assertEqual(prepared['segments'], [{'lang': 'en', 'text': 'The area is pi r squared. Then x, and y!'}])

    def test_an_unspeakable_formula_is_reported_and_the_rest_still_prepared(self):
        prepared = st.prepare(r'Look: {{math: \begin{pmatrix} a \end{pmatrix}}} and {{math: x^2}}', 'en')
        self.assertEqual(len(prepared['problems']), 1)
        self.assertIn('environments', prepared['problems'][0])
        self.assertIn('x squared', prepared['text'])
        self.assertTrue(st.prepare('{{math: x', 'en')['problems'])

    def test_numbers_in_plain_text_are_spelled_but_formulas_are_not_double_processed(self):
        self.assertEqual(st.prepare('We saw 3 events and 12% growth', 'en')['text'], 'We saw three events and twelve percent growth')
        self.assertEqual(st.prepare('Büyüme %5 ve 3,14 ile 2 olay', 'tr')['text'], 'Büyüme yüzde beş ve üç virgül bir dört ile iki olay')
        self.assertEqual(st.prepare('The 3rd of 1,000 items', 'en')['text'], 'The 3rd of 1,000 items', 'ordinals and thousands separators are left to the engine')
        self.assertEqual(st.prepare('x is 3', 'en', numbers=False)['text'], 'x is 3')


class Lexicon(unittest.TestCase):
    def test_whole_words_longest_first_ignoring_case_and_per_language(self):
        lexicon = {'en': {'Poisson': 'pwah-son', 'gradient descent': 'gray-dee-ent descent', 'gradient': 'gray-dee-ent'}, 'tr': {'Poisson': 'puvason'}}
        self.assertEqual(st.apply_lexicon('The poisson law and gradient descent, not gradients', 'en', lexicon), 'The pwah-son law and gray-dee-ent descent, not gradients')
        self.assertEqual(st.apply_lexicon('Poisson', 'tr', lexicon), 'puvason')
        self.assertEqual(st.apply_lexicon('Poisson', 'de', lexicon), 'Poisson')
        self.assertEqual(st.apply_lexicon('anything', 'en', None), 'anything')

    def test_the_lexicon_reaches_plain_text_and_language_spans_but_not_formulas(self):
        prepared = st.prepare('Poisson {{math: \\text{Poisson}}} {{en: Poisson}}', 'tr', {'tr': {'Poisson': 'puvason'}, 'en': {'Poisson': 'pwah-son'}})
        self.assertEqual([(s['lang'], s['text']) for s in prepared['segments']], [('tr', 'puvason Poisson'), ('en', 'pwah-son')])

    def test_a_missing_or_broken_lexicon_is_empty_never_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.assertEqual(st.load_lexicon(None), {})
            self.assertEqual(st.load_lexicon(tmp / 'nothing.json'), {})
            (tmp / 'bad.json').write_text('{not json', encoding='utf-8')
            self.assertEqual(st.load_lexicon(tmp / 'bad.json'), {})
            (tmp / 'list.json').write_text('[1, 2]', encoding='utf-8')
            self.assertEqual(st.load_lexicon(tmp / 'list.json'), {})
            (tmp / 'good.json').write_text('{"tr": {"a": "b"}, "en": "oops"}', encoding='utf-8')
            self.assertEqual(st.load_lexicon(tmp / 'good.json'), {'tr': {'a': 'b'}})


if __name__ == '__main__':
    unittest.main()
