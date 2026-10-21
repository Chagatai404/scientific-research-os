"""Prepared source-grounded vocabulary, separate from canonical identity/evidence.

Trusted publication supplies the actual glossary/concept catalog. Static checks
alone establish no canonical identity or scientific verification.
"""
from copy import deepcopy
import json
import re

import pedagogy_contract as pc
from pedagogy_source_comparison import source_digest
import terms as ledger

FIELDS = {'id', 'target', 'version', 'sources', 'prepared_by', 'source', 'requested', 'terms', 'categories'}
TERM_FIELDS = {'term_id', 'labels', 'concepts', 'plain', 'formal', 'example', 'prerequisites', 'contrasts', 'source_quote', 'locator', 'diagnostic'}


def _ids(value, limit=12):
    return isinstance(value, list) and len(value) <= limit and all(pc.text(v, 200) for v in value) and len(set(value)) == len(value)


def validate(entry, plan, glossary=None, concept_ids=None):
    """Validate authoring shape plus explicitly supplied canonical authorities."""
    if not isinstance(entry, dict) or set(entry) != FIELDS:
        return ['terms: exact common, source, requested, terms and categories fields required']
    errors = []
    try:
        if len(json.dumps(entry, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 60000:
            errors.append('terms: content exceeds 60000 UTF-8 bytes')
    except (TypeError, ValueError):
        return ['terms: finite JSON required']
    if not isinstance(entry['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', entry['id']): errors.append('terms: safe id required')
    if type(entry['version']) is not int or not 1 <= entry['version'] <= 1000000: errors.append('terms: bounded positive version required')
    if entry['target'] != plan.get('target') or not pc.text(entry['target'], 300): errors.append('terms: exact plan target required')
    if not pc.text(entry['prepared_by'], 200): errors.append('terms: explicit prepared-by attribution required')
    sources = entry['sources']
    if not isinstance(sources, list) or not 1 <= len(sources) <= 12 or any(not isinstance(s, dict) or set(s) != {'id', 'locator'} or not pc.text(s.get('id'), 200) or not pc.text(s.get('locator'), 400) for s in sources): errors.append('terms: precise source declarations required')
    source = entry['source']
    if not isinstance(source, dict) or set(source) != {'id', 'locator', 'access', 'text', 'sha256'}:
        return errors + ['terms: exact supplied source snapshot required']
    available = source.get('access') in ('excerpt', 'full')
    if source.get('access') not in ('excerpt', 'full', 'unavailable') or not pc.text(source.get('id'), 200) or not pc.text(source.get('locator'), 400): errors.append('terms: explicit source scope and locator required')
    text = source.get('text')
    if not isinstance(text, str) or (available and not pc.text(text, 16000)) or (not available and text != ''):
        errors.append('terms: bounded source text or empty unavailable snapshot required')
    elif source.get('sha256') != source_digest(text): errors.append('terms: exact UTF-8 snapshot hash required')
    if not isinstance(sources, list) or {'id': source.get('id'), 'locator': source.get('locator')} not in sources: errors.append('terms: snapshot must match declared identity/locator')
    requested = entry['requested']
    if not isinstance(requested, dict) or set(requested) != {'terms', 'categories'} or any(requested.get(k) is not None and (type(requested[k]) is not int or not 1 <= requested[k] <= limit) for k, limit in [('terms', 40), ('categories', 10)]):
        errors.append('terms: bounded requested counts or null required'); requested = {}
    rows = entry['terms']
    if not isinstance(rows, list) or len(rows) > 40 or (not available and rows):
        return errors + ['terms: at most 40 prepared terms; unavailable source permits none']
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != TERM_FIELDS:
            errors.append('terms: exact prepared term fields required'); continue
        key = row['term_id']
        if not isinstance(key, str) or not ledger.ID.fullmatch(key) or key in seen:
            errors.append('terms: unique canonical term identity required')
        else: seen.add(key)
        labels = row['labels']
        if not isinstance(labels, dict) or not 1 <= len(labels) <= 8 or any(not isinstance(lang, str) or not ledger.LANG.fullmatch(lang) or not pc.text(label, 200) for lang, label in labels.items()): errors.append('terms: bounded canonical language labels required')
        if not _ids(row['concepts']) or not row['concepts'] or not _ids(row['prerequisites']): errors.append('terms: bounded explicit concept/prerequisite links required')
        if glossary is not None:
            canonical = glossary.get(key) if isinstance(key, str) else None
            if canonical is None or labels != canonical.get('labels') or row['concepts'] != canonical.get('concepts'):
                errors.append('terms: term identity, bilingual labels and concepts must match actual canonical glossary')
        if concept_ids is not None:
            for links in (row['concepts'], row['prerequisites']):
                if isinstance(links, list) and any(not isinstance(link, str) or link not in concept_ids for link in links): errors.append('terms: linked concept/prerequisite absent from actual canonical catalog')
        if not pc.text(row['plain'], 2000) or row['formal'] is not None and not pc.text(row['formal'], 2000) or not pc.text(row['example'], 2000): errors.append('terms: bounded plain/formal/example text required')
        if not pc.text(row['source_quote'], 2000) or not isinstance(text, str) or row['source_quote'] not in text or row['locator'] != source.get('locator'): errors.append('terms: exact quote and locator in supplied snapshot required')
        contrasts = row['contrasts']
        if not isinstance(contrasts, list) or len(contrasts) > 8:
            errors.append('terms: at most eight explicit contrasts required')
        else:
            for contrast in contrasts:
                if not isinstance(contrast, dict) or set(contrast) != {'term_id', 'explanation'} or not isinstance(contrast.get('term_id'), str) or not ledger.ID.fullmatch(contrast['term_id']) or not pc.text(contrast.get('explanation'), 1000) or (glossary is not None and contrast['term_id'] not in glossary): errors.append('terms: contrast must name a known canonical term with an explanation')
        diagnostic = row['diagnostic']
        if diagnostic is not None:
            if not isinstance(diagnostic, dict) or set(diagnostic) != {'tree', 'question_id', 'question_sha256'}:
                errors.append('terms: diagnostic must bind an existing question'); continue
            tree = diagnostic['tree']
            question = next((q for q in (plan.get(tree) or {}).get('questions', []) if q.get('id') == diagnostic['question_id']), None) if tree in ('probe', 'check') else None
            if question is None or diagnostic['question_sha256'] != pc.digest(question): errors.append('terms: exact existing diagnostic question digest required')
    categories = entry['categories']
    if not isinstance(categories, list) or len(categories) > 10 or (not available and categories):
        return errors + ['terms: at most ten categories; unavailable source permits none']
    assigned, category_ids = [], set()
    for category in categories:
        if not isinstance(category, dict) or set(category) != {'id', 'title', 'rationale', 'members'}:
            errors.append('terms: exact category and membership fields required'); continue
        ident = category['id']
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', ident) or ident in category_ids: errors.append('terms: unique category id required')
        else: category_ids.add(ident)
        if not pc.text(category['title'], 200) or not pc.text(category['rationale'], 1000): errors.append('terms: category title and meaningful rationale required')
        members = category['members']
        if not isinstance(members, list) or not 1 <= len(members) <= 40:
            errors.append('terms: nonempty bounded category membership required'); continue
        for member in members:
            if not isinstance(member, dict) or set(member) != {'term_id', 'reason'} or not pc.text(member.get('reason'), 1000) or not isinstance(member.get('term_id'), str) or member['term_id'] not in seen: errors.append('terms: membership needs a prepared canonical term and reason')
            else: assigned.append(member['term_id'])
    if len(assigned) != len(seen) or set(assigned) != seen: errors.append('terms: assign each prepared term to exactly one meaningful category')
    for key, actual in [('terms', len(rows)), ('categories', len(categories))]:
        if requested.get(key) is not None and actual > requested[key]: errors.append('terms: prepared count exceeds requested count')
    return errors


def project(entry, student=None):
    """Read recorded per-language states through the existing term authority."""
    direct = isinstance(student,dict) and bool(student) and all(
        isinstance(key,str) and ledger.ID.fullmatch(key) and isinstance(value,dict) and
        all(isinstance(lang,str) and ledger.LANG.fullmatch(lang) and isinstance(state,str) and state in ledger.STATES for lang,state in value.items())
        for key,value in student.items())
    states = student if direct else ledger.term_view(student)
    if states is not None and (not isinstance(states,dict) or not all(
            isinstance(key,str) and ledger.ID.fullmatch(key) and isinstance(value,dict) and
            all(isinstance(lang,str) and ledger.LANG.fullmatch(lang) and isinstance(state,str) and state in ledger.STATES for lang,state in value.items())
            for key,value in states.items())):
        states = None
    rows = []
    for row in entry['terms']:
        rows.append(dict(deepcopy(row), recorded_states=None if states is None or row['term_id'] not in states else deepcopy(states[row['term_id']])))
    actual = {'terms': len(rows), 'categories': len(entry['categories'])}
    shortfalls = {key: {'requested': count, 'prepared': actual[key]} for key, count in entry['requested'].items() if count is not None and actual[key] < count}
    return {'entry_id': entry['id'], 'version': entry['version'], 'prepared_by': entry['prepared_by'],
        'status': 'unavailable' if entry['source']['access'] == 'unavailable' else 'ready',
        'source': deepcopy(entry['source']), 'terms': rows, 'categories': deepcopy(entry['categories']),
        'requested': deepcopy(entry['requested']), 'prepared': actual, 'shortfalls': shortfalls,
        'notice': 'Only supplied source-supported terms and defensible groups are prepared. Missing requested items are not invented.' if shortfalls else 'Prepared vocabulary; reading definitions never records demonstrated use.',
        'scope': 'Supplied ' + entry['source']['access'] + ' snapshot; source quotations matched locally, definitions and category membership remain prepared interpretations, not independent scientific verification.'}
