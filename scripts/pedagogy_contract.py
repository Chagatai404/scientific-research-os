"""Bounded optional teaching content. Validation is not scientific verification.

The existing questions/segments remain authoritative; this metadata cannot
replace their prompts, keys, criteria, routes or evidence contracts.
"""
import hashlib
import json
import re

MAX_BYTES = 120 * 1024
LEVELS = ('intuitive', 'intermediate', 'formal')
HINT_KINDS = ('cue', 'structure', 'partial-step')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def text(value, limit=4000):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and not re.search(r'[\x00-\x08\x0b-\x1f\x7f]', value)


def validate(plan):
    value = plan.get('pedagogy')
    if value is None and 'pedagogy' not in plan:
        return []
    problems = []
    if not isinstance(value, dict) or set(value) - {'schema', 'socratic', 'explanations'} or type(value.get('schema')) is not int or value.get('schema') != 1:
        return ['pedagogy: schema 1 object with socratic/explanations only required']
    try:
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')) > MAX_BYTES:
            problems.append('pedagogy: content exceeds 120 KiB')
    except (ValueError, TypeError):
        return ['pedagogy: finite JSON content required']
    for family in ('socratic', 'explanations'):
        entries = value.get(family, [])
        if not isinstance(entries, list) or len(entries) > 40:
            problems.append('pedagogy.' + family + ': at most 40 entries')
            continue
        seen, bound = set(), set()
        for entry in entries:
            at = 'pedagogy.' + family
            if not isinstance(entry, dict):
                problems.append(at + ': entry must be an object'); continue
            common = {'id', 'target', 'version', 'sources'}
            specific = {'tree', 'question_id', 'question_sha256', 'hints'} if family == 'socratic' else {'segment_id', 'segment_sha256', 'levels'}
            if set(entry) != common | specific:
                problems.append(at + ': exact binding, version, sources and content fields required')
            ident = entry.get('id')
            if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', ident) or ident in seen:
                problems.append(at + ': unique bounded entry id required')
            else:
                seen.add(ident)
            if entry.get('target') != plan.get('target') or not text(entry.get('target'), 300):
                problems.append(at + ': target must match the prepared plan target')
            if type(entry.get('version')) is not int or not 1 <= entry['version'] <= 1000000:
                problems.append(at + ': positive bounded version required')
            sources = entry.get('sources')
            if not isinstance(sources, list) or not 1 <= len(sources) <= 12 or any(
                not isinstance(s, dict) or set(s) != {'id', 'locator'} or not text(s.get('id'), 200) or not text(s.get('locator'), 400) for s in sources):
                problems.append(at + ': 1..12 source identities and precise locators required')
            if family == 'socratic':
                tree, qid = entry.get('tree'), entry.get('question_id')
                questions = (plan.get(tree) or {}).get('questions', []) if tree in ('probe', 'check') else []
                obj = next((q for q in questions if isinstance(q, dict) and q.get('id') == qid), None)
                key = (tree, qid) if isinstance(qid, str) and isinstance(tree, str) else None
                if obj is None or entry.get('question_sha256') != digest(obj):
                    problems.append(at + ': exact existing question digest required')
                hints = entry.get('hints')
                if not isinstance(hints, list) or not 1 <= len(hints) <= 3:
                    problems.append(at + ': 1..3 graduated hints required')
                else:
                    kinds = []
                    for hint in hints:
                        if not isinstance(hint, dict) or set(hint) != {'kind', 'text'} or hint.get('kind') not in HINT_KINDS or not text(hint.get('text'), 2000):
                            problems.append(at + ': typed bounded hint required')
                        else:
                            kinds.append(HINT_KINDS.index(hint['kind']))
                    if kinds != sorted(set(kinds)):
                        problems.append(at + ': hints must progress cue, structure, partial-step without duplicates')
            else:
                sid = entry.get('segment_id')
                obj = next((s for s in plan.get('segments', []) if isinstance(s, dict) and s.get('id') == sid), None)
                key = sid if isinstance(sid, str) else None
                if obj is None or entry.get('segment_sha256') != digest(obj):
                    problems.append(at + ': exact existing segment digest required')
                levels = entry.get('levels')
                if not isinstance(levels, dict) or not levels or set(levels) - set(LEVELS):
                    problems.append(at + ': one or more known explanation levels required')
                else:
                    for variant in levels.values():
                        if not isinstance(variant, dict) or set(variant) != {'text', 'assumptions', 'bridge'} or not text(variant.get('text'), 12000) or not text(variant.get('bridge'), 2000):
                            problems.append(at + ': explanation text and simplification bridge required'); continue
                        assumptions = variant.get('assumptions')
                        if not isinstance(assumptions, list) or not 1 <= len(assumptions) <= 12 or not all(text(a, 500) for a in assumptions):
                            problems.append(at + ': explicit bounded assumptions required')
            if key is None or key in bound:
                problems.append(at + ': each prepared object may have only one entry')
            else:
                bound.add(key)
    return problems
