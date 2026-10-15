"""Build a disposable lesson for the narration browser test: python support_narration_session.py <empty-dir>.

Prints JSON with the generated paths. Not a test module; synthetic content only.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs

B = chr(92)
SOURCE = ('# Understanding the gamma distribution\n\n'
          '## Why the shape matters\n\n'
          'The density is $f(x)=x^2$ for small $x$, and the mean is ' + B + '(' + B + 'mu' + B + '). Read the *emphasis* and the '
          '[[Exponential distribution|linked note]] too.\n\n'
          '$$\nE = mc^2\n$$ {#eq:energy}\n\n'
          'Energy is conserved, see ' + B + 'eqref{energy}.\n\n'
          '- First item with $y_i$.\n- Second item.\n\n'
          '$$\n' + B + 'begin{pmatrix} a & b ' + B + B + ' c & d ' + B + 'end{pmatrix}\n$$\n\n'
          '```python\nprint("code that must not be read aloud")\n```\n\n'
          '<!-- ros-question: shape -->\n\n'
          '### A detail\n\nDetail paragraph inside the first section.\n\n'
          '## Second section\n\nSecond section text that belongs to another part.\n\n'
          + '\n\n'.join(f'Filler paragraph {n} keeps the page tall enough to scroll to the last section. ' * 3 for n in range(1, 31)) + '\n')

QUESTIONS = [
    {'id': 'shape', 'kind': 'free-response', 'prompt': 'PROMPT TEXT what does the shape control?', 'hints': ['HINT TEXT use the units.'],
     'solution': 'SOLUTION TEXT it sets the tail.'},
]


def build(directory):
    directory = Path(directory)
    (directory / 'Sessions').mkdir(parents=True, exist_ok=True)
    hs.install_runtime(directory)
    hs.create_session(directory, 'Sessions/listen.md', SOURCE, title='Narration regression', questions=QUESTIONS)
    standalone = directory / 'standalone.html'
    hs.export_session(directory, 'Sessions/listen.md', standalone)
    return {'root': str(directory), 'standalone': str(standalone)}


if __name__ == '__main__':
    print(json.dumps(build(sys.argv[1])))
