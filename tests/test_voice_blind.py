"""Blind voice test page: seeded order, hidden labels, refusals, and the size limit."""
from pathlib import Path
import json
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import voice_blind_test as vb


def audio(directory: Path, name: str, size: int = 64) -> Path:
    path = directory / name
    path.write_bytes(b'RIFF' + bytes(size))
    return path


class BlindTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.entries = [
            {'id': 'alpha-voice', 'label': 'Alpha Voice', 'file': str(audio(self.dir, 'a.wav'))},
            {'id': 'beta-voice', 'label': 'Beta Voice', 'file': str(audio(self.dir, 'b.wav'))},
            {'id': 'old-baseline', 'label': 'Old Baseline', 'file': str(audio(self.dir, 'c.wav')), 'role': 'anchor'},
            {'id': 'alpha-voice-repeat', 'label': 'Alpha Voice (repeat)', 'file': str(self.dir / 'a.wav'), 'role': 'repeat'},
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def test_order_is_seeded_and_repeatable(self):
        samples = vb.load_samples(self.entries)
        first = [s['id'] for s in vb.shuffled(samples, 7)]
        self.assertEqual(first, [s['id'] for s in vb.shuffled(samples, 7)])
        self.assertEqual(sorted(first), sorted(s['id'] for s in samples))

    def test_visible_page_does_not_name_the_voices(self):
        page, key = vb.build_page(vb.load_samples(self.entries), 'Test', 'Say this.', 3)
        visible = re.sub(r'<script type="application/json".*?</script>', '', page, flags=re.S)
        visible = re.sub(r'src="data:[^"]*"', '', visible)
        for name in ('Alpha', 'Beta', 'Baseline', 'alpha-voice', 'a.wav'):
            self.assertNotIn(name, visible)
        self.assertEqual(sorted(k['sample'] for k in key['key']), [1, 2, 3, 4])
        self.assertIn('Sample 4', page)

    def test_key_maps_each_sample_to_its_file(self):
        _, key = vb.build_page(vb.load_samples(self.entries), 'Test', 'x', 5)
        by_id = {k['id']: k for k in key['key']}
        self.assertEqual(by_id['old-baseline']['role'], 'anchor')
        self.assertEqual(by_id['alpha-voice-repeat']['role'], 'repeat')
        self.assertEqual(by_id['beta-voice']['file'], 'b.wav')

    def test_text_is_escaped(self):
        page, _ = vb.build_page(vb.load_samples(self.entries), '<b>T</b>', '<script>x</script>', 1)
        self.assertNotIn('<script>x</script>', page)
        self.assertIn('&lt;script&gt;x&lt;/script&gt;', page)

    def test_refusals(self):
        with self.assertRaises(vb.BlindTestError):
            vb.load_samples(self.entries[:1])
        with self.assertRaises(vb.BlindTestError):
            vb.load_samples([self.entries[0], dict(self.entries[1], id='alpha-voice')])
        with self.assertRaises(vb.BlindTestError):
            vb.load_samples([self.entries[0], dict(self.entries[1], file=str(self.dir / 'missing.wav'))])
        with self.assertRaises(vb.BlindTestError):
            vb.load_samples([self.entries[0], dict(self.entries[1], file=str(self.dir / 'x.txt'))])
        with self.assertRaises(vb.BlindTestError):
            vb.load_samples([self.entries[0], dict(self.entries[1], role='judge')])

    def test_size_limit(self):
        big = [dict(e, file=str(audio(self.dir, f'big{i}.wav', 9 * 1024 * 1024))) for i, e in enumerate(self.entries[:2])]
        with self.assertRaises(vb.BlindTestError):
            vb.build_page(vb.load_samples(big), 'T', 'x', 1)

    def test_cli_writes_page_and_key_and_never_overwrites(self):
        manifest = self.dir / 'm.json'
        manifest.write_text(json.dumps({'title': 'T', 'paragraph': 'p', 'samples': [dict(e, file=Path(e['file']).name) for e in self.entries]}), encoding='utf-8')
        out = self.dir / 'page.html'
        self.assertEqual(vb.main(['build', str(manifest), str(out), '--seed', '2']), 0)
        self.assertTrue(out.exists() and out.with_suffix('.key.json').exists())
        self.assertEqual(vb.main(['build', str(manifest), str(out)]), 1)


if __name__ == '__main__':
    unittest.main()
