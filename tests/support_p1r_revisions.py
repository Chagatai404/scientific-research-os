"""P1R revision browser fixtures: real writers, synthetic content, disposable folders.

Each family is first presented (a real checkpoint through the writer), then a
NEW id is added with an explicit revision edge. Presented entries are never edited.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import html_sessions as hs
import support_pedagogy_browser
import support_p1d_comparison
from test_handout import SESSION


def edge(old, new):
    return dict(old_id=old['id'], old_version=old['version'], new_id=new['id'], new_version=new['version'])


def explanations(folder):
    root = Path(folder)
    baseline = Path(support_pedagogy_browser.build(str(root))['standalone'])
    hs.append_event(root, SESSION, {'type': 'checkpoint', 'event_id': 'presented-variance-levels-v1', 'question_id': None,
                                    'response': 'pedagogy-level:variance-levels:1:intuitive'})
    plan = hs.load_session(root, SESSION)['plan']
    old = next(e for e in plan['pedagogy']['explanations'] if e['id'] == 'variance-levels')
    new = deepcopy(old)
    new.update(id='variance-levels-2', version=2)
    for name, level in new['levels'].items():
        level['text'] = (f'REVISED-VERSION-TWO {name}: the centered cross term vanishes, so squared error splits '
                         'into variance plus squared bias under a stated finite second moment.')
    plan['pedagogy']['explanations'].append(new)
    plan['pedagogy']['revisions'] = [edge(old, new)]
    hs.update_session(root, SESSION, plan=plan)
    revised = root / 'explanations-revised.html'
    hs.export_session(root, SESSION, revised)
    return {'baseline': str(baseline), 'revised': str(revised)}


def comparisons(folder):
    root = Path(folder)
    baseline = Path(support_p1d_comparison.build(str(root))['standalone'])
    hs.append_event(root, SESSION, {'type': 'checkpoint', 'event_id': 'presented-summary-comparison-v1', 'question_id': None,
                                    'response': 'pedagogy-comparison:summary-comparison:1'})
    plan = hs.load_session(root, SESSION)['plan']
    old = next(e for e in plan['pedagogy']['comparisons'] if e['id'] == 'summary-comparison')
    new = deepcopy(old)
    new.update(id='summary-comparison-2', version=2)
    locator = old['source']['locator'] + ' REVISED-VERSION-TWO locator'
    new['source'] = dict(old['source'], locator=locator)
    new['sources'] = [{'id': new['source']['id'], 'locator': locator}]
    new['claims'] = [dict(c, locator=locator) for c in old['claims']]
    plan['pedagogy']['comparisons'].append(new)
    plan['pedagogy']['revisions'] = [edge(old, new)]
    hs.update_session(root, SESSION, plan=plan)
    revised = root / 'comparisons-revised.html'
    hs.export_session(root, SESSION, revised)
    return {'baseline': str(baseline), 'revised': str(revised)}


if __name__ == '__main__':
    folder = Path(sys.argv[1])
    (folder / 'explanations').mkdir(parents=True, exist_ok=True)
    (folder / 'comparisons').mkdir(parents=True, exist_ok=True)
    print(json.dumps({'session': SESSION,
                      'explanations': explanations(folder / 'explanations'),
                      'comparisons': comparisons(folder / 'comparisons')}))
