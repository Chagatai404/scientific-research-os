"""Bounded analogy presentation, honest limits and existing transfer practice.

Source/reviewer labels are declarations, not authenticated scientific acceptance.
Neither a different digest nor a novelty declaration awards independent evidence.
"""
from copy import deepcopy
import json
import re

from pedagogy_contract import digest, text
import pedagogy_practice as practice

FIELDS = {'id', 'target', 'version', 'sources', 'prepared_by', 'segment_id',
          'segment_sha256', 'domain', 'relevance', 'correspondences', 'limits',
          'worked', 'transfer', 'replacement'}


def _item(entry, plan):
    transfer = entry.get('transfer') if isinstance(entry, dict) else None
    return next((e for e in (plan.get('pedagogy') or {}).get('practice', [])
                 if isinstance(transfer, dict) and e.get('id') == transfer.get('practice_id')), None)


def novelty_digest(entry, plan):
    """Bind the novelty statement, not its truth, to the actual prepared objects."""
    transfer = entry['transfer']
    item = _item(entry, plan)
    return digest({'worked': entry['worked'], 'transfer': {key: transfer.get(key) for key in
        ('practice_id', 'practice_version', 'context_id', 'structure_id', 'differences')},
        'question_sha256': item.get('question_sha256') if item else None})


def _safe_id(value, limit=80):
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,' + str(limit) + '}', value))


def _actual_replacement(entry, state):
    replacement = entry['replacement']
    if replacement is None:
        return None, None
    answer = next((e for e in state.get('events', []) if e.get('type') == 'plan-answer'
        and e.get('question_id') == replacement['question_id']
        and e.get('event_id') == replacement['response_event_id'] and isinstance(e.get('response'), dict)), None)
    review = next((r for r in state.get('plan_reviews', []) if r.get('question_id') == replacement['question_id']
        and r.get('response_event_id') == replacement['response_event_id'] and digest(r) == replacement['review_sha256']
        and r == replacement['review_snapshot']), None)
    return answer, review


