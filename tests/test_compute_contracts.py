from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ComputeContracts(unittest.TestCase):
    def test_compute_protocol_preserves_authorization_and_provenance_boundaries(self):
        text = (ROOT / "references/COMPUTATIONAL_PROTOCOL.md").read_text(encoding="utf-8")
        for required in ("RESEARCH_PROTOCOL.md", "OBSERVED", "DECLARED", "DERIVED",
                         "UNKNOWN", "Repeatability", "Reproducibility",
                         "Independent reproduction", "not authorization",
                         "successful smoke test ≠ scientific validation",
                         "successful pilot ≠ authorization for production"):
            self.assertIn(required, text)
