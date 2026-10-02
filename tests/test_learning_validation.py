"""Exercise repository validation using disposable fixtures, without dependencies."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LearningValidationTests(unittest.TestCase):
    def test_validator_rejects_learning_metadata_and_missing_contracts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("scripts", "skills", "agents", "references", "assets", "examples", "extensions"):
                shutil.copytree(ROOT / name, root / name,
                                ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy2(ROOT / "README.md", root / "README.md")

            def validate():
                return subprocess.run([sys.executable, "-S", "-B", str(root / "scripts/validate.py")],
                                      cwd=root, capture_output=True, text=True, encoding="utf-8")

            result = validate()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            record = root / "examples/learning/gamma.md"
            original = record.read_text(encoding="utf-8")
            for field, old, bad in (("retention_target", "working", "memorized"),
                                    ("goals", '["research-foundations", "applied-probability"]', '"goal"'),
                                    ("courses", '["stat-xxx", "math-yyy"]', '["UPPER"]')):
                with self.subTest(field=field):
                    record.write_text(original.replace(f"{field}: {old}", f"{field}: {bad}"), encoding="utf-8")
                    result = validate()
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn(field, result.stdout)
            record.write_text(original, encoding="utf-8")

            for name in ("COURSE_LEARNING_PROTOCOL.md", "LATEX_TRANSCRIPTION_PROTOCOL.md", "TUTOR_PLANNING.md"):
                path = root / "references" / name
                saved = path.read_bytes()
                path.unlink()
                result = validate()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(name, result.stdout)
                path.write_bytes(saved)

            skill = root / "skills/course-study/SKILL.md"
            original_skill = skill.read_text(encoding="utf-8")
            skill.write_text(original_skill + "\nUse `99_Missing_Template.md`.\n", encoding="utf-8")
            result = validate()
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("missing template 99_Missing_Template.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
