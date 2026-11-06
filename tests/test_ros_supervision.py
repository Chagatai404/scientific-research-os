"""Supervision and diagnostics: a log file with masked secrets, background problems shown, child stderr kept for failures only."""
from __future__ import annotations

import http.client
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ros import api, desktop, runtime, serve  # noqa: E402
from ros.lib import connectivity, providers  # noqa: E402
import support_ros_demo as demo  # noqa: E402


class LogFile(unittest.TestCase):
    def test_backend_log_is_written_with_secrets_masked(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        saved = (threading.excepthook, sys.excepthook, logging.getLogger("ros").level, dict(os.environ))
        def restore():
            threading.excepthook, sys.excepthook = saved[0], saved[1]; logging.getLogger("ros").setLevel(saved[2])
            os.environ.clear(); os.environ.update(saved[3])
        self.addCleanup(restore)
        path = desktop.configure_logging(tmp.name)
        handler = next(h for h in logging.getLogger("ros").handlers if getattr(h, "_ros_backend", False))
        self.addCleanup(lambda: (logging.getLogger("ros").removeHandler(handler), handler.close()))
        log = logging.getLogger("ros")
        log.info("starting with api_key=sk-live-abc123 and Authorization: Bearer tok-999")
        try: raise RuntimeError("password=hunter2 failed")
        except RuntimeError: log.exception("a failure")
        handler.flush()
        text = path.read_text(encoding="utf-8")
        self.assertEqual(path, Path(tmp.name) / "backend.log"); self.assertEqual(handler.maxBytes, 2 << 20); self.assertEqual(handler.backupCount, 5)
        self.assertIn("starting with", text); self.assertIn("a failure", text); self.assertIn("RuntimeError", text)
        for secret in ("sk-live-abc123", "tok-999", "hunter2"): self.assertNotIn(secret, text)
        self.assertIn("[hidden]", text)

    def test_an_uncaught_thread_exception_is_logged_and_listed(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        saved = (threading.excepthook, sys.excepthook, dict(os.environ));
        def restore():
            threading.excepthook, sys.excepthook = saved[0], saved[1]; os.environ.clear(); os.environ.update(saved[2])
        self.addCleanup(restore)
        path = desktop.configure_logging(tmp.name)
        handler = next(h for h in logging.getLogger("ros").handlers if getattr(h, "_ros_backend", False))
        self.addCleanup(lambda: (logging.getLogger("ros").removeHandler(handler), handler.close()))
        with patch.dict(runtime.HEALTH, {}, clear=True):
            def boom(): raise KeyError("lost")
            thread = threading.Thread(target=boom, name="ros-test-thread"); thread.start(); thread.join()
            handler.flush()
            self.assertIn("ros-test-thread", path.read_text(encoding="utf-8"))
            self.assertEqual(runtime.health()["problems"][0]["component"], "process")


class Health(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1", "ROS_LOG_DIR": str(Path(self.tmp.name) / "logs")}); env.start(); self.addCleanup(env.stop)
        health = patch.dict(runtime.HEALTH, {}, clear=True); health.start(); self.addCleanup(health.stop)
        self.rec, _ = demo.build(Path(self.tmp.name) / "rec"); self.addCleanup(self.rec.close); self.addCleanup(api.release)

    def get(self, path):
        server = serve.start(self.rec, 0); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        port = server.server_address[1]
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", path, headers={"Host": f"127.0.0.1:{port}"}); r = c.getresponse(); body = json.loads(r.read()); c.close()
        return r.status, body

    def test_a_dispatcher_error_is_listed_masked_with_the_log_folder(self):
        dispatcher = runtime.Dispatcher(self.rec, interval=0, first=0)
        class Stop:
            n = 0
            def wait(self, seconds): Stop.n += 1; return Stop.n > 1
            def set(self): pass
        dispatcher.stop_event = Stop()
        with patch.object(runtime, "dispatch_once", side_effect=RuntimeError("model call failed, token=sekrit123")), self.assertLogs("ros", "ERROR"):
            dispatcher.loop()
        status, body = self.get("/services/health")
        self.assertEqual(status, 200)
        problems = body["result"]["problems"]
        self.assertEqual(problems[0]["component"], "agents"); self.assertIn("model call failed", problems[0]["error"])
        self.assertNotIn("sekrit123", json.dumps(body)); self.assertTrue(problems[0]["at"])
        self.assertEqual(body["result"]["log"], str(Path(self.tmp.name) / "logs"))

    def test_health_is_empty_when_nothing_went_wrong(self):
        self.assertEqual(self.get("/services/health")[1]["result"]["problems"], [])

    def test_connectivity_endpoint_uses_the_connector(self):
        connectivity.reset(); self.addCleanup(connectivity.reset)
        def down(address, timeout=None): raise OSError("down")
        with patch.object(connectivity, "CONNECT", down):
            status, body = self.get("/services/connectivity")
        self.assertEqual(status, 200); self.assertFalse(body["result"]["online"]); self.assertIn("checked_at", body["result"])

    def test_health_keeps_only_the_last_few_per_component(self):
        for n in range(30): runtime.report("jobs", f"failure {n}", log=False)
        rows = [p for p in runtime.health()["problems"] if p["component"] == "jobs"]
        self.assertEqual(len(rows), runtime.HEALTH_KEEP); self.assertIn("failure 29", [r["error"] for r in rows])


class ChildStderr(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        health = patch.dict(runtime.HEALTH, {}, clear=True); health.start(); self.addCleanup(health.stop)
        self.rec, _ = demo.build(Path(self.tmp.name) / "rec"); self.addCleanup(self.rec.close); self.addCleanup(api.release)

    def test_a_failed_engine_explains_itself_with_a_masked_stderr_tail(self):
        script = "import sys; sys.stderr.write('Traceback...\\nValueError: bad input api_key=abc999zzz\\n'); sys.exit(3)"
        with self.assertLogs("ros", "ERROR") as logs:
            result = runtime.engine_process(self.rec, "k1", [sys.executable, "-c", script], {"x": 1}, 20)
        self.assertFalse(result["ok"])
        self.assertIn("Engine failed or timed out", result["error"]); self.assertIn("ValueError: bad input", result["error"]); self.assertNotIn("abc999zzz", result["error"])
        self.assertNotIn("abc999zzz", "\n".join(logs.output)); self.assertIn("[hidden]", result["error"])
        self.assertEqual(runtime.health()["problems"][0]["component"], "engine")

    def test_a_successful_engine_never_shows_its_stderr(self):
        script = "import sys; sys.stderr.write('a harmless warning\\n'); print('{\"ok\": true}')"
        result = runtime.engine_process(self.rec, "k2", [sys.executable, "-c", script], {"x": 1}, 20)
        self.assertEqual(result, {"ok": True})

    def test_a_slow_engine_times_out_with_what_it_said(self):
        script = "import sys,time; sys.stderr.write('waiting for the licence server\\n'); sys.stderr.flush(); time.sleep(30)"
        with self.assertLogs("ros", "ERROR"):
            result = runtime.engine_process(self.rec, "k3", [sys.executable, "-c", script], {}, 1)
        self.assertIn("waiting for the licence server", result["error"])

    def test_stderr_tail_is_bounded_and_masked(self):
        import io
        tail = providers.StderrTail(io.StringIO("".join(f"line {n}\n" for n in range(500)) + "Authorization: Bearer abc.def.ghi\n"))
        import time; time.sleep(.1)
        self.assertLessEqual(len(tail.rows), 60); excerpt = tail.excerpt()
        self.assertIn("line 499", excerpt); self.assertNotIn("abc.def.ghi", excerpt)


if __name__ == "__main__":
    unittest.main()
