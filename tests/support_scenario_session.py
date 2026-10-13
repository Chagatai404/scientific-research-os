"""Build the multimodal lesson for release scenarios F and G: python support_scenario_session.py <empty-dir>.

One lesson with equations, a registered schematic placed inline, a sampling widget, a multiple-choice, a numeric and a free-response
question, navigation to an unfamiliar prerequisite and an earlier explanation. Prints JSON with the generated paths. Not a test module;
synthetic content only.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs
import visual_assets as va

B = chr(92)
SPEC = {'title': 'Fitting workflow', 'rows': [{'label': 'Steps', 'nodes': [
    {'id': 'a', 'text': 'Model the counts'}, {'id': 'b', 'text': 'Fit', 'kind': 'gate'}, {'id': 'c', 'text': 'Check', 'kind': 'done'}]}],
    'edges': [['a', 'b'], ['b', 'c']]}
FILLER = ' '.join(['The profile integrates to one over the positive axis.'] * 12)
SOURCE = ('# Fitting the gamma profile\n\n'
          '## Why the shape matters\n\n'
          'The profile is $f(x)=x^{a-1}e^{-x/b}$ and needs the [[Exponential distribution|exponential case]] first. ' + FILLER + '\n\n'
          '$$\n' + B + 'int_0^' + B + 'infty f(x)' + B + ',dx = ' + B + 'Gamma(a)b^a\n$$ {#eq:norm}\n\n'
          'The normalisation above is equation ' + B + 'eqref{norm}. ' + FILLER + '\n\n'
          '## Building the model\n\n'
          'We turn the profile into a procedure. ' + FILLER + '\n\n'
          '<!-- ros-question: mcq -->\n\n'
          '## Fitting\n\n'
          'Paragraph before the sampling widget. ' + FILLER + '\n\n'
          'Paragraph after the sampling widget. ' + FILLER + '\n\n'
          '<!-- ros-question: numeric -->\n\n'
          '<!-- ros-question: free -->\n\n'
          '## Checking the result\n\n'
          'Closing paragraph about checking the fit. ' + FILLER + '\n')
QUESTIONS = [
    {'id': 'mcq', 'kind': 'mcq', 'prompt': 'Which factor normalises **$f(x)$**?',
     'options': [{'value': 'A', 'label': '$' + B + 'Gamma(a)b^a$'}, {'value': 'B', 'label': '$b^{a-1}$'}, {'value': 'C', 'label': '$' + B + 'Gamma(a)$ only'}],
     'answer': 'A', 'hints': ['Check the units of $b$.'], 'solution': 'Because $' + B + 'int_0^' + B + 'infty x^{a-1}e^{-x/b}dx=' + B + 'Gamma(a)b^a$.'},
    {'id': 'numeric', 'kind': 'numeric', 'prompt': 'Evaluate $a/b$ for $a=3$, $b=1.5$.', 'answer': 2, 'tolerance': 0.01},
    {'id': 'free', 'kind': 'free-response', 'prompt': 'Explain why the scale parameter carries units.'},
]
NAVIGATION = [
    {'kind': 'prerequisite', 'label': 'Exponential distribution', 'target': 'Exponential distribution', 'note': '1 step(s) before the target'},
    {'kind': 'first-taught', 'label': 'First lesson on gamma', 'target': 'Sessions/earlier.md'},
]


def build(directory):
    directory = Path(directory)
    (directory / 'Sessions').mkdir(parents=True, exist_ok=True)
    hs.install_runtime(directory)
    va.ensure_schematic(directory, SPEC, visual_id='VIS-flow', concepts=['probability.gamma-density'])
    hs.create_session(directory, 'Sessions/lesson.md', SOURCE, title='Fitting the gamma profile', questions=QUESTIONS, widgets=[{'id': 'sample', 'kind': 'sampling'}])
    va.attach_visual(directory, 'Sessions/lesson.md', 'VIS-flow')
    va.place_visual(directory, 'Sessions/lesson.md', figure='VIS-flow', after_heading='Building the model', alt='Three boxes: model the counts, fit, check',
                    caption='The fitting workflow')
    va.place_visual(directory, 'Sessions/lesson.md', widget='sample', after_text='Paragraph before the sampling widget')
    hs.update_session(directory, 'Sessions/lesson.md', navigation=NAVIGATION)
    standalone = directory / 'lesson-standalone.html'
    hs.export_session(directory, 'Sessions/lesson.md', standalone)
    state = json.loads((directory / 'Sessions/lesson.state.json').read_text(encoding='utf-8'))
    return {'root': str(directory), 'html': str(directory / 'Sessions/lesson.html'), 'state': str(directory / 'Sessions/lesson.state.json'),
            'standalone': str(standalone), 'resources': [{'id': r['id'], 'path': r['path']} for r in state.get('resources', [])]}


if __name__ == '__main__':
    print(json.dumps(build(sys.argv[1])))
