"""Reproduce offline runtime from the pinned official npm KaTeX distribution.

Usage: python build.py /path/to/extracted/package
No dependency download or package code execution; only local source reads.
"""
from pathlib import Path
import base64
import hashlib
import json
import re
import sys


def build(package):
    target = Path(__file__).parent
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
    header = '/* KaTeX 0.16.22, MIT; see KATEX-LICENSE.txt. Offline deterministic bundle. */\n'
    (target / 'session.js').write_bytes(header.encode() + source + b'\n;\n' + (target / 'runtime.js').read_bytes())
    (target / 'session.css').write_text(header + css + '\n' + (target / 'theme.css').read_text(encoding='utf-8'), encoding='utf-8')
    (target / 'KATEX-LICENSE.txt').write_text(license_text, encoding='utf-8')
    (target / 'dependency-lock.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    build(Path(sys.argv[1]))
