import base64
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('verify_release', Path(__file__).resolve().parents[1] / 'tools' / 'verify_release.py')
vr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vr)
NAME = 'Research-OS-Setup-1.0.0-x64.exe'
BODY = b'installer'


def make(d, body=BODY, size=len(BODY), feed=True, installer=True):
    d = Path(d)
    if installer:
        (d / NAME).write_bytes(body)
    if feed:
        sha = base64.b64encode(hashlib.sha512(BODY).digest()).decode()
        (d / 'latest.yml').write_text(
            f'version: 1.0.0\nfiles:\n  - url: {NAME}\n    sha512: {sha}\n    size: {size}\npath: {NAME}\nsha512: {sha}\n',
            encoding='utf8')


class VerifyRelease(unittest.TestCase):
    def check(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            make(d, **kw)
            return vr.verify_release(d)

    def test_pass(self):
        self.assertEqual(self.check(), [])

    def test_missing_installer(self):
        self.assertTrue(any('missing from the release' in p for p in self.check(installer=False)))

    def test_size_mismatch(self):
        self.assertTrue(any('size' in p for p in self.check(size=5)))

    def test_hash_mismatch(self):
        self.assertTrue(any('sha512' in p for p in self.check(body=b'tampered')))

    def test_missing_feed(self):
        self.assertEqual(self.check(feed=False), ['missing update feed latest.yml'])


if __name__ == '__main__':
    unittest.main()
