"""Mechanical lint for teaching blocks and layered lecture notes.

It checks what a program can check: is the one idea short and in words, is a term used before it is introduced, is a
paragraph too long to read in a lesson, does a formula come before its words, is there a visual or a stated reason, is the
spoken script free of notation. It cannot judge whether the teaching is good, correct or clear, and says so in its output.
Every finding is a warning except a malformed card, which the gate already reports as an error. Nothing is written.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

import html_sessions as hs
import terms as ledger
import tutor_gate as tg
from common import parse_frontmatter

MAX_CORE_WORDS, MAX_CORE_SENTENCES = 40, 2
MAX_PARAGRAPH_WORDS = 80
MAX_DISPLAY_FORMULAS = 3
MAX_SPOKEN_WORDS = 220  # about 90 seconds at a measured pace
MAX_L0_WORDS = 30
MAX_FIRST_SCREEN_WORDS = 400
MIN_L1_QUESTIONS = 3
NEEDS_PREDICTION = {'concept', 'intuition', 'derivation'}
SPOKEN_NOTATION = re.compile(r'[$\\^_{}=<>]')
NOTE_NOTE = ('Mechanical checks only: this does not judge whether the teaching is correct, clear or well paced, '
             'and a clean lint is not evidence that anything was learned.')


def finding(code, where, message):
    return {'code': code, 'where': where, 'message': message, 'severity': 'warning'}


def words(text: str) -> int:
    return len(re.findall(r"[\w'’-]+", text, flags=re.UNICODE))


def sentences(text: str) -> int:
    return len([s for s in re.split(r'(?<=[.!?])\s+', text.strip()) if re.search(r'\w', s)])


def _level(line: str) -> int:
    match = re.match(r'(#{1,6})\s', line)
    return len(match[1]) if match else 7


def split_prose(lines):
    """Prose of a section as (paragraphs, display_formula_count, first_element_is_formula).

    Display math ($$ ... $$) is counted and left out of the words; each list item is its own paragraph.
    """
    paragraphs, current, formulas, in_math, first = [], [], 0, False, None

    def flush():
        if current:
            paragraphs.append(' '.join(current))
            current.clear()

    for raw in lines:
        line = raw.strip()
        stripped = re.sub(r'^(?:>\s?)+', '', line).strip()
        if stripped.startswith('$$') or in_math:
            if not in_math:
                flush()
                formulas += 1
                first = 'formula' if first is None else first
                in_math = not (stripped.count('$$') >= 2)
            elif '$$' in stripped:
                in_math = False
            continue
        if not stripped:
            flush()
            continue
        if stripped.startswith('|') or re.fullmatch(r'[-*_]{3,}', stripped) or stripped.startswith('[!') or stripped.startswith('<!--'):
            flush()
            continue
        first = 'words' if first is None else first
        if re.match(r'(?:[-*+]|\d+[.)])\s+', stripped):
            flush()
            stripped = re.sub(r'^(?:[-*+]|\d+[.)])\s+', '', stripped)
        current.append(stripped)
    flush()
    return paragraphs, formulas, first == 'formula'


def sections(state):
    """(problems, [(block, prose lines of its section)]) in document order, for the blocks that can be located."""
    problems, located = tg.block_issues(state)
    lines, _ = tg._lines(state)
    marked = [(n, text) for n, heading, text in hs.prose_lines(lines) if heading]
    result = []
    for block, start in located:
        level = _level(lines[start])
        end = next((n for n, _ in marked if n > start and _level(lines[n]) <= level), len(lines))
        body = [text for n, heading, text in hs.prose_lines(lines[:end]) if n > start and not heading]
        result.append((block, body))
    return problems, result


def _mentions(text: str, term: str) -> bool:
    return bool(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text, flags=re.IGNORECASE | re.UNICODE))


def lint_blocks(state, glossary=None, term_states=None, lang=None, require_spoken=False):
    """Findings for the declared teaching blocks of a session."""
    problems, found = sections(state)
    out = [p for p in problems if p['code'].startswith(('CARD', 'BLOCK_TERMS'))]
    texts = [' '.join(re.sub(r'\$[^$]*\$', ' ', line) for line in body) for _, body in found]
    for index, (block, body) in enumerate(found):
        where, card = block['id'], block.get('card')
        paragraphs, formulas, formula_first = split_prose(body)
        if not isinstance(card, dict):
            out.append(finding('CARD_MISSING', where, f"'{block['heading']}' has no Teaching Card: the reader meets the section as it is written, with no one-idea summary first"))
        else:
            core = ' '.join(str(card.get('core_idea', '')).split())
            if words(core) > MAX_CORE_WORDS or sentences(core) > MAX_CORE_SENTENCES:
                out.append(finding('CORE_IDEA_LONG', where, f'core idea is {words(core)} words in {sentences(core)} sentences; keep it to {MAX_CORE_SENTENCES} sentences and {MAX_CORE_WORDS} words'))
            if block['kind'] in NEEDS_PREDICTION and not card.get('predict'):
                out.append(finding('PREDICT_MISSING', where, 'no predict-first prompt on a concept, intuition or derivation block'))
            if block['kind'] in tg.EXPLAINING and not card.get('retrieve'):
                out.append(finding('RETRIEVE_MISSING', where, 'no retrieval prompt for the end of the section'))
            marker = any('resource:' in line or '![[' in line or 'ros-widget:' in line for line in body)
            if not (card.get('visual') or card.get('no_visual_reason') or marker):
                out.append(finding('NO_VISUAL', where, 'no figure or widget in the section, and the card gives no reason for having none'))
            spoken = card.get('spoken') if isinstance(card.get('spoken'), dict) else {}
            if require_spoken and not spoken:
                out.append(finding('SPOKEN_MISSING', where, 'no spoken script on the card'))
            if lang and spoken and lang not in spoken:
                out.append(finding('SPOKEN_LANGUAGE', where, f'the card has spoken scripts for {", ".join(sorted(spoken))} but not {lang}'))
            for code, script in spoken.items():
                if SPOKEN_NOTATION.search(script):
                    out.append(finding('SPOKEN_HAS_MATH', where, f'spoken[{code}] contains notation; write formulas out in words'))
                if words(script) > MAX_SPOKEN_WORDS:
                    out.append(finding('SPOKEN_LONG', where, f'spoken[{code}] is {words(script)} words; split the section (limit {MAX_SPOKEN_WORDS})'))
        if formula_first:
            out.append(finding('FORMULA_FIRST', where, f"'{block['heading']}' opens with a formula; put the idea in words first"))
        if formulas > MAX_DISPLAY_FORMULAS:
            out.append(finding('FORMULA_DENSITY', where, f'{formulas} display formulas in one section (limit {MAX_DISPLAY_FORMULAS}); split it'))
        for paragraph in paragraphs:
            if words(paragraph) > MAX_PARAGRAPH_WORDS:
                out.append(finding('LONG_PARAGRAPH', where, f'a paragraph of {words(paragraph)} words ("{paragraph[:40]}…"); keep paragraphs under {MAX_PARAGRAPH_WORDS}'))
        own = set(block.get('introduces') or {})
        for later, _ in found[index + 1:]:
            for term in (later.get('introduces') or {}):
                if term not in own and _mentions(texts[index], term):
                    out.append(finding('TERM_BEFORE_INTRO', where, f"'{term}' is used in '{block['heading']}' before '{later['heading']}' introduces it"))
        if glossary and term_states is not None:
            declared = set()
            for word in list(block.get('terms') or []) + list(own):
                try:
                    declared.add(ledger.term_id(word))
                except ValueError:
                    pass
            for key, entry in glossary.items():
                if key in declared:
                    continue
                label = entry['labels'].get(lang) if lang else None
                names = [label] if label else list(entry['labels'].values())
                if any(_mentions(texts[index], n) for n in names) and ledger.best_state(term_states.get(key, {}), lang) not in ledger.KNOWN:
                    out.append(finding('UNDECLARED_TERM', where, f"the text uses '{names[0]}', which is not declared in this block's terms and is not recorded as known for this learner"))
    return {'blocks': len(found), 'issues': out, 'warnings': len([i for i in out if i['severity'] != 'error']), 'note': NOTE_NOTE}


# ------------------------------------------------------------------------------------------------ lecture notes

LAYER = re.compile(r'##\s+L([0-3])\b')
PLACEHOLDER = re.compile(r'\{\{[^{}]*\}\}')


def _layers(lines):
    marks = [(n, int(m[1])) for n, line in enumerate(lines) if (m := LAYER.match(line))]
    return {layer: lines[n + 1:(marks[i + 1][0] if i + 1 < len(marks) else len(lines))] for i, (n, layer) in enumerate(marks)}, [layer for _, layer in marks]


def lint_note(text: str):
    """Findings for a layered lecture note: L0 gist, L1 core in 60 seconds (retrieval), L2 lecture, L3 derivation and sources."""
    meta, body = parse_frontmatter(text.replace('\r\n', '\n'))
    lines = body.split('\n')
    out = []
    if meta.get('type') != 'lecture-note':
        out.append(finding('NOTE_TYPE', 'frontmatter', 'type should be lecture-note'))
    for key in ('concept', 'up'):
        value = meta.get(key)
        if not value or value in ('""', "''", '[]'):
            out.append(finding('NOTE_FRONTMATTER', 'frontmatter', f'{key} is empty: a lecture note belongs to a concept and links up the graph'))
    layers, order = _layers(lines)
    if order != [0, 1, 2, 3]:
        out.append({'code': 'NOTE_LAYERS', 'where': 'headings', 'severity': 'error',
                    'message': 'a lecture note has the sections L0, L1, L2 and L3 once each, in that order (found: ' + (', '.join(f'L{n}' for n in order) or 'none') + ')'})
        return {'issues': out, 'warnings': len(out) - 1, 'errors': 1, 'note': NOTE_NOTE}
    gist_lines, word_lines, in_words = [], [], False
    for line in layers[0]:
        if re.match(r'###\s+Words you need', line):
            in_words = True
            continue
        (word_lines if in_words else gist_lines).append(line)
    gist = ' '.join(l.strip() for l in gist_lines if l.strip())
    if not gist:
        out.append(finding('NOTE_L0_EMPTY', 'L0', 'L0 has no gist'))
    elif words(gist) > MAX_L0_WORDS:
        out.append(finding('NOTE_L0_LONG', 'L0', f'the gist is {words(gist)} words; keep it to one sentence of at most {MAX_L0_WORDS}'))
    bullets = [l for l in word_lines if re.match(r'\s*[-*]\s+', l)]
    if not in_words:
        out.append(finding('NOTE_WORDS_MISSING', 'L0', 'no "Words you need" list under the gist'))
    elif any(not re.match(r'\s*[-*]\s+\*\*[^*]+\*\*\s+[—-]\s+\S', l) for l in bullets):
        out.append(finding('NOTE_WORDS_FORMAT', 'L0', 'write each word as "- **term** — one line"'))
    questions, open_ones, unanswered = 0, 0, 0
    l1 = layers[1]
    for n, line in enumerate(l1):
        match = re.match(r'>\s*\[!question\]([+-]?)\s*(.*)', line)
        if not match:
            continue
        questions += 1
        if match[1] != '-':
            open_ones += 1
        answer = []
        for follow in l1[n + 1:]:
            if not follow.startswith('>'):
                break
            answer.append(re.sub(r'^>\s?', '', follow).strip())
        if not any(answer) or PLACEHOLDER.search(' '.join(answer)):
            unanswered += 1
    if questions < MIN_L1_QUESTIONS:
        out.append(finding('NOTE_L1_QUESTIONS', 'L1', f'{questions} question callouts; write at least {MIN_L1_QUESTIONS} so the first screen is retrieval, not a summary to reread'))
    if open_ones:
        out.append(finding('NOTE_L1_OPEN', 'L1', f'{open_ones} question(s) show their answer; use [!question]- so the answer is collapsed until tried'))
    if unanswered:
        out.append(finding('NOTE_L1_ANSWER', 'L1', f'{unanswered} question(s) have no answer text'))
    first_screen = words(gist) + sum(words(l) for l in word_lines) + sum(words(re.sub(r'^>\s*\[!question\][+-]?', '', l)) for l in l1 if re.match(r'>\s*\[!question\]', l))
    if first_screen > MAX_FIRST_SCREEN_WORDS:
        out.append(finding('NOTE_FIRST_SCREEN', 'L0-L1', f'the first screen (L0 and the L1 questions) is {first_screen} words; keep it under {MAX_FIRST_SCREEN_WORDS}'))
    for layer, name in ((2, 'lecture'), (3, 'derivation and sources')):
        if not any(l.strip() for l in layers[layer]):
            out.append(finding(f'NOTE_L{layer}_EMPTY', f'L{layer}', f'L{layer} ({name}) is empty'))
    if not re.search(r'https?://|\[\[|doi|arxiv', '\n'.join(layers[3]), re.I):
        out.append(finding('NOTE_L3_SOURCES', 'L3', 'L3 names no source: add a link, a [[note]] or an identifier'))
    placeholders = len(PLACEHOLDER.findall(body))
    if placeholders:
        out.append(finding('NOTE_PLACEHOLDER', 'note', f'{placeholders} unfilled template placeholder(s)'))
    return {'issues': out, 'warnings': len(out), 'errors': 0, 'note': NOTE_NOTE}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    b = sub.add_parser('blocks', help="lint a session's declared teaching blocks")
    b.add_argument('--root', type=Path, required=True)
    b.add_argument('session')
    b.add_argument('--lang')
    b.add_argument('--require-spoken', action='store_true')
    b.add_argument('--strict', action='store_true', help='exit 1 on any finding, not only errors')
    n = sub.add_parser('note', help='lint a layered lecture note')
    n.add_argument('file', type=Path)
    n.add_argument('--strict', action='store_true')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        if args.command == 'blocks':
            state = hs.load_session(args.root, args.session)
            directory = ledger.learner_dir(args.root)
            glossary, _ = ledger.load_glossary(directory)
            events, _ = ledger.load_events(directory)
            result = lint_blocks(state, glossary, ledger.term_states(events) if events or glossary else None, args.lang, args.require_spoken)
        else:
            result = lint_note(args.file.read_text(encoding='utf-8'))
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    errors = [i for i in result['issues'] if i['severity'] == 'error']
    return 1 if errors or (args.strict and result['issues']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
