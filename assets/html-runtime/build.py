"""Reproduce offline runtime from the pinned official npm KaTeX distribution.

Usage: python build.py /path/to/extracted/package
       python build.py --refresh   (reuse the bundled KaTeX; re-embed fonts, theme and runtime)
No dependency download or package code execution; only local source reads.
"""
from pathlib import Path
import base64
import hashlib
import json
import re
import sys

TARGET = Path(__file__).parent
KATEX_HEADER = '/* KaTeX 0.16.22, MIT; see KATEX-LICENSE.txt. Offline deterministic bundle. */\n'
FONTS_HEADER = '/* Research OS document fonts, SIL OFL 1.1; see FONTS-LICENSE.txt. */\n'
LATIN = ('U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,'
         'U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD')
LATIN_EXT = ('U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,'
             'U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF')
# Variable WOFF2 subsets from the pinned Fontsource 5.3.0 packages; Latin-Extended covers Turkish.
DOCUMENT_FONTS = {
    'source': {
        'Atkinson Hyperlegible Next': 'https://registry.npmjs.org/@fontsource-variable/atkinson-hyperlegible-next/-/atkinson-hyperlegible-next-5.3.0.tgz',
        'Atkinson Hyperlegible Mono': 'https://registry.npmjs.org/@fontsource-variable/atkinson-hyperlegible-mono/-/atkinson-hyperlegible-mono-5.3.0.tgz',
        'Source Serif 4': 'https://registry.npmjs.org/@fontsource-variable/source-serif-4/-/source-serif-4-5.3.0.tgz',
        # The blackboard's handwriting (board.js). Patrick Hand is the default hand; Caveat is the more cursive alternative. Both SIL OFL 1.1.
        'Patrick Hand': 'https://registry.npmjs.org/@fontsource/patrick-hand/-/patrick-hand-5.3.0.tgz',
        'Caveat': 'https://registry.npmjs.org/@fontsource-variable/caveat/-/caveat-5.3.0.tgz',
        'Kalam': 'https://registry.npmjs.org/@fontsource/kalam/-/kalam-5.3.0.tgz',
    },
    'faces': [
        ('Atkinson Hyperlegible Next', 'normal', '200 800', 'atkinson-hyperlegible-next-latin-wght-normal.woff2', LATIN),
        ('Atkinson Hyperlegible Next', 'normal', '200 800', 'atkinson-hyperlegible-next-latin-ext-wght-normal.woff2', LATIN_EXT),
        ('Atkinson Hyperlegible Mono', 'normal', '200 800', 'atkinson-hyperlegible-mono-latin-wght-normal.woff2', LATIN),
        ('Atkinson Hyperlegible Mono', 'normal', '200 800', 'atkinson-hyperlegible-mono-latin-ext-wght-normal.woff2', LATIN_EXT),
        ('Source Serif 4', 'normal', '200 900', 'source-serif-4-latin-wght-normal.woff2', LATIN),
        ('Source Serif 4', 'normal', '200 900', 'source-serif-4-latin-ext-wght-normal.woff2', LATIN_EXT),
        ('Source Serif 4', 'italic', '200 900', 'source-serif-4-latin-wght-italic.woff2', LATIN),
        ('Source Serif 4', 'italic', '200 900', 'source-serif-4-latin-ext-wght-italic.woff2', LATIN_EXT),
        ('Patrick Hand', 'normal', '400', 'patrick-hand-latin-400-normal.woff2', LATIN),
        ('Patrick Hand', 'normal', '400', 'patrick-hand-latin-ext-400-normal.woff2', LATIN_EXT),
        ('Caveat', 'normal', '400 700', 'caveat-latin-wght-normal.woff2', LATIN),
        ('Caveat', 'normal', '400 700', 'caveat-latin-ext-wght-normal.woff2', LATIN_EXT),
        ('Kalam', 'normal', '400', 'kalam-latin-400-normal.woff2', LATIN),
        ('Kalam', 'normal', '400', 'kalam-latin-ext-400-normal.woff2', LATIN_EXT),
        ('Kalam', 'normal', '700', 'kalam-latin-700-normal.woff2', LATIN),
        ('Kalam', 'normal', '700', 'kalam-latin-ext-700-normal.woff2', LATIN_EXT),
    ],
}


def document_fonts():
    """Return embedded @font-face CSS and the lock entry for the reading/control fonts."""
    rules, hashes = [], {}
    for family, style, weight, name, unicode_range in DOCUMENT_FONTS['faces']:
        data = (TARGET / 'fonts' / name).read_bytes()
        if data[:4] != b'wOF2':
            raise ValueError('Not a WOFF2 font: ' + name)
        hashes[name] = hashlib.sha256(data).hexdigest()
        rules.append('@font-face{font-family:"' + family + '";font-style:' + style + ';font-display:swap;font-weight:'
                     + weight + ';src:url(data:font/woff2;base64,' + base64.b64encode(data).decode()
                     + ') format("woff2");unicode-range:' + unicode_range + '}')
    lock = {'version': '5.3.0', 'license': 'OFL-1.1', 'source': DOCUMENT_FONTS['source'], 'fonts': hashes}
    return FONTS_HEADER + '\n'.join(rules) + '\n', lock


