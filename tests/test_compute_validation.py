"""Mutate disposable repository copies; validation must not execute scientific tools."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ComputeValidationTests(unittest.TestCase):
    def test_validator_rejects_missing_contracts_unsafe_profiles_and_broken_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("scripts", "skills", "agents", "references", "assets", "examples", "extensions"):
                shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy2(ROOT / "README.md", root / "README.md")

            def validate():
                return subprocess.run([sys.executable, "-S", "-B", str(root / "scripts/validate.py")],
                                      cwd=root, capture_output=True, text=True, encoding="utf-8")

            for relative, replacement, message in (
                ("references/QML_PROTOCOL.md", None, "QML_PROTOCOL.md"),
                ("extensions/scientific-tools/geant4/GUIDE.md", None, "GUIDE.md"),
                ("extensions/scientific-tools/geant4/PROFILE.toml", 'schema_version = 99\n', "profile"),
                ("agents/ml-reviewer.md", '---\nname: ml-reviewer\ndescription: test\nmode: write\n---\n', "read-only"),
                ("skills/geant4/SKILL.md", '---\nname: bad\ndescription: test\n---\n', "directory"),
                ("extensions/scientific-tools/sklearn/GUIDE.md", 'Use `references/MISSING_PROTOCOL.md`.\n', "MISSING_PROTOCOL.md"),
            ):
                with self.subTest(path=relative):
                    path = root / relative
                    saved = path.read_bytes()
                    if replacement is None:
                        path.unlink()
                    else:
                        path.write_text(replacement, encoding="utf-8")
                    result = validate()
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn(message, result.stdout)
                    path.write_bytes(saved)
            path = root / "extensions/scientific-tools/geant4/PROFILE.toml"
            source = path.read_text(encoding="utf-8")
            path.write_text(source.replace('["geant4-config", "--version"]', '["python", "-c", "raise RuntimeError()"]'), encoding="utf-8")
            result = validate()
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("unsupported executable", result.stdout)
            self.assertNotIn("RuntimeError", result.stderr)
            path.write_text(source, encoding="utf-8")
            result = validate()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
