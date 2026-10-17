"""Build a disposable lesson with a blackboard for the board browser test: python support_board_session.py <empty-dir>.

Prints JSON with the generated paths. Not a test module; synthetic content only. The script sets no hand, so the page's default hand is what is tested.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs

SCRIPT = {'board_schema': 1, 'steps': [
    {'id': 's1', 'say': 'First.', 'do': [
        {'op': 'write', 'text': 'Gradient ığüşöçİ', 'at': [8, 8], 'size': 'large', 'color': 'yellow', 'id': 'title'},
        {'op': 'write', 'text': 'a small label', 'at': [8, 20], 'size': 'small', 'id': 'label'},
        {'op': 'math', 'tex': 'x^2 + 1', 'at': [8, 30], 'id': 'gone', 'delay': 0.2},
        {'op': 'draw', 'path': 'M 10 70 L 40 50 L 70 70', 'color': 'blue', 'id': 'roof', 'delay': 0.2}]},
    {'id': 's2', 'say': 'Second.', 'do': [
        {'op': 'circle', 'at': [100, 50], 'r': 10, 'color': 'pink', 'id': 'ring'},
        {'op': 'dot', 'at': [10, 70], 'id': 'ball'},
        {'op': 'move', 'target': 'ball', 'path': 'M 10 70 L 70 70', 'duration': 0.6, 'delay': 0.3},
        {'op': 'highlight', 'target': 'title', 'delay': 0.4}]},
    {'id': 's3', 'say': 'Third.', 'do': [{'op': 'erase', 'target': 'gone'}]},
]}


def build(directory):
    directory = Path(directory)
    (directory / 'Sessions').mkdir(parents=True, exist_ok=True)
    hs.install_runtime(directory)
    hs.create_session(directory, 'Sessions/board.md', '# A lecture on the board\n\nIntro.\n\n<!-- ros-widget: lecture -->\n\nAfter the board.\n', title='Board regression',
                      widgets=[{'id': 'lecture', 'kind': 'board', 'title': 'The board', 'script': SCRIPT}])
    standalone = directory / 'standalone.html'
    hs.export_session(directory, 'Sessions/board.md', standalone)
    return {'standalone': str(standalone), 'sentences': [s['say'] for s in SCRIPT['steps']]}


if __name__ == '__main__':
    print(json.dumps(build(sys.argv[1])))
