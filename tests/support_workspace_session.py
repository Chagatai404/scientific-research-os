"""Build a disposable lesson for the workspace browser test: python support_workspace_session.py <empty-dir>.

Prints JSON with the generated paths. Not a test module; synthetic content only.
"""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs

FILLER = ' '.join(['The density integrates to one over the positive axis.'] * 14)


def paragraphs(prefix, count=6):
    return '\n\n'.join(f'{prefix} {n}. {FILLER}' for n in range(1, count + 1))


SOURCE = f'''# Understanding the gamma distribution

## Why the shape matters

Start from [[Exponential distribution|the exponential case]], then see [[Missing note]], [[Secret]], [[https://example.org/x|an outside page]] and [[../escape|a traversal]].

{paragraphs('Why')}

### The shape parameter

{paragraphs('Shape')}

<!-- ros-question: shape -->

## Deriving the density

{paragraphs('Derive')}

<!-- ros-question: scale -->

## Applying it to showers

{paragraphs('Apply')}
'''

QUESTIONS = [
    {'id': 'shape', 'kind': 'free-response', 'prompt': 'What does the shape parameter control?'},
    {'id': 'scale', 'kind': 'free-response', 'prompt': 'Why does the scale parameter carry units?'},
]
NAVIGATION = [
    {'kind': 'prerequisite', 'label': 'Exponential distribution', 'target': 'Exponential distribution', 'note': '1 step(s) before the target'},
    {'kind': 'first-taught', 'label': 'First lesson on gamma', 'target': 'Sessions/earlier.md'},
    {'kind': 'application', 'label': 'Shower depth question', 'target': 'Shower depth'},
]


def build(directory):
    directory = Path(directory)
    (directory / 'Sessions').mkdir(parents=True, exist_ok=True)
    hs.install_runtime(directory)
    hs.create_session(directory, 'Sessions/lesson.md', SOURCE, questions=QUESTIONS)
    hs.update_session(directory, 'Sessions/lesson.md', navigation=NAVIGATION)
    html = (directory / 'Sessions/lesson.html').read_text(encoding='utf-8')
    anchors = {re.sub(r'<[^>]+>', '', text): ident for ident, text in re.findall(r'<h[1-6][^>]*\bid="(section-[^"]+)"[^>]*>(.*?)</h[1-6]>', html)}
    origin = {'section': anchors['Deriving the density'], 'title': 'Deriving the density'}
    hs.append_event(directory, 'Sessions/lesson.md', {'event_id': 'oq-answered', 'type': 'open-question', 'question_id': None,
                                                      'response': 'Why does the scale matter?', 'origin': origin})
    hs.answer_open_question(directory, 'Sessions/lesson.md', 'oq-answered', 'It sets the units of the variable.')
    hs.append_event(directory, 'Sessions/lesson.md', {'event_id': 'oq-open', 'type': 'open-question', 'question_id': None,
                                                      'response': 'Is the shape always an integer?',
                                                      'origin': {'section': anchors['Why the shape matters'], 'title': 'Why the shape matters'}})
    hs.append_event(directory, 'Sessions/lesson.md', {'event_id': 'r-shape', 'type': 'response', 'question_id': 'shape',
                                                      'response': 'It controls the skewness.'})
    standalone = directory / 'lesson-standalone.html'
    hs.export_session(directory, 'Sessions/lesson.md', standalone)
    return {'root': str(directory), 'html': str(directory / 'Sessions/lesson.html'), 'state': str(directory / 'Sessions/lesson.state.json'),
            'standalone': str(standalone), 'anchors': anchors}


if __name__ == '__main__':
    print(json.dumps(build(sys.argv[1])))
