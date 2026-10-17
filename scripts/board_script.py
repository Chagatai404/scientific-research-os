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
OPS = {
    'write': ('text', 'at', 'size', 'color'),
    'math': ('tex', 'at', 'size', 'color'),
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
REQUIRED = {'write': ('text', 'at'), 'math': ('tex', 'at'), 'draw': ('path',), 'arrow': ('from', 'to'), 'circle': ('at', 'r'), 'rect': ('at', 'w', 'h'),
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


def check(script) -> dict:
    problems = validate(script)
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
    for name in ('check', 'speech'):
        sub.add_parser(name).add_argument('script', type=Path)
    args = parser.parse_args(argv)
    try:
        script = json.loads(args.script.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    problems = validate(script)
    if args.command == 'check':
        print('\n'.join(problems) if problems else f'valid: {len(script["steps"])} steps')
        return 1 if problems else 0
    if problems:
        print('\n'.join(problems), file=sys.stderr)
        return 1
    print('\n'.join(speech(script)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
