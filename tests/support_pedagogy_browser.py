"""Disposable exported P1 fixture; synthetic sources, no real vault or service."""
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs
import pedagogy_contract as pc
from test_handout import make_vault, SESSION
from test_pedagogy_contract import prepared


def build(folder):
    root = Path(folder)
    make_vault(root, with_plan=False)
    plan = prepared()
    plan['budget'] = 8
    fixture = json.loads((ROOT / 'tests/fixtures/p1b/finite-mse.json').read_text(encoding='utf-8'))
    entry = plan['pedagogy']['explanations'][0]
    entry['levels'] = copy.deepcopy(fixture['levels'])
    entry['sources'] = copy.deepcopy(fixture['sources'])
    # Preserve prepared()'s choice/hints and add a separate three-hint short
    # question binding without changing its existing prompt, criteria or answer.
    short = plan['probe']['questions'][-1]
    hints = copy.deepcopy(plan['pedagogy']['socratic'][0])
    hints.update(id='variance-short-hints', question_id=short['id'], question_sha256=pc.digest(short), hints=[
        {'kind': 'cue', 'text': 'Think about the sign of a squared distance.'},
        {'kind': 'structure', 'text': 'Every squared distance is nonnegative; then consider their weighted average.'},
        {'kind': 'partial-step', 'text': 'Probabilities are nonnegative and sum to one, so averaging these squares cannot make a negative number.'}])
    plan['pedagogy']['socratic'].append(hints)
    hs.update_session(root, SESSION, text='---\ntype: course-session\n---\n# Synthetic P1 fixture\n\nOriginal lesson.\n', plan=plan)
    exported = root / 'pedagogy-standalone.html'
    hs.export_session(root, SESSION, exported)
    return {'standalone': str(exported), 'session': SESSION}


if __name__ == '__main__':
    print(json.dumps(build(sys.argv[1])))
