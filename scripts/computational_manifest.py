"""Schema-1 computational provenance; structural validity is not scientific truth."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path


FIELDS = {"schema_version", "experiment", "observed", "declared", "derived",
          "artifacts", "reproduction_command", "failure"}


def _json_value(value, path: str) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for i, item in enumerate(value):
            _json_value(item, f"{path}[{i}]")
        return
    if type(value) is dict and all(type(k) is str and k for k in value):
        for key, item in value.items():
            _json_value(item, f"{path}.{key}")
        return
    raise ValueError(f"{path}: expected finite JSON data with nonempty string keys")


def validate(record: dict) -> None:
    if type(record) is not dict or set(record) != FIELDS:
        raise ValueError("manifest: expected exactly " + ", ".join(sorted(FIELDS)))
    if type(record["schema_version"]) is not int or record["schema_version"] != 1:
        raise ValueError("schema_version: expected integer 1")
    if type(record["experiment"]) is not str or not record["experiment"].strip():
        raise ValueError("experiment: expected nonempty string")
    for field in ("observed", "declared", "derived"):
        if type(record[field]) is not dict:
            raise ValueError(f"{field}: expected mapping")
        # Provenance classes are containers, not values that can be merged together.
        if set(record[field]) & {"observed", "declared", "derived"}:
            raise ValueError(f"{field}: nested provenance-class containers are ambiguous")
    if type(record["artifacts"]) is not list or any(
        type(p) is not str or not p.strip() for p in record["artifacts"]
    ):
        raise ValueError("artifacts: expected list of nonempty path/URI strings")
    for field in ("reproduction_command", "failure"):
        if record[field] is not None and (
            type(record[field]) is not str or not record[field].strip()
        ):
            raise ValueError(f"{field}: expected nonempty string or null (UNKNOWN)")
    _json_value(record, "manifest")


def create(experiment: str, *, observed=None, declared=None, derived=None,
           artifacts=None, reproduction_command=None, failure=None) -> dict:
    record = deepcopy({
        "schema_version": 1, "experiment": experiment,
        "observed": {} if observed is None else observed,
        "declared": {} if declared is None else declared,
        "derived": {} if derived is None else derived,
        "artifacts": [] if artifacts is None else artifacts,
        "reproduction_command": reproduction_command, "failure": failure,
    })
    validate(record)
    return record


def dumps(record: dict) -> str:
    validate(record)
    return json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False,
                      allow_nan=False) + "\n"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads(text: str) -> dict:
    record = json.loads(text, object_pairs_hook=_unique_object)
    validate(record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="validate and print a manifest; never execute it")
    args = parser.parse_args()
    try:
        print(dumps(loads(args.path.read_text(encoding="utf-8"))), end="")
    except (OSError, ValueError) as exc:
        parser.exit(2, f"manifest: {exc}\n")


if __name__ == "__main__":
    main()
