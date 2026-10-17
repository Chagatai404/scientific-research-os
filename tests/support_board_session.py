"""Build a disposable lesson with a blackboard for the board browser test: python support_board_session.py <empty-dir>.

Prints JSON with the generated paths. Not a test module; synthetic content only. The script sets no hand, so the page's default hand is what is tested.
It also writes two short synthetic tones as stand-ins for recorded sentences (no engine, no binary in the repository): steps s1 and s2 have a recording, s3 has none,
so the page has to mix the recorded voice with its fallback. Two pages come out of it: a standalone export (recordings embedded) and the vault page (recordings
played from a path beside it).
"""
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import wave

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
# Seconds of each stand-in recording. s1 is longer than the captions would take for "First." (1.7 s), so a page that paces by the recording is told apart from one that does not.
TONES = {'s1': 3.0, 's2': 1.2}
PAUSES = {'s1': 0.5, 's2': 0.3}


def tone(path, seconds, hz, rate=24000):
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b''.join(struct.pack('<h', int(5000 * math.sin(2 * math.pi * hz * i / rate))) for i in range(int(rate * seconds))))


def build(directory):
    directory = Path(directory)
    (directory / 'Sessions').mkdir(parents=True, exist_ok=True)
    hs.install_runtime(directory)
    hs.create_session(directory, 'Sessions/board.md', '# A lecture on the board\n\nIntro.\n\n<!-- ros-widget: lecture -->\n\nAfter the board.\n', title='Board regression',
                      widgets=[{'id': 'lecture', 'kind': 'board', 'title': 'The board', 'script': SCRIPT}])
    standalone = directory / 'standalone.html'
    hs.export_session(directory, 'Sessions/board.md', standalone)
    (directory / 'Narration').mkdir()
    audio = {}
    for number, (step, seconds) in enumerate(TONES.items()):
        tone(directory / 'Narration' / f'{step}.wav', seconds, 220 * (number + 1))
        say = next(s['say'] for s in SCRIPT['steps'] if s['id'] == step)
        audio[step] = {'file': f'Narration/{step}.wav', 'seconds': seconds, 'pause': PAUSES[step], 'say_sha256': hashlib.sha256(say.encode('utf-8')).hexdigest()}
    hs.update_session(directory, 'Sessions/board.md', widgets=[{'id': 'lecture', 'kind': 'board', 'title': 'The board', 'script': SCRIPT, 'audio': audio}])
    narrated = directory / 'standalone-audio.html'
    hs.export_session(directory, 'Sessions/board.md', narrated)
    return {'standalone': str(standalone), 'sentences': [s['say'] for s in SCRIPT['steps']], 'standalone_audio': str(narrated),
            'vault_page': str(directory / 'Sessions' / 'board.html'), 'tones': TONES, 'pauses': PAUSES}


if __name__ == '__main__':
    print(json.dumps(build(sys.argv[1])))
