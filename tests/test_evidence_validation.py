from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_evidence as ev


def candidate(**changes):
    atom = dict(format_version=1, claim_id="E-001", claim_text="Synthetic stopping power is 12.74 MeV/cm.",
                claim_type="quantitative", evidence_type="explicit", verification_status="CANDIDATE",
                quantitative=True, comparison=False, consequential=True, provenance_class="system_specific",
                source="Synthetic regression fixture, not scientific evidence", source_identifier="fixture:stopping",
                source_version="1", source_locator="Table 1", evidence_excerpt="Material A: 12.74 MeV/cm",
                system_or_population="test setup", material_or_detector="Material A", observable="stopping power",
                energy_or_parameter_regime="fixture regime", source_value="12.74", source_units="MeV/cm",
                required_envelope=["material_or_detector", "energy_or_parameter_regime"])
    atom.update(changes)
    return atom


def reviewed(atom, reconstruction=None):
    atom = deepcopy(atom)
    atom["verification_status"] = "EXACT_SUPPORT"
    atom["verification"] = dict(
        from_status="CANDIDATE", verdict="EXACT_SUPPORT", verifier="synthetic test verifier",
        verified_at="2026-09-29", independent=True, source_accessed=True, claim_matches=True,
        units_checked=True, context_exposure="claim, source and minimal regime only",
        source_supported_claim=atom["claim_text"], fingerprint=ev.fingerprint(atom),
        reconstruction=deepcopy(reconstruction if reconstruction is not None else
                                {k: atom[k] for k in ev.BOUND if k in atom}))
    return atom


