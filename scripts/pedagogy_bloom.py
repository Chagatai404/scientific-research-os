"""Optional cognitive challenges reference existing practice, never new answers.

Bloom labels describe prepared activity, not a mandatory ladder, proficiency,
retention, scientific acceptance or research approval.
"""
from copy import deepcopy
import re

from pedagogy_contract import text
import pedagogy_practice as practice

LEVELS = ('remember', 'understand', 'apply', 'analyze', 'evaluate', 'create')
FIELDS = {'id', 'target', 'version', 'sources', 'prepared_by', 'challenges'}


def _practices(plan):
    return {e['id']: e for e in (plan.get('pedagogy') or {}).get('practice', []) if isinstance(e, dict) and isinstance(e.get('id'), str)}


def validate(entry, plan):
    if not isinstance(entry, dict) or set(entry) != FIELDS:
        return ['bloom: exact identity, source provenance and challenges required']
    errors = []
    if not isinstance(entry['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', entry['id']):
        errors.append('bloom: safe bounded id required')
    if entry['target'] != plan.get('target') or not text(entry['target'], 300):
        errors.append('bloom: target must match the prepared plan')
    if type(entry['version']) is not int or not 1 <= entry['version'] <= 1000000:
        errors.append('bloom: positive bounded version required')
    if not text(entry['prepared_by'], 200):
        errors.append('bloom: explicit bounded preparation provenance required')
    sources = entry['sources']
    if not isinstance(sources, list) or not 1 <= len(sources) <= 12 or any(
            not isinstance(s, dict) or set(s) != {'id', 'locator'} or not text(s.get('id'), 200)
            or not text(s.get('locator'), 400) for s in sources):
        errors.append('bloom: 1..12 source identities and locators required')
    challenges = entry['challenges']
    if not isinstance(challenges, list) or not 1 <= len(challenges) <= 6:
        return errors + ['bloom: 1..6 prepared challenges required']
    known, levels, used = _practices(plan), set(), set()
    for challenge in challenges:
        if not isinstance(challenge, dict) or set(challenge) != {'level', 'practice_id', 'practice_version', 'purpose', 'output_requirement'}:
            errors.append('bloom: exact level, practice reference, purpose and output required')
            continue
        level, ident = challenge['level'], challenge['practice_id']
        if not isinstance(level, str) or level not in LEVELS or level in levels:
            errors.append('bloom: unique known cognitive level required')
        else:
            levels.add(level)
        if not isinstance(ident, str) or ident not in known or ident in used:
            errors.append('bloom: each challenge must reference a distinct existing practice item')
            continue
        used.add(ident)
        target = known[ident]
        if type(challenge['practice_version']) is not int or challenge['practice_version'] != target.get('version'):
            errors.append('bloom: exact referenced practice version required')
        if target.get('target') != entry['target'] or practice.validate(target, plan):
            errors.append('bloom: practice must have the same target and valid exact question binding')
        if not text(challenge['purpose'], 1000) or not text(challenge['output_requirement'], 1000):
            errors.append('bloom: bounded authored purpose and assessable output required')
        q = practice.question_for(target, plan)
        if level in ('evaluate', 'create') and (q is None or q.get('kind') != 'short' or len(q.get('criteria', [])) < 2):
            errors.append('bloom: evaluate/create require written reasoning with at least two existing criteria')
    return errors


def project(entry, plan, events=(), reviews=(), options=None):
    """Prepare one optional view; only existing reviewed work can support evidence."""
    base = dict(entry_id=entry.get('id') if isinstance(entry, dict) else None,
                version=entry.get('version') if isinstance(entry, dict) else None,
                evidence=False, available=[], missing=list(LEVELS), view=None,
                selected=None, practice=None, recommended=None, unavailable=None, restored=False,
                reason='No suitable prepared Bloom challenges are available.')
    if validate(entry, plan):
        return base
    challenges = {c['level']: c for c in entry['challenges']}
    available = [level for level in LEVELS if level in challenges]
    options = options if isinstance(options, dict) else {}
    requested = options.get('requested_level')
    unavailable = requested if requested is not None and requested != 'all' and requested not in available else None
    known = _practices(plan)
    entries = [known[c['practice_id']] for c in entry['challenges']]
    current = practice.project(entries, plan, events, reviews, {k: options[k] for k in ('canonical', 'preferences') if k in options})
    saved_view = None
    prefix = f"pedagogy-bloom:{entry['id']}:{entry['version']}:"
    for event in events:
        response = event.get('response')
        if event.get('type') == 'checkpoint' and event.get('question_id') is None and isinstance(response, str) and response.startswith(prefix):
            level = response[len(prefix):]
            if level == 'all' or level in available:
                saved_view = level
    selected = None
    restored = False
    reason = 'Choose a prepared activity; levels are optional and never a completion ladder.'
    if requested == 'all' or requested in available:
        selected = requested
        reason = 'Your explicit challenge choice controls this view; it makes no claim about proficiency.'
    elif saved_view == 'all':
        selected, restored = 'all', True
        reason = 'Your saved all-activities view is preserved; the current practice recommendation remains separate.'
    elif current.get('action') in ('await_review', 'revise'):
        selected = next((c['level'] for c in entry['challenges'] if c['practice_id'] == current.get('entry_id')), None)
        reason = current['reason']
    if selected is None and saved_view is not None:
        selected, restored = saved_view, True
    if selected is None:
        canonical = options.get('canonical')
        canonical = canonical if isinstance(canonical, dict) and canonical.get('status') == 'ready' and canonical.get('target') == plan.get('target') else {}
        step = canonical.get('next') if isinstance(canonical.get('next'), dict) else {}
        preferred = {'recognition': 'remember', 'explanation': 'understand', 'application': 'apply',
                     'derivation': 'analyze', 'transfer': 'evaluate'}.get(step.get('dimension'))
        if preferred in available:
            selected = preferred
            reason = 'Current scoped advice suggests this cognitive activity; its output still needs the existing assessment.'
        else:
            prefs = options.get('preferences')
            prefs = prefs if isinstance(prefs, dict) else {}
            preferred = {'understand': 'understand', 'exam': 'apply', 'research': 'evaluate', 'apply': 'apply', 'review': 'remember'}.get(prefs.get('objective'))
            if preferred in available:
                selected = preferred
                reason = 'Your explicit objective suggests this optional activity, not a presumed level of knowledge.'
    if selected is None:
        selected = 'understand' if 'understand' in available else available[0]
    challenge = challenges.get(selected)
    projected = None
    if challenge:
        item = known[challenge['practice_id']]
        projected = practice.project([item], plan, events, reviews, {'requested_tier': item['tier']})
    return dict(base, available=available, missing=[level for level in LEVELS if level not in available],
                view=selected, selected=deepcopy(challenge), practice=projected, recommended=deepcopy(current),
                unavailable=unavailable, restored=restored, reason=reason,
                sources=deepcopy(entry['sources']), prepared_by=entry['prepared_by'])
