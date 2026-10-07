"""Release-slice contract boundaries and real provider packaging."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import re
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install
from common import parse_frontmatter


def reference(name):
    return (ROOT / "references" / name).read_text(encoding="utf-8")


class V08ContractTests(unittest.TestCase):
    def test_contract_inventory_distinguishes_completed_and_pending_slices(self):
        self.assertEqual(len(install.V08_REFERENCES), 6)
        completed = {'LITERATURE_RELIABILITY_PROTOCOL.md': 'literature_check.py',
                     'AUTHENTICATED_ACCESS_PROTOCOL.md': 'paper_access.py'}
        for name in install.V08_REFERENCES:
            text = reference(name)
            if name in completed:
                self.assertIn(completed[name], text)
            else:
                self.assertIn("Slice 0", text)
                self.assertRegex(text, r"planned|pending|not.*implemented")
        self.assertIn("V08_REFERENCES", (ROOT / "scripts/validate.py").read_text(encoding="utf-8"))

    def test_one_lifecycle_and_existing_approval_order(self):
        stages = reference("RESEARCH_PROTOCOL.md").split("## Stages\n", 1)[1].split("\n## ", 1)[0]
        names = re.findall(r"^(\d+)\. \*\*(.*?)\.\*\*", stages, re.M)
        self.assertEqual([int(n) for n, _ in names], list(range(1, 21)))
        self.assertEqual([name for _, name in names[11:15]],
                         ["Plan", "Human approval", "Build", "Experiment"])
        text = reference("ORCHESTRATION_PROTOCOL.md")
        for requirement in ("only research lifecycle", "immediately before launch/resume/retry",
                            "not authorization by itself", "Task state records execution"):
            self.assertIn(requirement, text)

    def test_literature_contract_retains_claim_and_access_separation(self):
        text = reference("LITERATURE_RELIABILITY_PROTOCOL.md")
        for requirement in ("CANDIDATE EvidenceAtoms", "Full-text reading alone",
                            "abstract-only access", "EvidenceAtom v1", "existing receipts remain valid",
                            "DOI/title", "DOI/author", "particle number", "deposited energy"):
            self.assertIn(requirement, text)
        for classification in ("FALSE_CONFLICT", "SCOPE_DIFFERENCE", "CONVENTION_DIFFERENCE",
                               "EVIDENCE_QUALITY_DIFFERENCE", "GENUINE_CONFLICT", "UNRESOLVED"):
            self.assertIn(classification, text)

    def test_access_contract_never_accepts_credentials(self):
        text = reference("AUTHENTICATED_ACCESS_PROTOCOL.md")
        for requirement in ("already-authenticated user environment/session", "Credentials remain external",
                            "never know or store", "browser cookies", "authentication headers",
                            "institutional login forms", "allowlist", "before persistence or agent exposure",
                            "Unknown automation permission fails closed", "fake/local fixtures only"):
            self.assertIn(requirement, text)
        self.assertIn("credential exception does not apply", text)

    def test_execution_state_cannot_manufacture_independence_or_support(self):
        text = reference("ORCHESTRATION_PROTOCOL.md")
        for state in ("READY", "RUNNING", "WAITING", "BLOCKED", "COMPLETE", "FAILED", "CANCELLED"):
            self.assertIn(state, text)
        for requirement in ("actual context", "not proof", "not scientific", "writer reservation",
                            "Reject concurrent writers", "no central database", "permanent daemon",
                            "Windows-safe", "manual/sequential", "stale RUNNING"):
            # Actual exposure is represented explicitly even without this exact prose.
            if requirement == "actual context":
                self.assertIn("context_exposure", text)
            else:
                self.assertIn(requirement, text)

    def test_ownership_and_defense_preserve_two_axes_and_real_learning(self):
        ownership = reference("RESEARCHER_OWNERSHIP_PROTOCOL.md")
        defense = reference("DEFENSE_PROTOCOL.md")
        for requirement in ("do not block scientifically valid research", "actual human-learning evidence",
                            "do not count against", "only tutor-initiated", "return point",
                            "single mastery scalar", "current strict schema-2 parser"):
            self.assertIn(requirement, ownership)
        for requirement in ("read-only projection", "Scientific support", "Personal defensibility",
                            "one question at a time", "actual", "No global ready flag",
                            "Successful viva", "manual list"):
            self.assertIn(requirement, defense)

    def test_design_routes_resolve_in_existing_responsibilities(self):
        routes = {
            "RESEARCH_PROTOCOL.md": ("ORCHESTRATION_PROTOCOL.md", "DEFENSE_PROTOCOL.md"),
            "SOURCE_POLICY.md": ("LITERATURE_RELIABILITY_PROTOCOL.md", "AUTHENTICATED_ACCESS_PROTOCOL.md"),
            "EVIDENCE_FORMAT.md": ("LITERATURE_RELIABILITY_PROTOCOL.md",),
            "PAPER_LIBRARY.md": ("AUTHENTICATED_ACCESS_PROTOCOL.md",),
            "LEARNING_PROTOCOL.md": ("RESEARCHER_OWNERSHIP_PROTOCOL.md", "DEFENSE_PROTOCOL.md"),
            "TUTOR_PLANNING.md": ("RESEARCHER_OWNERSHIP_PROTOCOL.md",),
            "KNOWLEDGE_MODEL.md": ("RESEARCHER_OWNERSHIP_PROTOCOL.md",),
            "RESEARCH_GRAPH_PROTOCOL.md": ("ORCHESTRATION_PROTOCOL.md", "DEFENSE_PROTOCOL.md"),
        }
        for owner, targets in routes.items():
            for target in targets:
                self.assertIn(target, reference(owner))
                self.assertTrue((ROOT / "references" / target).is_file())

    def test_actual_provider_bundles_have_identical_complete_contracts(self):
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            base = Path(temporary)
            install.install_agents_claude(base / "claude", False)
            install.install_agents_codex(base / "codex", False)
            for source in (ROOT / "agents").glob("*.md"):
                _, claude = parse_frontmatter((base / "claude" / source.name).read_text(encoding="utf-8"))
                codex = tomllib.loads((base / "codex" / f"{source.stem}.toml").read_text(encoding="utf-8"))["developer_instructions"]
                self.assertEqual(claude.strip(), codex.strip())
                for name in ("ORCHESTRATION_PROTOCOL.md", *install.V08_AGENT_REFERENCES.get(source.stem, ())):
                    self.assertIn(reference(name).strip(), claude)
            # Exercise the actual shared-reference copy mechanism for both targets.
            for provider in ("claude", "codex"):
                install.install_skills(base / f"{provider}-skills", False)
                for skill in ("research-session", "tutor"):
                    for name in install.V08_REFERENCES:
                        self.assertEqual((base / f"{provider}-skills" / skill / "references" / name).read_bytes(),
                                         (ROOT / "references" / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
