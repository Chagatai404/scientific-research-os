"""Board scripts: the lecture a tutor performs on the blackboard widget, as plain JSON that any agent can write and the repository checks.

Standard library only. A script is an ordered list of steps; each step has one spoken sentence (``say``) and actions (``do``) that start while it is
spoken: write text, write a formula, draw a path, an arrow, a circle, a rectangle, axes or a curve, place a dot and move it, highlight, erase. Cues bind
to sentences, never to clock time, so a slow voice cannot desynchronise the board. The renderer (``assets/html-runtime/board.js``) enforces the same
rules; ``tests/fixtures/board-cases.json`` holds the cases both must agree on.

Agents write these, so a script is untrusted data: text only ever becomes text, a path is parsed into numbers and rebuilt, a colour and a size are names
from a fixed table, and nothing in a script can be markup, a URL or a style.

    python board_script.py check script.json        exit 0 if valid, 1 and the problems if not
    python board_script.py speech script.json       the sentences to speak, one per line
"""
from __future__ import annotations
import argparse
import json
import math
import re
import sys
from pathlib import Path

SCHEMA = 1
WIDTH, HEIGHT = 160, 90                      # board units; the page scales them
COLORS = ('chalk', 'yellow', 'blue', 'green', 'pink', 'orange')
SIZES = ('small', 'medium', 'large', 'huge')
HANDS = ('kalam', 'patrick', 'caveat', 'kalam-patrick', 'patrick-kalam')   # the last two pair a title font with a body font
DEFAULT_HAND = 'kalam'                                                       # chosen by the researcher over Patrick Hand (too casual) on 2026-10-17
MAX_STEPS, MAX_ACTIONS_PER_STEP, MAX_ACTIONS = 200, 12, 1500
MAX_SAY, MAX_TEXT, MAX_TEX, MAX_PATH, MAX_NUMBERS, MAX_POINTS = 600, 300, 400, 1500, 300, 400
ID = re.compile(r'[A-Za-z0-9_-]{1,64}')
ARITY = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'C': 6, 'S': 4, 'Q': 4, 'T': 2, 'Z': 0}
PATH_TOKEN = re.compile(r'([MLHVCSQTZ])|(-?\d+(?:\.\d+)?)')
CONTROL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')

COMMON = ('op', 'id', 'delay', 'duration')
# Text and formulas are placed either at a point (``at``, optionally wrapped to a width ``w``) or in a named zone of the board (``zone``), where they stack from
# the top of the zone, wrap to its width and push the next item down. Drawings always use board coordinates. (x, y, width, height) in board units.
ZONES = {'title': (5, 2, 150, 15), 'left': (5, 18, 60, 62), 'right': (70, 18, 85, 62), 'body': (5, 18, 150, 62), 'caption': (5, 81, 150, 8)}
OPS = {
    'write': ('text', 'at', 'zone', 'w', 'size', 'color'),
    'math': ('tex', 'at', 'zone', 'w', 'size', 'color'),
    'draw': ('path', 'color', 'width'),
    'arrow': ('from', 'to', 'color', 'width'),
    'circle': ('at', 'r', 'color', 'width'),
    'rect': ('at', 'w', 'h', 'color', 'width'),
    'axes': ('at', 'w', 'h', 'color', 'width'),
    'plot': ('points', 'color', 'width'),
    'dot': ('at', 'r', 'color'),
    'move': ('target', 'path'),
    'highlight': ('target', 'color'),
    'erase': ('target',),
}
REQUIRED = {'write': ('text',), 'math': ('tex',), 'draw': ('path',), 'arrow': ('from', 'to'), 'circle': ('at', 'r'), 'rect': ('at', 'w', 'h'),
            'axes': ('at', 'w', 'h'), 'plot': ('points',), 'dot': ('at',), 'move': ('target', 'path'), 'highlight': ('target',), 'erase': ('target',)}


