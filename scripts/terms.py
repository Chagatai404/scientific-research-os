"""Term ledger, learner profile and Student Brief: what the learner is recorded as knowing, term by term.

Capability mastery says whether a learner can *do* something; this module records whether they know the *words* a lesson
uses, per language, so a tutor never throws an unexplained term at them. State is derived by folding an append-only
event log; nothing here grades an answer or infers mastery. An unseen term is unseen, not known.

Files under ``<vault>/.research-os/learner/`` (all optional):

    term-events.jsonl  one JSON event per line, appended only by ``record`` after an honest review
    glossary.json      {"terms": {id: {"labels": {lang: text}, "concepts": [ids]}}}
    profile.json       declared preferences: languages, goals, time budget. Never a "learning style".
"""
from __future__ import annotations
import argparse
import json
from datetime import date
from pathlib import Path
import re
import sys
import unicodedata

LEARNER_DIR = Path('.research-os') / 'learner'
EVENTS, GLOSSARY, PROFILE = 'term-events.jsonl', 'glossary.json', 'profile.json'
KINDS = ('introduced', 'restated', 'used', 'missed')
EVIDENCE = {'restated', 'used', 'missed'}  # introduced is the tutor's act, never the learner's
KNOWN = {'defined', 'used', 'fluent'}
STATES = ('unseen', 'introduced', 'shaky', 'defined', 'used', 'fluent')
LANG = re.compile(r'[a-z]{2,3}(?:-[A-Za-z]{2,4})?\Z')
ID = re.compile(r'[a-z0-9][a-z0-9-]{0,63}\Z')
PROFILE_KEYS = {'profile_schema', 'languages', 'goals', 'time_budget_minutes', 'checkpoint_pace'}
PACES = ('light', 'normal', 'frequent')
LANGUAGE_KEYS = {'primary', 'secondary', 'by_domain'}
STYLE_WORDS = re.compile(r'style|visual.?learner|auditory|kinesthetic|learning.?type', re.I)
MIN_MEASURED = 5
MAX_BRIEF_TERMS = 40


def term_id(text: str) -> str:
    """Stable ASCII slug of a term as written ("olasılık yoğunluğu" -> "olasilik-yogunlugu")."""
    folded = unicodedata.normalize('NFKD', str(text).replace('ı', 'i').replace('İ', 'i')).casefold()
    slug = re.sub(r'[^a-z0-9]+', '-', ''.join(c for c in folded if not unicodedata.combining(c))).strip('-')
    if not slug:
        raise ValueError('a term needs at least one letter or digit')
    return slug[:64].strip('-')


def learner_dir(vault) -> Path | None:
    return Path(vault) / LEARNER_DIR if vault else None


# ---------------------------------------------------------------------------------------------- reading

def load_glossary(directory: Path) -> tuple[dict, list[str]]:
    path = directory / GLOSSARY
    if not path.is_file():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        terms = data['terms']
        if not isinstance(terms, dict):
            raise TypeError
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {}, [f'{GLOSSARY}: unreadable ({type(exc).__name__}); terms are unlinked to concepts']
    clean, problems = {}, []
    for key, entry in terms.items():
        labels = entry.get('labels') if isinstance(entry, dict) else None
        concepts = entry.get('concepts', []) if isinstance(entry, dict) else None
        if (not ID.fullmatch(str(key)) or not isinstance(labels, dict) or not labels
                or any(not LANG.fullmatch(str(lang)) or not isinstance(text, str) or not text.strip() for lang, text in labels.items())
                or not isinstance(concepts, list) or any(not isinstance(c, str) or not c for c in concepts)):
            problems.append(f'{GLOSSARY}: entry {key!r} is malformed and was skipped')
            continue
        clean[key] = {'labels': dict(labels), 'concepts': sorted(set(concepts))}
    return clean, problems


def _event_problem(event) -> str | None:
    if not isinstance(event, dict):
        return 'not an object'
    if not ID.fullmatch(str(event.get('term', ''))):
        return 'term is not a term id'
    if not LANG.fullmatch(str(event.get('lang', ''))):
        return 'lang is not a language code'
    if event.get('kind') not in KINDS:
        return 'kind must be one of ' + ', '.join(KINDS)
    try:
        date.fromisoformat(str(event.get('date')))
    except ValueError:
        return 'date must be an ISO date'
    if event['kind'] in EVIDENCE and not (isinstance(event.get('reviewed_by'), str) and event['reviewed_by'].strip()):
        return 'learner evidence requires reviewed_by'
    confidence = event.get('confidence')
    if confidence is not None and not (isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and 0 <= confidence <= 1):
        return 'confidence must be between 0 and 1'
    hints = event.get('hints')
    if hints is not None and not (type(hints) is int and hints >= 0):
        return 'hints must be a non-negative integer'
    return None


