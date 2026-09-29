from copy import deepcopy
from pathlib import Path
import importlib.metadata as metadata
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scientific_tools as tools


def profile():
    return {"schema_version": 1, "id": "example", "name": "Example", "category": "analysis",
            "python": {"packages": ["example"]}, "probe": {"commands": [], "environment": []},
            "provenance": {"fields": ["version"]}}


class ToolTests(unittest.TestCase):
    def test_hep_partial_ecosystem_is_useful_without_root(self):
        def version(name):
            if name in {"uproot", "awkward"}:
                return "test-version"
            raise metadata.PackageNotFoundError(name)
        with patch.object(tools.metadata, "version", side_effect=version), \
                patch.object(tools.shutil, "which", return_value=None):
            result = tools.probe(tools.load_profiles()["root-scikit-hep"])
        self.assertTrue(result["available"])
        self.assertFalse(result["packages"]["ROOT"]["available"])
        self.assertFalse(result["commands"]["root-config"]["available"])
        self.assertTrue(result["packages"]["uproot"]["available"])
        self.assertTrue(result["packages"]["awkward"]["available"])
        self.assertFalse((tools.ROOT / "skills/root").exists())
        self.assertFalse((tools.ROOT / "skills/scikit-hep").exists())

    def test_quantum_metadata_never_queries_backend(self):
        for name in ("pennylane", "qiskit"):
            p = tools.load_profiles()[name]
            for available in (False, True):
                with patch.object(tools.metadata, "version", **(
                        {"return_value": "test-version"} if available else
                        {"side_effect": metadata.PackageNotFoundError})), \
                        patch.object(tools, "_run") as run:
                    result = tools.probe(p, accelerator=True)
                    self.assertEqual(result["available"], available)
                    self.assertNotIn("shots", result)
                    self.assertNotIn("backend", result)
                    run.assert_not_called()

    def test_ml_metadata_and_opt_in_accelerator(self):
        profiles = tools.load_profiles()
        with patch.object(tools.metadata, "version", return_value="test-version"), \
                patch.object(tools, "_run") as run:
            for name, package in (("pytorch", "torch"), ("sklearn", "scikit-learn")):
                self.assertEqual(tools.probe(profiles[name])["packages"][package]["observed_version"], "test-version")
            run.assert_not_called()
        response = '{"cuda_available":false,"cuda_build":null,"mps_available":false}'
        with patch.object(tools.metadata, "version", return_value="test-version"), \
                patch.object(tools, "_run", return_value=subprocess.CompletedProcess([], 0, response)) as run:
            state = tools.probe(profiles["pytorch"], accelerator=True)["accelerator"]
            self.assertIs(state["cuda_available"], False)
            self.assertIsNone(state["error"])
            self.assertEqual(run.call_args.args[0], [sys.executable, "-I", "-c", tools.TORCH_QUERY])
        for response in ('bad', '{"cuda_available":"yes"}', '[]'):
            with patch.object(tools, "_run", return_value=subprocess.CompletedProcess([], 0, response)):
                self.assertIsNone(tools.accelerator_state()["cuda_available"])
        with patch.object(tools, "_run", side_effect=subprocess.TimeoutExpired("torch", 5)):
            self.assertEqual(tools.accelerator_state()["error"], "TimeoutExpired")

    def test_geant4_binding_datasets_and_no_inference(self):
        p = tools.load_profiles()["geant4"]
        with patch.object(tools.metadata, "version", return_value="binding-test"), \
                patch.object(tools.shutil, "which", return_value=None), \
                patch.dict(tools.os.environ, {"G4LEDATA": "/example/data"}, clear=True):
            result = tools.probe(p)
        self.assertTrue(result["available"])
        self.assertFalse(result["commands"]["geant4-config"]["available"])
        self.assertEqual(result["packages"]["geant4_pybind"]["observed_version"], "binding-test")
        self.assertEqual(result["environment"]["G4LEDATA"], "/example/data")
        self.assertIsNone(result["environment"]["G4NEUTRONHPDATA"])
        for key in ("physics_list", "cuts", "geometry", "beam", "seed", "events"):
            self.assertNotIn(key, str(result))
        with patch.object(tools.metadata, "version", side_effect=metadata.PackageNotFoundError), \
                patch.object(tools.shutil, "which", return_value=None):
            self.assertFalse(tools.probe(p)["available"])

    def test_missing_package_and_metadata_without_import(self):
        with patch.object(tools.metadata, "version", side_effect=metadata.PackageNotFoundError), \
                patch.object(tools, "_run") as run:
            self.assertFalse(tools.probe(profile())["available"])
            run.assert_not_called()
        with patch.object(tools.metadata, "version", return_value="1.2"):
            result = tools.probe(profile())
            self.assertEqual(result["packages"]["example"]["observed_version"], "1.2")
            self.assertTrue(result["available"])
            self.assertNotIn("declared", result)

    def test_unsafe_profiles_rejected_before_effects(self):
        for commands in ("echo x", ["echo x"], [["python", "-c", "print(1)"]],
                         [["sh", "-c", "true"]], [["geant4-config", "--version", "|", "cat"]],
                         [["geant4-config;echo", "--version"]], [["/tmp/probe", "--version"]],
                         [["geant4-config", ">output"]], [[1]], [[]]):
            p = profile()
            p["probe"]["commands"] = commands
            with self.subTest(commands=commands), patch.object(tools, "_run") as run:
                with self.assertRaises(ValueError):
                    tools.probe(p)
                run.assert_not_called()
        for change in ({"schema_version": True}, {"schema_version": 2}, {"id": "../x"},
                       {"category": []}, {"python": {"packages": ["x;evil"]}},
                       {"python": {"packages": [], "script": "evil"}},
                       {"probe": {"command": "evil"}},
                       {"probe": {"commands": [], "environment": ["API_TOKEN"]}}):
            with self.assertRaises(ValueError):
                tools.validate_profile({**profile(), **change})

    def test_load_requires_guide_and_matching_unique_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "example"
            directory.mkdir()
            text = ('schema_version=1\nid="example"\nname="Example"\ncategory="analysis"\n'
                    '[python]\npackages=[]\n[probe]\ncommands=[]\nenvironment=[]\n'
                    '[provenance]\nfields=[]\n')
            (directory / "PROFILE.toml").write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "GUIDE"):
                tools.load_profiles(root)
            (directory / "GUIDE.md").write_text("Guide", encoding="utf-8")
            self.assertEqual(list(tools.load_profiles(root)), ["example"])
            second = root / "zzz"
            second.mkdir()
            (second / "PROFILE.toml").write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                tools.load_profiles(root)

    def test_command_normalization_timeout_and_missing_executable(self):
        p = profile()
        p.update(id="geant4", python={"packages": []})
        p["probe"]["commands"] = [["geant4-config", "--version"]]
        with patch.object(tools.shutil, "which", return_value=None), patch.object(tools, "_run") as run:
            self.assertFalse(tools.probe(p)["available"])
            run.assert_not_called()
        for result in (subprocess.CompletedProcess([], 0, "11.4.1\n"),
                       subprocess.CompletedProcess([], 1, ""),
                       subprocess.CompletedProcess([], 0, "bad\noutput")):
            with patch.object(tools.shutil, "which", return_value="/bin/geant4-config"), \
                    patch.object(tools.subprocess, "run", return_value=result) as run:
                observed = tools.probe(p)
                self.assertEqual(observed["available"], result.stdout == "11.4.1\n")
                self.assertFalse(run.call_args.kwargs["shell"])
                self.assertEqual(run.call_args.kwargs["timeout"], 5)
        with patch.object(tools.shutil, "which", return_value="/bin/geant4-config"), \
                patch.object(tools, "_run", side_effect=subprocess.TimeoutExpired("probe", 5)):
            self.assertEqual(tools.probe(p)["commands"]["geant4-config"]["error"], "TimeoutExpired")

    def test_windows_batch_is_inert(self):
        for suffix in ("cmd", "BAT", "ps1"):
            with patch.object(tools.shutil, "which", return_value=f"C:/tools/geant4-config.{suffix}"):
                self.assertIsNone(tools._executable("geant4-config"))

    def test_git_unknown_and_dirty_worktree(self):
        with patch.object(tools, "_executable", return_value=None):
            self.assertEqual(tools.git_state(Path.cwd()), {"commit": None, "dirty": None})
        with patch.object(tools, "_executable", return_value="git"), patch.object(tools, "_run", side_effect=[
            subprocess.CompletedProcess([], 0, "a" * 40 + "\n"),
            subprocess.CompletedProcess([], 0, "?? input.json\n")]):
            self.assertEqual(tools.git_state(Path.cwd()), {"commit": "a" * 40, "dirty": True})
