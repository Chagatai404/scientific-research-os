"""The repository validator ignores agent worktrees: .claude/worktrees/* hold full copies of the repository, fixtures included."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WorktreeCopiesTests(unittest.TestCase):
    def test_a_nested_copy_of_the_legacy_fixture_is_not_validated_as_a_session(self):
        nested = ROOT / '.claude' / 'worktrees' / 'validate-test-copy' / 'tests' / 'fixtures'
        self.assertFalse(nested.exists())
        try:
            nested.mkdir(parents=True)
            shutil.copytree(ROOT / 'tests/fixtures/legacy-v0.8.7', nested / 'legacy-v0.8.7')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/validate.py')], capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        finally:
            shutil.rmtree(ROOT / '.claude' / 'worktrees' / 'validate-test-copy', ignore_errors=True)
            try:
                (ROOT / '.claude' / 'worktrees').rmdir()
            except OSError:
                pass


if __name__ == '__main__':
    unittest.main()
