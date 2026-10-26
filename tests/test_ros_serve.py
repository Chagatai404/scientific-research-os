"""The portal server: loopback only, writes need the custom header, media with byte ranges, tools over HTTP."""
from __future__ import annotations

import http.client
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ros import serve  # noqa: E402
import support_ros_demo as demo  # noqa: E402


class ServeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.rec, cls.bundle = demo.build(Path(cls._tmp.name) / "rec")
        cls.server = serve.start(cls.rec, 0)
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.rec.close()
        cls._tmp.cleanup()

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": f"127.0.0.1:{self.port}", **(headers or {})}
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, dict(r.getheaders()), data

    def test_page_and_static_files(self):
        status, headers, body = self.req("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"/static/app.js", body)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        status, headers, _ = self.req("GET", "/static/vendor/katex/katex.min.js")
        self.assertEqual((status, headers["Cache-Control"]), (200, "max-age=31536000, immutable"))
        self.assertEqual(self.req("GET", "/static/../serve.py")[0], 404)

    def test_foreign_host_is_refused(self):
        status, _, _ = self.req("GET", "/api/status", headers={"Host": "evil.example:80"})
        self.assertEqual(status, 403)

    def test_reads_by_get_writes_only_by_post_with_header(self):
        status, _, body = self.req("GET", "/api/today")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["result"]["next_lesson"]["bundle"], self.bundle)
        self.assertEqual(self.req("GET", "/api/start?bundle=%22variance-1%22")[0], 405)
        self.assertEqual(self.req("POST", "/api/start", {"bundle": self.bundle})[0], 403)
        status, _, body = self.req("POST", "/api/start", {"bundle": self.bundle}, {"X-ROS": "1"})
        self.assertEqual(status, 200)
        step = json.loads(body)["result"]["next"]
        self.assertEqual(step["action"], "probe")
        self.assertNotIn("answer", step["question"])
        status, _, body = self.req("POST", "/api/answer", {"lesson": "x"}, {"X-ROS": "1"})
        self.assertEqual(status, 400)
        self.assertIn("item is required", json.loads(body)["error"])

    def test_media_ranges_and_confinement(self):
        path = f"/media/bundles/{self.bundle}/audio/mean.wav"
        status, headers, body = self.req("GET", path, headers={"Range": "bytes=0-43"})
        self.assertEqual((status, len(body), headers["Content-Type"]), (206, 44, "audio/wav"))
        self.assertTrue(headers["Content-Range"].startswith("bytes 0-43/"))
        self.assertEqual(self.req("GET", "/media/events.jsonl")[0], 404)
        self.assertEqual(self.req("GET", f"/media/bundles/{self.bundle}/../../events.jsonl")[0], 404)

    def test_events_stream_announces_changes(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", "/events", headers={"Host": "localhost"})
        r = c.getresponse()
        self.assertEqual(r.getheader("Content-Type"), "text/event-stream")
        self.assertEqual(r.readline(), b"event: change\n")
        c.close()


if __name__ == "__main__":
    unittest.main()


class PoolAndVaultTests(unittest.TestCase):
    """Several records through one portal, and the vault served read-only from its Research OS folder only."""

    def setUp(self):
        import os
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self._env = dict(os.environ)
        os.environ["ROS_HOME"] = str(tmp / "ros")
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._env)))
        self.addCleanup(serve.api.release)
        from ros import home, vault
        self.rec, _ = demo.build(home.home() / "projects" / "stat")
        self.other, _ = demo.build(home.home() / "projects" / "other")
        self.other.put_node("claim:other-only", "claim", text="Only in the other record", project="o", author="a",
                            assurance="draft", numbers=[], artifacts=[], citations=[])
        self.vault = tmp / "Vault"
        (self.vault / "Research OS" / "Handouts").mkdir(parents=True)
        (self.vault / "Research OS" / "Handouts" / "a.pdf").write_bytes(b"%PDF-1.4 hello")
        (self.vault / "Research OS" / "Handouts" / "n.md").write_text("# note\n")
        (self.vault / "Research OS" / "Handouts" / ".hidden.md").write_text("x")
        (self.vault / "Research OS" / "Handouts" / "run.exe").write_bytes(b"MZ")
        (self.vault / "Secret.md").write_text("outside the folder")
        (self.vault / "Research OS" / "link.md").symlink_to(self.vault / "Secret.md")
        home.set_settings(vault=str(self.vault))
        self.server = serve.start(self.rec, 0)
        self.port = self.server.server_address[1]
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), self.rec.close(), self.other.close()))

    def get(self, path):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", path, headers={"Host": f"127.0.0.1:{self.port}"})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, dict(r.getheaders()), data

    def test_a_record_argument_picks_the_record_and_unknown_ones_are_refused(self):
        _, _, body = self.get("/api/claims")
        self.assertEqual([c["id"] for c in json.loads(body)["result"]], ["claim:width"])
        _, _, body = self.get("/api/claims?record=%22other%22")
        self.assertIn("claim:other-only", [c["id"] for c in json.loads(body)["result"]])
        status, _, body = self.get("/api/claims?record=%22nope%22")
        self.assertEqual(status, 400)
        self.assertIn("no record", json.loads(body)["error"])
        status, _, _ = self.get("/api/claims?record=%22..%2F..%22")
        self.assertEqual(status, 400)
        _, _, body = self.get("/api/records")
        self.assertEqual({r["name"] for r in json.loads(body)["result"]}, {"stat", "other"})

    def test_the_vault_serves_notes_and_pdfs_from_its_folder_only(self):
        status, headers, body = self.get("/vault/Research%20OS/Handouts/a.pdf")
        self.assertEqual((status, body), (200, b"%PDF-1.4 hello"))
        self.assertEqual(headers["Content-Type"], "application/pdf")
        self.assertEqual(self.get("/vault/Handouts/a.pdf")[0], 200)  # the folder name is optional
        self.assertEqual(self.get("/vault/Research%20OS/Handouts/n.md")[0], 200)
        for bad in ("/vault/Research%20OS/Handouts/.hidden.md", "/vault/Research%20OS/Handouts/run.exe",
                    "/vault/Research%20OS/link.md", "/vault/Secret.md", "/vault/../Secret.md",
                    "/vault/Research%20OS/../Secret.md", "/vault/Research%20OS/%2e%2e/Secret.md",
                    "/vault/Research%20OS/Handouts/missing.pdf", "/vault/Research%20OS/Handouts%5Ca.pdf", "/vault/"):
            self.assertEqual(self.get(bad)[0], 404, bad)
        self.assertEqual(self.req_range("/vault/Research%20OS/Handouts/a.pdf", "bytes=0-3"), b"%PDF")

    def req_range(self, path, rng):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", path, headers={"Host": f"127.0.0.1:{self.port}", "Range": rng})
        r = c.getresponse()
        data = r.read()
        c.close()
        self.assertEqual(r.status, 206)
        return data

    def test_without_a_vault_nothing_is_served(self):
        from ros import home
        (home.home() / "settings.json").unlink()  # no vault is set
        self.assertEqual(self.get("/vault/Research%20OS/Handouts/a.pdf")[0], 404)

    def test_a_second_portal_is_recognised_and_run_opens_it(self):
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            code = serve.run(self.other, self.port, False)
        self.assertEqual(code, 0)
        self.assertIn(f"already running: http://127.0.0.1:{self.port}/", out.getvalue())

    def test_our_own_code_stays_within_the_budget(self):
        portal = ROOT / "ros" / "portal"
        self.assertLess((portal / "app.js").stat().st_size, 60 * 1024)
        self.assertLess((portal / "app.css").stat().st_size, 20 * 1024)
