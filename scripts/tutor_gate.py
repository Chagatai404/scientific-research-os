"""Executable gates for concept-first tutoring: prerequisites before application, honest probes, evidence that is proposed, never granted.

Pure functions over declared structure. Nothing here grades an answer, edits a learner ledger or infers mastery: canonical
ledgers stay human-approved (references/LEARNING_PROTOCOL.md) and unknown mastery stays unknown. A session opts in by
declaring ``teaching`` blocks (what each section introduces and assumes) and/or a ``contract`` on its questions; a session
that declares neither is left alone.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import html_sessions as hs
import knowledge as k
from tutor_contract import scoped_question_issues

BLOCK_KINDS = ('concept', 'intuition', 'derivation', 'review', 'application', 'implementation')
EXPLAINING = {'concept', 'intuition', 'derivation', 'review'}
PROBE_KINDS = ('conceptual-choice', 'short-explanation', 'derivation', 'prediction', 'error-identification', 'transfer',
               'calculation', 'tool-exercise', 'code-comprehension', 'implementation-task')
# Which knowledge-model methods each live question format can honestly carry; the dimension rules live in knowledge.py.
KIND_METHODS = {'mcq': {'mcq', 'recall', 'prediction'}, 'multi': {'mcq', 'recall'}, 'matching': {'mcq', 'recall'},
                'ordering': {'mcq', 'recall'}, 'numeric': {'computation'},
                'free-response': {'explanation', 'derivation', 'prediction', 'transfer', 'recall', 'computation'}}
AUTOCHECKED = {'mcq', 'multi', 'matching', 'ordering', 'numeric'}
LITERACY_FIELDS = ('why_selected', 'assumptions', 'how_it_works', 'how_to_run', 'how_to_verify', 'code_locations', 'failure_modes', 'alternatives')
LITERACY_LABELS = {'why_selected': 'Why this method', 'assumptions': 'What it assumes', 'how_it_works': 'How it works',
                   'how_to_run': 'How to run it', 'how_to_verify': 'How to check the output',
                   'code_locations': 'Where to find and change it', 'failure_modes': 'How it fails', 'alternatives': 'Alternatives'}
ESTABLISHED = {'demonstrated', 'retained'}
DEFAULT_BUDGET = 5
BLOCK_ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
CATCH_ALL = re.compile(r'\b(all|none|both)\s+of\s+the\s+above\b', re.I)
ABSOLUTE = re.compile(r'\b(always|never|only|all|none|every|cannot|must)\b', re.I)


def issue(code, where, message, severity='error'):
    return {'code': code, 'where': where, 'message': message, 'severity': severity}


def _text(value, low=1, high=2000):
    return isinstance(value, str) and low <= len(value.strip()) <= high


# ---------------------------------------------------------------- what the learner is recorded as knowing

def learner_view(source):
    """concept/capability id -> {'status', 'state', 'freshness'}. Absent means unknown, and unknown is never promoted.

    ``source`` is a context-kernel receipt, or a plain mapping ``{id: state}`` / ``{id: {'state':..., 'freshness':...}}``.
    """
    if not source:
        return {}
    if not isinstance(source, dict):
        raise ValueError('a context receipt or an id -> state mapping is required')
    if 'retrieval' in source:
        nodes = ((source['retrieval'] or {}).get('learner') or {}).get('nodes') or []
        raw = {n['id']: {'state': n.get('state'), 'freshness': n.get('freshness')} for n in nodes if isinstance(n, dict) and 'id' in n}
    else:
        raw = {key: value if isinstance(value, dict) else {'state': value} for key, value in source.items()}
    view = {}
    for key, entry in raw.items():
        state, freshness = entry.get('state'), entry.get('freshness')
        if state in ESTABLISHED:
            status = 'weak' if freshness in ('due', 'overdue') else 'established'
        else:
            status = 'weak' if state in ('fragile', 'stale') else 'in-progress' if state == 'learning' else 'unknown'
        view[key] = {'status': status, 'state': state, 'freshness': freshness}
    return view


def status_of(view, concept):
    return view.get(concept, {}).get('status', 'unknown')


# ---------------------------------------------------------------------------------- declared structure

def _lines(state):
    lines = state['source_markdown'].replace('\r\n', '\n').split('\n')
    return lines, [(n, text) for n, heading, text in hs.prose_lines(lines) if heading]


def opted_in(state):
    return bool(state.get('teaching')) or 'tutoring' in state or any('contract' in q for q in state.get('questions', []))


def literacy_issues(block_id, literacy):
    """Implementation literacy: why the method, what it assumes, how it works, how to run and verify it, where to change it, how it fails."""
    if not isinstance(literacy, dict) or set(literacy) - set(LITERACY_FIELDS):
        return [issue('LITERACY_SHAPE', block_id, 'literacy must be an object with only: ' + ', '.join(LITERACY_FIELDS))]
    out, missing = [], [f for f in LITERACY_FIELDS if f not in literacy]
    if missing:
        out.append(issue('LITERACY_INCOMPLETE', block_id, 'implementation literacy is missing: ' + ', '.join(LITERACY_LABELS[f] for f in missing)))
    for field in ('why_selected', 'how_it_works', 'how_to_run', 'how_to_verify'):
        if field in literacy and not _text(literacy[field], 20):
            out.append(issue('LITERACY_THIN', block_id, f'{LITERACY_LABELS[field]}: say it in a sentence or more (at least 20 characters)'))
    for field in ('assumptions', 'failure_modes', 'alternatives'):
        value = literacy.get(field)
        if field in literacy and (not isinstance(value, list) or not value or any(not _text(v, 8, 500) for v in value)):
            out.append(issue('LITERACY_THIN', block_id, f'{LITERACY_LABELS[field]}: a non-empty list of statements'))
    locations = literacy.get('code_locations')
    if 'code_locations' in literacy:
        if not isinstance(locations, list) or not locations or len(locations) > 20:
            out.append(issue('LITERACY_THIN', block_id, 'Where to find and change it: at least one code location'))
        else:
            for item in locations:
                path = item.get('path') if isinstance(item, dict) else None
                if (not isinstance(item, dict) or set(item) - {'path', 'note'} or not isinstance(path, str) or not path or '\\' in path or ':' in path
                        or any(part in {'', '.', '..'} for part in path.split('/')) or not _text(item.get('note'), 8, 300)):
                    out.append(issue('LITERACY_LOCATION', block_id, 'each code location is {"path": "relative/file.py", "note": "what to change there"}'))
                    break
    return out


def block_issues(state):
    """Structure of the declared teaching blocks, and each block's heading line. No learner needed."""
    blocks = state.get('teaching', [])
    if not isinstance(blocks, list) or len(blocks) > 64:
        return [issue('TEACHING_SHAPE', 'teaching', 'teaching must be a list of at most 64 blocks')], []
    _, headings = _lines(state)
    out, located, seen = [], [], set()
    for block in blocks:
        where = block.get('id') if isinstance(block, dict) else '?'
        if (not isinstance(block, dict) or set(block) - {'id', 'heading', 'kind', 'target', 'assumes', 'introduces', 'literacy'}
                or not {'id', 'heading', 'kind', 'target'} <= set(block)):
            out.append(issue('BLOCK_SHAPE', where, 'a teaching block needs id, heading, kind and target (optional: assumes, introduces, literacy)'))
            continue
        if not isinstance(block['id'], str) or not BLOCK_ID.match(block['id']) or block['id'] in seen:
            out.append(issue('BLOCK_ID', where, 'block ids are unique letters, digits, hyphen and underscore'))
            continue
        seen.add(block['id'])
        if block['kind'] not in BLOCK_KINDS:
            out.append(issue('BLOCK_KIND', where, 'kind must be one of: ' + ', '.join(BLOCK_KINDS)))
        if not isinstance(block['target'], str) or not k.ID.fullmatch(block['target']):
            out.append(issue('BLOCK_TARGET', where, 'target is the concept this block teaches, as a lowercase concept id'))
        assumes = block.get('assumes', [])
        if (not isinstance(assumes, list) or len(set(map(str, assumes))) != len(assumes) or any(not isinstance(a, str) or not k.ID.fullmatch(a) for a in assumes)
                or block.get('target') in assumes):
            out.append(issue('BLOCK_ASSUMES', where, 'assumes is a list of distinct concept ids, not including the target'))
        introduces = block.get('introduces', {})
        if not isinstance(introduces, dict) or any(not _text(term, 1, 100) or not _text(definition, 1, 500) for term, definition in introduces.items()):
            out.append(issue('BLOCK_INTRODUCES', where, 'introduces maps each new term to its definition'))
        hits = [n for n, text in headings if text.strip() == str(block['heading']).strip()]
        if len(hits) != 1:
            out.append(issue('BLOCK_HEADING', where, f"{'no' if not hits else 'more than one'} heading reads exactly {block['heading']!r}; a declaration must match the lesson"))
        else:
            located.append((block, hits[0]))
        if block['kind'] == 'implementation':
            out.extend(literacy_issues(where, block.get('literacy')))
        elif 'literacy' in block:
            out.append(issue('LITERACY_KIND', where, 'literacy belongs to implementation blocks'))
    return out, sorted(located, key=lambda item: item[1])


