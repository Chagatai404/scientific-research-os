"""Every place that names the release must name the same version (the backend and the engine guard read VERSION)."""
import json, re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VersionConsistency(unittest.TestCase):
    def test_every_version_source_agrees(self):
        version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
        init = re.search(r'__version__ = "([^"]+)"', (ROOT / 'ros' / '__init__.py').read_text(encoding='utf-8')).group(1)
        pyproject = re.search(r'^version = "([^"]+)"', (ROOT / 'pyproject.toml').read_text(encoding='utf-8'), re.M).group(1)
        desktop = json.loads((ROOT / 'desktop' / 'package.json').read_text(encoding='utf-8'))['version']
        client = re.search(r"'title': 'Research OS', 'version': '([^']+)'", (ROOT / 'ros' / 'lib' / 'providers.py').read_text(encoding='utf-8')).group(1)
        self.assertEqual({version, init, pyproject, desktop, client}, {version})


if __name__ == '__main__':
    unittest.main()