def write_bundle(katex_css, katex_js, inventory):
    fonts_css, inventory['document_fonts'] = document_fonts()
    # KaTeX, inline grammar, narration, blackboard, native reader, staged session,
    # then the runtime. refresh() splits
    # on the first "/* Research OS runtime" marker, which richtext.js carries, so the bundle round-trips.
    (TARGET / 'session.js').write_bytes(KATEX_HEADER.encode() + katex_js + b'\n;\n' + (TARGET / 'richtext.js').read_bytes()
                                        + b'\n' + (TARGET / 'narration.js').read_bytes() + b'\n' + (TARGET / 'board.js').read_bytes()
                                        + b'\n' + (TARGET / 'reader.js').read_bytes() + b'\n' + (TARGET / 'advice.js').read_bytes() + b'\n' + (TARGET / 'drafts.js').read_bytes() + b'\n' + (TARGET / 'stages.js').read_bytes() + b'\n' + (TARGET / 'runtime.js').read_bytes())
    (TARGET / 'session.css').write_text(KATEX_HEADER + katex_css + '\n' + fonts_css + (TARGET / 'theme.css').read_text(encoding='utf-8')
                                        + '\n' + (TARGET / 'board.css').read_text(encoding='utf-8') + '\n' + (TARGET / 'stages.css').read_text(encoding='utf-8'), encoding='utf-8')
    (TARGET / 'dependency-lock.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')


def build(package):
    distribution = package / 'dist'
    license_text = (package / 'LICENSE').read_text(encoding='utf-8')
    source = (distribution / 'katex.min.js').read_bytes()
    css = (distribution / 'katex.min.css').read_text(encoding='utf-8')
    inventory = {'dependency': 'KaTeX', 'version': '0.16.22',
                 'source': 'https://registry.npmjs.org/katex/-/katex-0.16.22.tgz',
                 'license': 'MIT', 'source_files': {'katex.min.js': hashlib.sha256(source).hexdigest(),
                 'katex.min.css': hashlib.sha256(css.encode()).hexdigest()}, 'fonts': {}}
    def font(match):
        name = match.group(1)
        data = (distribution / 'fonts' / name).read_bytes()
        inventory['fonts'][name] = hashlib.sha256(data).hexdigest()
        return 'src:url(data:font/woff2;base64,' + base64.b64encode(data).decode() + ') format("woff2")'
    css = re.sub(r'src:url\(fonts/([^()]+\.woff2)\) format\("woff2"\)(?:,[^;}]+)*', font, css)
    if 'url(fonts/' in css:
        raise ValueError('Unexpected unbundled font')
    write_bundle(css, source, inventory)
    (TARGET / 'KATEX-LICENSE.txt').write_text(license_text, encoding='utf-8')


def refresh():
    """Rebuild from the KaTeX already in the bundles, verified against the lock file."""
    inventory = json.loads((TARGET / 'dependency-lock.json').read_text(encoding='utf-8'))
    css = (TARGET / 'session.css').read_text(encoding='utf-8')
    if not css.startswith(KATEX_HEADER):
        raise ValueError('session.css does not start with the KaTeX bundle')
    end = min(i for i in (css.find('\n' + FONTS_HEADER), css.find('\n/* Research OS')) if i >= 0)
    katex_css = css[len(KATEX_HEADER):end]
    embedded = {hashlib.sha256(base64.b64decode(f)).hexdigest()
                for f in re.findall(r'url\(data:font/woff2;base64,([A-Za-z0-9+/=]+)\)', katex_css)}
    if embedded != set(inventory['fonts'].values()):
        raise ValueError('Bundled KaTeX fonts do not match dependency-lock.json')
    js = (TARGET / 'session.js').read_bytes().replace(b'\r\n', b'\n')
    marker = js.find(b'\n;\n/* Research OS runtime')
    if not js.startswith(KATEX_HEADER.encode()) or marker < 0:
        raise ValueError('session.js does not have the expected KaTeX + runtime layout')
    katex_js = js[len(KATEX_HEADER):marker]
    if hashlib.sha256(katex_js).hexdigest() != inventory['source_files']['katex.min.js']:
        raise ValueError('Bundled katex.min.js does not match dependency-lock.json')
    write_bundle(katex_css, katex_js, inventory)


if __name__ == '__main__':
    refresh() if sys.argv[1:] == ['--refresh'] else build(Path(sys.argv[1]))