def _number(value, low: float, high: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and low <= value <= high


def _point(value) -> bool:
    return isinstance(value, list) and len(value) == 2 and _number(value[0], 0, WIDTH) and _number(value[1], 0, HEIGHT)


def path_problem(d) -> str | None:
    """Why a path is refused, or None. Only absolute M L H V C S Q T Z and numbers; the page rebuilds the string from these tokens."""
    if not isinstance(d, str) or not 1 <= len(d) <= MAX_PATH:
        return f'path must be text of 1 to {MAX_PATH} characters'
    leftover = re.sub(r'[\s,]', '', PATH_TOKEN.sub('', d))
    if leftover:
        return f"path: unsupported command '{leftover[0]}'" if leftover[0].isalpha() else f"path has unsupported text '{leftover[0]}'"
    tokens = [m.group(0) for m in PATH_TOKEN.finditer(d)]
    if not tokens or tokens[0] != 'M':
        return 'path must start with M'
    numbers, command, count = 0, None, 0

    def close() -> str | None:
        if command is not None and ARITY[command] and (count == 0 or count % ARITY[command]):
            return f'path: wrong number of values for {command}'
        return None
    for token in tokens:
        if token in ARITY:
            problem = close()
            if problem:
                return problem
            command, count = token, 0
        else:
            if not -200 <= float(token) <= 400:
                return 'path numbers must be between -200 and 400'
            numbers, count = numbers + 1, count + 1
            if numbers > MAX_NUMBERS:
                return f'path has too many numbers (at most {MAX_NUMBERS})'
            if command == 'Z':
                return 'path: Z takes no values'
    return close()


def _check_action(action, where: str, known: set, problems: list) -> None:
    if not isinstance(action, dict):
        problems.append(f'{where}: an action must be an object')
        return
    op = action.get('op')
    if op not in OPS:
        problems.append(f"{where}: unknown op '{op}'")
        return
    for key in action:
        if key not in COMMON and key not in OPS[op]:
            problems.append(f"{where}: unknown key '{key}'")
    for key in REQUIRED[op]:
        if key not in action:
            problems.append(f"{where}: {op} needs '{key}'")
    if op in ('write', 'math'):
        if 'at' not in action and 'zone' not in action:
            problems.append(f"{where}: {op} needs 'at' (a point) or 'zone' ({', '.join(ZONES)})")
        elif 'at' in action and 'zone' in action:
            problems.append(f"{where}: {op} takes 'at' or 'zone', not both")
        if 'zone' in action and not (isinstance(action['zone'], str) and action['zone'] in ZONES):
            problems.append(f"{where}.zone: zone must be one of {', '.join(ZONES)}")
        if 'w' in action and 'at' not in action:
            problems.append(f"{where}.w: w sets the width of text placed with 'at'; a zone has its own width")
    defined = None
    if 'id' in action:
        ident = action['id']
        if not isinstance(ident, str) or not ID.fullmatch(ident):
            problems.append(f'{where}.id: id must be 1 to 64 letters, digits, - or _')
        elif ident in known or ident == 'all':
            problems.append(f"{where}.id: duplicate id '{ident}'")
        else:
            defined = ident
    if 'delay' in action and not _number(action['delay'], 0, 60):
        problems.append(f'{where}.delay: delay must be a number from 0 to 60')
    if 'duration' in action and not _number(action['duration'], 0.1, 30):
        problems.append(f'{where}.duration: duration must be a number from 0.1 to 30')
    if 'color' in action and action['color'] not in COLORS:
        problems.append(f'{where}.color: color must be one of {", ".join(COLORS)}')
    if 'size' in action and action['size'] not in SIZES:
        problems.append(f'{where}.size: size must be one of {", ".join(SIZES)}')
    if 'width' in action and not _number(action['width'], 0.2, 2.0):
        problems.append(f'{where}.width: width must be a number from 0.2 to 2')
    for key in ('at', 'from', 'to'):
        if key in action and not _point(action[key]):
            problems.append(f'{where}.{key}: {key} must be [x, y] with x 0 to {WIDTH} and y 0 to {HEIGHT}')
    for key, high in (('r', 80), ('w', WIDTH), ('h', HEIGHT)):
        if key in action and not _number(action[key], 0.2 if key == 'r' else 1, high):
            problems.append(f'{where}.{key}: {key} must be a number up to {high}')
    for key, limit in (('text', MAX_TEXT), ('tex', MAX_TEX)):
        if key in action and (not isinstance(action[key], str) or not 1 <= len(action[key]) <= limit or CONTROL.search(action[key])):
            problems.append(f'{where}.{key}: {key} must be 1 to {limit} characters of text')
    if 'path' in action:
        problem = path_problem(action['path'])
        if problem:
            problems.append(f'{where}.path: {problem}')
    if 'points' in action:
        points = action['points']
        if not (isinstance(points, list) and 2 <= len(points) <= MAX_POINTS and all(_point(p) for p in points)):
            problems.append(f'{where}.points: points must be 2 to {MAX_POINTS} [x, y] pairs inside the board')
    if 'target' in action:
        target = action['target']
        if target != 'all' and (not isinstance(target, str) or target not in known):
            problems.append(f"{where}.target: target '{target}' is not defined earlier")
        elif op in ('move', 'highlight') and target == 'all':
            problems.append(f"{where}.target: {op} needs one element, not 'all'")
    if defined:
        known.add(defined)


def validate(script) -> list[str]:
    """Every problem found, each starting with where it is. An empty list means the script is valid."""
    problems: list[str] = []
    if not isinstance(script, dict):
        return ['a board script must be an object']
    if script.get('board_schema') != SCHEMA:
        problems.append(f'board_schema must be {SCHEMA}')
    for key in script:
        if key not in ('board_schema', 'hand', 'open', 'steps'):
            problems.append(f"unknown key '{key}'")
    if 'hand' in script and script['hand'] not in HANDS:
        problems.append(f'hand must be one of {", ".join(HANDS)}')
    if 'open' in script and not isinstance(script['open'], bool):
        problems.append('open must be true or false')
    steps = script.get('steps')
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        problems.append(f'steps must be a list of 1 to {MAX_STEPS} steps')
        return problems
    known, step_ids, total = set(), set(), 0
    for i, step in enumerate(steps):
        where = f'steps[{i}]'
        if not isinstance(step, dict):
            problems.append(f'{where}: a step must be an object')
            continue
        for key in step:
            if key not in ('id', 'say', 'do'):
                problems.append(f"{where}: unknown key '{key}'")
        ident = step.get('id')
        if not isinstance(ident, str) or not ID.fullmatch(ident):
            problems.append(f'{where}.id: id must be 1 to 64 letters, digits, - or _')
        elif ident in step_ids:
            problems.append(f"{where}.id: duplicate id '{ident}'")
        else:
            step_ids.add(ident)
        say, actions = step.get('say', ''), step.get('do', [])
        if not isinstance(say, str) or len(say) > MAX_SAY or CONTROL.search(say):
            problems.append(f'{where}.say: say must be text of at most {MAX_SAY} characters')
        if not isinstance(actions, list) or len(actions) > MAX_ACTIONS_PER_STEP:
            problems.append(f'{where}.do: do must be a list of at most {MAX_ACTIONS_PER_STEP} actions')
            continue
        if not (isinstance(say, str) and say.strip()) and not actions:
            problems.append(f'{where}: a step needs speech or an action')
        total += len(actions)
        for j, action in enumerate(actions):
            _check_action(action, f'{where}.do[{j}]', known, problems)
    if total > MAX_ACTIONS:
        problems.append(f'a script may have at most {MAX_ACTIONS} actions')
    return problems


# --------------------------------------------------------------------------------------------------------------------------- layout (mirrors board.js)
# Where text and drawings go and whether they fit. A script is checked before it is shown, with text extents estimated from the hand's glyph widths; the page
# places each item with the extents it measured instead, and shifts new text to the next free slot. All numbers are board units (160 x 90). The estimates describe
# the default hand (Kalam) only. tests/fixtures/board-cases.json pins both implementations to the same cases.
# Advance widths of Kalam in 1/1000 em, measured in real Chrome by tests/board-metrics-probe.cjs: ascii is U+0020..U+007E, extra is the rest of Latin-1 and Latin Extended-A.
FONT = {
    'regular': {'ascii': [401,371,331,656,534,890,704,145,485,504,357,600,228,459,237,354,500,314,581,571,551,537,556,461,602,488,246,306,539,631,561,518,965,608,637,599,645,585,523,611,670,310,468,591,546,789,677,613,543,641,584,531,535,598,532,782,624,575,620,453,600,450,422,608,213,469,525,445,499,450,376,475,536,238,254,469,245,796,533,453,478,474,331,426,387,481,422,673,427,469,440,421,368,538,594], 'extra': {" ": 401, "¡": 354, "¢": 482, "£": 657, "¤": 600, "¥": 563, "¦": 369, "§": 464, "¨": 273, "©": 708, "ª": 474, "«": 657, "¬": 496, "®": 589, "¯": 365, "°": 339, "±": 600, "²": 308, "³": 311, "´": 219, "µ": 575, "¶": 521, "·": 237, "¸": 252, "¹": 154, "º": 452, "»": 833, "¼": 783, "½": 787, "¾": 876, "¿": 380, "À": 608, "Á": 608, "Â": 608, "Ã": 608, "Ä": 608, "Å": 608, "Æ": 831, "Ç": 603, "È": 585, "É": 585, "Ê": 585, "Ë": 585, "Ì": 310, "Í": 310, "Î": 310, "Ï": 310, "Ð": 619, "Ñ": 677, "Ò": 613, "Ó": 613, "Ô": 613, "Õ": 613, "Ö": 613, "×": 488, "Ø": 613, "Ù": 592, "Ú": 592, "Û": 592, "Ü": 592, "Ý": 575, "Þ": 503, "ß": 585, "à": 472, "á": 472, "â": 472, "ã": 472, "ä": 472, "å": 472, "æ": 743, "ç": 447, "è": 438, "é": 438, "ê": 438, "ë": 438, "ì": 238, "í": 238, "î": 238, "ï": 238, "ð": 452, "ñ": 532, "ò": 452, "ó": 452, "ô": 452, "õ": 452, "ö": 452, "÷": 600, "ø": 457, "ù": 479, "ú": 479, "û": 479, "ü": 479, "ý": 469, "þ": 526, "ÿ": 469, "Ā": 608, "ā": 472, "Ă": 608, "ă": 472, "Ą": 608, "ą": 472, "Ć": 685, "ć": 447, "Ĉ": 667, "ĉ": 444, "Ċ": 667, "ċ": 444, "Č": 692, "č": 447, "Ď": 645, "ď": 732, "Đ": 625, "đ": 508, "Ē": 585, "ē": 438, "Ĕ": 611, "ĕ": 444, "Ė": 585, "ė": 438, "Ę": 585, "ę": 438, "Ě": 585, "ě": 438, "Ĝ": 722, "ĝ": 500, "Ğ": 611, "ğ": 471, "Ġ": 722, "ġ": 500, "Ģ": 611, "ģ": 471, "Ĥ": 722, "ĥ": 500, "Ħ": 722, "ħ": 500, "Ĩ": 333, "ĩ": 278, "Ī": 310, "ī": 238, "Ĭ": 333, "ĭ": 278, "Į": 310, "į": 238, "İ": 310, "ı": 260, "Ĳ": 708, "ĳ": 552, "Ĵ": 389, "ĵ": 278, "Ķ": 602, "ķ": 495, "ĸ": 500, "Ĺ": 546, "ĺ": 234, "Ļ": 546, "ļ": 234, "Ľ": 546, "ľ": 448, "Ŀ": 611, "ŀ": 344, "Ł": 514, "ł": 362, "Ń": 677, "ń": 532, "Ņ": 677, "ņ": 532, "Ň": 677, "ň": 532, "ŉ": 604, "Ŋ": 702, "ŋ": 495, "Ō": 613, "ō": 452, "Ŏ": 722, "ŏ": 500, "Ő": 613, "ő": 452, "Œ": 940, "œ": 906, "Ŕ": 575, "ŕ": 318, "Ŗ": 575, "ŗ": 326, "Ř": 575, "ř": 318, "Ś": 526, "ś": 426, "Ŝ": 556, "ŝ": 389, "Ş": 539, "ş": 426, "Š": 526, "š": 426, "Ţ": 521, "ţ": 364, "Ť": 521, "ť": 432, "Ŧ": 611, "ŧ": 278, "Ũ": 722, "ũ": 500, "Ū": 592, "ū": 479, "Ŭ": 722, "ŭ": 500, "Ů": 592, "ů": 479, "Ű": 592, "ű": 479, "Ų": 579, "ų": 479, "Ŵ": 944, "ŵ": 722, "Ŷ": 722, "ŷ": 500, "Ÿ": 575, "Ź": 620, "ź": 432, "Ż": 620, "ż": 432, "Ž": 620, "ž": 432, "ſ": 278, "‐": 333, "‑": 333, "‒": 500, "–": 610, "—": 917, "―": 1000, "‖": 281, "‗": 500, "‘": 287, "’": 286, "‚": 291, "‛": 333, "“": 491, "”": 487, "„": 485, "‟": 444, "†": 403, "‡": 500, "•": 237, "‣": 350, "․": 333, "‥": 666, "…": 666, "‧": 250}},
    'bold': {'ascii': [385,478,484,780,592,991,786,220,478,530,375,600,262,531,237,282,513,302,583,547,545,506,542,472,590,506,246,306,475,672,616,608,1078,630,624,617,666,551,542,597,651,309,486,602,546,756,631,619,549,659,601,552,544,595,532,785,585,561,646,463,600,521,422,619,258,510,567,489,539,488,435,481,563,260,260,493,266,819,554,456,538,519,362,467,451,486,422,710,474,520,480,462,456,626,586], 'extra': {" ": 385, "¡": 425, "¢": 545, "£": 732, "¤": 600, "¥": 615, "¦": 455, "§": 529, "¨": 335, "©": 708, "ª": 536, "«": 426, "¬": 496, "®": 671, "¯": 377, "°": 421, "±": 600, "²": 335, "³": 300, "´": 266, "µ": 439, "¶": 592, "·": 237, "¸": 301, "¹": 161, "º": 452, "»": 833, "¼": 823, "½": 858, "¾": 962, "¿": 396, "À": 631, "Á": 631, "Â": 631, "Ã": 631, "Ä": 631, "Å": 631, "Æ": 899, "Ç": 629, "È": 551, "É": 551, "Ê": 551, "Ë": 551, "Ì": 309, "Í": 309, "Î": 309, "Ï": 309, "Ð": 649, "Ñ": 631, "Ò": 619, "Ó": 619, "Ô": 619, "Õ": 619, "Ö": 619, "×": 433, "Ø": 619, "Ù": 578, "Ú": 578, "Û": 578, "Ü": 578, "Ý": 561, "Þ": 535, "ß": 599, "à": 518, "á": 518, "â": 518, "ã": 518, "ä": 518, "å": 518, "æ": 770, "ç": 493, "è": 454, "é": 454, "ê": 454, "ë": 454, "ì": 260, "í": 260, "î": 260, "ï": 260, "ð": 452, "ñ": 552, "ò": 452, "ó": 452, "ô": 452, "õ": 452, "ö": 452, "÷": 600, "ø": 452, "ù": 479, "ú": 479, "û": 479, "ü": 479, "ý": 520, "þ": 526, "ÿ": 520, "Ā": 631, "ā": 518, "Ă": 631, "ă": 518, "Ą": 631, "ą": 518, "Ć": 629, "ć": 493, "Ĉ": 722, "ĉ": 444, "Ċ": 722, "ċ": 444, "Č": 629, "č": 493, "Ď": 666, "ď": 779, "Đ": 666, "đ": 508, "Ē": 551, "ē": 454, "Ĕ": 667, "ĕ": 444, "Ė": 551, "ė": 454, "Ę": 551, "ę": 454, "Ě": 551, "ě": 454, "Ĝ": 778, "ĝ": 500, "Ğ": 597, "ğ": 471, "Ġ": 778, "ġ": 500, "Ģ": 597, "ģ": 471, "Ĥ": 778, "ĥ": 556, "Ħ": 778, "ħ": 556, "Ĩ": 389, "ĩ": 278, "Ī": 309, "ī": 260, "Ĭ": 389, "ĭ": 278, "Į": 309, "į": 260, "İ": 309, "ı": 260, "Ĳ": 823, "ĳ": 552, "Ĵ": 500, "ĵ": 333, "Ķ": 602, "ķ": 495, "ĸ": 556, "Ĺ": 546, "ĺ": 234, "Ļ": 546, "ļ": 234, "Ľ": 546, "ľ": 501, "Ŀ": 667, "ŀ": 396, "Ł": 546, "ł": 383, "Ń": 631, "ń": 552, "Ņ": 631, "ņ": 552, "Ň": 631, "ň": 552, "ŉ": 729, "Ŋ": 769, "ŋ": 556, "Ō": 619, "ō": 452, "Ŏ": 778, "ŏ": 500, "Ő": 619, "ő": 452, "Œ": 950, "œ": 906, "Ŕ": 575, "ŕ": 326, "Ŗ": 575, "ŗ": 326, "Ř": 575, "ř": 326, "Ś": 539, "ś": 467, "Ŝ": 556, "ŝ": 389, "Ş": 539, "ş": 467, "Š": 539, "š": 467, "Ţ": 505, "ţ": 364, "Ť": 505, "ť": 522, "Ŧ": 667, "ŧ": 333, "Ũ": 722, "ũ": 556, "Ū": 578, "ū": 479, "Ŭ": 722, "ŭ": 556, "Ů": 578, "ů": 479, "Ű": 578, "ű": 479, "Ų": 543, "ų": 479, "Ŵ": 1000, "ŵ": 722, "Ŷ": 722, "ŷ": 500, "Ÿ": 561, "Ź": 646, "ź": 459, "Ż": 646, "ż": 459, "Ž": 646, "ž": 459, "ſ": 278, "‐": 333, "‑": 333, "‒": 500, "–": 624, "—": 968, "―": 1000, "‖": 324, "‗": 500, "‘": 352, "’": 352, "‚": 346, "‛": 333, "“": 606, "”": 595, "„": 569, "‟": 500, "†": 539, "‡": 500, "•": 237, "‣": 350, "․": 333, "‥": 667, "…": 795, "‧": 250}}}
FALLBACK, TRACKING = 560, 10          # an unknown character, and the letter-spacing (.01em) the board's text carries
LINE = 1.25                           # line height, as a multiple of the font size (board.css uses the same number)
GAP, PAD, STEP, EDGE = 1.5, 0.6, 1.0, 0.5    # space between stacked items, clearance when looking for a free slot, search step, margin kept from the board's edge
INSET_X, INSET_Y = 0.1, 0.2           # a line box is taller than the ink in it: the part of the font size trimmed from each side before boxes are compared
MIN_SHRINK, MATH_EM = 0.6, 1.05       # a formula that is too wide shrinks to at least this fraction; the formula's em as a multiple of the item's font size (board.css)
SIZE_PERCENT = {'small': 2.3, 'medium': 3.2, 'large': 4.6, 'huge': 6.8}   # font size as a percentage of the board width (board.js SIZES)


def _font_units(size: str) -> float:
    return SIZE_PERCENT.get(size, SIZE_PERCENT['medium']) * WIDTH / 100


def _advance(ch: str, bold: bool) -> int:
    table = FONT['bold' if bold else 'regular']
    code = ord(ch)
    return (table['ascii'][code - 32] if 32 <= code <= 126 else table['extra'].get(ch, FALLBACK)) + TRACKING


def _text_width(text: str, fs: float, bold: bool) -> float:
    return sum(_advance(ch, bold) for ch in text) / 1000 * fs


def wrap_text(text: str, fs: float, bold: bool, max_width: float) -> dict:
    """Greedy wrapping at spaces, the way the page wraps; a word wider than the line is not split here, it is reported as too wide."""
    space = _advance(' ', bold) / 1000 * fs
    lines, widest, too_wide = 0, 0.0, False
    for paragraph in str(text).split('\n'):
        current, started = 0.0, False
        lines += 1
        for word in paragraph.split(' '):
            w = _text_width(word, fs, bold)
            if w > max_width + 1e-9:
                too_wide = True
            if not started:
                current, started = w, True
            elif current + space + w <= max_width + 1e-9:
                current += space + w
            else:
                widest = max(widest, current)
                lines += 1
                current = w
        widest = max(widest, current)
    return {'width': widest, 'height': lines * LINE * fs, 'lines': lines, 'too_wide': too_wide}


_GREEK = set('alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega'.split())
_GREEK_UP = set('Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega'.split())
_RELATION = set('le leq ge geq ne neq approx sim simeq equiv to rightarrow leftarrow Rightarrow Leftarrow leftrightarrow Leftrightarrow mapsto in notin subset subseteq supset supseteq propto ll gg perp parallel cong'.split())
_BINARY = set('pm mp times div cup cap setminus oplus otimes wedge vee ast star circ bullet'.split())
_NAMED = set('sin cos tan cot sec csc log ln exp lim min max sup inf det dim arg gcd deg Pr ker'.split())
_WRAPPERS = set('text textbf textit mathrm mathbf mathit mathbb mathcal mathsf mathtt boldsymbol operatorname'.split())
_ACCENTS = set('bar hat vec tilde dot ddot overline underline widehat widetilde'.split())
_SPACES = {'quad': 1, 'qquad': 2, ',': 0.17, ':': 0.22, ';': 0.28, '!': -0.17, ' ': 0.28}
_SYMBOLS = {'cdot': 0.72, 'infty': 1, 'partial': 0.57, 'nabla': 0.83, 'ldots': 1.17, 'cdots': 1.17, 'dots': 1.17, 'vdots': 0.3, 'prime': 0.3, 'hbar': 0.55, 'ell': 0.42}
_MATH_TOKEN = re.compile(r'\\[A-Za-z]+|\\[\s\S]|[{}^_]|\s+|[\s\S]')


def _glyph_em(ch: str) -> float:
    if re.fullmatch(r'[a-z]', ch):
        return 0.52
    if re.fullmatch(r'[A-Z]', ch):
        return 0.7
    if re.fullmatch(r'[0-9]', ch):
        return 0.5
    if ch in '=<>':
        return 1.33
    if ch in '+-−':
        return 1.22
    if ch in '()[]':
        return 0.39
    if ch in '|.!':
        return 0.28
    if ch in ',;':
        return 0.45
    if ch in '/:':
        return 0.52
    if ch == '*':
        return 0.8
    if ch == "'":
        return 0.3
    return 0.6


def math_box(tex: str) -> tuple[float, float]:
    """A formula's (width, height) in em, from a small reading of the TeX: good to roughly a tenth for the formulas a lecture writes, never a substitute for the page's measurement."""
    t = [s for s in _MATH_TOKEN.findall(str(tex)) if not re.fullmatch(r'\s+', s)]
    pos = [0]

    def box(w, h=1.2):
        return (w, h)

    def command(name):
        if name in ('frac', 'dfrac', 'tfrac', 'binom'):
            a, b = base(), base()
            s = 1 if name == 'dfrac' else 0.7
            return box(s * max(a[0], b[0]) + 0.2, s * 0.82 * (a[1] + b[1]))
        if name == 'sqrt':
            if pos[0] < len(t) and t[pos[0]] == '[':
                while pos[0] < len(t) and t[pos[0]] != ']':
                    pos[0] += 1
                pos[0] += 1
            a = base()
            return box(1 + a[0], max(a[1], 1.2) + 0.15)
        if name == 'left':
            pos[0] += 1
            inner = sequence(False, True)
            return box(inner[0] + 1, inner[1] * 1.25 + 0.2 if inner[1] > 1.3 else inner[1] + 0.15)
        if name == 'right':
            pos[0] += 1
            return box(0.5)
        if name in _WRAPPERS:
            return base()
        if name in _ACCENTS:
            a = base()
            return box(a[0], a[1] + 0.2)
        if name in ('sum', 'prod'):
            return box(1, 1.5)
        if name in ('int', 'oint'):
            return box(0.56, 1.8)
        if name in _SPACES:
            return box(_SPACES[name], 0)
        if name in _SYMBOLS:
            return box(_SYMBOLS[name])
        if name in _GREEK:
            return box(0.6)
        if name in _GREEK_UP:
            return box(0.72)
        if name in _RELATION:
            return box(1.33)
        if name in _BINARY:
            return box(1.22)
        if name in _NAMED:
            return box(len(name) * 0.5 + 0.28)
        return box(0.7)

    def base():
        if pos[0] >= len(t):
            return box(0, 0)
        tok = t[pos[0]]
        pos[0] += 1
        if tok == '}':
            return box(0, 0)
        if tok == '{':
            return sequence(True)
        if tok[0] == '\\':
            return command(tok[1:])
        return box(_glyph_em(tok))

    def with_scripts(b):
        up = down = None
        while pos[0] < len(t) and t[pos[0]] in ('^', '_'):
            which = t[pos[0]]
            pos[0] += 1
            s = base()
            if which == '^':
                up = s
            else:
                down = s
        if up is None and down is None:
            return b
        w = max(up[0] if up else 0, down[0] if down else 0) * 0.7 + 0.05
        return box(b[0] + w, b[1] + (0.3 if up and down else 0.1))

    def sequence(braced=False, until_right=False):
        w = h = 0.0
        while pos[0] < len(t):
            if until_right and t[pos[0]] == '\\right':
                pos[0] += 2
                break
            if t[pos[0]] == '}':
                pos[0] += 1
                if braced:
                    break
                continue
            b = with_scripts(base())
            w += b[0]
            h = max(h, b[1])
        return box(w, h or 1.2)

    return sequence()


def estimate_item(action: dict) -> dict:
    """Width, height and font size (units) of a write or math action, for a script that has not been drawn: wrapped to its zone or its ``w``, a formula shrunk to fit."""
    size = action.get('size', 'medium')
    fs = _font_units(size)
    limit = ZONES[action['zone']][2] if 'zone' in action else action.get('w', float('inf'))
    if action['op'] == 'write':
        t = wrap_text(action['text'], fs, size in ('large', 'huge'), limit)
        return {'w': t['width'], 'h': t['height'], 'fs': fs, 'wide': t['too_wide']}
    mw, mh = math_box(action['tex'])
    em = fs * MATH_EM
    w, h, scale = mw * em, mh * em, 1.0
    if w > limit:
        scale = max(MIN_SHRINK, limit / w)
        w, h = w * scale, h * scale
    return {'w': w, 'h': h, 'fs': fs * scale, 'wide': w > limit + 1e-9}


def _curve(points, steps, out) -> None:
    for k in range(1, steps + 1):
        u = k / steps
        v = 1 - u
        if len(points) == 4:
            out.append((v * v * v * points[0][0] + 3 * v * v * u * points[1][0] + 3 * v * u * u * points[2][0] + u * u * u * points[3][0],
                        v * v * v * points[0][1] + 3 * v * v * u * points[1][1] + 3 * v * u * u * points[2][1] + u * u * u * points[3][1]))
        else:
            out.append((v * v * points[0][0] + 2 * v * u * points[1][0] + u * u * points[2][0], v * v * points[0][1] + 2 * v * u * points[1][1] + u * u * points[2][1]))


def sampled_path(d: str) -> list:
    """The polylines of a (valid) path, curves sampled, in board units."""
    t = [m.group(0) for m in PATH_TOKEN.finditer(d)]
    polys: list = []
    cur = None
    i, cmd = 0, None
    x = y = sx = sy = 0.0
    last = None                 # (kind, control point) of the previous curve, for S and T

    def take(n):
        nonlocal i
        values = [float(v) for v in t[i:i + n]]
        i += n
        return values

    def begin():
        nonlocal cur
        if cur is None:
            cur = [(x, y)]
            polys.append(cur)
    while i < len(t):
        if t[i] in ARITY:
            cmd = t[i]
            i += 1
            if cmd == 'Z':
                if cur is not None:
                    cur.append((sx, sy))
                    x, y = sx, sy
                    cur = None
                last = None
                continue
        nxt = None
        if cmd == 'M':
            x, y = take(2)
            sx, sy = x, y
            cur = [(x, y)]
            polys.append(cur)
            cmd = 'L'
        elif cmd == 'L':
            begin()
            x, y = take(2)
            cur.append((x, y))
        elif cmd == 'H':
            begin()
            x = take(1)[0]
            cur.append((x, y))
        elif cmd == 'V':
            begin()
            y = take(1)[0]
            cur.append((x, y))
        elif cmd == 'C':
            begin()
            a, b, c, e, f, g = take(6)
            _curve([(x, y), (a, b), (c, e), (f, g)], 8, cur)
            nxt = ('c', (c, e))
            x, y = f, g
        elif cmd == 'S':
            begin()
            c, e, f, g = take(4)
            a = (2 * x - last[1][0], 2 * y - last[1][1]) if last and last[0] == 'c' else (x, y)
            _curve([(x, y), a, (c, e), (f, g)], 8, cur)
            nxt = ('c', (c, e))
            x, y = f, g
        elif cmd == 'Q':
            begin()
            a, b, f, g = take(4)
            _curve([(x, y), (a, b), (f, g)], 6, cur)
            nxt = ('q', (a, b))
            x, y = f, g
        elif cmd == 'T':
            begin()
            f, g = take(2)
            a = (2 * x - last[1][0], 2 * y - last[1][1]) if last and last[0] == 'q' else (x, y)
            _curve([(x, y), a, (f, g)], 6, cur)
            nxt = ('q', a)
            x, y = f, g
        else:
            break
        last = nxt
    return polys


def _arrow_ink(a, b, head: float) -> list:
    angle = math.atan2(b[1] - a[1], b[0] - a[0])
    wing = math.pi / 7

    def side(k):
        return (b[0] - head * math.cos(angle + k), b[1] - head * math.sin(angle + k))
    return [[tuple(a), tuple(b)], [side(wing), tuple(b), side(-wing)]]


def _square_ink(c, r: float) -> list:
    return [[(c[0] - r, c[1] - r), (c[0] + r, c[1] - r), (c[0] + r, c[1] + r), (c[0] - r, c[1] + r), (c[0] - r, c[1] - r)]]


def _normal_path(d: str) -> str:
    return ' '.join(m.group(0) for m in PATH_TOKEN.finditer(d))


def ink_of(action: dict) -> list:
    """The ink of a drawing as polylines in board units: what a text box must stay clear of."""
    op = action['op']
    if op == 'draw':
        return sampled_path(_normal_path(action['path']))
    if op == 'arrow':
        return _arrow_ink(action['from'], action['to'], 2.6)
    if op == 'circle':
        cx, cy = action['at']
        r = action['r']
        return [[(cx + r * math.cos(2 * math.pi * k / 24), cy + r * math.sin(2 * math.pi * k / 24)) for k in range(25)]]
    if op == 'rect':
        x, y = action['at']
        w, h = action['w'], action['h']
        return [[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]]
    if op == 'axes':
        x, y = action['at']
        return _arrow_ink((x, y), (x, y - action['h']), 2.2) + _arrow_ink((x, y), (x + action['w'], y), 2.2)
    if op == 'plot':
        return [[tuple(p) for p in action['points']]]
    if op == 'dot':
        return _square_ink(action['at'], action.get('r', 1.4))
    return []


def _segment_hits_box(p, q, box) -> bool:
    """Does the segment p-q touch the box (x0, y0, x1, y1)? Liang-Barsky."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for d, gap in ((-dx, p[0] - box[0]), (dx, box[2] - p[0]), (-dy, p[1] - box[1]), (dy, box[3] - p[1])):
        if d == 0:
            if gap < 0:
                return False
            continue
        r = gap / d
        if d < 0:
            if r > t1:
                return False
            if r > t0:
                t0 = r
        else:
            if r < t0:
                return False
            if r < t1:
                t1 = r
    return True


def _poly_hits_box(poly, box) -> bool:
    if len(poly) == 1:
        return box[0] <= poly[0][0] <= box[2] and box[1] <= poly[0][1] <= box[3]
    return any(_segment_hits_box(poly[k - 1], poly[k], box) for k in range(1, len(poly)))


def _boxes_touch(a, b, pad: float) -> bool:
    return a[0] < b[2] + pad and b[0] < a[2] + pad and a[1] < b[3] + pad and b[1] < a[3] + pad


def _grow(box, pad: float):
    return (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)


def _num1(n: float) -> str:
    return f'{round(n * 10) / 10:g}'


class Layout:
    """The state of a board: what is on it, where, and the problems found placing it. ``shift`` is for the live page; a script check leaves positions alone and reports."""

    def __init__(self, shift: bool = False):
        self.shift = shift
        self.alive: list = []
        self.moved: list = []
        self.problems: list = []
        self._seen: set = set()

    def _note(self, where: str, text: str) -> None:
        self.problems.append(f'layout {where}: {text}')

    def _pair(self, where: str, a: dict, b: dict) -> None:
        key = '|'.join(sorted([a['key'], b['key']]))
        if key in self._seen:
            return
        self._seen.add(key)
        self._note(where, f"{a['label']} collides with {b['label']}" + (f" (step '{b['step']}')" if b.get('step') else ''))

    def _clash(self, box, pad: float):
        for e in self.alive:
            if e['kind'] == 'text':
                if _boxes_touch(box, e['box'], pad):
                    return e
            elif any(_poly_hits_box(p, _grow(box, pad / 2)) for p in e['polys']):
                return e
        return None

    def cursor(self, name: str) -> float:
        y = float(ZONES[name][1])
        for e in self.alive:
            if e.get('zone') == name:
                y = max(y, e['full'][3] + GAP)
        return y

    def _drop(self, key: str) -> None:
        self.alive = [e for e in self.alive if e['key'] != key]

    def add_text(self, s: dict) -> dict:
        """s: key, label, where, step, zone (or None), at, w, h, fs, wide. w and h are the item's own width and height."""
        self._drop(s['key'])
        zone = ZONES[s['zone']] if s['zone'] else None
        x = float(zone[0]) if zone else float(s['at'][0])
        y0 = self.cursor(s['zone']) if zone else float(s['at'][1])
        y = y0
        limit = zone[1] + zone[3] if zone else HEIGHT - EDGE

        def box_of(yy):
            return (x + INSET_X * s['fs'], yy + INSET_Y * s['fs'], x + s['w'] - INSET_X * s['fs'], yy + s['h'] - INSET_Y * s['fs'])
        box = box_of(y)
        hit = self._clash(box, PAD if zone else 0)
        settled = False
        if zone and y + s['h'] > limit + 1e-9:
            self._note(s['where'], f"zone '{s['zone']}' is full: no room for {s['label']} ({_num1(s['h'])} units tall)")
            settled, hit = True, None
        elif hit and (zone or self.shift):
            found = None
            yy = y + STEP
            while yy + s['h'] <= limit + 1e-9:
                if not self._clash(box_of(yy), PAD):
                    found = yy
                    break
                yy += STEP
            if found is not None:
                y = found
                box = box_of(y)
                hit = None
                self.moved.append({'key': s['key'], 'label': s['label'], 'step': s['step'], 'from': [x, y0], 'to': [x, y]})
            elif zone:
                self._note(s['where'], f"zone '{s['zone']}' is full: no room for {s['label']} below what is already there")
                hit, settled = None, True
        if s['wide']:
            if zone:
                self._note(s['where'], f"{s['label']} is too wide for zone '{s['zone']}' ({_num1(s['w'])} units, the zone is {zone[2]})")
            else:
                self._note(s['where'], f"{s['label']} is too wide ({_num1(s['w'])} units): give it a smaller size or a width")
        if not settled and (box[2] > WIDTH - EDGE + 1e-9 or box[0] < EDGE - 1e-9 or box[3] > HEIGHT - EDGE + 1e-9 or box[1] < EDGE - 1e-9):
            self._note(s['where'], f"{s['label']} leaves the board (it spans x {_num1(x)} to {_num1(x + s['w'])}, y {_num1(y)} to {_num1(y + s['h'])})")
        if hit:
            self._pair(s['where'], {'key': s['key'], 'label': s['label']}, hit)
        self.alive.append({'key': s['key'], 'kind': 'text', 'label': s['label'], 'step': s['step'], 'zone': s['zone'] or None, 'box': box, 'full': (x, y, x + s['w'], y + s['h'])})
        return {'x': x, 'y': y, 'moved': y != y0}

    def add_ink(self, s: dict) -> None:
        """s: key, label, where, step, polys, radius (a dot's radius, else 0)."""
        self._drop(s['key'])
        if any(q[0] < -1e-9 or q[0] > WIDTH + 1e-9 or q[1] < -1e-9 or q[1] > HEIGHT + 1e-9 for p in s['polys'] for q in p):
            self._note(s['where'], f"{s['label']} leaves the board")
        for e in self.alive:
            if e['kind'] == 'text' and any(_poly_hits_box(p, e['box']) for p in s['polys']):
                self._pair(s['where'], {'key': s['key'], 'label': s['label']}, e)
        self.alive.append({'key': s['key'], 'kind': 'ink', 'label': s['label'], 'step': s['step'], 'polys': s['polys'], 'radius': s.get('radius', 0)})

    def move_ink(self, key: str, where: str, to) -> None:
        e = next((a for a in self.alive if a['key'] == key), None)
        if not e or e['kind'] != 'ink' or not e['radius']:
            return
        e['polys'] = _square_ink(to, e['radius'])
        if any(q[0] < 0 or q[0] > WIDTH or q[1] < 0 or q[1] > HEIGHT for p in e['polys'] for q in p):
            self._note(where, f"{e['label']} moves off the board")
        for o in self.alive:
            if o['kind'] == 'text' and any(_poly_hits_box(p, o['box']) for p in e['polys']):
                self._pair(where, e, o)

    def remove(self, key: str) -> None:
        self._drop(key)

    def clear(self) -> None:
        self.alive = []


def _snippet(s: str) -> str:
    flat = re.sub(r'\s+', ' ', str(s)).strip()
    return flat[:25] + '...' if len(flat) > 28 else flat


def _label_of(action: dict) -> str:
    if action['op'] == 'write':
        return f'text "{_snippet(action["text"])}"'
    if action['op'] == 'math':
        return f'formula "{_snippet(action["tex"])}"'
    return f"the {action['op']}" + (f" '{action['id']}'" if action.get('id') else '')


def lay_out(layout: Layout, action: dict, ctx: dict, measure):
    """Applies one action to a layout. measure(action) gives a write or math item's size. ctx: where, step (id), i, j."""
    key = action.get('id') or f"#{ctx['i']}.{ctx['j']}"
    op = action['op']
    if op in ('write', 'math'):
        m = measure(action)
        return layout.add_text({'key': key, 'label': _label_of(action), 'where': ctx['where'], 'step': ctx['step'], 'zone': action.get('zone'), 'at': action.get('at'),
                                'w': m['w'], 'h': m['h'], 'fs': m['fs'], 'wide': m['wide']})
    if op == 'move':
        polys = sampled_path(_normal_path(action['path']))
        if polys and polys[-1]:
            layout.move_ink(action['target'], ctx['where'], polys[-1][-1])
        return None
    if op == 'erase':
        if action['target'] == 'all':
            layout.clear()
        else:
            layout.remove(action['target'])
        return None
    if op == 'highlight':
        return None
    layout.add_ink({'key': key, 'label': _label_of(action), 'where': ctx['where'], 'step': ctx['step'], 'polys': ink_of(action), 'radius': action.get('r', 1.4) if op == 'dot' else 0})
    return None


def layout_script(script: dict) -> Layout:
    """The layout of a whole (valid) script as estimated from the text's glyph widths."""
    layout = Layout(shift=False)
    for i, step in enumerate(script.get('steps', [])):
        for j, action in enumerate(step.get('do', [])):
            lay_out(layout, action, {'where': f"steps[{i}] (step '{step.get('id')}') do[{j}]", 'step': step.get('id'), 'i': i, 'j': j}, estimate_item)
    return layout


def layout_problems(script) -> list[str]:
    """Why a (grammatically valid) script would not fit its board: text or drawings that collide, zones that overflow, items that leave the board. Each names its step."""
    return [] if validate(script) else layout_script(script).problems


def check(script, layout: bool = False) -> dict:
    """The script, or ValueError naming what is wrong with it. ``layout=True`` also refuses a script whose items collide or leave the board (see layout_problems)."""
    problems = validate(script) or (layout_problems(script) if layout else [])
    if problems:
        raise ValueError('invalid board script: ' + '; '.join(problems[:8]))
    return script


def speech(script) -> list[str]:
    """The sentences to speak, in order (silent steps are left out)."""
    return [s['say'].strip() for s in check(script)['steps'] if s.get('say', '').strip()]


def append_steps(script, steps: list, open_: bool | None = None) -> dict:
    """A new script with ``steps`` added after the existing ones. The old script is not changed; the result is validated."""
    merged = {**script, 'steps': [*script.get('steps', []), *steps]}
    if open_ is not None:
        merged['open'] = open_
    return check(merged)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    checker = sub.add_parser('check')
    checker.add_argument('script', type=Path)
    checker.add_argument('--no-layout', action='store_true', help='check the grammar only, not whether text and drawings fit the board')
    sub.add_parser('speech').add_argument('script', type=Path)
    args = parser.parse_args(argv)
    try:
        script = json.loads(args.script.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    problems = validate(script)
    if args.command == 'check':
        if not problems and not args.no_layout:
            problems = layout_problems(script)
        print('\n'.join(problems) if problems else f'valid: {len(script["steps"])} steps')
        return 1 if problems else 0
    if problems:
        print('\n'.join(problems), file=sys.stderr)
        return 1
    print('\n'.join(speech(script)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
