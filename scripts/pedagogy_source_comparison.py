"""Bounded, read-only source comparison. Quote matching is not fact verification."""
from copy import deepcopy
import hashlib
import json
import re

import pedagogy_contract as pc

KINDS = ('correct', 'omitted', 'misconception', 'unsupported', 'emphasis')
FIELDS = {'id', 'target', 'version', 'sources', 'tree', 'question_id', 'question_sha256',
          'summary_event_id', 'summary_sha256', 'summary', 'source', 'claims', 'synthesis', 'prepared_by'}


def source_digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _attempts(entry, state):
    return [event for event in (state or {}).get('events', []) if isinstance(event, dict)
            and event.get('type') == 'plan-answer' and event.get('question_id') == entry.get('question_id')
            and isinstance(event.get('response'), dict) and event['response'].get('tree') == entry.get('tree')]


def validate(entry, plan, state=None):
    """Check supplied artifacts/bindings; never fetch a source or infer correctness."""
    errors = []
    if not isinstance(entry, dict) or set(entry) != FIELDS:
        return ['comparison: exact common, summary binding, source, claims and synthesis fields required']
    try:
        if len(json.dumps(entry, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 60000:
            errors.append('comparison: content exceeds 60000 UTF-8 bytes')
    except (ValueError, TypeError):
        return ['comparison: finite JSON required']
    if not isinstance(entry['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', entry['id']):
        errors.append('comparison: safe bounded id required')
    if type(entry['version']) is not int or not 1 <= entry['version'] <= 1000000:
        errors.append('comparison: positive bounded version required')
    if not pc.text(entry['prepared_by'], 200):
        errors.append('comparison: explicit prepared-by attribution required')
    if entry['target'] != plan.get('target') or not pc.text(entry['target'], 300):
        errors.append('comparison: exact plan target required')
    tree = entry['tree']
    question = next((q for q in (plan.get(tree) or {}).get('questions', []) if isinstance(q, dict) and q.get('id') == entry['question_id']), None) if tree in ('probe', 'check') else None
    if question is None or question.get('kind') != 'short' or entry['question_sha256'] != pc.digest(question):
        errors.append('comparison: exact existing short question digest required')
    if not pc.text(entry['summary_event_id'], 200) or not pc.text(entry['summary'], 4000) or entry['summary_sha256'] != pc.digest(entry['summary']):
        errors.append('comparison: immutable summary, actual event identity and exact answer digest required')
    sources = entry['sources']
    if not isinstance(sources, list) or not 1 <= len(sources) <= 12 or any(not isinstance(s, dict) or set(s) != {'id', 'locator'} or not pc.text(s.get('id'), 200) or not pc.text(s.get('locator'), 400) for s in sources):
        errors.append('comparison: precise declared source identities required')
    source = entry['source']
    if not isinstance(source, dict) or set(source) != {'id', 'locator', 'access', 'text', 'sha256'}:
        return errors + ['comparison: exact source artifact snapshot required']
    available = source.get('access') in ('excerpt', 'full')
    if source.get('access') not in ('excerpt', 'full', 'unavailable') or not pc.text(source.get('id'), 200) or not pc.text(source.get('locator'), 400):
        errors.append('comparison: explicit source access and precise locator required')
    text = source.get('text')
    if not isinstance(text, str) or (available and not pc.text(text, 16000)) or (not available and text != ''):
        errors.append('comparison: bounded available source text or empty unavailable snapshot required')
    elif source.get('sha256') != source_digest(text):
        errors.append('comparison: exact UTF-8 source snapshot digest required')
    if not isinstance(sources, list) or {'id': source.get('id'), 'locator': source.get('locator')} not in sources:
        errors.append('comparison: snapshot identity and locator must match declared source')
    synthesis = entry['synthesis']
    if (available and not pc.text(synthesis, 6000)) or (not available and synthesis != ''):
        errors.append('comparison: bounded synthesis only for available source required')
    claims = entry['claims']
    if not isinstance(claims, list) or len(claims) > 12 or (not available and claims):
        errors.append('comparison: at most 12 claims; unavailable source permits none')
    else:
        for claim in claims:
            if not isinstance(claim, dict) or set(claim) != {'kind', 'learner_quote', 'source_quote', 'locator', 'feedback', 'revision_prompt'}:
                errors.append('comparison: exact claim classification, quotes, locator and feedback required'); continue
            if claim['kind'] not in KINDS or not pc.text(claim['feedback'], 2000) or not pc.text(claim['revision_prompt'], 1000):
                errors.append('comparison: known classification and bounded feedback/revision prompt required')
            if not pc.text(claim['learner_quote'], 2000) or not isinstance(entry['summary'], str) or claim['learner_quote'] not in entry['summary']:
                errors.append('comparison: learner quote must occur verbatim in original summary')
            if not pc.text(claim['source_quote'], 2000) or not isinstance(text, str) or claim['source_quote'] not in text:
                errors.append('comparison: source quote must occur verbatim in snapshot')
            if claim['locator'] != source.get('locator'):
                errors.append('comparison: claim locator must match the bound source snapshot')
    if state is not None:
        attempts = _attempts(entry, state)
        matches = [e for e in attempts if e.get('event_id') == entry['summary_event_id']]
        identities = [e for e in state.get('events', []) if isinstance(e, dict) and e.get('event_id') == entry['summary_event_id']]
        if len(matches) != 1 or len(identities) != 1 or matches[0]['response'].get('answer') != entry['summary']:
            errors.append('comparison: binding must identify one unchanged actual raw summary attempt')
    return errors


def project(entry, state=None):
    """Project prepared text with honest source/attempt scope, without ledger writes."""
    attempts = _attempts(entry, state)
    matching = [e for e in attempts if e.get('event_id') == entry['summary_event_id'] and e['response'].get('answer') == entry['summary']]
    bound = len(matching) == 1 and sum(isinstance(e, dict) and e.get('event_id') == entry['summary_event_id'] for e in (state or {}).get('events', [])) == 1
    historical = bound and attempts[-1].get('event_id') != entry['summary_event_id']
    status = 'unbound' if not bound else 'unavailable' if entry['source']['access'] == 'unavailable' else 'historical' if historical else 'ready'
    synthesis_revealed = bound and entry['source']['access'] != 'unavailable' and any(
        isinstance(e, dict) and e.get('type') == 'checkpoint' and e.get('question_id') is None
        and e.get('response') == f"pedagogy-comparison-synthesis:{entry['id']}:{entry['version']}" for e in (state or {}).get('events', []))
    sections = []
    if bound and entry['source']['access'] != 'unavailable':
        for claim in entry['claims']:
            label = 'Related learner anchor (omitted point is absent)' if claim['kind'] == 'omitted' else 'Learner quote (original summary)'
            title = 'unsupported within supplied snapshot' if claim['kind'] == 'unsupported' else claim['kind']
            sections.append({'title': title, 'text': label + ': ' + claim['learner_quote'] + '\n\nSource quote: ' + claim['source_quote'] + '\n\nLocator: ' + claim['locator'] + '\n\nPrepared feedback: ' + claim['feedback'] + '\n\nRevision challenge: ' + claim['revision_prompt']})
    return deepcopy({'entry_id': entry['id'], 'version': entry['version'], 'status': status,
        'historical': historical, 'summary_event_id': entry['summary_event_id'], 'summary': entry['summary'] if bound else None,
        'source': entry['source'], 'sections': sections, 'prepared_by': entry['prepared_by'],
        'synthesis_available': historical and status != 'unavailable',
        'synthesis_revealed': synthesis_revealed,
        'synthesis': entry['synthesis'] if synthesis_revealed else None,
        'scope': 'Supplied ' + entry['source']['access'] + ' snapshot; quoted text checked locally, external source content not independently verified.',
        'notice': 'A newer summary is awaiting its own comparison; this review refers to the original attempt.' if historical else
            'Source unavailable. Provide the source before a comparison can be prepared.' if status == 'unavailable' else
            'Original summary attempt unavailable; comparison cannot be displayed.' if status == 'unbound' else
            'Prepared feedback only; opening this comparison awards no learning evidence.'})
