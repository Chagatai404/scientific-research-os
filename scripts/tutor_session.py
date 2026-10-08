"""Replay bounded interruptible lesson checkpoints; no grading or ledger writes.

Input is a session declaration with an append-only event list. The default CLI
prints its projection; --output explicitly creates a new confined checkpoint.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import tempfile

import knowledge as k
from migrate_learning import confined
from paper_access import read_json, root_path
from tutor_contract import scoped_question_issues

KINDS = {'CLARIFICATION', 'DEEPEN', 'PREREQUISITE', 'CHALLENGE', 'METHOD',
         'TOOL', 'TRANSFER', 'PROJECT_APPLICATION', 'OFF_TOPIC_BRANCH'}


def shape(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError('invalid lesson declaration')


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 4000 or '\x00' in value:
        raise ValueError('bounded nonempty lesson text required')
    return value


def identity(value):
    if not isinstance(value, str) or not k.ID.fullmatch(value):
        raise ValueError('lesson ID required')
    return value


def checkpoint(value):
    shape(value, {'target', 'lesson_stage', 'unresolved_question', 'prerequisite_branch'})
    identity(value['target'])
    text(value['lesson_stage'])
    for field in ('unresolved_question', 'prerequisite_branch'):
        if value[field] is not None:
            text(value[field])
    return deepcopy(value)


def strings(values, *, ids=False):
    if not isinstance(values, list) or len(values) > 30:
        raise ValueError('bounded lesson list required')
    for value in values:
        (identity if ids else text)(value)
    if len(values) != len(set(values)):
        raise ValueError('duplicate lesson item')
    return values


def probe(value):
    shape(value, {'capability', 'schema', 'scope', 'dimension', 'method', 'context',
                  'question', 'contract', 'established', 'criteria', 'units', 'independent_example'})
    identity(value['capability'])
    if type(value['schema']) is not int or value['schema'] not in {2, 3}:
        raise ValueError('explicit scoped schema required')
    text(value['question'])
    strings(value['established'], ids=True)
    if not strings(value['criteria']):
        raise ValueError('explicit answer criteria required')
    if type(value['units']) is not int or not 1 <= value['units'] <= 8:
        raise ValueError('count every assessment component')
    if type(value['independent_example']) is not bool:
        raise ValueError('independent example declaration required')
    issues = scoped_question_issues(value['contract'], set(value['established']),
                                   scope=value['scope'], dimension=value['dimension'],
                                   method=value['method'], context=value['context'],
                                   independent_example=value['independent_example'], schema=value['schema'])
    if issues:
        raise ValueError('invalid capability question contract')
    if value['contract']['TESTS'] != [value['capability']]:
        raise ValueError('one separately assessed capability per probe')


def replay(declaration):
    """Validate all events, deriving branch and budget state after restart."""
    shape(declaration, {'session_schema', 'session_id', 'main', 'events'}, {'budget'})
    if type(declaration['session_schema']) is not int or declaration['session_schema'] != 1:
        raise ValueError('unsupported session schema')
    identity(declaration['session_id'])
    main = checkpoint(declaration['main'])
    events = declaration['events']
    if not isinstance(events, list) or len(events) > 100:
        raise ValueError('bounded event list required')
    limit = declaration.get('budget', 5)
    if type(limit) is not int or not 1 <= limit <= 8:
        raise ValueError('initial diagnostic budget must be 1..8')
    frames = [{'checkpoint': main, 'return_point': None, 'branch_id': None,
               'classification': None, 'answered': False}]
    used, pending, evidence, seen, extensions = 0, None, [], set(), []
    for event in events:
        if not isinstance(event, dict) or event.get('type') not in {
                'question', 'answer_branch', 'resume', 'progress', 'probe', 'learner_reasoning', 'respond', 'review', 'extend_budget'}:
            raise ValueError('unknown lesson event')
        kind = event['type']
        frame = frames[-1]
        if kind == 'question':
            shape(event, {'type', 'id', 'question', 'target', 'lesson_stage'},
                  {'classification', 'prerequisite_branch'})
            identity(event['id'])
            if event['id'] in seen or len(frames) >= 16:
                raise ValueError('duplicate or excessively nested branch')
            seen.add(event['id'])
            text(event['question'])
            classification = event.get('classification')
            if classification is not None and classification not in KINDS:
                raise ValueError('unsupported optional branch label')
            branch = checkpoint({'target': event['target'], 'lesson_stage': event['lesson_stage'],
                                 'unresolved_question': event['question'],
                                 'prerequisite_branch': event.get('prerequisite_branch')})
            frames.append({'checkpoint': branch, 'return_point': deepcopy(frame['checkpoint']),
                           'branch_id': event['id'], 'classification': classification, 'answered': False})
        elif kind == 'answer_branch':
            shape(event, {'type', 'id', 'answer'})
            if len(frames) == 1 or event['id'] != frame['branch_id'] or frame['answered']:
                raise ValueError('answer must match the active unanswered branch')
            text(event['answer'])
            frame['answered'] = True  # Tutor explanation is never learning evidence.
            frame['checkpoint']['unresolved_question'] = None
        elif kind == 'resume':
            shape(event, {'type', 'id'})
            if len(frames) == 1 or event['id'] != frame['branch_id'] or not frame['answered']:
                raise ValueError('resolve the active branch before returning')
            if pending is not None and pending['branch_id'] == frame['branch_id']:
                raise ValueError('finish the branch assessment before returning')
            returning = frames.pop()
            frames[-1]['checkpoint'] = returning['return_point']
        elif kind == 'progress':
            shape(event, {'type', 'checkpoint'})
            frame['checkpoint'] = checkpoint(event['checkpoint'])
        elif kind == 'extend_budget':
            shape(event, {'type', 'limit', 'reason', 'learner_requested'})
            text(event['reason'])
            if event['learner_requested'] is not True or type(event['limit']) is not int or not limit < event['limit'] <= 30:
                raise ValueError('explicit learner request and bounded larger budget required')
            limit = event['limit']
            extensions.append({'limit': limit, 'reason': event['reason']})
        elif kind in {'probe', 'learner_reasoning'}:
            shape(event, {'type', 'id', 'assessment'} | ({'answer'} if kind == 'learner_reasoning' else set()))
            identity(event['id'])
            if pending is not None or event['id'] in seen:
                raise ValueError('finish the current assessment; IDs cannot be reused')
            probe(event['assessment'])
            if kind == 'learner_reasoning':
                if len(frames) == 1 or frame['answered'] or event['assessment']['question'] != frame['checkpoint']['unresolved_question']:
                    raise ValueError('learner reasoning must refer to the active unresolved learner question')
                text(event['answer'])
            else:
                used += event['assessment']['units']
            if used > limit:
                raise ValueError('diagnostic budget exhausted across all branches')
            seen.add(event['id'])
            pending = {'id': event['id'], 'assessment': deepcopy(event['assessment']),
                       'branch_id': frame['branch_id'], 'origin': kind,
                       'answer': event['answer'] if kind == 'learner_reasoning' else None}
        elif kind == 'respond':
            shape(event, {'type', 'id', 'answer'})
            if pending is None or event['id'] != pending['id'] or pending['answer'] is not None or pending['branch_id'] != frame['branch_id']:
                raise ValueError('answer requires one pending tutor assessment')
            pending['answer'] = text(event['answer'])
        elif kind == 'review':
            shape(event, {'type', 'id', 'outcome', 'assistance', 'criteria_met', 'rationale',
                          'reviewed_by', 'solution_revealed'})
            if pending is None or event['id'] != pending['id'] or pending['answer'] is None or pending['branch_id'] != frame['branch_id']:
                raise ValueError('review requires an actual answer to its declared probe')
            if event['outcome'] not in {'pass', 'partial', 'fail'} or event['assistance'] not in {'none', 'hinted', 'open-notes'}:
                raise ValueError('explicit outcome and assistance required')
            met = event['criteria_met']
            if not isinstance(met, list) or len(met) != len(pending['assessment']['criteria']) or any(type(x) is not bool for x in met):
                raise ValueError('review every declared answer criterion')
            if (event['outcome'] == 'pass') != all(met):
                raise ValueError('pass requires every explicit criterion to be met')
            if type(event['solution_revealed']) is not bool or event['solution_revealed'] and event['assistance'] == 'none':
                raise ValueError('revealed solutions cannot be unassisted evidence')
            text(event['rationale'])
            text(event['reviewed_by'])
            evidence.append(dict(deepcopy(pending), review=deepcopy(event),
                                 evidence_id=declaration['session_id'] + '.' + pending['id']))
            pending = None
    return {'session_schema': 1, 'session_id': declaration['session_id'],
            'original_target': main['target'], 'active': deepcopy(frames[-1]['checkpoint']),
            'branches': deepcopy(frames[1:]), 'budget': {'limit': limit, 'used': used, 'extensions': extensions},
            'pending_assessment': pending, 'assessed_answers': evidence,
            'note': 'Human-reviewed answer provenance only. Canonical capability ledgers remain authoritative; no mastery or retention inferred.'}


def literacy_targets(root, collection, mappings):
    """Select consequential artifact-to-capability mappings; never create ledgers."""
    if not isinstance(mappings, list) or len(mappings) > 20:
        raise ValueError('select at most 20 consequential targets')
    result, seen = [], set()
    for item in mappings:
        shape(item, {'artifact', 'sha256', 'capability', 'dimension', 'why_consequential', 'introduced_by'})
        path = confined(root, item['artifact'])
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError('bounded local artifact required')
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('artifact changed since selection')
        text(item['why_consequential'])
        text(item['introduced_by'])
        node = collection.nodes.get(identity(item['capability']))
        if node is None or node.issues or node.meta['learning_schema'] != 3:
            raise ValueError('unique valid schema-3 canonical capability required')
        if item['dimension'] not in k.LITERACY_DIMENSIONS or item['dimension'] not in node.meta['required_dimensions']:
            raise ValueError('mapping must name an explicit literacy profile dimension')
        key = (item['artifact'], item['capability'], item['dimension'])
        if key in seen:
            raise ValueError('duplicate literacy target')
        seen.add(key)
        result.append(dict(item, learning_scope=node.meta['learning_scope'], ledger=node.path))
    return result


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Invalid tutor-session command.\n')


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--input', help='Root-relative session declaration')
    inputs.add_argument('--targets', help='Root-relative selective literacy mapping declaration')
    parser.add_argument('--output', help='Explicitly create a new checkpoint; never overwrite')
    args = parser.parse_args(argv)
    try:
        root = root_path(args.root)
        if args.targets:
            if args.output:
                raise ValueError('target selection is read-only')
            data = read_json(confined(root, args.targets))
            shape(data, {'literacy_schema', 'mappings'})
            if type(data['literacy_schema']) is not int or data['literacy_schema'] != 1:
                raise ValueError('unsupported literacy mapping schema')
            result = literacy_targets(root, k.discover(root, date.today()), data['mappings'])
            print(json.dumps({'targets': result, 'note': 'Selective ledger references, no grades or automatic obligations.'}, indent=2))
            return 0
        declaration = read_json(confined(root, args.input))
        result = replay(declaration)
        if args.output:
            destination = confined(root, args.output)
            payload = json.dumps(declaration, ensure_ascii=False, indent=2) + '\n'
            if len(payload.encode('utf-8')) > 64 * 1024:
                raise ValueError('checkpoint too large')
            # Publish a complete file exclusively: no overwrite and no truncated
            # checkpoint on an interrupted write. The temporary file is local.
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                                 dir=destination.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.link(temporary, destination)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (ValueError, TypeError, KeyError, OSError, UnicodeError):
        print(json.dumps({'error': 'Invalid or unavailable lesson checkpoint.'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