def load_events(directory: Path) -> tuple[list[dict], list[str]]:
    """Valid events in file order, and one diagnostic per rejected line. A bad line never hides the good ones."""
    path = directory / EVENTS
    if not path.is_file():
        return [], []
    events, problems = [], []
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeError) as exc:
        return [], [f'{EVENTS}: unreadable ({type(exc).__name__})']
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            problems.append(f'{EVENTS}:{number}: not valid JSON')
            continue
        problem = _event_problem(event)
        if problem:
            problems.append(f'{EVENTS}:{number}: {problem}')
        else:
            events.append(event)
    return events, problems


def state_of(events: list[dict]) -> str:
    """State of one term in one language from its events (file order breaks date ties).

    unseen -> introduced (presented) -> defined (learner restated, reviewed) -> used (applied unprompted, reviewed)
    -> fluent (used on two different dates with no miss in between). A reviewed miss makes the term shaky until new evidence.
    """
    if not events:
        return 'unseen'
    ordered = [e for _, e in sorted(enumerate(events), key=lambda p: (p[1]['date'], p[0]))]
    last_miss = max((i for i, e in enumerate(ordered) if e['kind'] == 'missed'), default=-1)
    after = ordered[last_miss + 1:]
    used_dates = {e['date'] for e in after if e['kind'] == 'used'}
    if len(used_dates) >= 2:
        return 'fluent'
    if used_dates:
        return 'used'
    if any(e['kind'] == 'restated' for e in after):
        return 'defined'
    if last_miss >= 0:
        return 'shaky'
    return 'introduced'


def term_states(events: list[dict]) -> dict[str, dict[str, str]]:
    """term id -> {language: state}."""
    grouped: dict[str, dict[str, list]] = {}
    for event in events:
        grouped.setdefault(event['term'], {}).setdefault(event['lang'], []).append(event)
    return {term: {lang: state_of(items) for lang, items in sorted(langs.items())} for term, langs in sorted(grouped.items())}


def best_state(by_lang: dict[str, str], lang: str | None = None) -> str:
    """The state that matters for a lesson in ``lang`` (or the best across languages when none is given)."""
    if lang is not None:
        return by_lang.get(lang, 'unseen')
    return max(by_lang.values(), key=STATES.index, default='unseen')


def load_profile(directory: Path) -> tuple[dict, list[str]]:
    path = directory / PROFILE
    if not path.is_file():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return {}, [f'{PROFILE}: unreadable ({type(exc).__name__})']
    problems = profile_issues(data)
    return ({} if problems else data), [f'{PROFILE}: {p}' for p in problems]


def profile_issues(data) -> list[str]:
    """Declared fields only. A "learning style" is refused: matching instruction to a style has no supporting evidence
    (Pashler, McDaniel, Rohrer & Bjork 2008); measured behaviour is derived from the event log instead."""
    if not isinstance(data, dict):
        return ['profile must be an object']
    problems = [f'{key!r} looks like a learning style; Research OS personalizes on measured knowledge and performance, not styles'
                for key in data if STYLE_WORDS.search(str(key))]
    problems += [f'unknown field {key!r}' for key in data if key not in PROFILE_KEYS and not STYLE_WORDS.search(str(key))]
    languages = data.get('languages', {})
    if not isinstance(languages, dict) or set(languages) - LANGUAGE_KEYS:
        problems.append('languages is an object with only: ' + ', '.join(sorted(LANGUAGE_KEYS)))
    else:
        if 'primary' in languages and not LANG.fullmatch(str(languages['primary'])):
            problems.append('languages.primary must be a language code')
        secondary = languages.get('secondary', [])
        if not isinstance(secondary, list) or not all(LANG.fullmatch(str(x)) for x in secondary):
            problems.append('languages.secondary must be a list of language codes')
        by_domain = languages.get('by_domain', {})
        if not isinstance(by_domain, dict) or any(not LANG.fullmatch(str(v)) for v in by_domain.values()):
            problems.append('languages.by_domain maps a domain to a language code')
    if 'checkpoint_pace' in data and data['checkpoint_pace'] not in PACES:
        problems.append('checkpoint_pace is light, normal or frequent: how often routine code is walked through; it never lowers a consequential unit or an approval')
    if 'goals' in data and (not isinstance(data['goals'], list) or any(not isinstance(g, str) or not g.strip() for g in data['goals'])):
        problems.append('goals is a list of non-empty strings')
    if 'time_budget_minutes' in data and not (type(data['time_budget_minutes']) is int and 0 < data['time_budget_minutes'] <= 1440):
        problems.append('time_budget_minutes is a positive integer')
    return problems


