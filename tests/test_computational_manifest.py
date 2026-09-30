from copy import deepcopy
from pathlib import Path
import sys
import json
import subprocess
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import computational_manifest as manifest


class ManifestTests(unittest.TestCase):
    def test_documented_example_runs_without_optional_packages(self):
        root = Path(__file__).resolve().parents[1]
        path = root / "examples/compute/manifest.json"
        record = manifest.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(record["declared"], json.loads((path.parent / "declared-ml.json").read_text(encoding="utf-8")))
        self.assertTrue(record["declared"]["example_only"])
        self.assertIsNone(record["observed"]["git"]["commit"])
        result = subprocess.run([sys.executable, "-S", "-B", str(root / "scripts/computational_manifest.py"), str(path)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(manifest.loads(result.stdout), record)

    def test_roundtrip_determinism_unknown_tools_and_separation(self):
        declared = {"threads": 2, "seed": None}
        record = manifest.create("RQ-1", observed={"tools": {"future-tool": {"version": None}}},
                                 declared=declared, derived={"budget": {"value": 4, "formula": "2*2"}})
        declared["threads"] = 999
        self.assertEqual(record["declared"]["threads"], 2)
        self.assertNotIn("threads", record["observed"])
        self.assertEqual(manifest.loads(manifest.dumps(record)), record)
        self.assertEqual(manifest.dumps(dict(reversed(list(record.items())))), manifest.dumps(record))

    def test_rejects_malformed_structure_and_non_json_values(self):
        original = manifest.create("RQ-1")
        for field, value in (("schema_version", True), ("schema_version", 2),
                             ("experiment", " "), ("observed", []), ("declared", None),
                             ("derived", {"observed": {}}), ("artifacts", [2]),
                             ("reproduction_command", []), ("failure", False),
                             ("observed", {"x": float("nan")}),
                             ("declared", {"x": {1: "bad"}}), ("derived", {"x": (1, 2)})):
            with self.subTest(field=field, value=value):
                record = deepcopy(original)
                record[field] = value
                with self.assertRaises(ValueError):
                    manifest.validate(record)
        for record in ([], {}, {**original, "physics_list": "invented"}):
            with self.assertRaises(ValueError):
                manifest.validate(record)

    def test_duplicate_keys_and_invalid_json_rejected(self):
        for text in ('{"schema_version": 1, "schema_version": 1}', '{', 'null'):
            with self.assertRaises(ValueError):
                manifest.loads(text)

    def test_commands_are_inert_and_unknown_failure_is_not_success(self):
        record = manifest.create("example", reproduction_command="echo example | tool > output")
        self.assertIsNone(record["failure"])
        self.assertEqual(manifest.loads(manifest.dumps(record)), record)
