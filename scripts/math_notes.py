"""Obsidian MathJax helpers and conservative warnings, not a TeX compiler."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re


def expression(value):
    if not isinstance(value, str) or not value.strip() or '$' in value:
        raise ValueError('expected a nonempty equation without dollar delimiters')
    return value.strip()


def inline(value):
    value = expression(value)
    if '\n' in value:
        raise ValueError('inline math must stay on one line')
    return '$' + value + '$'


def display(value):
    return '$$\n' + expression(value) + '\n$$'


def formula(title, equation, *, variables=None, units=None, assumptions=None,
            regime=None, source=None):
    if not isinstance(title, str) or not title.strip() or '\n' in title:
        raise ValueError('formula title must be one nonempty line')
    lines = [f'> [!formula] {title.strip()}']
    lines += ['> ' + line for line in display(equation).splitlines()]
    if variables:
        lines += ['>', '> **Variables:** ' + '; '.join(inline(key) + ': ' + val.replace('\n', '\n> ')
                                                     for key, val in variables.items())]
    for name, value in [('Units', units), ('Assumptions', assumptions), ('Validity', regime), ('Source', source)]:
        if value:
            lines += ['>', '> **' + name + ':** ' + str(value).replace('\n', '\n> ')]
    return '\n'.join(lines) + '\n'


def issues(text):
    result, fence, display_open = [], '', False
    for number, original in enumerate(text.splitlines(), 1):
        line = re.sub(r'^\s*>\s?', '', original)
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if marker:
            token = marker[1]
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = ''
            continue
        if fence:
            continue
        line = re.sub(r'`[^`]*`', '', line)
        if re.search(r'<\s*/?\s*(?:sub|sup)\b', line, re.I):
            result.append(f'{number}: prefer MathJax to HTML sub/sup for mathematical quantities')
        dollars = re.sub(r'\\\$', '', line)
        if '$$' in dollars:
            if dollars.strip() != '$$':
                result.append(f'{number}: display delimiters must occupy separate lines')
            if dollars.count('$$') % 2:
                display_open = not display_open
            continue
        if display_open:
            continue
        if dollars.count('$') % 2:
            result.append(f'{number}: unbalanced inline math delimiters (check currency manually)')
        prose = re.sub(r'\$[^$]*\$', '', dollars)
        prose = re.sub(r'!?\[\[[^\]]*\]\]|\[[^\]]*\]\([^)]*\)', '', prose)
        if re.search(r'\b[A-Z](?:_[A-Za-z0-9{}]+|\^[A-Za-z0-9{}]+)\b', prose):
            result.append(f'{number}: possible raw subscript/superscript outside math')
    if display_open:
        result.append('unclosed display math delimiters')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('notes', nargs='+', type=Path)
    args = parser.parse_args(argv)
    report = {str(path): issues(path.read_text(encoding='utf-8-sig')) for path in args.notes}
    print(json.dumps(report, indent=2))
    return int(any(report.values()))


if __name__ == '__main__':
    raise SystemExit(main())