def measured(events: list[dict]) -> dict:
    """What the log shows about how this learner answers; ``None`` until there is enough evidence to say anything."""
    scored = [e for e in events if e['kind'] in EVIDENCE]
    out = {'evidence_events': len(scored), 'hint_rate': None, 'calibration_gap': None,
           'note': f'reported only from {MIN_MEASURED} or more relevant events; positive gap = more confident than correct'}
    hinted = [e for e in scored if e.get('hints') is not None]
    if len(hinted) >= MIN_MEASURED:
        out['hint_rate'] = round(sum(1 for e in hinted if e['hints'] > 0) / len(hinted), 3)
    rated = [e for e in scored if e.get('confidence') is not None]
    if len(rated) >= MIN_MEASURED:
        accuracy = sum(1 for e in rated if e['kind'] != 'missed') / len(rated)
        out['calibration_gap'] = round(sum(e['confidence'] for e in rated) / len(rated) - accuracy, 3)
    return out


# ---------------------------------------------------------------------------------------------- the brief

def brief(vault, concepts=(), lang: str | None = None, max_terms: int = MAX_BRIEF_TERMS) -> dict:
    """Bounded Student Brief for one lesson. Never raises: every problem is reported in ``diagnostics``.

    ``status``: ``not-configured`` (no vault), ``empty`` (no ledger yet, so every term is unseen) or ``ok``.
    ``unseen`` lists only glossary terms linked to the lesson's concepts; a term the glossary does not know cannot be listed.
    """
    directory = learner_dir(vault)
    if directory is None:
        return {'status': 'not-configured', 'diagnostics': [], 'note': 'no vault was given; term knowledge is unknown, not absent'}
    glossary, problems = load_glossary(directory)
    events, event_problems = load_events(directory)
    profile, profile_problems = load_profile(directory)
    diagnostics = (problems + event_problems + profile_problems)[:25]
    if not (directory / EVENTS).is_file() and not glossary and not profile:
        return {'status': 'empty', 'diagnostics': diagnostics, 'languages': {}, 'known': [], 'shaky': [], 'introduced': [], 'unseen': [],
                'language_gaps': [], 'measured': measured([]), 'truncated': None,
                'note': 'no term ledger yet: every term is unseen, nothing is assumed known'}
    states = term_states(events)
    wanted = set(concepts)
    relevant = {t for t, e in glossary.items() if wanted & set(e['concepts'])}
    primary = lang or (profile.get('languages') or {}).get('primary')
    entries = {'known': [], 'shaky': [], 'introduced': [], 'unseen': []}
    gaps = []

    def label(term):
        labels = glossary.get(term, {}).get('labels', {})
        return labels.get(primary) or next(iter(labels.values()), term)

    for term in sorted(relevant | {t for t, langs in states.items() if 'shaky' in langs.values()}):
        by_lang = states.get(term, {})
        state = best_state(by_lang, primary)
        if state not in KNOWN and 'shaky' in by_lang.values():
            state = 'shaky'  # a miss in any language is a signal for this lesson too
        row = {'term': term, 'label': label(term), 'states': by_lang}
        if state in KNOWN:
            entries['known'].append(row)
        elif state == 'shaky':
            entries['shaky'].append(row)
        elif state == 'introduced':
            entries['introduced'].append(row)
        elif term in relevant:
            entries['unseen'].append(row)
        if primary and state not in KNOWN and best_state(by_lang) in KNOWN:
            gaps.append({'term': term, 'label': label(term), 'known_in': sorted(l for l, s in by_lang.items() if s in KNOWN), 'missing_in': primary})
    total = sum(len(v) for v in entries.values())
    truncated = None
    if total > max_terms:
        truncated = {'omitted': total - max_terms}
        for key in ('unseen', 'introduced', 'known', 'shaky'):  # least urgent first; weak terms are never cut before known ones
            while sum(len(v) for v in entries.values()) > max_terms and entries[key]:
                entries[key].pop()
    return {'status': 'ok', 'diagnostics': diagnostics, 'languages': (profile.get('languages') or {}), 'goals': profile.get('goals', []),
            'time_budget_minutes': profile.get('time_budget_minutes'), 'checkpoint_pace': profile.get('checkpoint_pace'), 'language_used': primary, **entries,
            'language_gaps': gaps[:max_terms], 'measured': measured(events), 'truncated': truncated,
            'note': 'derived from the event log; an unseen or unlisted term is unknown, never assumed known'}


