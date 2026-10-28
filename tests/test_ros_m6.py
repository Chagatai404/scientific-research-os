"""Installation for any agent client, exports, vault migration, and the contract between docs and tools."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ros import api, export, importers, install, research  # noqa: E402
from ros.store import Record  # noqa: E402
import support_ros_demo as demo  # noqa: E402

SKILLS = {"learn", "prepare", "research", "audit", "defend", "notes-to-latex"}
AGENTS = {"scout", "verifier", "auditor", "adversary", "visual-maker", "video-scout", "librarian"}
REFERENCES = {"TEACHING", "PREPARATION", "RESEARCH", "EVIDENCE", "DATA_MODEL", "PORTAL", "VOICE", "SAFETY",
              "VAULT", "HANDOUTS", "DIRECTOR"}


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)


class InstallTests(Fixture):
    def test_claude_project_install_writes_skills_agents_and_merges_mcp(self):
        (self.tmp / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
        out = install.install("claude", self.tmp)
        self.assertTrue(out["installed"])
        for s in SKILLS:
            self.assertTrue((self.tmp / ".claude/skills" / s / "SKILL.md").exists(), s)
            self.assertTrue((self.tmp / ".claude/skills" / s / "references/SAFETY.md").exists(), s)
        self.assertTrue((self.tmp / ".claude/skills/audit/lenses/statistics.md").exists())
        self.assertEqual({p.stem for p in (self.tmp / ".claude/agents").glob("*.md")}, AGENTS)
        servers = json.loads((self.tmp / ".mcp.json").read_text())["mcpServers"]
        self.assertEqual(servers["other"], {"command": "x"})
        self.assertEqual(servers["research-os"]["args"], ["-m", "ros", "mcp"])
        again = install.install("claude", self.tmp)
        self.assertEqual(again["written"], [])

    def test_hand_edits_are_refused_unless_forced(self):
        install.install("claude", self.tmp)
        skill = self.tmp / ".claude/skills/learn/SKILL.md"
        skill.write_text(skill.read_text() + "\nmy note\n")
        out = install.install("claude", self.tmp)
        self.assertFalse(out["installed"])
        self.assertEqual(out["refused"], [".claude/skills/learn/SKILL.md"])
        self.assertIn("my note", skill.read_text())
        self.assertTrue(install.install("claude", self.tmp, force=True)["installed"])
        self.assertNotIn("my note", skill.read_text())

    def test_a_foreign_file_in_the_way_is_not_overwritten(self):
        target = self.tmp / ".claude/agents/scout.md"
        target.parent.mkdir(parents=True)
        target.write_text("someone else's scout")
        self.assertEqual(install.install("claude", self.tmp)["refused"], [".claude/agents/scout.md"])

    def test_codex_gemini_and_agents_md_keep_what_was_there(self):
        (self.tmp / "AGENTS.md").write_text("# House rules\n\nBe kind.\n")
        (self.tmp / ".codex").mkdir()
        (self.tmp / ".codex/config.toml").write_text('model = "x"\n')
        install.install("codex", self.tmp)
        install.install("codex", self.tmp)
        agents = (self.tmp / "AGENTS.md").read_text()
        self.assertTrue(agents.startswith("# House rules"))
        self.assertEqual(agents.count(install.BEGIN), 1)
        self.assertIn("**learn**", agents)
        toml = (self.tmp / ".codex/config.toml").read_text()
        self.assertTrue(toml.startswith('model = "x"'))
        self.assertEqual(toml.count("[mcp_servers.research-os]"), 1)
        self.assertTrue((self.tmp / ".agents/skills/research/lenses/geant4.md").exists())
        install.install("gemini", self.tmp)
        settings = json.loads((self.tmp / ".gemini/settings.json").read_text())
        self.assertIn("research-os", settings["mcpServers"])
        self.assertIn(install.BEGIN, (self.tmp / "GEMINI.md").read_text())

    def test_dry_run_writes_nothing(self):
        out = install.install("agents", self.tmp, dry_run=True)
        self.assertEqual(out["would_write"], ["AGENTS.md"])
        self.assertFalse((self.tmp / "AGENTS.md").exists())


class ExportTests(Fixture):
    def test_obsidian_notes_and_edits_are_kept(self):
        import os
        from unittest import mock
        rec, _ = demo.build(self.tmp / "rec")
        self.addCleanup(rec.close)
        research.decide(rec, "claim:width", "revise", "Researcher", "Needs the integrity audit.")
        vault = self.tmp / "vault"
        vault.mkdir()
        with mock.patch.dict(os.environ, {"ROS_HOME": str(self.tmp / "home")}):
            out = api.call("export", rec, kind="obsidian", path=str(vault))
            base = vault / "Research OS" / "Projects" / "rec"
            self.assertTrue((base / "rec.md").exists())
            note = (base / "Capabilities" / "Variance.md").read_text()
            self.assertIn("[[Research OS/Projects/rec/Capabilities/Mean|Mean]]", note)
            self.assertEqual(len(list((base / "Decisions").glob("*.md"))), 1)
            self.assertEqual(api.call("export", rec, kind="obsidian", path=str(vault))["created"], [])
            (base / "Capabilities" / "Variance.md").write_text(note.replace("## Requires", "## My reading"))
            rec.append("retrieval", "capability:variance", {"day": "2026-09-01", "period": "p", "timing": "same-session",
                                                            "method": "explanation", "outcome": "fail",
                                                            "assistance": "none", "evidence": "e", "review": None})
            again = api.call("export", rec, kind="obsidian", path=str(vault))
            self.assertIn("Research OS/Projects/rec/Capabilities/Variance.md", again["kept_edited"])
            self.assertIn("## My reading", (base / "Capabilities" / "Variance.md").read_text())
            self.assertGreater(out["created_count"], 3)

    def test_static_snapshot_is_self_contained_and_says_read_only(self):
        rec, bundle = demo.build(self.tmp / "rec")
        self.addCleanup(rec.close)
        lesson = api.call("start", rec, bundle=bundle)["lesson"]
        step = api.call("next", rec, lesson=lesson)
        api.call("answer", rec, lesson=lesson, item=step["item"], response=3)
        path = export.static(rec, self.tmp / "out" / "snapshot.html")
        html = path.read_text()
        self.assertIn("Read-only snapshot", html)
        self.assertIn("Mean of 2 and 4?", html)
        self.assertNotRegex(html, r"(?:src|href)=['\"]https?:")
        self.assertIn("default-src 'none'", html)


class MigrateTests(Fixture):
    def test_a_vault_migrates_and_every_answer_is_accounted_for(self):
        vault = self.tmp / "vault"
        shutil.copytree(ROOT / "tests" / "fixtures" / "legacy-v0.8.7", vault)
        shutil.copytree(ROOT / "examples" / "learning", vault / "learning")
        rec = Record(self.tmp / "rec")
        self.addCleanup(rec.close)
        report = importers.migrate(rec, vault)
        self.assertTrue(report["check"]["ok"], report["check"])
        self.assertEqual(report["check"]["answers"], 3)
        self.assertEqual(report["learning"]["capabilities"], 3 + 1)  # the example notes and the legacy note
        self.assertTrue((rec.root / "migration-report.json").exists())
        self.assertEqual(importers.migrate(rec, vault)["sessions"]["events_added"], 0)


class DocsContractTests(unittest.TestCase):
    def front(self, path):
        m = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
        self.assertTrue(m, f"{path} has no frontmatter")
        return dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)

    def test_the_skills_agents_and_protocols_are_all_present(self):
        self.assertEqual({p.name for p in (ROOT / "skills").iterdir() if p.is_dir()}, SKILLS)
        self.assertEqual({p.stem for p in (ROOT / "agents").glob("*.md")}, AGENTS)
        self.assertEqual({p.stem for p in (ROOT / "references").glob("*.md")}, REFERENCES)
        for s in SKILLS:
            meta = self.front(ROOT / "skills" / s / "SKILL.md")
            self.assertEqual(meta["name"].strip(), s)
            self.assertGreater(len(meta["description"].strip()), 40)
        for a in AGENTS:
            self.assertEqual(self.front(ROOT / "agents" / f"{a}.md")["name"].strip(), a)

    def test_docs_point_only_at_things_that_exist(self):
        docs = list((ROOT / "skills").rglob("*.md")) + list((ROOT / "agents").glob("*.md")) + \
            list((ROOT / "references").glob("*.md")) + [ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / "AGENTS.md"] + \
            list((ROOT / "docs").glob("*.md")) + list((ROOT / "extensions").rglob("*.md")) + \
            list((ROOT / "examples").rglob("README.md"))
        for path in docs:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertNotRegex(text, r"scripts/[a-z_]+\.py", "the old scripts are gone")
                self.assertNotRegex(text, r"\b[A-Z_]+_(?:PROTOCOL|POLICY|FORMAT)(?:\.md)?\b", "the old protocol files are gone")
                for ref in re.findall(r"references/([A-Z_]+\.md)", text):
                    self.assertTrue((ROOT / "references" / ref).exists(), ref)
                for target in re.findall(r"\]\(((?!https?:|#|mailto:)[^)\s]+)\)", text):
                    self.assertTrue((path.parent / target.split("#")[0]).exists(), f"broken link {target}")
                for mod in re.findall(r"ros\.lib\.([a-z_]+)", text):
                    self.assertTrue((ROOT / "ros" / "lib" / f"{mod}.py").exists(), mod)

    def test_every_tool_a_skill_invokes_exists(self):
        """A backticked `name --arg ...` in a skill is a tool call; the tool must exist with those arguments."""
        specials = {"init": set(), "learn": {"bundle", "title"}, "serve": {"port", "open"}, "install": set(),
                    "migrate": set()}
        for s in SKILLS - {"notes-to-latex"}:
            text = (ROOT / "skills" / s / "SKILL.md").read_text(encoding="utf-8")
            calls = re.findall(r"`([a-z_]+)((?: --[a-z_-]+(?: [^`-][^`]*?)?)+)`", text)
            self.assertTrue(calls or s in ("audit",), f"{s} invokes no tool")
            for tool, args in calls:
                with self.subTest(skill=s, tool=tool):
                    if tool in ("python", "ros"):
                        continue
                    self.assertTrue(tool in api.TOOLS or tool in specials, tool)
                    known = set(api.TOOLS[tool].params) if tool in api.TOOLS else specials[tool]
                    for arg in re.findall(r"--([a-z_-]+)", args):
                        if known:
                            self.assertIn(arg.replace("-", "_"), known, f"{tool} --{arg}")

    def test_human_acts_are_marked(self):
        self.assertEqual({n for n, t in api.TOOLS.items() if t.human}, {"approve", "decide", "waive", "source_register", "source_change", "source_location", "source_engine_root", "source_use_vault", "source_relocate", "provider_configure", "notebook_request", "execution_configure", "compute_request", "transcription_accept", "vision_permission"})


if __name__ == "__main__":
    unittest.main()
