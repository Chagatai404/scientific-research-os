"""Export the differentiated synthetic practice fixture in a disposable vault."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs
from test_handout import make_vault, SESSION


def build(folder):
    root = Path(folder)
    make_vault(root, with_plan=False)
    fixture = json.loads((ROOT / 'tests/fixtures/p1c/tiered-variance.json').read_text(encoding='utf-8'))
    hs.update_session(root, SESSION, text='---\ntype: course-session\n---\n# Synthetic tiered practice\n\nDisposable verification fixture.\n', plan=fixture['plan'])
    exported = root / 'practice-standalone.html'
    hs.export_session(root, SESSION, exported)
    return {'standalone': str(exported), 'session': SESSION}


if __name__ == '__main__':
    print(json.dumps(build(sys.argv[1])))
