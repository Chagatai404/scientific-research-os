"""Build a disposable scientific session for browser tests: python support_scientific_session.py <empty-dir>.

Prints JSON with the generated paths. Not a test module; synthetic content only.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs

B = chr(92)
SOURCE = (ROOT / 'tests/fixtures/html/scientific-v09.md').read_text(encoding='utf-8').replace('<!-- ros-question: normalization -->', '') + '''
## Normalization with a label

The profile integrates to one, as in \\eqref{norm}, and [@eq:norm] again after the equation.

$$
\\int_0^\\infty f(t)\\,dt = 1
$$ {#eq:norm}

<!-- ros-question: mcq -->

<!-- ros-question: num -->

<!-- ros-question: free -->

<!-- ros-question: match -->
'''.replace('\\\\', B)

QUESTIONS = [
    {'id': 'mcq', 'kind': 'mcq', 'prompt': 'Which factor normalizes **$f(t)$** so that ' + B + '(' + B + 'int_0^' + B + 'infty f,dt=1' + B + ') holds?',
     'options': [{'value': 'A', 'label': '$b^{a}/' + B + 'Gamma(a)$'}, {'value': 'B', 'label': '*Not* $b^{a-1}$'}, {'value': 'C', 'label': '$' + B + 'Gamma(a)$ only'}],
     'answer': 'A', 'hints': ['Check the *units* of $b$: an inverse depth.'],
     'solution': 'Because $' + B + 'int_0^' + B + 'infty t^{a-1}e^{-bt}dt=' + B + 'Gamma(a)/b^{a}$, see ' + B + 'eqref{norm}.'},
    {'id': 'num', 'kind': 'numeric', 'prompt': 'Evaluate **$a/b$** for $a=3$, $b=1.5$.', 'answer': 2, 'tolerance': 0.01},
    {'id': 'free', 'kind': 'free-response', 'prompt': 'Explain why the origin $t=0$ matters, citing [@eq:norm].'},
    {'id': 'match', 'kind': 'matching', 'prompt': 'Match each *symbol* to its role', 'options': ['$a$', '$b$'], 'answer': {'shape': '$a$', 'scale': '$b$'}},
]


def build(directory):
    directory = Path(directory)
    (directory / 'Sessions').mkdir(parents=True, exist_ok=True)
    hs.install_runtime(directory)
    hs.create_session(directory, 'Sessions/sci.md', SOURCE, title='Scientific rendering regression', questions=QUESTIONS)
    hs.append_event(directory, 'Sessions/sci.md', {'event_id': 'r-free', 'type': 'response', 'question_id': 'free', 'response': 'Because $t=0$ fixes the **origin**.'})
    hs.review_response(directory, 'Sessions/sci.md', 'free', 'partially-correct',
                       'Close: the origin sets $b$ via ' + B + '(t-t_0' + B + '), so state it as **$t_0$**.')
    hs.append_event(directory, 'Sessions/sci.md', {'event_id': 'oq-1', 'type': 'open-question', 'question_id': None,
                                                   'response': 'Why does ' + B + '(a>0' + B + ') matter for **$' + B + 'Gamma(a)$**?'})
    hs.answer_open_question(directory, 'Sessions/sci.md', 'oq-1', 'It keeps $' + B + 'Gamma(a)$ finite; see ' + B + 'eqref{norm}.')
    standalone = directory / 'standalone.html'
    hs.export_session(directory, 'Sessions/sci.md', standalone)
    return {'root': str(directory), 'html': str(directory / 'Sessions/sci.html'), 'state': str(directory / 'Sessions/sci.state.json'),
            'standalone': str(standalone)}


if __name__ == '__main__':
    print(json.dumps(build(sys.argv[1])))