def term_view(source) -> dict | None:
    """term id -> {language: state} from a context receipt (``retrieval.learner.student``), a brief, or a plain mapping.

    ``None`` means no term data is available, which is different from ``{}`` ("a ledger exists and every term is unseen").
    """
    if not isinstance(source, dict) or not source:
        return None
    student = ((source.get('retrieval') or {}).get('learner') or {}).get('student') if 'retrieval' in source else source
    if not isinstance(student, dict):
        return None
    if 'status' in student:
        if student['status'] == 'not-configured':
            return None
        return {row['term']: row.get('states') or {} for group in ('known', 'shaky', 'introduced', 'unseen') for row in student.get(group, [])}
    return {key: value for key, value in student.items() if isinstance(value, dict)} or None


# ---------------------------------------------------------------------------------------------- writing

def record_event(vault, term: str, lang: str, kind: str, *, reviewed_by: str | None = None, session: str | None = None,
                 confidence: float | None = None, hints: int | None = None, on: str | None = None) -> dict:
    """Append one event. Learner evidence (restated, used, missed) needs the name of whoever reviewed it."""
    directory = learner_dir(vault)
    if directory is None:
        raise ValueError('a vault is required to record term events')
    event = {'term': term if ID.fullmatch(term) else term_id(term), 'lang': lang, 'kind': kind, 'date': on or date.today().isoformat()}
    for key, value in (('reviewed_by', reviewed_by), ('session', session), ('confidence', confidence), ('hints', hints)):
        if value is not None:
            event[key] = value
    problem = _event_problem(event)
    if problem:
        raise ValueError(problem)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / EVENTS).open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + '\n')
    return event


def define_term(vault, key: str, labels: dict[str, str], concepts: list[str]) -> dict:
    """Add or extend a glossary entry (explicit; a single-writer working record)."""
    directory = learner_dir(vault)
    if directory is None:
        raise ValueError('a vault is required to edit the glossary')
    if not ID.fullmatch(key):
        raise ValueError('glossary id must be lowercase letters, digits and hyphens')
    if any(not LANG.fullmatch(l) or not t.strip() for l, t in labels.items()):
        raise ValueError('labels map a language code to a non-empty text')
    glossary, _ = load_glossary(directory)
    entry = glossary.setdefault(key, {'labels': {}, 'concepts': []})
    entry['labels'].update(labels)
    entry['concepts'] = sorted(set(entry['concepts']) | set(concepts))
    directory.mkdir(parents=True, exist_ok=True)
    (directory / GLOSSARY).write_text(json.dumps({'terms': glossary}, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
    return entry


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('brief', help='print the Student Brief as JSON')
    p.add_argument('--concept', action='append', default=[])
    p.add_argument('--lang')
    p = sub.add_parser('record', help='append a reviewed term event')
    p.add_argument('--term', required=True)
    p.add_argument('--lang', required=True)
    p.add_argument('--kind', required=True, choices=KINDS)
    p.add_argument('--reviewed-by')
    p.add_argument('--session')
    p.add_argument('--confidence', type=float)
    p.add_argument('--hints', type=int)
    p.add_argument('--date')
    p = sub.add_parser('define', help='add a glossary entry linking a term to concepts')
    p.add_argument('--id', required=True)
    p.add_argument('--label', action='append', default=[], metavar='LANG=TEXT')
    p.add_argument('--concept', action='append', default=[])
    sub.add_parser('check', help='report ledger, glossary and profile problems (exit 1 if any)')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        if args.command == 'brief':
            print(json.dumps(brief(args.vault, args.concept, args.lang), indent=2, ensure_ascii=False))
        elif args.command == 'record':
            print(json.dumps(record_event(args.vault, args.term, args.lang, args.kind, reviewed_by=args.reviewed_by, session=args.session,
                                          confidence=args.confidence, hints=args.hints, on=args.date), ensure_ascii=False))
        elif args.command == 'define':
            labels = dict(item.split('=', 1) for item in args.label)
            print(json.dumps(define_term(args.vault, args.id, labels, args.concept), ensure_ascii=False))
        else:
            result = brief(args.vault)
            print(json.dumps(result['diagnostics'], indent=2, ensure_ascii=False))
            return 1 if result['diagnostics'] else 0
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
