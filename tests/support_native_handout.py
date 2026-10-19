"""Disposable native handout fixture; no real vault, compiler or external source."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import handout
import html_sessions as hs
from test_handout import make_vault, SESSION


def build(folder):
    root = Path(folder)
    make_vault(root)
    hs.update_session(root, SESSION, text='---\ntype: course-session\n---\n# Variance\n\nOriginal lesson.\n')
    resource = json.loads((ROOT / 'tests/fixtures/readable-handout.json').read_text())
    handout.publish_readable(root, SESSION, resource)
    exported = root / 'standalone.html'
    hs.export_session(root, SESSION, exported)
    return {'standalone': str(exported), 'session': SESSION}


if __name__ == '__main__':
    print(json.dumps(build(sys.argv[1])))
