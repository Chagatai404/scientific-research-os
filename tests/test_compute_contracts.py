from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ComputeContracts(unittest.TestCase):
    def test_geant4_routes_to_shared_policies_and_preserves_detector_authority(self):
        skill = (ROOT / "skills/geant4/SKILL.md").read_text(encoding="utf-8")
        for name in ("RESEARCH", "COMPUTATIONAL", "GEANT4"):
            self.assertIn(f"references/{name}_PROTOCOL.md", skill)
        protocol = " ".join((ROOT / "references/GEANT4_PROTOCOL.md").read_text(encoding="utf-8").split())
        for phrase in ("world volume", "overlap", "material composition/density", "energy accounting",
                       "random engine", "multithreading", "not automatically authoritative",
                       "Project-pinned", "No stage automatically authorizes"):
            self.assertIn(phrase, protocol)

    def test_compute_protocol_preserves_authorization_and_provenance_boundaries(self):
        text = (ROOT / "references/COMPUTATIONAL_PROTOCOL.md").read_text(encoding="utf-8")
        for required in ("RESEARCH_PROTOCOL.md", "OBSERVED", "DECLARED", "DERIVED",
                         "UNKNOWN", "Repeatability", "Reproducibility",
                         "Independent reproduction", "not authorization",
                         "successful smoke test ≠ scientific validation",
                         "successful pilot ≠ authorization for production"):
            self.assertIn(required, text)