class EvidenceTests(unittest.TestCase):
    def codes(self, atom, board=None):
        return {e["code"] for e in ev.validate(atom, board)}

    def test_roundtrip_and_state_gate(self):
        atom = candidate()
        self.assertEqual(ev.EvidenceAtom.parse(ev.EvidenceAtom(atom).serialize()).record, atom)
        self.assertEqual(ev.validate(atom), [])
        atom["verification_status"] = "EXACT_SUPPORT"
        self.assertIn("EVIDENCE_VERIFICATION_REQUIRED", self.codes(atom))
        self.assertEqual(ev.validate(reviewed(candidate())), [])

    def test_missing_fields_and_false_attestations(self):
        for field, code in (("source_units", "MISSING_UNITS"), ("source_locator", "MISSING_LOCATOR"),
                            ("material_or_detector", "MISSING_ENVELOPE")):
            atom = candidate()
            del atom[field]
            self.assertIn("EVIDENCE_" + code, self.codes(atom))
        for field in ("independent", "source_accessed", "claim_matches", "units_checked"):
            atom = reviewed(candidate())
            atom["verification"][field] = False
            self.assertIn("EVIDENCE_VERIFICATION_REQUIRED", self.codes(atom))

    def test_cache_invalidates_all_consequential_changes(self):
        original = reviewed(candidate())
        self.assertTrue(ev.reusable(original, deepcopy(original)))
        for field, value in (("claim_text", "different claim"), ("source_version", "2"),
                             ("material_or_detector", "Material B"), ("source_value", "13.74"),
                             ("source_locator", "Table 2"), ("invalidated_by", ["contradictory source"])):
            changed = deepcopy(original)
            changed[field] = value
            self.assertFalse(ev.reusable(original, changed))
            self.assertIn("EVIDENCE_STALE_VERIFICATION", self.codes(changed))

    def test_transfer_is_visible_and_excluded_from_facts(self):
        atom = candidate(target_envelope={"material_or_detector": "Material B"})
        self.assertIn("EVIDENCE_TRANSFER_UNLABELLED", self.codes(atom))
        atom["provenance_class"] = "transferred_approximation"
        atom = reviewed(atom)
        self.assertIn("EVIDENCE_TRANSFER_UNLABELLED", self.codes(atom))
        atom["verification_status"] = "TRANSFERRED"
        self.assertEqual(ev.validate(atom), [])
        self.assertFalse(ev.reusable(atom, atom))

    def test_reasoning_and_corrections_cannot_become_facts(self):
        atom = candidate(verification_status="REASONING_REQUIRED")
        self.assertIn("EVIDENCE_MISSING_FIELD", self.codes(atom))
        atom["reasoning_reason"] = "Ambiguous scientific definition"
        self.assertEqual(ev.validate(atom), [])
        for kind in ("interpretation", "hypothesis"):
            self.assertIn("EVIDENCE_STATE", self.codes(reviewed(candidate(evidence_type=kind))))
        atom = reviewed(candidate())
        atom["verification"]["corrected_claim"] = "A materially different claim"
        self.assertIn("EVIDENCE_SOURCE_MISMATCH", self.codes(atom))
        atom = reviewed(candidate(unresolved_mismatches=["source contradicts observable"]))
        self.assertIn("EVIDENCE_STATE", self.codes(atom))

    def test_parser_and_malformed_records(self):
        for text in ('[]', '{"claim_id":"a","claim_id":"b"}', '{"x":NaN}'):
            with self.assertRaises(ValueError):
                ev.EvidenceAtom.parse(text)
        for field, value in (("required_envelope", [None]), ("target_envelope", []),
                             ("quantitative", "true"), ("verification_status", "VERIFIED"),
                             ("source_value", 12.74), ("unknown", True)):
            self.assertTrue(ev.validate(candidate(**{field: value})))
        for field in ev.TEXT:
            self.assertTrue(ev.validate(candidate(**{field: []})))

    def test_reconstruction_cannot_hide_omitted_envelope(self):
        original = candidate()
        atom = reviewed(original)
        del atom["material_or_detector"]
        atom["required_envelope"] = []
        atom["verification"]["fingerprint"] = ev.fingerprint(atom)
        self.assertIn("EVIDENCE_SOURCE_MISMATCH", self.codes(atom))

    def test_candidate_and_transferred_records_are_not_factual_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atom = candidate()
            (root / "candidate.json").write_text(ev.EvidenceAtom(atom).serialize(), encoding="utf-8")
            command = [sys.executable, "-S", str(ROOT / "scripts/validate_evidence.py"), str(root), "--facts-only"]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["atoms"], [])

    def test_derived_dependency_and_arithmetic(self):
        source = reviewed(candidate())
        length = reviewed(candidate(claim_id="E-002", source_value="2", source_units="cm",
                                    observable="path length", claim_text="Path is 2 cm.",
                                    evidence_excerpt="Path is 2 cm.", source_identifier="fixture:path"))
        board = {a["claim_id"]: a for a in (source, length)}
        derived = candidate(claim_id="E-003", claim_type="derived", evidence_type="derived",
                            claim_text="Expected loss is 25.48 MeV.", observable="expected loss",
                            derived_value="25.48", derived_units="MeV",
                            derivation=dict(formula="stopping_power * path_length", definition="Path-integrated loss",
                                            operation="product", inputs=[dict(claim_id=a["claim_id"],
                                            fingerprint=ev.fingerprint(a), value=a["source_value"], units=a["source_units"])
                                            for a in board.values()]))
        del derived["source_value"], derived["source_units"]
        self.assertEqual(ev.validate(derived, board), [])
        verified = reviewed(derived)
        self.assertEqual(ev.validate(verified, board), [])
        self.assertIn("EVIDENCE_UNVERIFIED_INPUT", self.codes(verified))
        bad = deepcopy(derived)
        bad["derived_value"] = "88"
        self.assertIn("EVIDENCE_ARITHMETIC", self.codes(bad, board))
        board["E-001"]["source_value"] = "13.74"
        self.assertIn("EVIDENCE_UNVERIFIED_INPUT", self.codes(verified, board))

    def test_comparisons_require_complete_relation(self):
        atom = candidate(claim_type="comparison", comparison=True, subject="A", comparator="B",
                         direction="wider", magnitude="10%", condition="same energy")
        self.assertEqual(ev.validate(atom), [])
        for field in ev.COMPARISON:
            changed = deepcopy(atom)
            del changed[field]
            self.assertIn("EVIDENCE_COMPARISON_MISSING_" + field.upper(), self.codes(changed))

    def test_missing_and_cyclic_derivation_dependencies(self):
        atom = candidate(claim_id="loop", claim_type="derived", evidence_type="derived",
                         derived_value="1", derived_units="1",
                         derivation=dict(formula="x", definition="synthetic", operation="reviewed",
                                         inputs=[dict(claim_id="loop", fingerprint="stale", value="1", units="1")]))
        self.assertIn("EVIDENCE_UNVERIFIED_INPUT", self.codes(atom, {"loop": atom}))
        atom["derivation"]["operation"] = []
        self.assertIn("EVIDENCE_DERIVATION", self.codes(atom))

    def test_cli_validates_before_rendering_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atom = reviewed(candidate())
            path = root / "atom.json"
            path.write_text(ev.EvidenceAtom(atom).serialize(), encoding="utf-8")
            command = [sys.executable, "-S", str(ROOT / "scripts/validate_evidence.py"), str(root), "--markdown", "--facts-only"]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("12.74", result.stdout)
            self.assertIn("Table 1", result.stdout)
            (root / "duplicate.json").write_text(path.read_text(), encoding="utf-8")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("duplicate", result.stderr)


if __name__ == "__main__":
    unittest.main()
