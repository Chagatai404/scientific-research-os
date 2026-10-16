"""Text for the ear: say a formula in words (English or Turkish), mark language spans, and apply a pronunciation lexicon. Standard library only.

A spoken script is ordinary words plus marked spans, written ``{{kind: ...}}``:

* ``{{math: \\frac{a}{b}}}``  a formula, said in words by the rules below, in the script's language
* ``{{en: gradient descent}}`` text in another language, spoken by that language's voice (code-switching)
* a pronunciation lexicon maps terms to respellings for the engine, outside formulas

The formula rules cover a defined subset of TeX. Anything outside it (matrices, aligned equations, an unpaired bar, a function arrow outside a limit, ``f: A -> B``)
raises ``Unspeakable`` with the reason: the script author writes those in words. The rules say a formula flat and literally; they do not decide what an ambiguous
formula means. The Turkish phrasings were written without review by a native speaker; treat them as a draft until one has listened.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

LANGUAGES = ('en', 'tr')


class Unspeakable(ValueError):
    """A formula the rules do not cover, or would have to guess about."""


# ---------------------------------------------------------------- numbers

EN_UNITS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen',
            'sixteen', 'seventeen', 'eighteen', 'nineteen']
EN_TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
EN_SCALES = ['', 'thousand', 'million', 'billion', 'trillion']
TR_UNITS = ['sıfır', 'bir', 'iki', 'üç', 'dört', 'beş', 'altı', 'yedi', 'sekiz', 'dokuz']
TR_TENS = ['', 'on', 'yirmi', 'otuz', 'kırk', 'elli', 'altmış', 'yetmiş', 'seksen', 'doksan']
TR_SCALES = ['', 'bin', 'milyon', 'milyar', 'trilyon']


def _en_below_1000(n: int) -> str:
    words = []
    if n >= 100:
        words.append(EN_UNITS[n // 100] + ' hundred')
        n %= 100
    if n >= 20:
        words.append(EN_TENS[n // 10] + ('-' + EN_UNITS[n % 10] if n % 10 else ''))
    elif n:
        words.append(EN_UNITS[n])
    return ' '.join(words)


def _tr_below_1000(n: int) -> str:
    out = ''
    if n >= 100:
        out += ('' if n // 100 == 1 else TR_UNITS[n // 100] + ' ') + 'yüz'
        n %= 100
    if n >= 10:
        out += (' ' if out else '') + TR_TENS[n // 10]
        n %= 10
    if n:
        out += (' ' if out else '') + TR_UNITS[n]
    return out


def integer_words(n: int, lang: str) -> str:
    """A whole number in words, up to 10^15. Negative numbers say the sign first."""
    if lang not in LANGUAGES:
        raise Unspeakable(f'no number rules for {lang!r}')
    if n < 0:
        return ('minus ' if lang == 'en' else 'eksi ') + integer_words(-n, lang)
    if n >= 10 ** 15:
        raise Unspeakable('numbers of 10^15 or more are not spoken; write the magnitude in words')
    if n == 0:
        return 'zero' if lang == 'en' else 'sıfır'
    groups, scale = [], 0
    while n:
        n, part = divmod(n, 1000)
        if part:
            text = _en_below_1000(part) if lang == 'en' else _tr_below_1000(part)
            if lang == 'tr' and scale == 1 and part == 1:
                text = ''  # "bin", not "bir bin"
            groups.append((text + ' ' + (EN_SCALES if lang == 'en' else TR_SCALES)[scale]).strip())
        scale += 1
    return ' '.join(reversed(groups))


def number_words(text: str, lang: str) -> str:
    """``12`` or ``3.14`` in words. The fractional digits are read one by one, which is how they are said."""
    if not re.fullmatch(r'\d+(?:\.\d+)?', text):
        raise Unspeakable(f'{text!r} is not a plain number')
    whole, _, fraction = text.partition('.')
    out = integer_words(int(whole), lang)
    if fraction:
        digits = ' '.join((EN_UNITS if lang == 'en' else TR_UNITS)[int(d)] for d in fraction)
        out += (' point ' if lang == 'en' else ' virgül ') + digits
    return out


# ---------------------------------------------------------------- vocabulary (English, Turkish)

GREEK = {'alpha': ('alpha', 'alfa'), 'beta': ('beta', 'beta'), 'gamma': ('gamma', 'gama'), 'delta': ('delta', 'delta'), 'epsilon': ('epsilon', 'epsilon'),
         'varepsilon': ('epsilon', 'epsilon'), 'zeta': ('zeta', 'zeta'), 'eta': ('eta', 'eta'), 'theta': ('theta', 'teta'), 'vartheta': ('theta', 'teta'),
         'iota': ('iota', 'iyota'), 'kappa': ('kappa', 'kappa'), 'lambda': ('lambda', 'lambda'), 'mu': ('mu', 'mü'), 'nu': ('nu', 'nü'), 'xi': ('ksi', 'ksi'),
         'pi': ('pi', 'pi'), 'rho': ('rho', 'ro'), 'sigma': ('sigma', 'sigma'), 'tau': ('tau', 'tau'), 'upsilon': ('upsilon', 'üpsilon'), 'phi': ('phi', 'fi'),
         'varphi': ('phi', 'fi'), 'chi': ('chi', 'ki'), 'psi': ('psi', 'psi'), 'omega': ('omega', 'omega')}
GREEK_CAPITAL = {'Gamma': 'gamma', 'Delta': 'delta', 'Theta': 'theta', 'Lambda': 'lambda', 'Xi': 'xi', 'Pi': 'pi', 'Sigma': 'sigma', 'Phi': 'phi', 'Psi': 'psi', 'Omega': 'omega'}
SYMBOLS = {  # command -> (English, Turkish)
    'cdot': ('times', 'çarpı'), 'times': ('times', 'çarpı'), 'div': ('divided by', 'bölü'), 'pm': ('plus or minus', 'artı eksi'), 'mp': ('minus or plus', 'eksi artı'),
    'infty': ('infinity', 'sonsuz'), 'partial': ('partial', 'kısmi'), 'nabla': ('nabla', 'nabla'), 'leq': ('is less than or equal to', 'küçük eşittir'),
    'le': ('is less than or equal to', 'küçük eşittir'), 'geq': ('is greater than or equal to', 'büyük eşittir'), 'ge': ('is greater than or equal to', 'büyük eşittir'),
    'neq': ('is not equal to', 'eşit değildir'), 'ne': ('is not equal to', 'eşit değildir'), 'approx': ('is approximately equal to', 'yaklaşık olarak eşittir'),
    'equiv': ('is equivalent to', 'denktir'), 'propto': ('is proportional to', 'ile orantılıdır'), 'in': ('is an element of', 'elemanıdır'),
    'notin': ('is not an element of', 'elemanı değildir'), 'subset': ('is a subset of', 'alt kümesidir'), 'cup': ('union', 'birleşim'), 'cap': ('intersection', 'kesişim'),
    'Rightarrow': ('implies', 'gerektirir'), 'Leftrightarrow': ('if and only if', 'ancak ve ancak'), 'ldots': ('and so on', 've böyle devam eder'),
    'dots': ('and so on', 've böyle devam eder'), 'cdots': ('and so on', 've böyle devam eder'), 'hbar': ('h bar', 'h çizgi'), 'ell': ('ell', 'el'),
    'circ': ('degrees', 'derece'), 'degree': ('degrees', 'derece'), 'angle': ('angle', 'açı'), 'perp': ('is perpendicular to', 'diktir'), 'parallel': ('is parallel to', 'paraleldir')}
PLAIN = {'+': ('plus', 'artı'), '-': ('minus', 'eksi'), '=': ('equals', 'eşittir'), '<': ('is less than', 'küçüktür'), '>': ('is greater than', 'büyüktür'),
         '/': ('over', 'bölü'), '*': ('times', 'çarpı'), ',': (',', ','), ';': (',', ','), '.': ('', ''), '(': ('open parenthesis', 'parantez aç'),
         ')': ('close parenthesis', 'parantez kapa'), '[': ('open bracket', 'köşeli parantez aç'), ']': ('close bracket', 'köşeli parantez kapa'),
         '!': ('factorial', 'faktöriyel')}
FUNCTIONS = {'sin': ('sine', 'sinüs'), 'cos': ('cosine', 'kosinüs'), 'tan': ('tangent', 'tanjant'), 'cot': ('cotangent', 'kotanjant'), 'sec': ('secant', 'sekant'),
             'csc': ('cosecant', 'kosekant'), 'sinh': ('hyperbolic sine', 'hiperbolik sinüs'), 'cosh': ('hyperbolic cosine', 'hiperbolik kosinüs'),
             'tanh': ('hyperbolic tangent', 'hiperbolik tanjant'), 'arcsin': ('arc sine', 'ark sinüs'), 'arccos': ('arc cosine', 'ark kosinüs'),
             'arctan': ('arc tangent', 'ark tanjant'), 'ln': ('natural log', 'doğal logaritma'), 'log': ('log', 'logaritma'), 'exp': ('exponential', 'üstel'),
             'det': ('determinant', 'determinant'), 'max': ('maximum', 'maksimum'), 'min': ('minimum', 'minimum'), 'dim': ('dimension', 'boyut'), 'gcd': ('gcd', 'ebob')}
ACCENTS = {'vec': ('vector {}', 'vektör {}'), 'mathbf': ('vector {}', 'vektör {}'), 'boldsymbol': ('vector {}', 'vektör {}'), 'hat': ('{} hat', '{} şapka'),
           'bar': ('{} bar', '{} çizgi'), 'overline': ('{} bar', '{} çizgi'), 'tilde': ('{} tilde', '{} yaklaşık işareti'), 'dot': ('{} dot', '{} nokta'),
           'ddot': ('{} double dot', '{} çift nokta')}
SETS = {'R': ('the real numbers', 'gerçel sayılar'), 'N': ('the natural numbers', 'doğal sayılar'), 'Z': ('the integers', 'tam sayılar'),
        'Q': ('the rational numbers', 'rasyonel sayılar'), 'C': ('the complex numbers', 'karmaşık sayılar')}
SKIP = {',', ';', '!', ':', ' ', 'quad', 'qquad', 'displaystyle', 'textstyle', 'limits', 'nolimits'}
LETTER_EN = {'a': 'ay', 'A': 'capital ay'}
LETTER_TR = {'b': 'be', 'c': 'ce', 'd': 'de', 'f': 'fe', 'g': 'ge', 'h': 'he', 'j': 'je', 'k': 'ke', 'l': 'le', 'm': 'me', 'n': 'ne', 'p': 'pe', 'q': 'kü',
             'r': 're', 's': 'se', 't': 'te', 'v': 've', 'w': 'çift ve', 'x': 'iks', 'y': 'ye', 'z': 'ze'}
FUNCTION_LETTERS = set('fgh') | set('FGH')
BIG = {'sum': ('the sum', 'toplam'), 'prod': ('the product', 'çarpım'), 'int': ('the integral', 'integral'), 'oint': ('the contour integral', 'kontur integrali'),
       'lim': ('the limit', 'limit')}
ENDS_ARGUMENT_OP = set('+-=<>,;/*)]')
ENDS_ARGUMENT_SYMBOL = {'leq', 'le', 'geq', 'ge', 'neq', 'ne', 'approx', 'equiv', 'pm', 'mp', 'in', 'notin', 'subset', 'Rightarrow', 'Leftrightarrow', 'times', 'cdot', 'div'}
UNSPEAKABLE_COMMANDS = {'forall', 'exists', 'mapsto', 'sim', 'll', 'gg', 'prime', 'star', 'oplus', 'otimes', 'langle', 'rangle', 'neg', 'land', 'lor', 'emptyset'}
MAX_DEPTH = 8
TOKEN = re.compile(r'\\[A-Za-z]+|\\.|\d+(?:\.\d+)?|[A-Za-z]|\s+|.', re.S)
CLOSERS = ('\\right', '\\rvert', '|', '\\vert')


def _i(lang: str) -> int:
    if lang not in LANGUAGES:
        raise Unspeakable(f'no formula rules for language {lang!r} (available: {", ".join(LANGUAGES)})')
    return LANGUAGES.index(lang)


# ---------------------------------------------------------------- parsing

class Parser:
    def __init__(self, tex: str):
        self.tokens = TOKEN.findall(tex)
        self.i = 0

    def _skip(self):
        while self.i < len(self.tokens) and self.tokens[self.i].isspace():
            self.i += 1

    def peek(self):
        self._skip()
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self):
        tok = self.peek()
        if tok is None:
            raise Unspeakable('the formula ends in the middle of a construct')
        self.i += 1
        return tok

    def sequence(self, stop=(), depth=0):
        if depth > MAX_DEPTH:
            raise Unspeakable('the formula is nested too deeply to say; split it into steps in words')
        nodes = []
        while self.peek() is not None and self.peek() not in stop:
            nodes.append(self.scripted(depth))
        return nodes

    def argument(self, depth):
        """One argument: a braced group or a single token."""
        if self.peek() == '{':
            return self.atom(depth + 1)
        if self.peek() == '}':
            raise Unspeakable('unbalanced braces')
        return self.atom(depth + 1)

    def scripted(self, depth):
        atom = self.atom(depth)
        sub = sup = None
        while self.peek() in ('^', '_'):
            marker = self.take()
            part = self.argument(depth)
            if marker == '^':
                if sup is not None:
                    raise Unspeakable('two superscripts on one symbol')
                sup = part
            else:
                if sub is not None:
                    raise Unspeakable('two subscripts on one symbol')
                sub = part
        if self.peek() == "'":
            raise Unspeakable("a prime (') is read as a derivative or a new variable; write which in words")
        return ('script', atom, sub, sup) if (sub or sup) else atom

    def atom(self, depth):
        tok = self.take()
        if tok == '{':
            nodes = self.sequence(('}',), depth + 1)
            if self.peek() != '}':
                raise Unspeakable('unbalanced braces')
            self.i += 1
            return ('group', nodes)
        if tok in ('}', '^', '_'):
            raise Unspeakable(f'unexpected {tok!r}')
        if tok == '&':
            raise Unspeakable('alignment and matrix columns are not spoken; write the equations in words')
        if tok == '|':
            nodes = self.sequence(('|',), depth + 1)
            if self.peek() != '|':
                raise Unspeakable('an unpaired vertical bar could be an absolute value, a norm or "given"; write which in words')
            self.i += 1
            return ('abs', nodes)
        if re.fullmatch(r'\d+(?:\.\d+)?', tok):
            return ('num', tok)
        if re.fullmatch(r'[A-Za-z]', tok):
            if tok in FUNCTION_LETTERS and self.peek() == '(':
                self.i += 1
                inner = self.sequence((')',), depth + 1)
                if self.peek() != ')':
                    raise Unspeakable('unbalanced parentheses')
                self.i += 1
                return ('call', tok, inner)
            return ('var', tok)
        if tok.startswith('\\'):
            return self.command(tok[1:], depth)
        return ('op', tok)

    def command(self, name, depth):
        if name in SKIP:
            return ('skip',)
        if name in ('frac', 'dfrac', 'tfrac'):
            return ('frac', self.argument(depth), self.argument(depth))
        if name == 'sqrt':
            index = None
            if self.peek() == '[':
                self.i += 1
                index = self.sequence((']',), depth + 1)
                if self.peek() != ']':
                    raise Unspeakable('unbalanced brackets')
                self.i += 1
            return ('sqrt', index, self.argument(depth))
        if name in ('text', 'mathrm', 'textrm', 'operatorname', 'mathit'):
            return ('text', self.raw_group())
        if name == 'mathbb':
            letter = self.raw_group().strip()
            if letter not in SETS:
                raise Unspeakable(f'\\mathbb{{{letter}}} is not a set the rules name; write it in words')
            return ('set', letter)
        if name in ACCENTS:
            return ('accent', name, self.argument(depth))
        if name in ('left', 'right'):
            delim = self.take()
            if delim == '.':
                return ('skip',)
            if delim in ('|', '\\vert', '\\lvert', '\\rvert'):
                return self.fenced_bar(depth)
            if delim in ('(', ')', '[', ']'):
                return ('op', delim)
            return self._unknown(delim)
        if name in ('lvert', 'rvert', 'vert'):
            return self.fenced_bar(depth)
        if name in GREEK:
            return ('greek', name)
        if name in GREEK_CAPITAL:
            return ('greek_capital', name)
        if name in FUNCTIONS:
            return ('function', name)
        if name in BIG:
            return ('big', name)
        if name in SYMBOLS:
            return ('symbol', name)
        if name in ('to', 'rightarrow'):
            return ('arrow',)
        if name in ('begin', 'end'):
            raise Unspeakable('environments (matrices, aligned equations, cases) are not spoken; write them in words')
        if name == '\\':
            raise Unspeakable('line breaks in a formula are not spoken; write each line in words')
        if name in UNSPEAKABLE_COMMANDS:
            raise Unspeakable(f'\\{name} has more than one reading or an order that needs a sentence; write it in words')
        return self._unknown('\\' + name)

    def _unknown(self, token):
        raise Unspeakable(f'{token} is not in the set of symbols the rules cover; write it in words')

    def fenced_bar(self, depth):
        nodes = self.sequence(CLOSERS, depth + 1)
        closer = self.peek()
        if closer is None:
            raise Unspeakable('an unpaired vertical bar could be an absolute value, a norm or "given"; write which in words')
        self.i += 1
        if closer == '\\right':
            self.take()
        return ('abs', nodes)

    def raw_group(self):
        tok = self.take()
        if tok != '{':
            return tok
        out, depth = [], 1
        while self.i < len(self.tokens):
            tok = self.tokens[self.i]
            self.i += 1
            if tok == '{':
                depth += 1
            elif tok == '}':
                depth -= 1
                if depth == 0:
                    return ''.join(out)
            out.append(tok)
        raise Unspeakable('unbalanced braces')


def parse(tex: str):
    parser = Parser(tex)
    nodes = parser.sequence()
    if parser.peek() is not None:
        raise Unspeakable(f'unbalanced {parser.peek()!r}')
    return nodes


# ---------------------------------------------------------------- saying

def _simple(node) -> bool:
    """A single spoken unit, so no 'end of ...' marker is needed after it."""
    if node[0] == 'group':
        inner = [n for n in node[1] if n[0] != 'skip']
        if len(inner) == 1:
            return _simple(inner[0])
        return len(inner) == 2 and inner[0] == ('op', '-') and inner[1][0] in ('num', 'var', 'greek')
    if node[0] == 'script':
        return node[1][0] in ('num', 'var', 'greek') and node[2] is None and node[3] is not None and node[3][0] in ('num', 'var', 'greek')
    return node[0] in ('num', 'var', 'greek', 'greek_capital', 'symbol', 'text', 'set')


def _letter(ch: str, lang: str) -> str:
    return (LETTER_EN if lang == 'en' else LETTER_TR).get(ch, ch)


def _ends_argument(node) -> bool:
    if node[0] == 'op':
        return node[1] in ENDS_ARGUMENT_OP
    if node[0] == 'symbol':
        return node[1] in ENDS_ARGUMENT_SYMBOL
    return node[0] == 'arrow'


def say(nodes, lang: str) -> str:
    """Words for a sequence of nodes."""
    i = _i(lang)
    parts, k = [], 0
    nodes = [n for n in nodes if n[0] != 'skip']
    while k < len(nodes):
        node = nodes[k]
        kind = node[0]
        if kind == 'function' or (kind == 'script' and node[1][0] == 'function'):
            name = node[1][1] if kind == 'script' else node[1]
            word = FUNCTIONS[name][i]
            if kind == 'script':
                if node[2] is not None:
                    raise Unspeakable('a subscript on a function name is not spoken; write it in words')
                word = f'{word} {_power(node[3], lang)}'
            k += 1
            if k < len(nodes) and nodes[k] == ('op', '('):
                depth, j = 1, k + 1
                while j < len(nodes) and depth:
                    depth += (nodes[j] == ('op', '(')) - (nodes[j] == ('op', ')'))
                    j += 1
                if depth:
                    raise Unspeakable('unbalanced parentheses')
                argument = say(nodes[k + 1:j - 1], lang)
                k = j
            else:
                j = k
                while j < len(nodes) and not _ends_argument(nodes[j]):
                    j += 1
                if j == k:
                    parts.append(word)
                    continue
                argument = say(nodes[k:j], lang)
                k = j
            parts.append(f'{word} of {argument}' if lang == 'en' else f'{word} {argument}')
            continue
        if kind == 'big' or (kind == 'script' and node[1][0] == 'big'):
            parts.append(_big(node, nodes[k + 1:], lang))
            break
        parts.append(_one(node, lang))
        k += 1
    return re.sub(r'\s+,', ',', ' '.join(p for p in parts if p)).strip()


def _power(exponent, lang: str) -> str:
    """The words for an exponent, with a closing marker when it is more than one unit."""
    body = [n for n in (exponent[1] if exponent[0] == 'group' else [exponent]) if n[0] != 'skip']
    if len(body) == 1 and body[0][0] == 'num':
        if body[0][1] == '2':
            return 'squared' if lang == 'en' else 'kare'
        if body[0][1] == '3':
            return 'cubed' if lang == 'en' else 'küp'
    text = say(body, lang)
    if _simple(exponent):
        return f'to the {text}' if lang == 'en' else f'üzeri {text}'
    return f'to the power of {text}, end of power' if lang == 'en' else f'üzeri {text}, üs sonu'


def _one(node, lang: str) -> str:
    i = _i(lang)
    kind = node[0]
    if kind == 'num':
        return number_words(node[1], lang)
    if kind == 'var':
        return _letter(node[1], lang)
    if kind == 'greek':
        return GREEK[node[1]][i]
    if kind == 'greek_capital':
        return ('capital ' if lang == 'en' else 'büyük ') + GREEK[GREEK_CAPITAL[node[1]]][i]
    if kind == 'set':
        return SETS[node[1]][i]
    if kind == 'symbol':
        return SYMBOLS[node[1]][i]
    if kind == 'text':
        return node[1].strip()
    if kind == 'arrow':
        raise Unspeakable('an arrow outside a limit has more than one reading (tends to, maps to, implies); write it in words')
    if kind == 'op':
        if node[1] in PLAIN:
            return PLAIN[node[1]][i]
        raise Unspeakable(f'{node[1]!r} is not spoken by the rules; write it in words')
    if kind == 'group':
        return say(node[1], lang)
    if kind == 'abs':
        inner = say(node[1], lang)
        return f'the absolute value of {inner}, end absolute value' if lang == 'en' else f'{inner} sayısının mutlak değeri'
    if kind == 'call':
        args = say(node[2], lang)
        return f'{_letter(node[1], lang)} of {args}' if lang == 'en' else f'{_letter(node[1], lang)} {args}'
    if kind == 'accent':
        return ACCENTS[node[1]][i].format(say([node[2]], lang))
    if kind == 'frac':
        top, bottom = say([node[1]], lang), say([node[2]], lang)
        if _simple(node[1]) and _simple(node[2]):
            return f'{top} over {bottom}' if lang == 'en' else f'{top} bölü {bottom}'
        return (f'the fraction with numerator {top} and denominator {bottom}, end fraction' if lang == 'en'
                else f'payı {top}, paydası {bottom} olan kesir, kesir sonu')
    if kind == 'sqrt':
        inner = say([node[2]], lang)
        end = '' if _simple(node[2]) else (', end root' if lang == 'en' else ', kök sonu')
        if node[1] is None:
            return f'the square root of {inner}{end}' if lang == 'en' else f'karekök {inner}{end}'
        degree = say(node[1], lang)
        if degree == ('two' if lang == 'en' else 'iki'):
            return f'the square root of {inner}{end}' if lang == 'en' else f'karekök {inner}{end}'
        if degree == ('three' if lang == 'en' else 'üç'):
            return f'the cube root of {inner}{end}' if lang == 'en' else f'küpkök {inner}{end}'
        return f'the {degree}-th root of {inner}{end}' if lang == 'en' else f'{degree}. dereceden kök {inner}{end}'
    if kind == 'script':
        base, sub, sup = node[1], node[2], node[3]
        text = say(base[1], lang) if base[0] == 'group' else _one(base, lang)
        if base[0] in ('frac', 'abs') or (base[0] == 'group' and len(base[1]) > 1):
            text = ('the quantity ' if lang == 'en' else 'parantez içi ') + text
        if sub is not None:
            inner = say([sub], lang)
            marker = ('sub', ', end sub') if lang == 'en' else ('indis', ', indis sonu')
            text += f' {marker[0]} {inner}' + ('' if _simple(sub) else marker[1])
        if sup is not None:
            text += ' ' + _power(sup, lang)
        return text
    if kind == 'function':
        return FUNCTIONS[node[1]][i]
    raise Unspeakable(f'no rule for {kind}')


def _big(node, rest, lang: str) -> str:
    i = _i(lang)
    base, sub, sup = (node[1], node[2], node[3]) if node[0] == 'script' else (node, None, None)
    name = base[1]
    head = BIG[name][i]
    body = say(rest, lang)
    if name == 'lim':
        if sub is None:
            raise Unspeakable('a limit needs to say what tends to what')
        condition = _limit_condition(sub, lang)
        return (f'the limit as {condition} of {body}' if lang == 'en' else f'{condition}, limit {body}').strip()
    sub_text = say([sub], lang) if sub is not None else ''
    sup_text = say([sup], lang) if sup is not None else ''
    if lang == 'en':
        span = ''
        if sub is not None and sup is not None:
            span = f' from {sub_text} to {sup_text}'
        elif sub is not None:
            span = f' over {sub_text}'
        elif sup is not None:
            span = f' up to {sup_text}'
        return f'{head}{span}{" of " + body if body else ""}'.strip()
    span = ''
    if sub is not None and sup is not None:
        span = f', {sub_text} ile {sup_text} arasında,'
    elif sub is not None:
        span = f', {sub_text} üzerinde,'
    elif sup is not None:
        span = f', {sup_text} değerine kadar,'
    return f'{head}{span} {body}'.strip()


def _limit_condition(sub, lang: str) -> str:
    group = [n for n in (sub[1] if sub[0] == 'group' else [sub]) if n[0] != 'skip']
    if ('arrow',) not in group:
        raise Unspeakable('a limit subscript needs an arrow, as in x \\to a')
    cut = group.index(('arrow',))
    variable, target = say(group[:cut], lang), say(group[cut + 1:], lang)
    if not variable or not target:
        raise Unspeakable('a limit needs both the variable and the value it tends to')
    return f'{variable} tends to {target}' if lang == 'en' else f'{variable}, {target} değerine yaklaşırken'


def verbalize(tex: str, lang: str) -> str:
    """A formula in words, or ``Unspeakable`` with the reason. Never a guess."""
    _i(lang)
    if not tex or not tex.strip():
        raise Unspeakable('an empty formula')
    words = say(parse(tex), lang)
    if not words:
        raise Unspeakable('nothing to say')
    return re.sub(r'\s+', ' ', words).strip()


# ---------------------------------------------------------------- spans, lexicon, scripts

SPAN_KINDS = {'math', 'm'} | set(LANGUAGES)


def scan(script: str) -> list[tuple[str, str]]:
    """Split a script into ``(kind, text)`` pieces: ``plain`` text and ``{{kind: text}}`` spans. Braces inside a span are balanced, so ``{{math: \\frac{a}{b}}}`` works."""
    pieces, i, plain = [], 0, []
    while i < len(script):
        if script.startswith('{{', i):
            match = re.match(r'\{\{\s*(\w+)\s*:', script[i:])
            if match and match[1].lower() in SPAN_KINDS:
                depth, j = 2, i + match.end()
                while j < len(script) and depth:
                    depth += (script[j] == '{') - (script[j] == '}')
                    j += 1
                if depth:
                    raise Unspeakable(f'an unclosed {{{{{match[1]}: ...}}}} span')
                if plain:
                    pieces.append(('plain', ''.join(plain)))
                    plain = []
                kind = match[1].lower()
                pieces.append(('math' if kind == 'm' else kind, script[i + match.end():j - 2].strip()))
                i = j
                continue
        plain.append(script[i])
        i += 1
    if plain:
        pieces.append(('plain', ''.join(plain)))
    return pieces


def load_lexicon(path: Path | None) -> dict:
    """``{"tr": {"gradient descent": "gradient dissent"}}``. A missing or unreadable file is an empty lexicon, never a failure."""
    if path is None or not Path(path).is_file():
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {lang: {str(k): str(v) for k, v in terms.items()} for lang, terms in data.items() if isinstance(terms, dict)}


def apply_lexicon(text: str, lang: str, lexicon: dict | None) -> str:
    """Replace whole words, longest term first, ignoring case. Outside formulas only."""
    terms = (lexicon or {}).get(lang, {})
    for term in sorted(terms, key=len, reverse=True):
        text = re.sub(r'(?<!\w)' + re.escape(term) + r'(?!\w)', lambda _m, v=terms[term]: v, text, flags=re.IGNORECASE)
    return text


PERCENT = re.compile(r'(\d+(?:[.,]\d+)?)\s*%')
PERCENT_PREFIX = re.compile(r'%(\d+(?:[.,]\d+)?)')
NUMBER = re.compile(r'(?<![\w.,])(\d+(?:[.,]\d+)?)(?!\w)')


def spell_numbers(text: str, lang: str) -> str:
    """Digits in plain text become words, so every engine says the same thing. A comma is a decimal comma in Turkish; in English a comma between digits is
    left alone, because a thousands separator is not something to guess at."""
    if lang not in LANGUAGES:
        return text

    def to_words(raw: str) -> str:
        return number_words(raw.replace(',', '.') if lang == 'tr' else raw, lang)

    def percent(match):
        words = to_words(match[1])
        return f'{words} percent' if lang == 'en' else f'yüzde {words}'
    text = PERCENT.sub(percent, text)
    text = PERCENT_PREFIX.sub(percent, text)
    return NUMBER.sub(lambda m: m[0] if (lang == 'en' and ',' in m[1]) else to_words(m[1]), text)


def prepare(script: str, lang: str, lexicon: dict | None = None, numbers: bool = True) -> dict:
    """Turn a spoken script into voice segments. ``problems`` lists every span the rules could not say; with problems the result must not be spoken."""
    _i(lang)
    segments, problems = [], []
    try:
        pieces = scan(script)
    except Unspeakable as exc:
        return {'lang': lang, 'segments': [], 'text': '', 'problems': [str(exc)]}
    for kind, text in pieces:
        if kind == 'math':
            try:
                spoken, seg_lang = verbalize(text, lang), lang
            except Unspeakable as exc:
                problems.append(f'{{{{math: {text}}}}}: {exc}')
                continue
        else:
            seg_lang = kind if kind in LANGUAGES else lang
            spoken = spell_numbers(text, seg_lang) if numbers else text
            spoken = apply_lexicon(spoken, seg_lang, lexicon)
        spoken = re.sub(r'\s+', ' ', spoken).strip()
        if not spoken:
            continue
        if segments and segments[-1]['lang'] == seg_lang:
            segments[-1]['text'] += ('' if re.match(r'[.,;:!?)]', spoken) else ' ') + spoken  # punctuation attaches to the word before it
        else:
            segments.append({'lang': seg_lang, 'text': spoken})
    return {'lang': lang, 'segments': segments, 'text': re.sub(r'\s+([.,;:!?)])', r'\1', ' '.join(s['text'] for s in segments)), 'problems': problems}


def words(text: str) -> int:
    return len(re.findall(r'\w+', text))
