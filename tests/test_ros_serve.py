"""The portal server: loopback only, writes need the custom header, media with byte ranges, tools over HTTP."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

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

    def test_a_refused_request_cannot_smuggle_a_second_one_in_its_body(self):
        # A web page sends a POST the server refuses (no X-ROS header) whose body is a complete second request that would pass
        # every check. On a kept-alive connection that body must never be read as a request.
        import socket
        before = len(self.rec.nodes(type="concept"))
        forged = json.dumps({"id": "concept:smuggled", "type": "concept", "data": {"title": "Smuggled"}}).encode()
        inner = (f"POST /api/add_node HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nX-ROS: 1\r\nContent-Type: application/json\r\n"
                 f"Content-Length: {len(forged)}\r\n\r\n").encode() + forged
        outer = (f"POST /api/add_node HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nContent-Type: text/plain\r\n"
                 f"Origin: http://evil.example\r\nContent-Length: {len(inner)}\r\n\r\n").encode() + inner
        with socket.create_connection(("127.0.0.1", self.port), timeout=3) as raw:
            raw.sendall(outer)
            received = b""
            while True:
                try:
                    chunk = raw.recv(65536)
                except TimeoutError:  # the connection was kept open: the body may have been taken as a request
                    break
                if not chunk:
                    break
                received += chunk
        self.assertEqual(received.count(b"HTTP/1.1 "), 1, "one response, then the connection is closed")
        self.assertIn(b"403", received.split(b"\r\n", 1)[0])
        self.assertIsNone(self.rec.node("concept:smuggled")); self.assertEqual(len(self.rec.nodes(type="concept")), before)
        # A chunked body (not parsed here) is refused rather than left on the connection.
        self.assertEqual(self.req("POST", "/api/add_node", headers={"X-ROS": "1", "Transfer-Encoding": "chunked"})[0], 400)

    def test_acts_that_are_the_persons_alone_need_a_browser_paired_by_the_printed_link(self):
        # The session call gives the page its CSRF token and sets no cookie (cookies reach every port of 127.0.0.1): only the
        # token from the printed link, sent by the page as a header, pairs it.
        status, headers, body = self.req("GET", "/services/session")
        self.assertEqual(status, 200); self.assertNotIn("Set-Cookie", headers); self.assertFalse(json.loads(body)["result"]["paired"])
        csrf = json.loads(body)["result"]["csrf"]
        packet = {"name": "approve", "args": {"subject": "experiment:none", "decision": "approved", "by": "Me"}}
        unpaired = {"X-ROS": "1", "X-ROS-CSRF": csrf, "Sec-Fetch-Site": "same-origin", "Content-Type": "application/json"}
        for wrong in ({}, {"X-ROS-Pair": "wrong-token"}, {"X-ROS-Pair": "\u00e9t\u00e9"}):
            status, _, body = self.req("POST", "/services/human-prepare", packet, {**unpaired, **wrong})
            self.assertEqual(status, 403, wrong); self.assertIn(b"not paired", body)
        status, headers, _ = self.req("GET", "/?pair=" + self.server.pairing)
        self.assertNotIn("Set-Cookie", headers, "a query string never pairs: the token belongs in the fragment")
        paired = {**unpaired, "X-ROS-Pair": self.server.pairing}
        status, _, body = self.req("GET", "/services/session", headers={"X-ROS-Pair": self.server.pairing})
        self.assertTrue(json.loads(body)["result"]["paired"])
        status, _, body = self.req("POST", "/services/human-prepare", packet, paired)
        self.assertEqual(status, 200, body)
        self.assertEqual(self.req("GET", "/", headers={"X-ROS-CSRF": "\u00e9"})[0], 200, "non-ASCII headers are refused, never a crash")

    def test_a_page_or_script_an_agent_writes_into_a_bundle_never_runs_as_the_portal(self):
        folder = Path(self.rec.root) / "bundles" / self.bundle
        (folder / "planted.html").write_text("<script src='planted.js'></script>", encoding="utf-8")
        (folder / "planted.js").write_text("fetch('/services/human-commit')", encoding="utf-8")
        for name in ("planted.html", "planted.js"):
            status, headers, _ = self.req("GET", f"/media/bundles/{self.bundle}/{name}")
            self.assertEqual(status, 200)
            self.assertTrue(headers["Content-Type"].startswith("text/plain"), name)
            self.assertIn("sandbox", headers.get("Content-Security-Policy", ""))

    def test_no_request_makes_the_server_open_a_network_share(self):
        for path in ("/static///evil.example/s/x.css", "/static/%5c%5cevil.example%5cs%5cx", "/workspace///evil/s/a.js",
                     "/static/C:/Windows/win.ini", "/media/bundles%5c..%5cevents.jsonl"):
            self.assertEqual(self.req("GET", path)[0], 404, path)
        status, _, body = self.req("GET", "/api/migrate_check?vault=%5C%5Cevil%5Cs")
        self.assertEqual(status, 400); self.assertIn(b"network share", body)

    def test_another_site_may_link_to_the_portal_but_not_fetch_from_it(self):
        cross = {"Sec-Fetch-Site": "cross-site"}
        self.assertEqual(self.req("GET", "/", headers=cross)[0], 200, "a link from elsewhere opens the page")
        for path in ("/api/status", "/services/catalog", "/events", f"/media/bundles/{self.bundle}/plan.json", "/services/session"):
            self.assertEqual(self.req("GET", path, headers=cross)[0], 403, path)
        self.assertEqual(self.req("GET", "/source-media?source=%22x%22", headers=cross)[0], 403, "the person's source media")
        self.assertIn("frame-ancestors 'self'", self.req("GET", "/")[1].get("Content-Security-Policy", ""))

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


    def test_model_check_is_explicit_bounded_and_sends_no_record_content(self):
        before = len(self.rec.events())
        headers = {"X-ROS": "1", "Sec-Fetch-Site": "same-origin"}
        with patch.object(serve, "_engine", return_value={"ok": True, "text": "READY", "model": "codex:gpt-6.1-sol"}) as engine:
            status, _, body = self.req("POST", "/services/model-check", {"model": "codex:gpt-6.1-sol", "effort": "low"}, headers)
            self.assertEqual(status, 200)
            result = json.loads(body)["result"]
            self.assertEqual((result["model"], result["effort"], result["text"]), ("codex:gpt-6.1-sol", "low", "READY"))
            request = engine.call_args.args[0]
            self.assertEqual(request["messages"], [{"role": "user", "content": "Reply exactly READY."}])
            self.assertEqual(request["effort"], "low")
            self.assertNotIn("record", request)
            self.assertNotIn(str(self.rec.root), json.dumps(request))
            engine.reset_mock()
            self.assertEqual(self.req("POST", "/services/model-check", {"model": "codex:gpt-6.1-sol", "effort": "invalid"}, headers)[0], 400)
            self.assertEqual(self.req("POST", "/services/model-check", {"model": "codex:gpt-6.1-sol"}, {"X-ROS": "1"})[0], 403)
            engine.assert_not_called()
        self.assertEqual(len(self.rec.events()), before)

    def test_preserved_drawing_reference_is_an_inert_confined_download(self):
        from ros import handouts
        made = handouts.create(self.rec, "lecture", ["capability:variance"], "Drawing Reference", "drawing-reference")
        figures = handouts.folder(self.rec, made["handout"]) / "figures"
        figures.mkdir(exist_ok=True)
        source = '{"type":"excalidraw","elements":[]}'
        (figures / "sketch.excalidraw").write_text(source, encoding="utf-8")
        status, headers, data = self.req("GET", "/media/handouts/drawing-reference/figures/sketch.excalidraw")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/octet-stream")
        self.assertEqual(headers["Content-Disposition"], 'attachment; filename="drawing.excalidraw"')
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(data.decode(), source)
        self.assertEqual(self.req("GET", "/media/handouts/drawing-reference/figures/../../events.excalidraw")[0], 404)


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


class SelectedRecordEventsTests(unittest.TestCase):
    """Real SSE frames retain record isolation without occupying the API lock."""

    def setUp(self):
        from ros.store import Record
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.rec = Record(Path(self.tmp.name) / "projects" / "default")
        self.other = Record(Path(self.tmp.name) / "projects" / "other")
        for rec in (self.rec, self.other):
            rec.put_node("concept:one", "concept", title="One")
            self.addCleanup(rec.close)
        self.server = serve.start(self.rec, 0)
        self.port = self.server.server_address[1]
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def stream(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", path)
        response = conn.getresponse()
        self.addCleanup(response.close)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/event-stream")
        self.assertIsNone(response.getheader("Access-Control-Allow-Origin"))
        return response

    def frame(self, response):
        lines = []
        while True:
            line = response.readline()
            self.assertTrue(line, "SSE stream ended before a complete frame")
            if line == b"\n":
                return b"".join(lines)
            lines.append(line)

    def request(self, path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", path, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.getheader("Content-Type"), response.read()
        finally:
            conn.close()

    def change(self, response):
        for _ in range(5):
            if self.frame(response).startswith(b"event: change\n"):
                return
        self.fail("record change did not arrive")

    def test_a_stream_also_reports_changes_in_the_records_its_map_spans(self):
        # Knowledge (default) links the project (other): an agent writing in the project changes Knowledge's map.
        from ros import api
        self.addCleanup(api.release)  # linking keeps Knowledge open in the cache; release it before the folder goes
        api.call("link", self.rec, user_wide=True)
        api.call("link", self.other, project="project:other")
        default = self.stream("/events")
        self.assertTrue(self.frame(default).startswith(b"event: change\n"))
        self.other.put_node("claim:new", "claim", title="Written by an agent in the project")
        self.change(default)
        self.other.append("decision", "claim:new", {"outcome": "revise", "rationale": "r"}, actor="person")
        self.change(default)

    def test_default_and_selected_streams_watch_only_their_own_record(self):
        default = self.stream("/events")
        selected = self.stream("/events?record=%22other%22")
        self.assertTrue(self.frame(default).startswith(b"event: change\n"))
        self.assertTrue(self.frame(selected).startswith(b"event: change\n"))
        self.rec.append("test.change", "concept:one", {})
        self.change(default)
        for _ in range(3):
            self.assertEqual(self.frame(selected), b": keep-alive\n")
        # An API call completes while both streams are live, and opens the pooled index.
        self.assertEqual(self.request("/api/workspace_entity?record=other&subject=concept%3Aone")[0], 200)
        pooled = self.server.pool.get("other")
        self.assertIsNotNone(pooled._db)
        self.other.put_node("concept:two", "concept", title="Two")
        self.change(selected)
        self.other.append("test.change", "concept:two", {})
        self.change(selected)
        self.other.put_edge("concept:one", "requires", "concept:two")
        self.change(selected)
        default.close()
        selected.close()
        self.server.shutdown()
        self.server.server_close()
        self.assertIsNone(pooled._db)
        self.assertEqual(self.server.pool.all(), [self.rec])

    def test_plain_record_names_and_invalid_names_before_stream_headers(self):
        selected = self.stream("/events?record=other")
        self.assertTrue(self.frame(selected).startswith(b"event: change\n"))
        for name in ("missing", "..%2F..", "%22..%5C..%22", "%5B%22other%22%5D"):
            status, ctype, body = self.request("/events?record=" + name)
            self.assertEqual(status, 400)
            self.assertIn("application/json", ctype)
            self.assertIn("no record", json.loads(body)["error"])
        self.assertEqual(self.request("/events?record=other", {"Host": "evil.example:80"})[0], 403)
