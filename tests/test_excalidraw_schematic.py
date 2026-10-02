import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import excalidraw_schematic as ex  # noqa: E402

SPEC = {
    "title": "Plan",
    "rows": [
        {"label": "Fri", "nodes": [{"id": "a", "text": "Learn\nZ_q"}, {"id": "b", "text": "Pre-register"}]},
        {"label": "Sat", "nodes": [{"id": "c", "text": "Controls"}, {"id": "d", "text": "Gate?", "kind": "gate"}]},
    ],
    "edges": [["a", "b"], ["a", "c"], ["c", "d", "gate"]],
}


def drawing_of(text: str) -> dict:
    return json.loads(re.search(r"```json\n(.*?)\n```", text, re.S).group(1))


class ExcalidrawSchematicTests(unittest.TestCase):
    def test_output_is_plugin_format_with_expected_elements(self):
        text = ex.render(SPEC)
        self.assertIn("excalidraw-plugin: parsed", text)
        data = drawing_of(text)
        kinds = [e["type"] for e in data["elements"]]
        self.assertEqual(kinds.count("rectangle"), 4)
        self.assertEqual(kinds.count("arrow"), 3)
        # title + note + two row labels + one text per node
        self.assertEqual(kinds.count("text"), 4 + 4)

    def test_every_text_element_is_listed_with_its_block_id(self):
        text = ex.render(SPEC)
        for element in drawing_of(text)["elements"]:
            if element["type"] == "text":
                self.assertIn(f" ^{element['id']}", text)

    def test_contained_text_is_bound_to_its_box(self):
        data = drawing_of(ex.render(SPEC))
        by_id = {e["id"]: e for e in data["elements"]}
        bound = [e for e in data["elements"] if e["type"] == "text" and e["containerId"]]
        self.assertEqual(len(bound), 4)
        for t in bound:
            box = by_id[t["containerId"]]
            self.assertIn({"id": t["id"], "type": "text"}, box["boundElements"])

    def test_deterministic_for_a_seed_and_different_across_seeds(self):
        self.assertEqual(ex.render(SPEC, 3), ex.render(SPEC, 3))
        self.assertNotEqual(ex.render(SPEC, 3), ex.render(SPEC, 4))

    def test_default_note_labels_it_a_schematic(self):
        self.assertIn("not quantitative", ex.render(SPEC))

    def test_bad_specs_are_rejected(self):
        for spec in ({}, {"rows": []},
                     {"rows": [{"nodes": [{"id": "a", "text": "x"}, {"id": "a", "text": "y"}]}]},
                     {"rows": [{"nodes": [{"id": "a", "text": "x", "kind": "weird"}]}]},
                     {"rows": [{"nodes": [{"id": "a", "text": "x"}]}], "edges": [["a", "zzz"]]},
                     {"rows": [{"nodes": [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}]}],
                      "edges": [["a", "b", "odd"]]}):
            with self.assertRaises(ex.SpecError):
                ex.render(spec)

    def test_cli_writes_a_new_file_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "spec.json"
            spec.write_text(json.dumps(SPEC), encoding="utf-8")
            out = Path(tmp) / "Plan.excalidraw.md"
            self.assertEqual(ex.main(["--spec", str(spec), "--out", str(out)]), 0)
            first = out.read_text(encoding="utf-8")
            self.assertEqual(ex.main(["--spec", str(spec), "--out", str(out), "--seed", "99"]), 2)
            self.assertEqual(out.read_text(encoding="utf-8"), first)
            self.assertEqual(ex.main(["--spec", str(spec), "--out", str(Path(tmp) / "bad.md")]), 2)
            self.assertEqual(ex.main(["--spec", str(spec), "--out", str(Path(tmp) / "no" / "x.excalidraw.md")]), 2)

    def test_installed_as_a_graph_helper(self):
        import install
        self.assertIn("excalidraw_schematic.py", install.GRAPH_HELPERS)


if __name__ == "__main__":
    unittest.main()
