"""Exercise deployed instructions, not just source-document wording."""
from pathlib import Path
import sys
import tomllib
import tempfile
import unittest
from contextlib import redirect_stdout
import io

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install
from common import parse_frontmatter

class InstallationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp_path = Path(temporary.name)
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_installed_skills_have_current_shared_references(self):
        tmp_path = self.tmp_path
        base = tmp_path / "skills"
        install.install_skills(base, False)
        # Reinstallation must replace stale policy copies too.
        stale = base / "tutor" / "references" / "LEARNING_PROTOCOL.md"
        stale.write_text("obsolete", encoding="utf-8")
        install.install_skills(base, False)
        for skill in (ROOT / "skills").iterdir():
            if not (skill / "SKILL.md").is_file():
                continue
            assert (base / skill.name / "SKILL.md").read_bytes() == (skill / "SKILL.md").read_bytes()
            for reference in (ROOT / "references").glob("*.md"):
                assert (base / skill.name / "references" / reference.name).read_bytes() == reference.read_bytes()


    def test_both_agent_formats_preserve_roles_and_bundle_canonical_policy(self):
        tmp_path = self.tmp_path
        claude, codex = tmp_path / "claude", tmp_path / "codex"
        install.install_agents_claude(claude, False)
        install.install_agents_codex(codex, False)
        policy = (ROOT / "references" / "AGENT_POLICY.md").read_text(encoding="utf-8")
        research = (ROOT / "references" / "RESEARCH_PROTOCOL.md").read_text(encoding="utf-8")
        boundaries = research[research.index("## Blocker / relevance triage"):research.index("## Scientific invariants")]
        for source in (ROOT / "agents").glob("*.md"):
            meta, role = parse_frontmatter(source.read_text(encoding="utf-8"))
            installed_meta, claude_body = parse_frontmatter((claude / source.name).read_text(encoding="utf-8"))
            config = tomllib.loads((codex / f'{meta["name"]}.toml').read_text(encoding="utf-8"))
            assert installed_meta == meta
            assert config["name"] == meta["name"]
            for body in (claude_body, config["developer_instructions"]):
                assert role.strip() in body
                assert policy in body
                assert boundaries.strip() in body
                if meta["name"] in {"literature-scout", "source-verifier"}:
                    assert (ROOT / "references" / "SOURCE_POLICY.md").read_text(encoding="utf-8") in body


    def test_dry_run_creates_no_files(self):
        tmp_path = self.tmp_path
        target = tmp_path / "not-created"
        install.install_skills(target / "skills", True)
        install.install_agents_claude(target / "claude", True)
        install.install_agents_codex(target / "codex", True)
        assert not target.exists()
