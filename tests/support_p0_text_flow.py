"""Coherent offline variance fixture backed by the actual context/session writers.

Sources are explicitly synthetic. No scientific source-verification or live Obsidian
acceptance is implied. Only temporary roots passed by the test are written.
"""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import context_kernel as ck
import handout
import html_sessions as hs
import knowledge
import plan_evidence
from test_handout import make_vault, SESSION
from test_ontology import entity, capability, row


def build(folder):
    root = Path(folder)
    make_vault(root)
    hs.update_session(root, SESSION, text='---\ntype: course-session\n---\n# Variance\n\nSynthetic acceptance lesson.\n')
    learning = root / '02 Knowledge'
    learning.mkdir()
    records = {
        'domain.md': entity('domain', 'mathematics'),
        'subject.md': entity('subject', 'probability', domains=['mathematics']),
        'expectation.md': entity('concept', 'expectation', subjects=['probability']),
        'variance.md': entity('concept', 'variance', subjects=['probability'], prerequisites=['expectation']),
        'expectation-capability.md': capability('expectation.explain', 'expectation', rows=row(day=date.today().isoformat(), review='2030-01-01')),
        'variance-capability.md': capability('variance.explain', 'variance'),
    }
    for name, text in records.items():
        (learning / name).write_text(text, encoding='utf-8')
    request = dict(workflow='course-study', vault=str(root), learning_root=str(learning),
                   target={'kind': 'concept', 'id': 'variance'}, as_of=date.today().isoformat())
    receipt = ck.preflight(request)[0]
    hs.bind_session_context(root, SESSION, receipt)
    plan = deepcopy(hs.load_session(root, SESSION)['plan'])
    plan['segments'] = [s for s in plan['segments'] if not s.get('video')]
    plan['segments'][1]['plays_if'] = {'wrong': ['why']}
    plan['check'] = {'start': 'novel', 'questions': [{
        'id': 'novel', 'kind': 'short', 'units': 1,
        'prompt': 'Z is -2 or 4 with equal probability. Derive its variance and explain why adding 8 leaves it unchanged.',
        'tests': 'variance.explain: independent explanation and finite-distribution transfer',
        'criteria': ['Derives mean 1 and variance 9 from squared centred distances',
                     'Explains cancellation of the shift when centring'],
        'next': 'end', 'solution': 'The mean is 1; squared centred distances are both 9. Adding 8 shifts the mean by 8 too, preserving centred distances.'
    }]}
    hs.update_session(root, SESSION, plan=plan)
    content = json.loads((ROOT / 'tests/fixtures/readable-handout.json').read_text(encoding='utf-8'))
    handout.publish_readable(root, SESSION, content)
    exported = root / 'standalone.html'
    hs.export_session(root, SESSION, exported)
    mapping = dict(question_sha256=plan_evidence.question_digest(plan['check']['questions'][0]),
        capability='variance.explain', scope='transfer', dimension='transfer', method='transfer',
        contract={'TESTS': ['variance.explain'], 'ASSUMES': ['expectation.explain'], 'INTRODUCES': {}},
        assistance='none', independent_example=True, reviewed_by='synthetic explicit mapping reviewer',
        response_event_id='not-submitted', response_sha256=plan_evidence.response_digest(''), question_at_attempt_verified=True)
    return {'standalone': str(exported), 'session': SESSION, 'learning': str(learning), 'evidence_mapping': mapping}


def ingest(root, events, review=None, mapping=None):
    """Exercise real validation, locks, deduplication and attempt-bound review."""
    for event in events:
        hs.append_event(Path(root), SESSION, event)
    if review:
        hs.review_plan_answer(Path(root), SESSION, **review)
    state = hs.load_session(Path(root), SESSION)
    result = {'state': state, 'adaptation': hs.session_adaptation(state)}
    if mapping is not None:
        # The scripted fixture reviewer binds its explicit declaration to the
        # exact browser response. Production callers must supply this themselves.
        mapping = dict(mapping)
        answer = [e for e in state['events'] if e['type'] == 'plan-answer' and e.get('question_id') == 'novel'][-1]
        mapping.update(response_event_id=answer['event_id'], response_sha256=plan_evidence.response_digest(answer['response']['answer']))
        result['evidence_proposal'] = plan_evidence.propose(state, 'novel', mapping,
            knowledge.discover(Path(root) / '02 Knowledge', date.today()))
    return result


if __name__ == '__main__':
    if sys.argv[1] == 'ingest':
        request = json.loads(Path(sys.argv[3]).read_text(encoding='utf-8'))
        print(json.dumps(ingest(sys.argv[2], request['events'], request.get('review'), request.get('mapping'))))
    else:
        print(json.dumps(build(sys.argv[1])))