def _option_labels(question):
    labels = []
    for option in question.get('options') or []:
        labels.append(str(option.get('label', option.get('value', ''))) if isinstance(option, dict) else str(option))
    return labels


def mcq_warnings(question):
    """Heuristics only: cues a guesser could use. Whether the distractors are scientifically plausible needs a human."""
    qid, labels = question['id'], _option_labels(question)
    if question.get('kind') not in ('mcq', 'multi'):
        return []
    out = []
    if len(labels) < 3:
        out.append(issue('MCQ_FEW_OPTIONS', qid, 'fewer than three options: a guess is too likely to be right', 'warning'))
    normal = [re.sub(r'\W+', ' ', label.lower()).strip() for label in labels]
    if len(set(normal)) != len(normal):
        out.append(issue('MCQ_DUPLICATE_OPTIONS', qid, 'two options say the same thing', 'warning'))
    if any(CATCH_ALL.search(label) for label in labels):
        out.append(issue('MCQ_CATCH_ALL', qid, '"all/none of the above" lets a learner answer without discriminating', 'warning'))
    answer = question.get('answer')
    correct = [answer] if question.get('kind') == 'mcq' else (answer if isinstance(answer, list) else [])
    keyed = {}
    for option in question.get('options') or []:
        keyed[str(option.get('value')) if isinstance(option, dict) else str(option)] = str(option.get('label', option.get('value', ''))) if isinstance(option, dict) else str(option)
    right = [keyed[str(a)] for a in correct if str(a) in keyed]
    wrong = [label for key, label in keyed.items() if key not in {str(a) for a in correct}]
    if question.get('kind') == 'mcq' and len(right) == 1 and wrong:
        lengths = sorted(len(w) for w in wrong)
        median = lengths[len(lengths) // 2]
        if len(right[0]) > 1.6 * max(median, 1) and len(right[0]) > max(lengths):
            out.append(issue('MCQ_LENGTH_CUE', qid, 'the correct option is much longer than the others; length gives it away', 'warning'))
        if not ABSOLUTE.search(right[0]) and any(ABSOLUTE.search(w) for w in wrong):
            out.append(issue('MCQ_ABSOLUTE_CUE', qid, 'distractors use absolute words ("always", "never", "only") the correct option avoids', 'warning'))
    return out


def question_issues(question, established):
    """One question against the canonical TESTS/ASSUMES/INTRODUCES contract and the knowledge model's scope rules."""
    qid = question['id']
    contract = question.get('contract')
    if contract is None:
        return [issue('NO_CONTRACT', qid, 'declare TESTS, ASSUMES and INTRODUCES (and scope, dimension, method) so this probe is tied to one capability', 'warning')]
    out = []
    scope, dimension, method = question.get('scope'), question.get('dimension'), question.get('method')
    try:
        problems = scoped_question_issues(contract, set(established), scope=scope, dimension=dimension, method=method,
                                          context=question.get('context') or '', independent_example=question.get('independent_example') is True,
                                          schema=question.get('schema', 3))
    except (TypeError, ValueError, KeyError) as exc:
        problems = [str(exc) or 'invalid contract']
    out.extend(issue('CONTRACT', qid, p) for p in problems)
    tests = contract.get('TESTS') if isinstance(contract, dict) else None
    if isinstance(tests, list) and len(tests) != 1:
        out.append(issue('ONE_CAPABILITY', qid, 'a probe tests one separately assessed capability'))
    kind = question.get('kind', 'free-response')
    if method is not None and method not in KIND_METHODS.get(kind, set()):
        out.append(issue('METHOD_KIND', qid, f'a {kind} question cannot honestly carry the method {method!r}'))
    if type(question.get('units')) is not int or not 1 <= question['units'] <= 8:
        out.append(issue('UNITS', qid, 'count every assessed component: units is 1..8'))
    if question.get('probe') not in PROBE_KINDS:
        out.append(issue('PROBE_KIND', qid, 'probe must be one of: ' + ', '.join(PROBE_KINDS)))
    criteria = question.get('criteria')
    if kind not in AUTOCHECKED or criteria is not None:
        if not isinstance(criteria, list) or not criteria or any(not _text(c, 3, 500) for c in criteria):
            out.append(issue('CRITERIA', qid, 'explicit answer criteria are required for a response that someone must review'))
    out.extend(mcq_warnings(question))
    return out


def budget_issues(state):
    """The existing diagnostic budget: every assessed unit counts, and only the learner can extend it."""
    tutoring = state.get('tutoring', {})
    if not isinstance(tutoring, dict) or set(tutoring) - {'budget', 'extensions'}:
        return [issue('TUTORING_SHAPE', 'tutoring', 'tutoring is {"budget": 1..8, "extensions": [...]}')]
    limit = tutoring.get('budget', DEFAULT_BUDGET)
    if type(limit) is not int or not 1 <= limit <= 8:
        return [issue('BUDGET', 'tutoring', 'the initial diagnostic budget is 1..8')]
    for extension in tutoring.get('extensions', []):
        if (not isinstance(extension, dict) or set(extension) != {'limit', 'reason', 'learner_requested'} or extension['learner_requested'] is not True
                or type(extension['limit']) is not int or not limit < extension['limit'] <= 30 or not _text(extension['reason'], 3, 500)):
            return [issue('BUDGET_EXTENSION', 'tutoring', 'an extension needs an explicit learner request, a larger bounded limit and a reason')]
        limit = extension['limit']
    used = sum(q['units'] for q in state.get('questions', []) if isinstance(q.get('contract'), dict) and type(q.get('units')) is int and q['units'] > 0)
    if used > limit:
        return [issue('BUDGET_EXCEEDED', 'tutoring', f'{used} assessed units exceed the diagnostic budget of {limit}; only the learner can extend it')]
    return []


def structural_issues(state):
    """Everything checkable without knowing the learner. Empty for a session that has not opted in."""
    if not opted_in(state):
        return []
    out, _ = block_issues(state)
    for question in state.get('questions', []):
        contract = question.get('contract')
        assumed = set(contract.get('ASSUMES') or []) if isinstance(contract, dict) and isinstance(contract.get('ASSUMES'), list) else set()
        out.extend(question_issues(question, assumed))  # the learner is unknown here, so assumptions are not judged yet
    out.extend(budget_issues(state))
    return out


# ------------------------------------------------------------------- the gate: what may come before what

def _question_lines(lines, questions):
    marked = {}
    for n, line in enumerate(lines):
        match = hs.QUESTION_MARKER.match(line.strip())
        if match and match[1] not in marked:
            marked[match[1]] = n
    end = len(lines)
    return {q['id']: marked.get(q['id'], end + i) for i, q in enumerate(questions)}


def introduction_gate(state, learner):
    """May this session introduce what it introduces, in this order, to this learner? Teaching is not evidence:
    a concept explained earlier is *explained*, never *demonstrated*, and unknown mastery stays unknown."""
    problems, located = block_issues(state)
    lines, _ = _lines(state)
    explained, blocks, issues, unknown = {}, [], list(problems), set()
    for block, line in located:
        dependencies = []
        for concept in block.get('assumes', []):
            status = status_of(learner, concept)
            if status == 'unknown':
                unknown.add(concept)
            if status == 'established':
                dependencies.append({'concept': concept, 'status': 'established', 'by': 'learner record'})
            elif concept in explained:
                dependencies.append({'concept': concept, 'status': 'explained-earlier', 'by': explained[concept],
                                     'note': 'explained earlier in this session; not yet demonstrated'})
            else:
                dependencies.append({'concept': concept, 'status': 'unsupported', 'learner_status': status,
                                     'options': ['teach it in an earlier block', 'probe it with a contract question', 'branch to a prerequisite lesson']})
                issues.append(issue('UNSUPPORTED_PREREQUISITE', block['id'],
                                    f"'{block['heading']}' assumes {concept}, which is {status} for this learner and is not taught earlier in this session"))
        if block['kind'] == 'application' and status_of(learner, block['target']) != 'established' and block['target'] not in explained:
            issues.append(issue('APPLICATION_BEFORE_CONCEPT', block['id'],
                                f"'{block['heading']}' applies {block['target']} before the concept itself is taught or established; teach the general idea first"))
        if block['kind'] in EXPLAINING:
            explained.setdefault(block['target'], block['id'])
        blocks.append({'id': block['id'], 'heading': block['heading'], 'kind': block['kind'], 'line': line + 1, 'dependencies': dependencies})
    positions = _question_lines(lines, state.get('questions', []))
    sequence = [(line, block['target']) for block, line in located if block['kind'] in EXPLAINING]
    for question in state.get('questions', []):
        if not isinstance(question.get('contract'), dict):
            continue
        before = {target for line, target in sequence if line < positions[question['id']]}
        known = {c for c, v in learner.items() if v['status'] == 'established'} | before
        issues.extend(i for i in question_issues(question, known) if i['code'] == 'CONTRACT' and i['message'].startswith('unresolved assumption'))
        unknown.update(c for c in (question['contract'].get('ASSUMES') or []) if status_of(learner, c) == 'unknown')
    return {'blocks': blocks, 'unknown_mastery': sorted(unknown), 'issues': issues}


def check(state, learner=None):
    """Structure, then (when a learner view is given) the introduction gate. ``learner=None`` says the gate was not run."""
    structure = structural_issues(state)
    result = {'opted_in': opted_in(state), 'gate_run': learner is not None and opted_in(state), 'gate': None, 'issues': list(structure)}
    if learner is not None and result['opted_in']:
        gate = introduction_gate(state, learner)
        result['gate'] = {key: gate[key] for key in ('blocks', 'unknown_mastery')}
        known = {(i['code'], i['where'], i['message']) for i in structure}
        result['issues'].extend(i for i in gate['issues'] if (i['code'], i['where'], i['message']) not in known)
    errors = [i for i in result['issues'] if i['severity'] == 'error']
    result['outcome'] = 'blocked' if errors else 'ready'
    result['errors'], result['warnings'] = errors, [i for i in result['issues'] if i['severity'] != 'error']
    return result


# ------------------------------------------------------------------------------------- evidence, proposed

def evidence_proposal(state, question_id):
    """What this question's actual, reviewed answer could contribute, for a human to accept into the canonical ledger.

    Never writes. A click, an auto-checked option or an unreviewed answer is not evidence; a revealed solution or a hint
    makes an attempt assisted; recognition cannot stand in for reconstruction; retention is a later, separate record.
    """
    question = next((q for q in state['questions'] if q['id'] == question_id), None)
    if question is None:
        raise ValueError('Unknown question')
    contract = question.get('contract') if isinstance(question.get('contract'), dict) else None
    events = [e for e in state['events'] if e.get('question_id') == question_id]
    responses = [e for e in events if e['type'] == 'response']
    blockers = []
    if contract is None:
        blockers.append('the question has no TESTS/ASSUMES/INTRODUCES contract')
    if not responses:
        blockers.append('no actual learner response: nothing is invented')
    latest = responses[-1] if responses else None
    review = None
    if latest is not None:
        review = next((r for r in reversed(question.get('reviews', [])) if r.get('response_event_id') == latest['event_id']), None)
        if review is None:
            blockers.append('the latest response has not been reviewed; an unreviewed or auto-checked answer is never ledger evidence')
        elif review['verdict'] == 'reviewed':
            blockers.append("the review records no judgement (verdict 'reviewed')")
    when = (latest or {}).get('created_at', '')
    hints = max([int(e['response']) for e in events if e['type'] == 'hint' and isinstance(e.get('response'), int) and e.get('created_at', '') <= when] or [0])
    solution = any(e['type'] == 'solution' and e.get('created_at', '') < when for e in events)
    assistance = 'open-notes' if solution else 'hinted' if hints else 'none'
    criteria = question.get('criteria') or []
    met = (review or {}).get('criteria_met')
    if review is not None and criteria:
        if not isinstance(met, list) or len(met) != len(criteria):
            blockers.append('the review must state, for every declared criterion, whether it was met')
        elif review['verdict'] == 'correct' and not all(met):
            blockers.append("a 'correct' verdict requires every declared criterion to be met")
    outcome = {'correct': 'pass', 'partially-correct': 'partial', 'incorrect': 'fail'}.get((review or {}).get('verdict'))
    method, dimension, scope = question.get('method'), question.get('dimension'), question.get('scope')
    # Recognition (a choice) may demonstrate recognition only; reconstruction needs the learner to produce the reasoning.
    carries = dimension == 'recognition' or (method in k.RECONSTRUCTION or method == 'prediction') and method != 'mcq'
    independent = outcome == 'pass' and assistance == 'none' and not blockers and carries
    return {'question_id': question_id, 'capability': contract['TESTS'][0] if contract and contract.get('TESTS') else None,
            'scope': scope, 'dimension': dimension, 'method': method, 'context': question.get('context') or '',
            'response': (latest or {}).get('response'), 'response_event_id': (latest or {}).get('event_id'),
            'criteria': criteria, 'criteria_met': met, 'outcome': outcome, 'assistance': assistance, 'hints_used': hints,
            'solution_revealed': solution, 'reviewed_by': (review or {}).get('reviewed_by'),
            'transfer': bool(scope == 'transfer' and question.get('independent_example') is True),
            'retention': {'status': 'not-assessed', 'note': 'retention is recorded by later retrieval, not by this attempt'},
            'proposable': not blockers, 'blockers': blockers, 'counts_as_independent_demonstration': bool(independent),
            'note': 'A proposal for human review. The canonical capability ledger stays authoritative; no mastery or retention is inferred here.'}


# ----------------------------------------------------------------------------------- literacy on the page

def literacy_markdown(block):
    """The implementation-literacy items of a block as ordinary lesson Markdown, so declaring them means showing them."""
    literacy = block['literacy']
    out = ['**Implementation literacy**', '']
    for field in LITERACY_FIELDS:
        value = literacy[field]
        if field == 'code_locations':
            text = '; '.join(f"`{item['path']}` — {item['note']}" for item in value)
        elif isinstance(value, list):
            text = '; '.join(value)
        else:
            text = value
        out.append(f'- **{LITERACY_LABELS[field]}:** {text}')
    return out


def expand_literacy(source, blocks):
    """The lesson source with each implementation block's literacy items inserted under its heading (projection only)."""
    lines = source.replace('\r\n', '\n').split('\n')
    headings = [(n, text) for n, heading, text in hs.prose_lines(lines) if heading]
    inserts = []
    for block in blocks:
        hits = [n for n, text in headings if text.strip() == str(block['heading']).strip()]
        if len(hits) == 1 and not literacy_issues(block['id'], block['literacy']):
            inserts.append((hits[0], literacy_markdown(block)))
    for line, extra in sorted(inserts, reverse=True):
        lines[line + 1:line + 1] = [''] + extra + ['']
    return '\n'.join(lines)


# ---------------------------------------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--root', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    gate = sub.add_parser('check', help='gate a session: structure, then prerequisites against the learner record')
    gate.add_argument('session')
    source = gate.add_mutually_exclusive_group(required=True)
    source.add_argument('--receipt', type=Path, help='context receipt (the "receipt" of html_sessions.py context --json, or a receipt file)')
    source.add_argument('--learner', type=Path, help='JSON {concept-id: state}')
    source.add_argument('--no-learner', action='store_true', help='structure only; the prerequisite gate is NOT run')
    proof = sub.add_parser('evidence', help='what a reviewed answer could contribute to the ledger (a proposal; writes nothing)')
    proof.add_argument('session'); proof.add_argument('question')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        state = hs.load_session(args.root, args.session)
        if args.command == 'evidence':
            print(json.dumps(evidence_proposal(state, args.question), ensure_ascii=False, indent=2))
            return 0
        if args.no_learner:
            view = None
        else:
            data = json.loads((args.receipt or args.learner).read_text(encoding='utf-8'))
            view = learner_view(data['receipt'] if isinstance(data, dict) and isinstance(data.get('receipt'), dict) else data)
        result = check(state, view)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result['outcome'] == 'blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
