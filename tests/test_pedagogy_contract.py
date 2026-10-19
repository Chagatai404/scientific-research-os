import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pedagogy_contract as pc
import session_plan


def prepared():
    plan = json.loads((ROOT / 'examples/session-plan-variance.json').read_text(encoding='utf-8'))
    q, seg = plan['probe']['questions'][0], plan['segments'][0]
    common = dict(target=plan['target'], version=1, sources=[dict(id='synthetic-fixture', locator='finite distribution definition')])
    plan['pedagogy'] = dict(schema=1, socratic=[dict(common, id='variance-hints', tree='probe', question_id=q['id'], question_sha256=pc.digest(q),
        hints=[dict(kind='cue', text='What quantity measures distance from the mean?'), dict(kind='structure', text='Consider squared deviations before averaging.')])],
        explanations=[dict(common, id='variance-levels', segment_id=seg['id'], segment_sha256=pc.digest(seg), levels={
            'intuitive': dict(text='Variance averages squared distances from the mean.', assumptions=['A finite distribution with a finite mean.'], bridge='Distances are squared so signs do not cancel.')})])
    return plan


class Contracts(unittest.TestCase):
    def test_legacy_and_bound_content_validate_without_mutation(self):
        plan = prepared(); before = copy.deepcopy(plan)
        self.assertEqual(session_plan.validate(plan), [])
        self.assertEqual(plan, before)
        del plan['pedagogy']
        self.assertEqual(session_plan.validate(plan), [])

    def test_changed_question_or_segment_requires_rebinding(self):
        for key in ('probe', 'segments'):
            plan = prepared()
            if key == 'probe': plan[key]['questions'][0]['prompt'] += ' Explain.'
            else: plan[key][0]['title'] = 'A changed explanation'
            self.assertTrue(any('digest' in p for p in session_plan.validate(plan)))

    def test_target_and_sources_and_versions_are_explicit(self):
        for key, value in [('target', 'another target'), ('sources', []), ('version', True), ('sources', [dict(id='book', locator='')])]:
            plan = prepared(); plan['pedagogy']['socratic'][0][key] = value
            self.assertTrue(session_plan.validate(plan), (key, value))

    def test_cannot_override_criteria_or_duplicate_a_binding(self):
        plan = prepared(); item = plan['pedagogy']['socratic'][0]
        item['criteria'] = ['Always correct']
        self.assertTrue(session_plan.validate(plan))
        del item['criteria']; plan['pedagogy']['socratic'].append(dict(item, id='duplicate'))
        self.assertTrue(session_plan.validate(plan))

    def test_order_bounds_and_unknown_types_are_rejected(self):
        for change in (lambda p: p['pedagogy'].update(extra=[]),
                       lambda p: p['pedagogy']['socratic'][0]['hints'].reverse(),
                       lambda p: p['pedagogy']['explanations'][0]['levels'].update(mastery={}),
                       lambda p: p['pedagogy']['explanations'][0]['levels']['intuitive'].update(text='x' * 13000),
                       lambda p: p['pedagogy'].update(schema=True)):
            plan = prepared(); change(plan)
            self.assertTrue(session_plan.validate(plan))

    def test_container_byte_bound(self):
        plan = prepared(); entry = plan['pedagogy']['explanations'][0]
        entry['levels']['intuitive']['text'] = '界' * 12000
        entry['levels']['intermediate'] = copy.deepcopy(entry['levels']['intuitive'])
        entry['levels']['formal'] = copy.deepcopy(entry['levels']['intuitive'])
        entry['levels']['formal']['bridge'] = '界' * 2000
        entry['levels']['formal']['assumptions'] = ['界' * 500] * 12
        self.assertTrue(any('120 KiB' in p for p in session_plan.validate(plan)))


if __name__ == '__main__': unittest.main()
