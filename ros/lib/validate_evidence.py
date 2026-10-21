"""EvidenceAtom v1: dependency-free records, checks, reuse and Markdown output.

Checks compare declared structure, not scientific prose. Verification receipts are
auditable attestations, not cryptographic proof of source access or independence.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sys

STATES = {"CANDIDATE", "EXACT_SUPPORT", "OVERSTATED", "CONTRADICTED", "NOT_FOUND",
          "TRANSFERRED", "UNRESOLVED", "REASONING_REQUIRED"}
ENVELOPE = ("system_or_population", "particle_or_process", "material_or_detector",
            "energy_or_parameter_regime", "observable", "coordinate_or_origin_convention",
            "model_or_approximation")
COMPARISON = ("subject", "comparator", "direction", "magnitude", "condition")
SOURCE = ("source", "source_identifier", "source_version", "source_locator", "evidence_excerpt")
TEXT = {"claim_id", "claim_text", "claim_type", "evidence_type", "verification_status",
        "provenance_class", "source_value", "source_units", "derived_value", "derived_units",
        "notes", "reasoning_reason", *ENVELOPE, *COMPARISON, *SOURCE}
FIELDS = TEXT | {"format_version", "quantitative", "comparison", "consequential",
                 "required_envelope", "target_envelope", "derivation", "verification",
                 "unresolved_mismatches", "invalidated_by"}
BOUND = (*SOURCE, *ENVELOPE, *COMPARISON, "source_value", "source_units",
         "derived_value", "derived_units", "derivation", "evidence_type", "provenance_class")


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(atom: dict) -> str:
    """Bind all content, including regime and invalidations, except review/status."""
    payload = {k: v for k, v in atom.items() if k not in {"verification", "verification_status"}}
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceAtom:
    """JSON-backed representation; validate before using as evidence."""
    record: dict

    @classmethod
    def parse(cls, text: str) -> "EvidenceAtom":
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate JSON key: {key}")
                result[key] = value
            return result
        value = json.loads(text, object_pairs_hook=unique,
                           parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"invalid number: {x}")))
        if not isinstance(value, dict):
            raise ValueError("EvidenceAtom must be a JSON object")
        return cls(value)

    def serialize(self) -> str:
        return json.dumps(self.record, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def validate(atom: dict, board: dict[str, dict] | None = None,
             trail: tuple[str, ...] = ()) -> list[dict[str, str]]:
    errors = []

    def error(code, field, message):
        errors.append({"code": "EVIDENCE_" + code, "field": field, "message": message})

    def require(field, code="MISSING_FIELD"):
        if not atom.get(field):
            error(code, field, "Required nonempty field")

    if not isinstance(atom, dict):
        return [{"code": "EVIDENCE_FORMAT", "field": "", "message": "Expected object"}]
    for key, value in atom.items():
        if key not in FIELDS:
            error("FORMAT", key, "Unknown field")
        elif key in TEXT and (not isinstance(value, str) or not value.strip()):
            error("FORMAT", key, "Expected nonempty string; omit inapplicable fields")
    for key in ("quantitative", "comparison", "consequential"):
        if type(atom.get(key)) is not bool:
            error("FORMAT", key, "Explicit boolean required")
    if type(atom.get("format_version")) is not int or atom.get("format_version") != 1:
        error("FORMAT", "format_version", "Expected version 1")
    if errors:
        return errors
    for key in ("claim_id", "claim_text", "claim_type", "evidence_type", "verification_status",
                "provenance_class", "source", "source_identifier", "observable"):
        require(key)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", atom.get("claim_id", "")):
        error("FORMAT", "claim_id", "Use a stable identifier of letters, digits, dot, underscore or hyphen")
    if atom.get("claim_type") not in {"qualitative", "quantitative", "comparison", "derived"}:
        error("FORMAT", "claim_type", "Unknown claim type")
    if atom.get("evidence_type") not in {"explicit", "derived", "interpretation", "hypothesis"}:
        error("FORMAT", "evidence_type", "Unknown evidence type")
    if atom.get("provenance_class") not in {"target_regime", "system_specific", "transferred_approximation",
                                             "project_assumption", "unresolved"}:
        error("FORMAT", "provenance_class", "Unknown provenance class")
    status = atom.get("verification_status")
    if status not in STATES:
        error("STATE", "verification_status", "Unknown state")
    accepted = status in {"EXACT_SUPPORT", "TRANSFERRED"}
    if atom.get("consequential") or accepted:
        require("source_locator", "MISSING_LOCATOR")
    required = atom.get("required_envelope", [])
    if not isinstance(required, list) or any(not isinstance(k, str) or k not in ENVELOPE for k in required):
        error("FORMAT", "required_envelope", "Expected envelope field names")
        required = []
    for key in required:
        require(key, "MISSING_ENVELOPE")
    quantitative = atom.get("quantitative") or atom.get("claim_type") in {"quantitative", "derived"}
    comparison = atom.get("comparison") or atom.get("claim_type") == "comparison"
    derived = atom.get("evidence_type") == "derived" or atom.get("claim_type") == "derived" or "derived_value" in atom
    if quantitative and not atom.get("quantitative"):
        error("FORMAT", "quantitative", "Quantitative type requires true flag")
    if comparison and not atom.get("comparison"):
        error("FORMAT", "comparison", "Comparison type requires true flag")
    if comparison or any(k in atom for k in COMPARISON):
        for key in COMPARISON:
            require(key, "COMPARISON_MISSING_" + key.upper())
        if not atom.get("comparison"):
            error("FORMAT", "comparison", "Comparison fields require true flag")
    if (quantitative and not derived) or "source_value" in atom or "source_units" in atom:
        require("source_value", "NUMERICAL_PROVENANCE")
        require("source_units", "MISSING_UNITS")
    for key in ("invalidated_by", "unresolved_mismatches"):
        value = atom.get(key, [])
        if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
            error("FORMAT", key, "Expected list of nonempty reasons")
        if accepted and value:
            error("STATE", key, "Unresolved or invalidated evidence cannot be accepted")
    target = atom.get("target_envelope", {})
    if not isinstance(target, dict) or any(k not in ENVELOPE or not isinstance(v, str) or not v.strip()
                                           for k, v in target.items()):
        error("FORMAT", "target_envelope", "Expected envelope fields with nonempty strings")
        target = {}
    for key in target:
        require(key, "MISSING_ENVELOPE")
    transfer = any(atom.get(k) != v for k, v in target.items())
    if transfer and atom.get("provenance_class") != "transferred_approximation":
        error("TRANSFER_UNLABELLED", "target_envelope", "Source and target envelopes differ")
    if (transfer or atom.get("provenance_class") == "transferred_approximation") and status == "EXACT_SUPPORT":
        error("TRANSFER_UNLABELLED", "verification_status", "Use TRANSFERRED, not target factual support")
    if status == "TRANSFERRED" and (not target or atom.get("provenance_class") != "transferred_approximation"):
        error("TRANSFER_UNLABELLED", "target_envelope", "Transferred evidence needs target context and label")
    if status == "REASONING_REQUIRED":
        require("reasoning_reason")
    if derived:
        require("derived_value", "NUMERICAL_PROVENANCE")
        require("derived_units", "MISSING_UNITS")
        if atom.get("evidence_type") != "derived" or not atom.get("quantitative"):
            error("FORMAT", "evidence_type", "Derived quantities require derived type and quantitative flag")
        derivation = atom.get("derivation")
        if not isinstance(derivation, dict) or not derivation:
            error("DERIVED_VALUE_MISSING_DERIVATION", "derivation", "Formula, definition and inputs required")
        else:
            for key in ("formula", "definition", "inputs", "operation"):
                if not derivation.get(key):
                    error("DERIVATION", "derivation." + key, "Required derivation metadata")
            for key in ("formula", "definition"):
                if not isinstance(derivation.get(key), str):
                    error("DERIVATION", "derivation." + key, "Expected text")
            operation = derivation.get("operation")
            if operation not in ("product", "sum", "ratio", "reviewed"):
                error("DERIVATION", "derivation.operation", "Use product, sum, ratio or reviewed")
            inputs = derivation.get("inputs")
            values = []
            if not isinstance(inputs, list) or not inputs:
                error("DERIVATION", "derivation.inputs", "Expected nonempty input list")
                inputs = []
            for i, item in enumerate(inputs):
                path = f"derivation.inputs.{i}"
                if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k].strip()
                                                     for k in ("claim_id", "fingerprint", "value", "units")):
                    error("DERIVATION", path, "Each input needs claim_id, fingerprint, value and units")
                    continue
                source = (board or {}).get(item["claim_id"])
                if source is None or item["claim_id"] in (*trail, atom.get("claim_id")):
                    error("UNVERIFIED_INPUT", path, "Missing or cyclic input evidence")
                elif source.get("verification_status") != "EXACT_SUPPORT" or validate(source, board, (*trail, atom.get("claim_id"))):
                    error("UNVERIFIED_INPUT", path, "Input must pass independent exact verification")
                else:
                    prefix = "derived" if source.get("evidence_type") == "derived" else "source"
                    if (item["fingerprint"] != fingerprint(source) or item["value"] != source.get(prefix + "_value")
                            or item["units"] != source.get(prefix + "_units")):
                        error("UNVERIFIED_INPUT", path, "Input snapshot differs from verified record")
                try:
                    value = Decimal(item["value"])
                    if not value.is_finite():
                        raise InvalidOperation
                    values.append(value)
                except InvalidOperation:
                    error("DERIVATION", path, "Arithmetic input must be a finite decimal")
            if values and len(values) == len(inputs) and operation in ("product", "sum", "ratio"):
                try:
                    if operation == "sum":
                        result = sum(values)
                        if any(x["units"] != atom.get("derived_units") for x in inputs):
                            error("DERIVATION", "derived_units", "Sum units must match; convert in separate atoms")
                    elif operation == "ratio":
                        if len(values) != 2:
                            raise ValueError("Ratio requires two inputs")
                        result = values[0] / values[1]
                    else:
                        result = Decimal(1)
                        for value in values:
                            result *= value
                    if result != Decimal(atom.get("derived_value", "")):
                        error("ARITHMETIC", "derived_value", f"Expected {result}; record rounding separately")
                except (InvalidOperation, ArithmeticError, ValueError) as exc:
                    error("ARITHMETIC", "derivation", str(exc))
    elif "derivation" in atom or "derived_units" in atom:
        error("DERIVATION", "derivation", "Derivation requires a separate derived value")
    if accepted:
        if atom.get("evidence_type") in {"interpretation", "hypothesis"} or atom.get("provenance_class") in {"project_assumption", "unresolved"}:
            error("STATE", "evidence_type", "Reasoning is not verified factual evidence")
        require("evidence_excerpt")
        receipt = atom.get("verification")
        if not isinstance(receipt, dict):
            error("VERIFICATION_REQUIRED", "verification", "Independent source receipt required")
        else:
            for key in ("verifier", "context_exposure", "source_supported_claim", "verified_at"):
                if not isinstance(receipt.get(key), str) or not receipt[key].strip():
                    error("VERIFICATION_REQUIRED", "verification." + key, "Required review metadata")
            for key in ("independent", "source_accessed", "claim_matches", "units_checked"):
                if receipt.get(key) is not True:
                    error("VERIFICATION_REQUIRED", "verification." + key, "Positive independent attestation required")
            if receipt.get("verdict") != "EXACT_SUPPORT" or receipt.get("from_status") != "CANDIDATE":
                error("STATE", "verification", "Acceptance requires a candidate-to-exact source review")
            if receipt.get("fingerprint") != fingerprint(atom):
                error("STALE_VERIFICATION", "verification.fingerprint", "Content changed since verification")
            reconstruction = receipt.get("reconstruction")
            if not isinstance(reconstruction, dict):
                error("VERIFICATION_REQUIRED", "verification.reconstruction", "Independent source reconstruction required")
            else:
                for key in BOUND:
                    if (key in atom or key in reconstruction) and reconstruction.get(key) != atom.get(key):
                        error("SOURCE_MISMATCH", key, "Claim field differs from independent source reconstruction")
            if receipt.get("corrected_claim"):
                error("SOURCE_MISMATCH", "claim_text", "Material correction requires a new candidate; preserve original")
    elif "verification" in atom and not isinstance(atom["verification"], dict):
        error("FORMAT", "verification", "Expected object")
    return errors


def reusable(atom: dict, requested: dict, board: dict[str, dict] | None = None) -> bool:
    """Exact factual reuse only; callers supply the current claim/source/regime."""
    return (atom.get("verification_status") == "EXACT_SUPPORT"
            and requested.get("verification_status") in {"CANDIDATE", "EXACT_SUPPORT"}
            and not validate(atom, board) and fingerprint(atom) == fingerprint(requested))


def render(atom: dict) -> str:
    """Called after validation by CLI; quote content so it stays evidence, not markup."""
    lines = [f"### {atom['claim_id']} — {atom['verification_status']}", ""]
    for key in ("claim_text", *SOURCE, *ENVELOPE, "target_envelope", *COMPARISON,
                "source_value", "source_units", "derivation", "derived_value", "derived_units",
                "provenance_class", "reasoning_reason", "unresolved_mismatches", "invalidated_by", "notes"):
        if key in atom:
            value = atom[key] if isinstance(atom[key], str) else canonical(atom[key])
            lines.extend([f"**{key}:**", *("> " + line for line in value.splitlines()), ""])
    if isinstance(atom.get("verification"), dict):
        review = atom["verification"]
        lines.extend(["**Verification:**", "> " + canonical({k: v for k, v in review.items() if k != "reconstruction"}), ""])
    return "\n".join(lines)


def load_board(path: Path) -> tuple[dict[str, dict], list[dict]]:
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    board, errors = {}, []
    if not files:
        errors.append({"code": "EVIDENCE_FORMAT", "field": str(path), "message": "No JSON records found"})
    for file in files:
        try:
            atom = EvidenceAtom.parse(file.read_text(encoding="utf-8")).record
            claim_id = atom.get("claim_id")
            if not isinstance(claim_id, str) or not claim_id.strip() or claim_id in board:
                raise ValueError("Missing or duplicate claim_id")
            board[claim_id] = atom
        except (OSError, ValueError) as exc:
            errors.append({"code": "EVIDENCE_FORMAT", "field": str(file), "message": str(exc)})
    return board, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="One atom JSON or directory of atoms (including derivation inputs)")
    parser.add_argument("--markdown", action="store_true", help="Render validated records to stdout")
    parser.add_argument("--facts-only", action="store_true", help="Emit only EXACT_SUPPORT records")
    args = parser.parse_args()
    board, errors = load_board(args.path)
    for claim_id, atom in board.items():
        errors.extend(dict(e, claim_id=claim_id) for e in validate(atom, board))
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, indent=2), file=sys.stderr if args.markdown else sys.stdout)
        return 1
    selected = [a for a in board.values() if not args.facts_only or a["verification_status"] == "EXACT_SUPPORT"]
    if args.markdown:
        print("\n".join(render(a) for a in selected))
    else:
        print(json.dumps({"valid": True, "count": len(selected), "atoms": selected}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
