"""Read-only ownership and defense projections; scientific support is not mastery."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import os
from pathlib import Path
import tempfile

import computational_manifest as cm
import knowledge as k
import literature_check as lc
from migrate_learning import confined
from paper_access import root_path, safe_text
import research
import tutor_session as ts
import validate_evidence as ev

LINKS = {'evidence', 'source', 'theory', 'assumptions', 'method', 'implementation',
         'experiment', 'manifest', 'limitations', 'decision'}
USES = {'presentation', 'manuscript', 'modification', 'personal_understanding', 'major_decision'}
TOPICS = {
    'explanation': ('Explain this claim without notes and connect it to its evidence.', 'Explain the mechanism and distinguish evidence from inference.'),
    'derivation': ('Derive or motivate the central relation, including its limiting cases.', 'Reconstruct the steps, units and limiting cases.'),
    'assumptions': ('Which assumptions are necessary, and what breaks if one is violated?', 'Name necessary assumptions and a consequential violation.'),
    'range': ('In which regime is this claim valid, and where should it fail?', 'State the supported range and a boundary failure.'),
    'units': ('Check the units and dimensional consistency of this claim.', 'Explain the relevant units and dimensional check.'),
    'limiting_cases': ('What happens in a limiting case, and why?', 'Reason through a meaningful limit.'),
    'epistemic': ('Separate the facts, assumptions and hypotheses in this claim.', 'Separate each epistemic category with justification.'),
    'alternative': ('What alternative interpretation is compatible with the evidence?', 'Give an alternative and a discriminating observation.'),
    'falsification': ('What observation would falsify or materially weaken the conclusion?', 'Specify a discriminating falsification test.'),
    'navigation': ('Locate the relevant code or workflow and explain how you would modify it.', 'Locate consequential behavior and explain a concrete modification.'),
    'method': ('Why was this method chosen over a plausible alternative?', 'Justify choice, assumptions, alternative and failure mode.'),
    'tool': ('Perform the relevant reproducible tool action and inspect whether it succeeded.', 'Demonstrate the action, reproduction steps and success/failure inspection.'),
    'failure': ('What failure mode could produce a misleading result here?', 'Explain a failure mode and how to detect it.'),
    'reconsideration': ('What new result would change your conclusion?', 'Describe evidence that would change the conclusion.'),
    'transfer': ('Apply the reasoning to this explicitly unfamiliar scenario.', 'Reconstruct the reasoning in an independent unfamiliar example.'),
}


def digest(value):
    return hashlib.sha256(ev.canonical(value).encode('utf-8')).hexdigest()


def target_fingerprint(claim):
    return digest({key: claim[key] for key in ('claim_id', 'text', 'scope')})


def shape(value, required, optional=()):
    ts.shape(value, required, optional)


def text(value):
    safe_text(value)
    return value


def identifier(value):
    if not isinstance(value, str) or not lc.ID.fullmatch(value) or len(value) > 100:
        raise ValueError('bounded record ID required')
    return value


def items(value, limit=30):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError('bounded list required')
    return value


def dated(value, as_of):
    if k.iso_date(value) > as_of:
        raise ValueError('future review cannot establish current readiness')


def reference(value):
    shape(value, {'path', 'sha256'}, {'record_id', 'line'})
    text(value['path'])
    if not isinstance(value['sha256'], str) or not lc.HASH.fullmatch(value['sha256']):
        raise ValueError('bound file hash required')
    if 'record_id' in value:
        identifier(value['record_id'])
    if 'line' in value and (type(value['line']) is not int or value['line'] < 1):
        raise ValueError('one-based code line required')


class Inputs:
    """Bounded, versioned inputs; detect cooperative changes before export."""
    def __init__(self, root):
        self.root = root_path(root)
        self.hashes = {}
        self.total = 0
        self.markdown = None

    def read(self, relative, expected=None):
        path = confined(self.root, relative)
        with path.open('rb') as stream:
            data = stream.read(50 * 1024 * 1024 + 1)
        if len(data) > 50 * 1024 * 1024:
            raise ValueError('bounded local input required')
        actual = hashlib.sha256(data).hexdigest()
        if relative not in self.hashes:
            self.total += len(data)
            if len(self.hashes) >= 1000 or self.total > 64 * 1024 * 1024:
                raise ValueError('bounded projection inputs required')
        elif self.hashes[relative] != actual:
            raise ValueError('input changed during projection')
        self.hashes[relative] = actual
        if expected is not None and actual != expected:
            raise ValueError('referenced file changed')
        return data

    def json(self, relative, expected=None):
        data = self.read(relative, expected)
        if len(data) > lc.MAX_BYTES:
            raise ValueError('bounded JSON input required')
        return ev.EvidenceAtom.parse(data.decode('utf-8')).record

    def ref(self, value):
        reference(value)
        return self.read(value['path'], value['sha256'])

    def markdown_paths(self):
        paths = []
        for directory, folders, files in os.walk(self.root, followlinks=False):
            folders[:] = sorted(x for x in folders if not x.startswith('.') and not (Path(directory) / x).is_symlink())
            for name in sorted(files):
                path = Path(directory) / name
                if path.suffix.lower() == '.md' and not path.is_symlink():
                    paths.append(path.relative_to(self.root).as_posix())
                    if len(paths) > 500:
                        raise ValueError('use a bounded records root')
        return sorted(paths)

    def prepare(self):
        self.markdown = self.markdown_paths()
        for path in self.markdown:
            if len(self.read(path)) > lc.MAX_BYTES:
                raise ValueError('bounded Markdown required')

    def finish(self):
        if self.markdown != self.markdown_paths():
            raise ValueError('record set changed during projection')
        for path, expected in list(self.hashes.items()):
            self.read(path, expected)
        return [{'path': path, 'sha256': value} for path, value in sorted(self.hashes.items())]


def requirement(value):
    shape(value, {'capability', 'scope', 'dimension', 'context'})
    ts.identity(value['capability'])
    if value['scope'] not in k.SCOPES or value['dimension'] not in k.supported_dimensions(3):
        raise ValueError('explicit capability scope/dimension required')
    if (value['scope'] == 'transfer') != (value['dimension'] == 'transfer'):
        raise ValueError('transfer scope and dimension must agree')
    if value['scope'] == 'project_application':
        ts.identity(value['context'])
    elif value['context'] != '':
        raise ValueError('non-project context must be empty')


def requirements(values):
    items(values, 20)
    seen = set()
    for value in values:
        requirement(value)
        key = ev.canonical(value)
        if key in seen:
            raise ValueError('duplicate capability requirement')
        seen.add(key)


def capability_state(collection, value, as_of):
    node = collection.nodes.get(value['capability'])
    unknown = dict(value, state='unknown', freshness='unknown', sufficient=False,
                   ledger=None, attempts=[], diagnostics=[])
    if node is None or node.issues:
        unknown['diagnostics'] = ['missing, duplicate or invalid canonical capability']
        return unknown
    unknown['ledger'] = node.path
    if not node.mastery or value['dimension'] not in k.supported_dimensions(node.meta['learning_schema']):
        unknown['diagnostics'] = ['legacy or unsupported dimension; no scoped mastery inferred']
        return unknown
    if value['scope'] == 'project_application' and not collection.ontology.valid(value['context'], {'project', 'research-block'}):
        unknown['diagnostics'] = ['missing or invalid project/block context']
        return unknown
    rows = [a for a in node.attempts if a.day <= as_of and a.scope == value['scope']
            and a.dimension == value['dimension'] and a.context == value['context']]
    assessment = k.mastery(rows, as_of, node.meta['learning_schema'])[value['scope']][value['dimension']]
    closure, todo = set(), list(node.prerequisites)
    while todo:
        key = todo.pop()
        if key not in closure:
            closure.add(key)
            if key in collection.nodes:
                todo.extend(collection.nodes[key].prerequisites)
    missing = sorted(closure - k.ready_nodes(collection.nodes))
    sufficient = (assessment.state in {'demonstrated', 'retained'} and assessment.review is not None
                  and as_of <= assessment.review and not missing)
    return dict(value, **k.assessment_data(assessment, as_of), sufficient=sufficient, ledger=node.path,
                retention_target=node.retention_target, blocked_by=missing,
                attempts=[{'date': str(a.day), 'period': a.period, 'timing': a.timing,
                           'method': a.method, 'outcome': a.outcome, 'assistance': a.assistance,
                           'evidence': a.evidence} for a in rows], diagnostics=[])


def personal(states):
    if not states or all(state['state'] == 'unknown' for state in states):
        return 'UNKNOWN'
    return 'DEFENSIBLE' if all(state['sufficient'] for state in states) else 'INCOMPLETE'


def linked(inputs, value, kind, registry):
    """Link validity, not support or learning. Invalid links remain visible."""
    reference(value)
    try:
        raw = inputs.ref(value)
        status = 'BOUND_REFERENCE'
        if 'line' in value and value['line'] > len(raw.decode('utf-8').splitlines()):
            raise ValueError('code line missing')
        if kind in {'experiment', 'decision'}:
            record = registry.records.get(value.get('record_id'))
            expected = 'experiment' if kind == 'experiment' else 'research-decision'
            if record is None or record.path != value['path'] or record.type != expected or any(
                    d.severity == 'ERROR' and (not d.path or d.path == record.path) for d in registry.diagnostics):
                raise ValueError('invalid typed research record')
            status = ('ACCEPTED_DECISION' if kind == 'decision' and record.meta['status'] == 'accepted'
                      else 'UNACCEPTED_DECISION' if kind == 'decision' else record.meta['status'])
        elif kind == 'manifest':
            data = cm.loads(raw.decode('utf-8'))
            status = 'COMPUTATION_FAILED' if data['failure'] is not None else 'VALID_MANIFEST'
        elif kind == 'evidence':
            data = ev.EvidenceAtom.parse(raw.decode('utf-8')).record
            if ev.validate(data):
                raise ValueError('invalid standalone EvidenceAtom')
            status = data['verification_status']
        return dict(value, kind=kind, state=status)
    except (ValueError, OSError, UnicodeError, KeyError, TypeError):
        return dict(value, kind=kind, state='MISSING_INVALID_OR_CHANGED')


def ownership_data(value, as_of):
    shape(value, {'ownership_schema', 'gaps'})
    if type(value['ownership_schema']) is not int or value['ownership_schema'] != 1:
        raise ValueError('unsupported ownership schema')
    seen = set()
    for gap in items(value['gaps'], 100):
        shape(gap, {'gap_id', 'subject', 'introduced_by', 'required_for', 'consequence',
                    'affected', 'requirements', 'selection'})
        identifier(gap['gap_id'])
        if gap['gap_id'] in seen:
            raise ValueError('duplicate ownership gap')
        seen.add(gap['gap_id'])
        for key in ('subject', 'introduced_by', 'consequence'):
            text(gap[key])
        ts.strings(gap['required_for'])
        if not gap['required_for'] or set(gap['required_for']) - USES:
            raise ValueError('select consequential ownership contexts')
        if not items(gap['affected'], 20) or not gap['requirements']:
            raise ValueError('affected work and selective requirements required')
        for affected in gap['affected']:
            shape(affected, {'kind', 'ref'})
            if affected['kind'] not in {'implementation', 'theory', 'method', 'decision', 'experiment', 'manifest', 'evidence'}:
                raise ValueError('typed affected work required')
            reference(affected['ref'])
        requirements(gap['requirements'])
        shape(gap['selection'], {'reviewed_by', 'reviewed_at', 'rationale'})
        text(gap['selection']['reviewed_by'])
        text(gap['selection']['rationale'])
        dated(gap['selection']['reviewed_at'], as_of)


def ownership_rows(inputs, data, collection, registry, as_of):
    ownership_data(data, as_of)
    result = []
    for gap in data['gaps']:
        states = [capability_state(collection, value, as_of) for value in gap['requirements']]
        affected = [linked(inputs, value['ref'], value['kind'], registry) for value in gap['affected']]
        broken = any(link['state'] == 'MISSING_INVALID_OR_CHANGED' for link in affected)
        status = ('OPEN_REFERENCE_GAP' if broken else 'RESOLVED' if personal(states) == 'DEFENSIBLE'
                  else 'OPEN_UNKNOWN' if personal(states) == 'UNKNOWN' else 'OPEN_EVIDENCE_GAP')
        result.append({'gap_id': gap['gap_id'], 'subject': gap['subject'], 'introduced_by': gap['introduced_by'],
                       'required_for': gap['required_for'], 'consequence': gap['consequence'],
                       'selection': gap['selection'], 'affected': affected, 'capabilities': states,
                       'state': status, 'research_blocker': False})
    return result


def claim_data(claim, as_of):
    shape(claim, {'claim_id', 'text', 'scope', 'literature', 'review', 'requirements', 'links', 'ownership_gaps'})
    identifier(claim['claim_id'])
    text(claim['text'])
    if not isinstance(claim['scope'], dict) or set(claim['scope']) - set(ev.ENVELOPE + ev.COMPARISON + (
            'source_value', 'source_units', 'derived_value', 'derived_units')):
        raise ValueError('explicit target scope required')
    for value in claim['scope'].values():
        text(value)
    requirements(claim['requirements'])
    ts.strings(claim['ownership_gaps'])
    if not isinstance(claim['links'], dict) or set(claim['links']) - LINKS:
        raise ValueError('documented graph links required')
    for links in claim['links'].values():
        for ref in items(links, 20):
            reference(ref)
    if claim['literature'] is not None:
        shape(claim['literature'], {'ref', 'atom_id'})
        reference(claim['literature']['ref'])
        identifier(claim['literature']['atom_id'])
    if claim['review'] is not None:
        review = claim['review']
        shape(review, {'status', 'reviewed_by', 'reviewed_at', 'target_fingerprint', 'atom_fingerprint', 'literature_fingerprint', 'rationale'})
        if review['status'] not in {'matches', 'overstated', 'unresolved'}:
            raise ValueError('explicit target wording review required')
        for key in ('reviewed_by', 'rationale'):
            text(review[key])
        dated(review['reviewed_at'], as_of)
        for key in ('target_fingerprint', 'atom_fingerprint', 'literature_fingerprint'):
            if not isinstance(review[key], str) or not lc.HASH.fullmatch(review[key]):
                raise ValueError('bound wording/atom review required')


def science(inputs, claim, reports):
    unknown = {'state': 'UNCERTAIN', 'reason': 'No valid, current wording review and factual evidence.',
               'atom_id': None, 'atom_status': None, 'source': None, 'evidence': None}
    if claim['literature'] is None:
        return unknown
    spec = claim['literature']
    try:
        ref = spec['ref']
        inputs.ref(ref)
        key = (ref['path'], ref['sha256'])
        if key not in reports:
            manifest = inputs.json(ref['path'], ref['sha256'])
            # Capture every dependency the canonical checker reads, not only the
            # displayed atom: derivations/conflicts/access may change eligibility.
            for entry in items(manifest.get('claims'), 500):
                inputs.read(entry['atom_ref'])
                if 'access_ref' in entry:
                    inputs.read(entry['access_ref']['record_ref'])
                    inputs.read(entry['access_ref']['document_ref'])
            reports[key] = (manifest, lc.check(inputs.root, manifest))
        manifest, report = reports[key]
        entry = next(row for row in manifest['claims'] if row['claim_id'] == spec['atom_id'])
        atom = inputs.json(entry['atom_ref'])
        unknown.update(atom_id=spec['atom_id'], atom_status=atom.get('verification_status'),
                       source={key: atom.get(key) for key in ('source_identifier', 'source_version', 'source_locator')},
                       evidence={'path': entry['atom_ref'], 'sha256': inputs.hashes[entry['atom_ref']]})
        if not report['valid'] or atom['claim_id'] != spec['atom_id']:
            return dict(unknown, reason='Invalid literature/evidence inputs; inspect canonical checks.')
        review = claim['review']
        if review is None or review['target_fingerprint'] != target_fingerprint(claim) or review['atom_fingerprint'] != ev.fingerprint(atom) or review['literature_fingerprint'] != report['manifest_fingerprint']:
            return dict(unknown, reason='Missing or stale target wording/atom review.')
        if review['status'] == 'overstated' or atom['verification_status'] == 'OVERSTATED':
            return dict(unknown, state='OVERSTATED', reason='Bound review identifies overstatement.')
        if atom['verification_status'] in {'CONTRADICTED', 'NOT_FOUND'}:
            return dict(unknown, state='UNSUPPORTED', reason='Canonical atom does not support the target.')
        if review['status'] != 'matches':
            return dict(unknown, reason='Target reviewer records unresolved scientific support.')
        required = set(atom.get('required_envelope', []))
        if atom.get('quantitative'):
            required |= {'derived_value', 'derived_units'} if atom.get('evidence_type') == 'derived' else {'source_value', 'source_units'}
        if atom.get('comparison'):
            required |= set(ev.COMPARISON)
        if not required <= claim['scope'].keys() or any(atom.get(key) != value for key, value in claim['scope'].items()):
            return dict(unknown, reason='Target scope/value is missing or differs from linked evidence.')
        factual = {row['atom']['claim_id'] for row in report['facts']}
        if spec['atom_id'] not in factual or atom['verification_status'] != 'EXACT_SUPPORT':
            return dict(unknown, reason='Qualified, unresolved, disputed or access-limited evidence.')
        return dict(unknown, state='SUPPORTED', reason='Current reviewed target matches eligible referenced evidence; no project acceptance implied.')
    except (ValueError, OSError, TypeError, KeyError, UnicodeError, StopIteration):
        return dict(unknown, reason='Missing, invalid or changed literature/evidence reference.')


def project(root, declaration, as_of, *, inputs=None):
    shape(declaration, {'defense_schema', 'presentation_id', 'claims'}, {'ownership_ref'})
    if type(declaration['defense_schema']) is not int or declaration['defense_schema'] != 1:
        raise ValueError('unsupported defense schema')
    identifier(declaration['presentation_id'])
    inputs = inputs or Inputs(root)
    inputs.prepare()
    collection = k.discover(inputs.root, as_of)
    registry = research.validate(inputs.root)
    gaps, ownership_error = [], None
    if declaration.get('ownership_ref') is not None:
        ref = declaration['ownership_ref']
        reference(ref)
        try:
            gaps = ownership_rows(inputs, inputs.json(ref['path'], ref['sha256']), collection, registry, as_of)
        except (ValueError, OSError, TypeError, KeyError, UnicodeError):
            ownership_error = 'Missing, invalid or changed ownership requirements.'
    gap_index = {gap['gap_id']: gap for gap in gaps}
    claims, seen, reports = [], set(), {}
    for claim in items(declaration['claims'], 50):
        claim_data(claim, as_of)
        if claim['claim_id'] in seen:
            raise ValueError('duplicate presentation claim')
        seen.add(claim['claim_id'])
        states = [capability_state(collection, value, as_of) for value in claim['requirements']]
        selected = [gap_index[key] for key in claim['ownership_gaps'] if key in gap_index]
        missing = sorted(set(claim['ownership_gaps']) - gap_index.keys())
        # Referenced ownership requirements are part of the personal objective.
        combined = {ev.canonical({key: state[key] for key in ('capability', 'scope', 'dimension', 'context')}): state
                    for state in states + [state for gap in selected for state in gap['capabilities']]}
        states = list(combined.values())
        readiness = personal(states)
        if missing or any(gap['state'] == 'OPEN_REFERENCE_GAP' for gap in selected):
            readiness = 'INCOMPLETE' if states else 'UNKNOWN'
        links = {kind: [linked(inputs, ref, kind, registry) for ref in refs] for kind, refs in claim['links'].items()}
        claims.append({'claim_id': claim['claim_id'], 'text': claim['text'], 'scope': claim['scope'],
                       'target_fingerprint': target_fingerprint(claim), 'scientific_support': science(inputs, claim, reports),
                       'personal_defensibility': readiness, 'capabilities': states, 'links': links,
                       'missing_link_categories': sorted(LINKS - {kind for kind, refs in links.items() if refs}),
                       'ownership_gaps': selected, 'missing_ownership_gaps': missing,
                       'next_actions': []})
        # No cross-axis score: actions stay attached to this claim and its gaps.
        row = claims[-1]
        row['next_actions'] = ([] if row['scientific_support']['state'] == 'SUPPORTED' else [{'action': 'source_review_or_reword'}])
        row['next_actions'] += [{'action': 'assess_or_repair_capability', 'capability': s['capability'],
                                'scope': s['scope'], 'dimension': s['dimension'], 'context': s['context']}
                               for s in states if not s['sufficient']]
        if not states:
            row['next_actions'].append({'action': 'select_personal_capability_requirements'})
        if missing or any(gap['state'] == 'OPEN_REFERENCE_GAP' for gap in selected):
            row['next_actions'].append({'action': 'repair_ownership_references'})
        if readiness != 'DEFENSIBLE' and not row['next_actions']:
            row['next_actions'].append({'action': 'review_personal_requirements'})
    return {'projection_schema': 1, 'snapshot': True, 'presentation_id': declaration['presentation_id'],
            'as_of': str(as_of), 'declaration_fingerprint': digest(declaration), 'claims': claims,
            'ownership': gaps, 'ownership_diagnostic': ownership_error,
            'inputs': inputs.finish(), 'note': 'Read-only snapshot. No global ready flag, scientific acceptance, learning promotion or research gate.'}


def ownership(root, declaration, as_of, *, inputs=None):
    inputs = inputs or Inputs(root)
    inputs.prepare()
    rows = ownership_rows(inputs, declaration, k.discover(inputs.root, as_of), research.validate(inputs.root), as_of)
    return {'projection_schema': 1, 'snapshot': True, 'as_of': str(as_of),
            'declaration_fingerprint': digest(declaration), 'ownership': rows,
            'inputs': inputs.finish(), 'note': 'Advisory ownership gaps; no scientific invalidation or execution gate.'}


def question_for(state, wording, topic=None, scenario=None):
    dimension = state['dimension']
    topic = topic or {'explanation': 'explanation', 'recognition': 'epistemic', 'derivation': 'derivation',
                      'transfer': 'transfer', 'application': 'failure', 'method_understanding': 'method',
                      'tool_operation': 'tool', 'implementation_navigation': 'navigation'}[dimension]
    if topic not in TOPICS or (dimension == 'transfer') != (topic == 'transfer'):
        raise ValueError('topic must match the actual assessed dimension')
    if dimension in {'tool_operation', 'implementation_navigation'} and topic != {
            'tool_operation': 'tool', 'implementation_navigation': 'navigation'}[dimension]:
        raise ValueError('operation/navigation questions must assess the actual action')
    if topic == 'transfer' and not scenario:
        return None  # An independent scenario must be prepared, never inferred.
    if scenario is not None:
        text(scenario)
    prompt, criterion = TOPICS[topic]
    method = 'computation' if dimension in {'tool_operation', 'application'} else 'derivation' if dimension == 'derivation' else 'transfer' if dimension == 'transfer' else 'explanation' if dimension != 'recognition' else 'prediction'
    return {'capability': state['capability'], 'schema': 3, 'scope': state['scope'], 'dimension': dimension,
            'context': state['context'], 'method': method, 'question': prompt + ' Target: ' + wording +
            (' Scenario: ' + scenario if topic == 'transfer' else ''),
            'contract': {'TESTS': [state['capability']], 'ASSUMES': [], 'INTRODUCES': {}},
            'established': [], 'criteria': [criterion], 'units': 1, 'independent_example': topic == 'transfer'}


def viva(projection, *, claim_id=None, session=None, topic=None, scenario=None):
    rows = projection['claims']
    target = next((row for row in rows if row['claim_id'] == claim_id), None) if claim_id else next(
        (row for row in rows if row['personal_defensibility'] != 'DEFENSIBLE'), rows[0] if rows else None)
    if target is None:
        raise ValueError('explicit existing viva claim required')
    states = target['capabilities']
    result = {'claim_id': target['claim_id'], 'scientific_support': target['scientific_support'],
              'personal_defensibility': target['personal_defensibility'],
              'declaration_fingerprint': projection['declaration_fingerprint'], 'question': None,
              'note': 'One question at a time; honest uncertainty is welcome. Session answers never update canonical readiness.'}
    passed, used, limit = set(), 0, 5
    if session is not None:
        shape(session, {'viva_schema', 'declaration_fingerprint', 'claim_id', 'lesson', 'answer_reviews'})
        if type(session['viva_schema']) is not int or session['viva_schema'] != 1 or session['claim_id'] != target['claim_id'] or session['declaration_fingerprint'] != projection['declaration_fingerprint']:
            raise ValueError('viva session must bind the current target declaration')
        lesson = ts.replay(session['lesson'])
        allowed = {ev.canonical({key: state[key] for key in ('capability', 'scope', 'dimension', 'context')}) for state in states}
        answers = {answer['id']: answer for answer in lesson['assessed_answers']}
        for event in session['lesson']['events']:
            if event['type'] in {'probe', 'learner_reasoning'} and ev.canonical({key: event['assessment'][key] for key in ('capability', 'scope', 'dimension', 'context')}) not in allowed:
                raise ValueError('viva assessment outside reviewed claim requirements')
        reviews, seen = {}, set()
        for review in items(session['answer_reviews'], 100):
            shape(review, {'assessment_id', 'answer_kind', 'follow_up'})
            key = review['assessment_id']
            if key not in answers or key in seen or review['answer_kind'] not in {'substantive', 'vague', 'uncertain', 'fabricated'}:
                raise ValueError('actual unique answer review required')
            seen.add(key)
            answer = answers[key]
            if review['answer_kind'] != 'substantive' and answer['review']['outcome'] == 'pass':
                raise ValueError('uncertainty/vagueness cannot masquerade as capability mastery')
            if review['follow_up'] is not None:
                ts.probe(review['follow_up'])
                if any(review['follow_up'][key] != answer['assessment'][key] for key in ('capability', 'scope', 'dimension', 'context')):
                    raise ValueError('drill-down must preserve the assessed objective')
            reviews[key] = review
        # Review list order is metadata, not answer chronology. A later failed,
        # assisted or unclassified answer supersedes prior round sufficiency.
        for answer in lesson['assessed_answers']:
            if answer['id'] in reviews and answer['review']['outcome'] == 'pass' and answer['review']['assistance'] == 'none':
                passed.add(ev.canonical({key: answer['assessment'][key] for key in ('capability', 'scope', 'dimension', 'context')}))
            else:
                passed.discard(ev.canonical({key: answer['assessment'][key] for key in ('capability', 'scope', 'dimension', 'context')}))
        result['lesson'] = lesson
        used, limit = lesson['budget']['used'], lesson['budget']['limit']
        if lesson['branches']:
            return dict(result, action='answer_learner_question_then_resume')
        if lesson['pending_assessment'] is not None:
            pending = lesson['pending_assessment']
            return dict(result, action='await_answer' if pending['answer'] is None else 'review_actual_answer',
                        question=pending['assessment'] if pending['answer'] is None else None)
        if answers:
            latest = lesson['assessed_answers'][-1]
            review = reviews.get(latest['id'])
            if review is None:
                return dict(result, action='classify_actual_answer_before_continuing')
            if review['answer_kind'] == 'uncertain':
                return dict(result, action='acknowledge_uncertainty_and_offer_targeted_learning')
            if review['answer_kind'] in {'vague', 'fabricated'} or latest['review']['outcome'] != 'pass':
                if used >= limit:
                    return dict(result, action='budget_exhausted_pause_or_request_extension')
                return dict(result, action='drill_down' if review['answer_kind'] != 'fabricated' else 'separate_observation_from_inference',
                            question=review['follow_up'], preparation_needed=review['follow_up'] is None)
            if latest['review']['assistance'] != 'none':
                return dict(result, action='review_assistance_and_prepare_fresh_probe',
                            preparation_needed=True)
    if used >= limit:
        return dict(result, action='budget_exhausted_pause_or_request_extension')
    remaining = [state for state in states if ev.canonical({key: state[key] for key in ('capability', 'scope', 'dimension', 'context')}) not in passed]
    if not remaining:
        return dict(result, action='round_complete_review_canonical_evidence' if states else 'select_capability_requirements')
    state = next((state for state in remaining if not state['sufficient']), remaining[0])
    probe = question_for(state, target['text'], topic, scenario)
    if probe is None:
        return dict(result, action='prepare_independent_transfer_scenario')
    ts.probe(probe)
    return dict(result, action='ask_one_question', question=probe)


def publish(root, relative, value):
    destination = confined(root, relative)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(value, ensure_ascii=True, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = ts.SafeParser(description=__doc__)
    parser.add_argument('mode', choices=('project', 'ownership', 'viva'))
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--input', required=True)
    parser.add_argument('--as-of', type=k.iso_date, default=date.today())
    parser.add_argument('--export', help='Explicitly create a new snapshot; never overwrite')
    parser.add_argument('--claim')
    parser.add_argument('--session')
    parser.add_argument('--topic', choices=sorted(TOPICS))
    parser.add_argument('--scenario')
    args = parser.parse_args(argv)
    try:
        inputs = Inputs(args.root)
        declaration = inputs.json(args.input)
        if args.mode != 'viva' and any((args.claim, args.session, args.topic, args.scenario)):
            raise ValueError('viva options require viva mode')
        session = inputs.json(args.session) if args.session else None
        result = ownership(inputs.root, declaration, args.as_of, inputs=inputs) if args.mode == 'ownership' else project(inputs.root, declaration, args.as_of, inputs=inputs)
        if args.mode == 'viva':
            feedback = viva(result, claim_id=args.claim, session=session, topic=args.topic, scenario=args.scenario)
            feedback.update(snapshot=True, as_of=str(args.as_of), inputs=result['inputs'])
            result = feedback
        if args.export:
            publish(inputs.root, args.export, result)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (ValueError, TypeError, KeyError, OSError, UnicodeError, RecursionError):
        print(json.dumps({'error': 'Invalid or unavailable defense inputs.'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
