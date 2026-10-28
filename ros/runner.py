"""The timer and the worker behind "nobody has to start anything". A long-lived process (``ros serve``, ``ros mcp``, or
``ros go`` in the foreground) runs a ``Runner``: one thread asks every open record to ``reconcile`` (``tick`` every few
seconds, ``scan`` every half minute, ``daily`` once a day), another runs the local jobs that reconcile queued (a PDF build,
a voice render) as subprocesses **outside** the registry lock, so the portal stays responsive while they run.

There is no pid file and no lease: a job is claimed through the record like any task, a crashed runner's claim lapses
after the usual thirty minutes, and an output is named by the hash of its input, so two runners doing the same job is
wasteful and harmless.
"""
from __future__ import annotations

from collections import deque
from datetime import date
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from typing import Callable

from . import api
from .store import Record

TICK = 5.0
SCAN = 30.0


class Runner:
    def __init__(self, records: Callable[[], list[Record]], tick: float = TICK, scan: float = SCAN):
        self.records, self.tick, self.scan = records, tick, scan
        self.by = f"runner:{socket.gethostname()}:{os.getpid()}"
        self.errors: deque = deque(maxlen=20)
        self._stop = threading.Event()
        self._work = threading.Event()
        self._threads: list[threading.Thread] = []
        self._last_scan = 0.0
        self._day = None

    # ---- one step of each, usable on their own (tests, ``ros go``) --------------------------------------------------
    def tick_once(self, scan: bool = False, daily: bool = False) -> dict:
        out = {}
        for rec in self.records():
            for mode in ("tick", *(("scan",) if scan else ()), *(("daily",) if daily else ())):
                try:
                    r = api.call("reconcile", rec, mode=mode)
                except Exception as exc:
                    self.errors.append(f"{rec.root.name} {mode}: {type(exc).__name__}: {exc}")
                    continue
                if r.get("ran"):
                    out.setdefault(rec.root.name, {})[mode] = r["ran"]
                for name, err in (r.get("errors") or {}).items():
                    self.errors.append(f"{rec.root.name} {name}: {err}")
        return out

    def run_jobs_once(self, limit: int = 1) -> list[dict]:
        done = []
        for rec in self.records():
            try:
                waiting = api.call("jobs", rec)
            except Exception as exc:
                self.errors.append(f"{rec.root.name} jobs: {type(exc).__name__}: {exc}")
                continue
            for job in waiting:
                if len(done) >= limit:
                    return done
                try:
                    api.call("claim", rec, task=job["id"], by=self.by)
                except (ValueError, KeyError):
                    continue  # someone else has it
                result = self._run(job)
                try:
                    api.call("job_done", rec, task=job["id"], result=result, by=self.by)
                except Exception as exc:
                    self.errors.append(f"{rec.root.name} job_done: {type(exc).__name__}: {exc}")
                done.append({"record": rec.root.name, "job": job["id"], "brief": job.get("brief"), **result})
        return done

    @staticmethod
    def _run(job: dict, own=None) -> dict:
        env = dict(os.environ)  # a job runs this program's own modules, so they must be importable from anywhere
        root = job.get("pythonpath") or str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
        started = time.monotonic()
        try:
            argv = job['argv']
            if getattr(sys, 'frozen', False) and argv[:2] == [sys.executable, '-m']:
                modes = {'ros.lib.pdf': 'pdf', 'ros': 'cli'}
                if argv[2] not in modes: return {'ok': False, 'code': None, 'output': 'Frozen worker is unavailable for this optional engine', 'seconds': 0}
                argv = [sys.executable, '--worker', modes[argv[2]], *argv[3:]]
            if own:
                p=subprocess.Popen(argv,cwd=job['cwd'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,stdin=subprocess.DEVNULL,
                                   **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}))
                own(p)
                stdout,stderr=p.communicate(timeout=job['timeout']);p.stdout.close();p.stderr.close()
                p=type('Result',(),{'returncode':p.returncode,'stdout':stdout,'stderr':stderr})()
            else:
                p = subprocess.run(argv, cwd=job["cwd"], env=env, capture_output=True, text=True,
                                   timeout=job["timeout"], stdin=subprocess.DEVNULL)
            return {"ok": p.returncode == 0, "code": p.returncode, "output": (p.stdout + p.stderr)[-1500:],
                    "seconds": round(time.monotonic() - started, 1)}
        except subprocess.TimeoutExpired:
            return {"ok": False, "code": None, "output": "timed out", "seconds": round(time.monotonic() - started, 1)}
        except OSError as exc:
            return {"ok": False, "code": None, "output": str(exc), "seconds": 0}

    def until_idle(self, max_seconds: float = 600, on_progress: Callable[[dict], None] | None = None) -> dict:
        """Tick and run jobs in the foreground until nothing is left to do (what ``ros go`` does without a server)."""
        started, total = time.monotonic(), {"ticks": 0, "jobs": 0}
        self.tick_once(scan=True, daily=True)
        while time.monotonic() - started < max_seconds:
            ran = self.run_jobs_once(limit=5)
            total["jobs"] += len(ran)
            for r in ran:
                if on_progress:
                    on_progress(r)
            quiet = self.tick_once()
            total["ticks"] += 1
            if not ran and not quiet:
                break
        return total

    # ---- the threads --------------------------------------------------------------------------------------------------
    def start(self) -> "Runner":
        if self._threads:
            return self
        self._threads = [threading.Thread(target=self._ticker, daemon=True, name="ros-ticker"),
                         threading.Thread(target=self._worker, daemon=True, name="ros-worker")]
        for t in self._threads:
            t.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._work.set()
        for t in self._threads:
            t.join(timeout=5)
        self._threads = []

    def _ticker(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            scan = now - self._last_scan >= self.scan
            if scan:
                self._last_scan = now
            today = date.today()
            daily = self._day != today
            self._day = today
            self.tick_once(scan=scan, daily=daily)
            self._work.set()
            self._stop.wait(self.tick)

    def _worker(self) -> None:
        while not self._stop.is_set():
            self._work.wait(timeout=self.tick * 4)
            self._work.clear()
            if self._stop.is_set():
                break
            while not self._stop.is_set() and self.run_jobs_once(limit=1):
                pass
