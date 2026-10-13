"""Generated notes for optional Obsidian plugins: practice cards (Spaced Repetition) and a prerequisite canvas (Canvas).

Both are one-way projections of canonical records into a *new* file that the researcher may open, arrange or delete.
Neither is read back: a card the plugin schedules or a canvas the researcher rearranges changes nothing canonical.

- **Cards** come from session questions that have a prepared solution and that the learner has actually answered. Each card
  is plain Markdown (prompt, a ``?`` separator line, solution) under a ``#flashcards/research-os`` tag, with no scheduling
  data of any kind: the plugin keeps its own schedule, and the canonical retention schedule and learning ledger are not
  duplicated or replaced. Answering a card is not a demonstration of the capability.
- **Canvas** draws the canonical prerequisites of one capability as a JSON Canvas 1.0 file (file nodes and edges), arranged in
  columns by depth. It is not a progress map: no mastery or readiness is drawn.

Dry run by default; ``--apply`` writes a new file and refuses to overwrite one.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import sys

CARD_LIMIT = 2000
BREAKERS = {'?', '??', '---'}


class ExportError(ValueError):
    pass


def _root(vault):
    root = Path(vault).expanduser().resolve()
    if not root.is_dir():
        raise ExportError(f'not a directory: {vault}')
    return root


def _target(root, relative, suffix):
    """A new file path inside the vault: relative, visible, not an existing file."""
    value = str(relative).replace('\\', '/')
    parts = value.split('/')
    if (not value or value.startswith('/') or re.match(r'[A-Za-z]:', value) or any(p in ('', '.', '..') or p.startswith('.') for p in parts)
            or not value.lower().endswith(suffix)):
        raise ExportError(f'the output must be a visible relative path ending in {suffix}: {relative}')
    path = root.joinpath(*parts)
    try:
        path.resolve().relative_to(root)
    except (OSError, ValueError):
        raise ExportError('the output must stay inside the vault') from None
    if path.exists() or path.is_symlink():
        raise ExportError(f'{value} already exists; choose a new name (nothing is overwritten)')
    return path, value


def _write_new(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(text, encoding='utf-8', newline='\n')
    os.replace(temp, path)


# ------------------------------------------------------------------------------------------------ cards

def _clean(text):
    text = re.sub(r'<!--.*?-->', '', str(text), flags=re.S)  # a comment could carry another plugin's scheduling data
    return text.replace('\r\n', '\n').strip()


def cards(vault, session, *, out=None, apply=False, plugin_state=None):
    """Practice cards from a session's answered questions. Returns the plan; writes only with ``apply``."""
    import html_sessions
    root = _root(vault)
    state = html_sessions.load_session(root, session)
    answered = {e.get('question_id') for e in state['events'] if e['type'] == 'response'}
    made, skipped = [], []
    for question in state['questions']:
        qid = question['id']
        if not str(question.get('solution') or '').strip():
            skipped.append(dict(question=qid, reason='no prepared solution'))
        elif qid not in answered:
            skipped.append(dict(question=qid, reason='not answered yet'))
        else:
            prompt, solution = _clean(question.get('prompt', '')), _clean(question['solution'])
            if not prompt or not solution:
                skipped.append(dict(question=qid, reason='empty after removing comments'))
            elif len(prompt) > CARD_LIMIT or len(solution) > CARD_LIMIT:
                skipped.append(dict(question=qid, reason=f'longer than {CARD_LIMIT} characters'))
            elif any(line.strip() in BREAKERS for line in (prompt + '\n' + solution).split('\n')):
                skipped.append(dict(question=qid, reason='contains a line the plugin would read as a card separator'))
            else:
                made.append((qid, prompt, solution))
    stem = Path(str(session)).stem
    path, relative = _target(root, out or f'Practice/Cards - {stem}.md', '.md')
    body = ['---', 'ros_generated: spaced-repetition-cards', f'ros_source_session: {json.dumps(str(session).replace(chr(92), "/"))}',
            'ros_canonical: false', '---', f'# Practice cards: {state["title"]}', '',
            'Generated from questions in the session above that were answered and have a prepared solution. The Spaced Repetition plugin keeps '
            'its own schedule for these cards; the canonical retention schedule and the learning ledger are separate, and answering a card '
            'is not a demonstration. Regenerating makes a new file; this one is yours to edit or delete.', '', '#flashcards/research-os', '']
    for qid, prompt, solution in made:
        body += [prompt, '?', solution, '', f'<!-- ros-card: {hashlib.sha256((str(session) + qid).encode("utf-8")).hexdigest()[:12]} question {qid} -->', '']
    text = '\n'.join(body).rstrip() + '\n'
    plugin = plugin_state or {}
    result = dict(applied=False, path=relative, cards=len(made), skipped=skipped, scheduling_data_written=False,
                  plugin=plugin if plugin else 'not checked',
                  note='Separators assume the plugin\'s default ("?" for multi-line cards, the #flashcards tag family); confirm them in its settings.')
    if plugin and not plugin.get('usable'):
        result['warning'] = 'Spaced Repetition is not enabled and compatible in this vault; the note is plain Markdown and still readable.'
    if apply:
        if not made:
            raise ExportError('no answered question with a prepared solution; nothing to write')
        _write_new(path, text)
        result['applied'] = True
    else:
        result['preview'] = text
    return result


