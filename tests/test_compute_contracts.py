from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ComputeContracts(unittest.TestCase):
    def test_canonical_cycle_routes_compute_without_changing_approval(self):
        text = " ".join((ROOT / "references/RESEARCH_PROTOCOL.md").read_text(encoding="utf-8").split())
        for phrase in ("COMPUTATIONAL_PROTOCOL.md", "Probe capability does not authorize build",
                       "explicit approval remains required", "seed/variance analysis",
                       "noise/shot sensitivity", "UNKNOWN", "resource budget"):
            self.assertIn(phrase, text)
        policy = (ROOT / "references/AGENT_POLICY.md").read_text(encoding="utf-8")
        for name in ("simulation-reviewer", "ml-reviewer", "qml-reviewer"):
            self.assertIn(name, policy)
        self.assertIn("different role names are not proof of independence", policy)

    def test_qml_inherits_ml_and_distinguishes_regimes(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import computational_manifest as manifest
        text = " ".join((ROOT / "references/QML_PROTOCOL.md").read_text(encoding="utf-8").split())
        self.assertIn("explicitly extends `ML_PROTOCOL.md`", text)
        for regime in ("exact-simulator", "finite-shot-simulator", "noisy-simulator", "real-qpu"):
            self.assertIn(regime, text)
            record = manifest.create("example", declared={"execution_regime": regime})
            self.assertEqual(manifest.loads(manifest.dumps(record))["declared"]["execution_regime"], regime)
        for phrase in ("test-set discipline", "state preparation/data loading", "shot budget",
                       "as insufficient", "classical preprocessing", "claim strength must match"):
            self.assertIn(phrase, text)
        for name in ("pennylane", "qiskit"):
            self.assertFalse((ROOT / "skills" / name).exists())

    def test_ml_test_discipline_and_fairness_contract(self):
        text = " ".join((ROOT / "references/ML_PROTOCOL.md").read_text(encoding="utf-8").split())
        for phrase in ("test-set discipline", "iterative development signal", "training fold",
                       "same split", "input information", "optimization opportunity",
                       "compute/resource budgets", "multiple seeds", "event-family/group leakage"):
            self.assertIn(phrase, text)
        self.assertFalse((ROOT / "skills/pytorch").exists())
        self.assertFalse((ROOT / "skills/sklearn").exists())

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
