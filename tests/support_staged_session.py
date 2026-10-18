"""Build a disposable staged session (a session plan) for the staged-view browser test: python support_staged_session.py <empty-dir>.

Prints JSON with the generated paths. Not a test module; synthetic content only (examples/session-plan-variance.json). The lesson text is a recognisable sentence,
so the test can prove the staged view never shows the reading page.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs

LESSON_TEXT = 'READING PAGE SENTENCE that the staged view must never show.'


def build(directory):
    directory = Path(directory)
    (directory / 'Sessions').mkdir(parents=True, exist_ok=True)
    hs.install_runtime(directory)
    plan = json.loads((ROOT / 'examples' / 'session-plan-variance.json').read_text(encoding='utf-8'))
    hs.create_session(directory, 'Sessions/staged.md', f'# Variance and rescaling\n\n{LESSON_TEXT}\n', title='Variance and rescaling')
    hs.update_session(directory, 'Sessions/staged.md', plan=plan)
    standalone = directory / 'standalone.html'
    hs.export_session(directory, 'Sessions/staged.md', standalone)
    return {'standalone': str(standalone), 'lesson_text': LESSON_TEXT}


if __name__ == '__main__':
    print(json.dumps(build(sys.argv[1])))
