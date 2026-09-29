"""Synthetic source reconstructions, not model or scientific truth benchmarks."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from test_evidence_validation import candidate, reviewed
import validate_evidence as ev

FIXTURES = Path(__file__).parent / "fixtures/evidence"


class ScientificFailureRegressions(unittest.TestCase):
    def check_fixture(self, name):
        fixture = json.loads((FIXTURES / (name + ".json")).read_text(encoding="utf-8"))
        source = fixture["source_atom"]
        valid = reviewed(source)
        self.assertEqual(ev.validate(valid), [])
        corrupt = deepcopy(source)
        corrupt.update(fixture["corrupt_changes"])
        # Even a fresh fingerprint cannot override an independently reconstructed relation.
        invalid = reviewed(corrupt, valid["verification"]["reconstruction"])
        errors = ev.validate(invalid)
        self.assertIn("EVIDENCE_SOURCE_MISMATCH", {e["code"] for e in errors})
        return errors

    def test_A_comparator_inversion(self):
        self.check_fixture("comparator_inversion")
        self.check_fixture("width_inversion")

    def test_B_conditioning_variable_inversion(self):
        errors = self.check_fixture("conditioning_inversion")
        self.assertIn("condition", {e["field"] for e in errors})

    def test_C_observable_substitution(self):
        self.check_fixture("observable_substitution")

    def test_D_unsupported_derived_classification(self):
        self.check_fixture("unsupported_classification")
        atom = candidate(claim_type="derived", evidence_type="derived", derived_value="88", derived_units="%",
                         observable="active fraction")
        self.assertIn("EVIDENCE_DERIVED_VALUE_MISSING_DERIVATION", {e["code"] for e in ev.validate(atom)})

    def test_E_numerical_provenance(self):
        self.check_fixture("wrong_material")
        self.check_fixture("wrong_source_value")

    def test_semantic_only_corruption_cannot_auto_promote(self):
        # The validator cannot infer that prose contradicts otherwise unchanged fields.
        # A source verifier must reject it, and no receipt means no acceptance.
        atom = candidate(claim_text="A materially different scientific claim.", verification_status="EXACT_SUPPORT")
        self.assertIn("EVIDENCE_VERIFICATION_REQUIRED", {e["code"] for e in ev.validate(atom)})
        atom = reviewed(candidate())
        atom["verification"]["claim_matches"] = False
        self.assertIn("EVIDENCE_VERIFICATION_REQUIRED", {e["code"] for e in ev.validate(atom)})


if __name__ == "__main__":
    unittest.main()
