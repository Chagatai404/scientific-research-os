"""Declarative metadata discovery. No experiment execution or package installation."""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tomllib

import computational_manifest as manifest

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / "extensions" / "scientific-tools"
ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
PACKAGE = re.compile(r"[A-Za-z0-9]+(?:[-_.][A-Za-z0-9]+)*\Z")
# Exact argument tuples, bound to the applicable pack. Profiles cannot extend this.
COMMANDS = {"geant4": {("geant4-config", "--version")},
            "root-scikit-hep": {("root-config", "--version")}}
G4_ENV = {"G4LEDATA", "G4LEVELGAMMADATA", "G4PARTICLEXSDATA", "G4NEUTRONHPDATA",
          "G4RADIOACTIVEDATA", "G4PIIDATA", "G4REALSURFACEDATA", "G4SAIDXSDATA",
          "G4ABLADATA", "G4INCLDATA", "G4ENSDFSTATEDATA"}


def _table(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(f"{label}: expected exactly {', '.join(sorted(keys))}")


def _strings(value, pattern, label):
    if type(value) is not list or any(type(v) is not str or not pattern.fullmatch(v) for v in value):
        raise ValueError(f"{label}: expected list of valid names")
    if len(value) != len(set(value)):
        raise ValueError(f"{label}: duplicate names")


def validate_profile(profile: dict) -> None:
    _table(profile, {"schema_version", "id", "name", "category", "python", "probe", "provenance"}, "profile")
    if type(profile["schema_version"]) is not int or profile["schema_version"] != 1:
        raise ValueError("profile schema_version: expected integer 1")
    for field in ("id", "category"):
        if type(profile[field]) is not str or not ID.fullmatch(profile[field]):
            raise ValueError(f"{field}: expected lowercase hyphenated identifier")
    if type(profile["name"]) is not str or not profile["name"].strip():
        raise ValueError("name: expected nonempty string")
    _table(profile["python"], {"packages"}, "python")
    _strings(profile["python"]["packages"], PACKAGE, "python.packages")
    _table(profile["probe"], {"commands", "environment"}, "probe")
    commands = profile["probe"]["commands"]
    if type(commands) is not list:
        raise ValueError("probe.commands: expected list of argument arrays")
    seen = set()
    for command in commands:
        if (type(command) is not list or not command
                or any(type(arg) is not str for arg in command)
                or tuple(command) not in COMMANDS.get(profile["id"], set())):
            raise ValueError("probe.commands: unsupported executable/arguments; only code-owned probes allowed")
        if tuple(command) in seen:
            raise ValueError("probe.commands: duplicate probe")
        seen.add(tuple(command))
    names = profile["probe"]["environment"]
    _strings(names, re.compile(r"[A-Z][A-Z0-9_]*\Z"), "probe.environment")
    allowed = G4_ENV if profile["id"] == "geant4" else set()
    if not set(names) <= allowed:
        raise ValueError("probe.environment: only known dataset variables are supported")
    _table(profile["provenance"], {"fields"}, "provenance")
    _strings(profile["provenance"]["fields"], re.compile(r"[a-z][a-z0-9_]*\Z"), "provenance.fields")


def load_profiles(root: Path = PACKS) -> dict:
    if not root.is_dir():
        raise ValueError(f"missing tool-pack directory: {root}")
    result = {}
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        path = directory / "PROFILE.toml"
        try:
            with path.open("rb") as stream:
                profile = tomllib.load(stream)
            validate_profile(profile)
            if profile["id"] in result:
                raise ValueError(f"duplicate tool ID: {profile['id']}")
            if profile["id"] != directory.name:
                raise ValueError("tool ID must match directory name")
            if not (directory / "GUIDE.md").is_file():
                raise ValueError("missing GUIDE.md")
        except (OSError, ValueError) as exc:
            raise ValueError(f"{path}: {exc}") from exc
        result[profile["id"]] = profile
    return result


def _executable(name):
    path = shutil.which(name)
    # Windows can invoke batch files through a shell even with shell=False.
    if path and Path(path).suffix.lower() in {".bat", ".cmd", ".ps1"}:
        return None
    return path


def _run(arguments):
    return subprocess.run(arguments, shell=False, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=5, check=False)


def probe(profile: dict) -> dict:
    validate_profile(profile)  # Also protect direct API callers, before any effects.
    packages, commands = {}, {}
    for package in profile["python"]["packages"]:
        item = {"available": False, "observed_version": None, "error": None}
        try:
            item["observed_version"] = metadata.version(package)
            item["available"] = True
        except metadata.PackageNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            item["error"] = type(exc).__name__
        packages[package] = item
    for command in profile["probe"]["commands"]:
        executable = _executable(command[0])
        item = {"available": False, "path": executable, "observed_version": None,
                "returncode": None, "error": None}
        if executable:
            try:
                completed = _run([executable, *command[1:]])
                item["returncode"] = completed.returncode
                output = completed.stdout.strip()
                if completed.returncode == 0 and output and len(output) <= 256 and "\n" not in output:
                    item.update(available=True, observed_version=output)
                else:
                    item["error"] = "version probe failed or malformed output"
            except (OSError, subprocess.TimeoutExpired) as exc:
                item["error"] = type(exc).__name__
        commands[command[0]] = item
    return {"id": profile["id"],
            "available": any(i["available"] for i in [*packages.values(), *commands.values()]),
            "packages": packages, "commands": commands,
            "environment": {name: os.environ.get(name) for name in profile["probe"]["environment"]},
            "runtime": {"python": platform.python_version(), "platform": platform.platform()}}


def git_state(repo: Path) -> dict:
    state = {"commit": None, "dirty": None}
    executable = _executable("git")
    if not executable:
        return state
    try:
        commit = _run([executable, "-C", str(repo.resolve()), "rev-parse", "HEAD"])
        status = _run([executable, "-C", str(repo.resolve()), "status", "--porcelain", "--untracked-files=normal"])
        if commit.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", commit.stdout.strip()):
            state["commit"] = commit.stdout.strip()
        if status.returncode == 0:
            state["dirty"] = bool(status.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packs", type=Path, default=PACKS)
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("list", help="list profiles without running probes")
    inspect = sub.add_parser("probe")
    inspect.add_argument("tool", nargs="?")
    inspect.add_argument("--all", action="store_true")
    create = sub.add_parser("manifest")
    create.add_argument("--experiment", required=True)
    create.add_argument("--tool", action="append", default=[])
    create.add_argument("--repo", type=Path, default=Path.cwd())
    create.add_argument("--declared", type=Path, help="JSON mapping of explicit choices; never executed")
    create.add_argument("--reproduction-command")
    args = parser.parse_args()
    try:
        profiles = load_profiles(args.packs)
        if args.operation == "list":
            output = [{key: p[key] for key in ("id", "name", "category")} for p in profiles.values()]
        elif args.operation == "probe":
            if bool(args.tool) == args.all:
                raise ValueError("choose one tool or --all")
            output = [probe(p) for p in profiles.values()] if args.all else probe(profiles[args.tool])
        else:
            observed = {"git": git_state(args.repo),
                        "environment": {"python": platform.python_version(), "platform": platform.platform()},
                        "tools": {name: probe(profiles[name]) for name in sorted(set(args.tool))}}
            declared = json.loads(args.declared.read_text(encoding="utf-8"),
                                  object_pairs_hook=manifest._unique_object) if args.declared else {}
            output = manifest.create(args.experiment, observed=observed, declared=declared,
                                     reproduction_command=args.reproduction_command)
        print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"scientific-tools: {exc}\n")


if __name__ == "__main__":
    main()