# ------------------------------------------------------------------------------------------------ canvas

def _identifier(*parts):
    return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:16]


def canvas(vault, capability, *, out=None, apply=False, as_of=None):
    """A JSON Canvas 1.0 file of one capability's canonical prerequisites."""
    import knowledge
    root = _root(vault)
    collection = knowledge.discover(root, as_of or date.today())
    view = knowledge.query(collection, 'capability', capability)
    nodes = {n['id']: n for n in view['nodes']}
    if capability not in nodes:
        raise ExportError(f'no capability {capability} under {root}' + (f" ({'; '.join(view['diagnostics'])})" if view['diagnostics'] else ''))
    depth = {}

    def level(key, trail=()):
        if key in depth:
            return depth[key]
        if key in trail:  # a cycle is a canonical diagnostic; do not loop on it here
            return 0
        depth[key] = 1 + max([level(p, trail + (key,)) for p in nodes[key]['prerequisites'] if p in nodes] + [-1])
        return depth[key]
    for key in nodes:
        level(key)
    columns = {}
    for key in sorted(nodes, key=lambda k: (depth[k], k)):
        columns.setdefault(depth[key], []).append(key)
    width, height, gap_x, gap_y = 360, 80, 120, 40
    cards_ = [dict(id=_identifier('header', capability), type='text', x=0, y=-200, width=width * 2, height=140,
                   text=f'**Prerequisites of {nodes[capability]["title"]}** (`{capability}`)\n\nDrawn from the canonical prerequisite lists on '
                        f'{(as_of or date.today()).isoformat()}. This is a drawing, not a progress map: no mastery or readiness is shown, '
                        'and moving or editing anything here changes nothing canonical.')]
    ids = {}
    for column, keys in sorted(columns.items()):
        for row, key in enumerate(keys):
            ids[key] = _identifier('node', capability, key)
            cards_.append(dict(id=ids[key], type='file', file=nodes[key]['path'], x=column * (width + gap_x), y=row * (height + gap_y), width=width, height=height))
    edges = [dict(id=_identifier('edge', capability, p, k), fromNode=ids[p], toNode=ids[k], fromSide='right', toSide='left', label='prerequisite of')
             for k in sorted(nodes) for p in sorted(nodes[k]['prerequisites']) if p in nodes]
    document = dict(nodes=cards_, edges=edges)
    path, relative = _target(root, out or f'Canvases/Prerequisites - {capability}.canvas', '.canvas')
    result = dict(applied=False, path=relative, nodes=len(cards_), edges=len(edges), diagnostics=view['diagnostics'], draws_mastery=False,
                  note='A drawing of recorded prerequisites; the canonical records are unchanged and are not read back from the canvas.')
    if apply:
        _write_new(path, json.dumps(document, indent=2, ensure_ascii=False) + '\n')
        result['applied'] = True
    else:
        result['canvas'] = document
    return result


# --------------------------------------------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('cards', 'canvas'):
        command = sub.add_parser(name)
        command.add_argument('--vault', type=Path, default=Path.cwd())
        command.add_argument('--out', help='new vault-relative output path')
        command.add_argument('--apply', action='store_true')
    sub.choices['cards'].add_argument('session', help='vault-relative path of the session Markdown bridge')
    sub.choices['canvas'].add_argument('capability', help='learning_id of the capability')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        import obsidian_plugins
        if args.command == 'cards':
            detected = obsidian_plugins.detect(args.vault, obsidian_version=(obsidian_plugins.app_version_hint() or (None,))[0])['spaced-repetition']
            result = cards(args.vault, args.session, out=args.out, apply=args.apply,
                           plugin_state={'state': detected['state'], 'usable': detected['usable'], 'compatibility': detected['compatibility']})
        else:
            result = canvas(args.vault, args.capability, out=args.out, apply=args.apply)
    except (ExportError, ValueError, OSError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
