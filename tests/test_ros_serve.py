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