def validate(entry, plan, state=None):
    """Structural checks plus immutable replacement provenance when state is supplied.

    Historical replacement readings do not require that review to remain latest.
    The current-attempt requirement belongs to automatic recommendation only.
    """
    if not isinstance(entry, dict) or set(entry) != FIELDS:
        return ['analogy: exact common, segment, mapping, limits and transfer fields required']
    errors = []
    try:
        if len(json.dumps(entry, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 60000:
            errors.append('analogy: at most 60000 UTF-8 bytes per entry')
    except (TypeError, ValueError):
        return ['analogy: finite JSON required']
    if not _safe_id(entry['id'], 64) or type(entry['version']) is not int or not 1 <= entry['version'] <= 1000000:
        errors.append('analogy: safe bounded identity and positive version required')
    if entry['target'] != plan.get('target') or not text(entry['target'], 300):
        errors.append('analogy: exact prepared target required')
    if not text(entry['prepared_by'], 200):
        errors.append('analogy: bounded preparation provenance required')
    sources = entry['sources']
    if not isinstance(sources, list) or not 1 <= len(sources) <= 12 or any(
            not isinstance(s, dict) or set(s) != {'id', 'locator'} or not text(s.get('id'), 200)
            or not text(s.get('locator'), 400) for s in sources):
        errors.append('analogy: 1..12 precise source identities required')
    segment = next((s for s in plan.get('segments', []) if s.get('id') == entry['segment_id']), None)
    if segment is None or entry['segment_sha256'] != digest(segment):
        errors.append('analogy: exact existing segment digest required')
    domain = entry['domain']
    if not isinstance(domain, dict) or set(domain) != {'name', 'accessibility'} or not all(text(v, 500) for v in domain.values()):
        errors.append('analogy: named accessible domain required; familiarity is not a learner trait')
    if not text(entry['relevance'], 1000):
        errors.append('analogy: explicit bounded relevance rationale required')
    mappings = entry['correspondences']
    if not isinstance(mappings, list) or not 1 <= len(mappings) <= 8 or any(
            not isinstance(m, dict) or set(m) != {'formal', 'analogy', 'relationship'}
            or not all(text(v, 1000) for v in m.values()) for m in mappings):
        errors.append('analogy: 1..8 explicit formal-to-analogy relationships required')
    limits = entry['limits']
    if not isinstance(limits, list) or not 1 <= len(limits) <= 8 or not all(text(v, 1000) for v in limits):
        errors.append('analogy: 1..8 honest bounded failure limits required')
    worked = entry['worked']
    if not isinstance(worked, dict) or set(worked) != {'context_id', 'structure_id', 'description'} or not _safe_id(worked.get('context_id')) or not _safe_id(worked.get('structure_id')) or not text(worked.get('description'), 1000):
        errors.append('analogy: explicit worked context, reasoning structure and description required')
    transfer = entry['transfer']
    if not isinstance(transfer, dict) or set(transfer) != {'practice_id', 'practice_version', 'context_id', 'structure_id', 'differences', 'novelty'}:
        return errors + ['analogy: exact existing transfer practice and novelty declaration required']
    if not _safe_id(transfer['context_id']) or not _safe_id(transfer['structure_id']):
        errors.append('analogy: bounded transfer context and reasoning structure required')
    if isinstance(worked, dict) and transfer['structure_id'] == worked.get('structure_id'):
        errors.append('analogy: a renamed worked structure is not independent transfer')
    differences = transfer['differences']
    if not isinstance(differences, list) or not 1 <= len(differences) <= 8 or any(
            not isinstance(d, dict) or set(d) != {'aspect', 'description'} or not text(d.get('aspect'), 80)
            or not text(d.get('description'), 1000) for d in differences):
        errors.append('analogy: explicit substantive transfer differences required')
    item = _item(entry, plan)
    if type(transfer['practice_version']) is not int or item is None or transfer['practice_version'] != item.get('version'):
        errors.append('analogy: exact referenced transfer practice version required')
    q = practice.question_for(item, plan) if item else None
    if item is None or practice.validate(item, plan) or item.get('dimension') != 'transfer' or item.get('independent') is not True or q is None or q.get('kind') != 'short' or len(q.get('criteria', [])) < 2:
        errors.append('analogy: existing written transfer practice with its unchanged rubric required')
    novelty = transfer['novelty']
    if not isinstance(novelty, dict) or set(novelty) != {'status', 'reviewed_by', 'rationale', 'comparison_sha256'}:
        errors.append('analogy: exact bounded novelty provenance required')
    else:
        status = novelty['status']
        if status not in ('unreviewed', 'reviewed-different', 'uncertain') or not text(novelty['rationale'], 2000):
            errors.append('analogy: honest novelty status and rationale required')
        if novelty['reviewed_by'] is not None and not text(novelty['reviewed_by'], 200):
            errors.append('analogy: bounded reviewer attribution or explicit null required')
        if status == 'unreviewed' and novelty['reviewed_by'] is not None:
            errors.append('analogy: unreviewed novelty cannot name a completed reviewer')
        if status == 'reviewed-different' and (not text(novelty['reviewed_by'], 200) or novelty['reviewed_by'] == entry['prepared_by']):
            errors.append('analogy: different reviewer attribution is required; identity is not authenticated by this field')
        if novelty['comparison_sha256'] != novelty_digest(entry, plan):
            errors.append('analogy: novelty statement must bind actual profiles and transfer question digest')
    replacement = entry['replacement']
    if replacement is not None:
        fields = {'entry_id', 'version', 'question_id', 'response_event_id', 'review_sha256', 'review_snapshot', 'reason'}
        if not isinstance(replacement, dict) or set(replacement) != fields:
            return errors + ['analogy: exact historical replacement and actual review binding required']
        old = next((e for e in (plan.get('pedagogy') or {}).get('analogies', []) if e.get('id') == replacement['entry_id'] and e.get('version') == replacement['version']), None)
        if old is None or old.get('id') == entry['id'] or old.get('target') != entry['target'] or type(replacement['version']) is not int:
            errors.append('analogy: retain the original same-target analogy when replacing it')
        if not text(replacement['question_id'], 64) or not text(replacement['response_event_id'], 200) or not isinstance(replacement['review_sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', replacement['review_sha256']) or not text(replacement['reason'], 1000):
            errors.append('analogy: bounded original attempt, review digest and replacement reason required')
        snapshot = replacement['review_snapshot']
        if not isinstance(snapshot, dict) or len(json.dumps(snapshot, ensure_ascii=False).encode('utf-8')) > 12000 or digest(snapshot) != replacement['review_sha256']:
            errors.append('analogy: exact immutable review snapshot of at most 12000 UTF-8 bytes required')
        if state is not None:
            answer, review = _actual_replacement(entry, state)
            tree = answer.get('response', {}).get('tree') if answer else None
            actual_question = next((q for q in (plan.get(tree) or {}).get('questions', [])
                if q.get('id') == replacement['question_id']), None) if tree in ('probe', 'check') else None
            if answer is None or actual_question is None or review is None or review.get('verdict') not in ('incorrect', 'partially-correct') or not text(review.get('feedback'), 32000):
                errors.append('analogy: replacement must bind a real original answer and substantive gap review')
    return errors


def _current_replacement(entry, events, reviews):
    r = entry['replacement']
    if r is None:
        return False
    latest = next((e for e in reversed(events) if e.get('type') == 'plan-answer' and e.get('question_id') == r['question_id']), None)
    review = next((e for e in reversed(reviews) if e.get('question_id') == r['question_id'] and e.get('response_event_id') == r['response_event_id']), None)
    return bool(latest and latest.get('event_id') == r['response_event_id'] and review and review == r['review_snapshot'])


def project(entries, plan, events=(), reviews=(), options=None):
    base = dict(available=False, evidence=False, entry_id=None, version=None, revealed=False,
                restored=False, unavailable=None, replacement_current=False, content=None,
                transfer_practice_id=None, transfer_question_id=None, novelty_status=None,
                reason='No suitable prepared analogy is available.')
    if not isinstance(entries, list) or len(entries) > 40:
        return base
    state = {'events': events, 'plan_reviews': reviews}
    valid = [e for e in entries if not validate(e, plan, state)]
    if not valid:
        return base
    options = options if isinstance(options, dict) else {}
    requested = options.get('requested_id')
    selected = next((e for e in valid if e['id'] == requested), None)
    unavailable = requested if requested is not None and selected is None else None
    reason = 'This prepared analogy may support the current target; its mapping and limits are illustrative, not evidence.'
    if selected:
        reason = 'Your explicit analogy choice controls this view; it makes no claim about familiarity or understanding.'
    else:
        selected = next((e for e in reversed(valid) if _current_replacement(e, events, reviews)), None)
        if selected:
            reason = 'This replacement addresses the latest actual reviewed misconception; original work and feedback remain unchanged.'
    restored = False
    if selected is None:
        for event in events:
            if event.get('type') != 'checkpoint' or event.get('question_id') is not None:
                continue
            found = next((e for e in valid if event.get('response') == f"pedagogy-analogy:{e['id']}:{e['version']}"), None)
            if found:
                selected, restored = found, True
    if selected is None:
        selected = next((e for e in valid if e['replacement'] is None), valid[0])
    item = _item(selected, plan)
    revealed = any(e.get('type') == 'checkpoint' and e.get('question_id') is None
                   and e.get('response') == f"pedagogy-analogy:{selected['id']}:{selected['version']}" for e in events)
    content = None
    if revealed:
        content = deepcopy({k: selected[k] for k in ('domain', 'relevance', 'correspondences', 'limits', 'worked', 'sources', 'prepared_by')})
        content['novelty'] = deepcopy(selected['transfer']['novelty'])
        content['differences'] = deepcopy(selected['transfer']['differences'])
        content['replacement_reason'] = selected['replacement']['reason'] if selected['replacement'] else None
    return dict(base, available=True, entry_id=selected['id'], version=selected['version'],
                revealed=revealed, restored=restored, unavailable=unavailable,
                replacement_current=_current_replacement(selected, events, reviews), content=content,
                transfer_practice_id=item['id'], transfer_question_id=item['question_id'],
                novelty_status=selected['transfer']['novelty']['status'], reason=reason)
