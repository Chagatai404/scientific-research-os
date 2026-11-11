"""The experiment workbench's engine: a per-workspace Python environment and one approved experiment run, with live output.

Run by the operations worker for the operation kind ``experiment`` (``desktop_operations.run``), or on its own as
``python -m ros.lib.environments`` with ``{"kind": "experiment", "packet": {...}}`` (or the bare packet) as JSON on stdin. The
packet is built by ``ros.workbench`` from an approved plan revision; this engine only carries it out:

- ``prepare``: a venv under the project folder (``.ros-env/<key>``), with ``uv`` when present and ``pip`` otherwise; the packages,
  index and git repositories are exactly the packet's (the plan's), with every ambient configuration route switched off (pip and uv
  configuration files and variables, git's global and system configuration), so nothing is downloaded from anywhere the plan does
  not name. The installed distributions are written to ``requirements.lock`` and ``lock.json``.
- ``run``: the command in the project folder with an allow-listed environment (``credentials.child_env`` on top), a time limit,
  an output limit and a cooperative stop (a ``STOP`` file in the run folder, written by the person's ``experiment_stop``).
- ``capabilities``: what this computer can run (Python, venv, uv, pip, git, the scientific-tool packs, Manim), each observed.

Everything the person should see is appended while it happens to ``<run_dir>/stream.jsonl`` (one JSON object per line: ``start``,
``out``/``err`` output, ``note``, ``files``, ``exit``), which the record's ``experiment_follow`` tails with a byte cursor. The run
folder is under the record, never the project folder, so the experiment's own code cannot rewrite what is shown. This is trusted
code execution with the person's own rights, not an operating-system sandbox. Standard library only.
"""
from __future__ import annotations

import codecs
import difflib
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import threading
import time

from . import credentials

STREAM = "stream.jsonl"
STOP = "STOP"
MAX_OUTPUT = 2 * 1024 * 1024
CHUNK = 8192
SKIP = {".git", ".ros-env", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache", ".tox", ".ipynb_checkpoints"}
MAX_FILES = 5000
HASH_LIMIT = 32 * 1024 * 1024
DIFF_LIMIT = 64 * 1024
DIFF_FILES = 60
# The variables an experiment's process gets from this computer (names compare case-insensitively); everything else, credentials
# and PYTHONPATH included, is left out. Geant4's dataset variables (G4*) and ROOT's location are kept so those packs work.
KEEP = {"PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA",
        "LANG", "LC_ALL", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "ROOTSYS", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH",
        "UV_CACHE_DIR"}
FREEZE = ("import importlib.metadata as m, json, platform, sys\n"
          "rows = sorted({(d.metadata['Name'] or '', d.version) for d in m.distributions() if d.metadata['Name']}, key=lambda r: r[0].lower())\n"
          "print(json.dumps({'python': platform.python_version(), 'executable': sys.executable, 'packages': rows}))\n")
NO_WINDOW = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)} \
    if os.name == "nt" else {"start_new_session": True}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class Stream:
    """The run's live log: JSON lines appended and flushed as they happen, output bounded by ``limit`` bytes. A process's small
    writes are gathered into whole lines (or 4 KB, or a quarter of a second) so the log reads as the program printed it."""

    def __init__(self, run_dir: Path, limit: int = MAX_OUTPUT):
        run_dir.mkdir(parents=True, exist_ok=True)
        self.path, self.limit, self.lock, self.write_lock = run_dir / STREAM, limit, threading.Lock(), threading.Lock()
        self.bytes, self.over = 0, False
        self.digests = {"out": hashlib.sha256(), "err": hashlib.sha256()}
        self.sizes = {"out": 0, "err": 0}
        self.pending, self.since = {"out": "", "err": ""}, {"out": 0.0, "err": 0.0}
        self.tail = []

    def emit(self, kind: str, **data) -> None:
        line = json.dumps({"k": kind, "at": round(time.time(), 3), **data}, ensure_ascii=False) + "\n"
        with self.write_lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(line)
            stream.flush()

    def output(self, name: str, text: str) -> None:
        """Take what a process wrote; hashes and sizes count every byte, the log keeps at most ``limit`` of them."""
        if not text:
            return
        ready = ""
        with self.lock:
            raw = text.encode("utf-8")
            self.digests[name].update(raw)
            self.sizes[name] += len(raw)
            if not self.pending[name]:
                self.since[name] = time.monotonic()
            self.pending[name] += text
            buffered = self.pending[name]
            cut = buffered.rfind("\n") + 1
            if len(buffered) >= 4096:
                cut = len(buffered)
            if cut:
                ready, self.pending[name] = buffered[:cut], buffered[cut:]
                self.since[name] = time.monotonic()
        self._write(name, ready)

    def flush(self, age: float = 0.0) -> None:
        """Write what has waited at least ``age`` seconds without a line end (a progress bar, a prompt)."""
        for name in ("out", "err"):
            with self.lock:
                if not self.pending[name] or time.monotonic() - self.since[name] < age:
                    continue
                ready, self.pending[name] = self.pending[name], ""
            self._write(name, ready)

    def _write(self, name: str, text: str) -> None:
        if not text:
            return
        with self.lock:
            if self.over:
                return
            raw = text.encode("utf-8")
            room = self.limit - self.bytes
            if len(raw) > room:
                text, self.over = raw[:max(0, room)].decode("utf-8", "ignore"), True
            self.bytes += len(text.encode("utf-8"))
            self.tail.append(text)
            if len(self.tail) > 400:
                del self.tail[:200]
            over = self.over
        if text:
            self.emit(name, t=text.replace("\r\n", "\n"))
        if over:
            self.emit("note", t=f"Output limit of {self.limit} bytes reached; the process is stopped.")

    def summary(self) -> dict:
        return {name: {"bytes": self.sizes[name], "sha256": self.digests[name].hexdigest()} for name in ("out", "err")}


def _reader(pipe, name: str, stream: Stream) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    try:
        while True:
            block = pipe.read1(CHUNK) if hasattr(pipe, "read1") else pipe.read(CHUNK)
            if not block:
                break
            stream.output(name, decoder.decode(block))
        stream.output(name, decoder.decode(b"", final=True))
    except (OSError, ValueError):
        pass


def kill_tree(process: subprocess.Popen) -> None:
    """Stop a process and everything it started."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/pid", str(process.pid), "/T", "/F"], capture_output=True, timeout=20, **NO_WINDOW)
        else:
            import signal
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        process.kill()
    except OSError:
        pass


def supervise(argv: list[str], cwd: Path, env: dict, stream: Stream, deadline: float, stop: Path) -> dict:
    """Run one process to its end, the deadline, the output limit or the person's stop, streaming what it writes."""
    started = time.monotonic()
    if stop.exists():
        return {"code": None, "stopped": True, "timed_out": False, "output_limit": False, "seconds": 0.0}
    process = subprocess.Popen(argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               **NO_WINDOW)
    readers = [threading.Thread(target=_reader, args=(process.stdout, "out", stream), daemon=True),
               threading.Thread(target=_reader, args=(process.stderr, "err", stream), daemon=True)]
    for reader in readers:
        reader.start()
    stopped = timed_out = limited = False
    while process.poll() is None:
        if stop.exists():
            stopped = True
        elif time.monotonic() > deadline:
            timed_out = True
        elif stream.over:
            limited = True
        if stopped or timed_out or limited:
            kill_tree(process)
            break
        stream.flush(0.25)
        time.sleep(0.05)
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        kill_tree(process)
    for reader in readers:
        reader.join(timeout=5)
    stream.flush()
    for pipe in (process.stdout, process.stderr):
        try:
            pipe.close()
        except OSError:
            pass
    return {"code": process.returncode, "stopped": stopped, "timed_out": timed_out, "output_limit": limited,
            "seconds": round(time.monotonic() - started, 3)}


# ---- the environment a process gets ----------------------------------------------------------------------------------
def base_environment(extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k.upper() in KEEP or k.upper().startswith("G4")}
    env = credentials.child_env(env, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", PYTHONNOUSERSITE="1",
                                PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INPUT="1",
                                UV_NO_CONFIG="1", UV_PYTHON_DOWNLOADS="never", GIT_TERMINAL_PROMPT="0",
                                GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_ALLOW_PROTOCOL="https:file")
    env.update(extra or {})
    return env


def venv_bin(env_dir: Path) -> Path:
    return env_dir / ("Scripts" if os.name == "nt" else "bin")


def venv_python(env_dir: Path) -> Path:
    return venv_bin(env_dir) / ("python.exe" if os.name == "nt" else "python")


def base_python(requested: str | None = None) -> str:
    """The interpreter a new environment is made from. A frozen backend's own executable is not a Python."""
    if requested:
        return requested
    if not getattr(sys, "frozen", False):
        return sys.executable
    found = shutil.which("python") or shutil.which("python3") or shutil.which("py")
    if not found:
        raise ValueError("Install Python on this computer to run experiments: none was found on PATH.")
    return found


def _executable(name: str) -> str | None:
    path = shutil.which(name)
    if path and Path(path).suffix.lower() in {".bat", ".cmd", ".ps1"}:
        return None  # Windows would run a batch file through a shell
    return path


def _quick(argv: list[str], timeout: int = 20, env: dict | None = None) -> tuple[int | None, str]:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                              stdin=subprocess.DEVNULL, env=env if env is not None else base_environment(), **NO_WINDOW)
        return done.returncode, (done.stdout or done.stderr).strip()[:400]
    except (OSError, subprocess.SubprocessError) as exc:
        return None, type(exc).__name__


# ---- files: what a run created or changed --------------------------------------------------------------------------
def snapshot(folder: Path, keep_text: bool = False) -> dict:
    """Each file under the project folder (skipping version control, environments and caches) with its hash; bounded."""
    files, texts, truncated = {}, {}, False
    for root, dirs, names in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not os.path.islink(os.path.join(root, d)))
        for name in sorted(names):
            path = Path(root) / name
            if path.is_symlink() or not path.is_file():
                continue
            if len(files) >= MAX_FILES:
                truncated = True
                break
            rel = path.relative_to(folder).as_posix()
            try:
                stat = path.stat()
                if stat.st_size > HASH_LIMIT:
                    files[rel] = {"bytes": stat.st_size, "sha256": None, "signature": f"{stat.st_size}:{stat.st_mtime_ns}"}
                    continue
                raw = path.read_bytes()
            except OSError:
                continue
            files[rel] = {"bytes": len(raw), "sha256": sha256(raw)}
            if keep_text and len(raw) <= DIFF_LIMIT and b"\0" not in raw and len(texts) < 2000:
                texts[rel] = raw
        if truncated:
            break
    return {"files": files, "texts": texts, "truncated": truncated}


def _text(raw: bytes | None) -> list[str] | None:
    if raw is None or b"\0" in raw or len(raw) > DIFF_LIMIT:
        return None
    return raw.decode("utf-8", "replace").splitlines(keepends=True)


def changes(folder: Path, before: dict, after: dict) -> list[dict]:
    rows, diffs = [], 0
    old, new = before["files"], after["files"]
    for rel in sorted(set(old) | set(new)):
        a, b = old.get(rel), new.get(rel)
        if a == b:
            continue
        state = "created" if a is None else "deleted" if b is None else "changed"
        row = {"path": rel, "state": state, "sha256": (b or {}).get("sha256"), "previous_sha256": (a or {}).get("sha256"),
               "bytes": (b or {}).get("bytes")}
        if state != "deleted" and diffs < DIFF_FILES:
            try:
                current = _text((folder / rel).read_bytes()) if (b or {}).get("bytes", 0) <= DIFF_LIMIT else None
            except OSError:
                current = None
            previous = _text(before["texts"].get(rel)) if state == "changed" else []
            if current is not None and previous is not None:
                diff = "".join(difflib.unified_diff(previous, current, "a/" + rel, "b/" + rel, n=2))
                row["diff"] = diff[:12000] + ("\n[diff truncated]\n" if len(diff) > 12000 else "")
                diffs += 1
        rows.append(row)
    return rows[:500]


def hashes(folder: Path, paths: list[str]) -> list[dict]:
    out = []
    for rel in paths[:200]:
        path = (folder / rel)
        try:
            real = path.resolve(strict=True)
            if not real.is_relative_to(folder.resolve()) or not real.is_file():
                continue
            out.append({"path": rel, "sha256": file_sha256(real), "bytes": real.stat().st_size})
        except (OSError, ValueError):
            out.append({"path": rel, "sha256": None, "missing": True})
    return out


# ---- actions -------------------------------------------------------------------------------------------------------
def _folder(packet: dict) -> Path:
    folder = Path(packet["folder"]).resolve(strict=True)
    if not folder.is_dir():
        raise ValueError("The project folder is missing.")
    return folder


def _deadline(packet: dict) -> float:
    return time.monotonic() + max(1, min(int(packet.get("timeout", 600)), 7200))


def _step(argv, cwd, env, stream, deadline, stop, what):
    stream.emit("note", t=what, argv=[str(a) for a in argv])
    status = supervise(argv, cwd, env, stream, deadline, stop)
    if status["stopped"]:
        raise _Stopped(what)
    if status["timed_out"] or status["output_limit"]:
        raise ValueError(f"{what}: {'time limit' if status['timed_out'] else 'output limit'} reached")
    if status["code"] != 0:
        raise ValueError(f"{what} failed (exit code {status['code']})")
    return status


class _Stopped(Exception):
    pass


def _index_args(index_url: str | None) -> list[str]:
    if not index_url:
        return ["--no-index"]
    if index_url.startswith("file://"):
        from urllib.request import url2pathname
        from urllib.parse import urlparse
        return ["--no-index", "--find-links", url2pathname(urlparse(index_url).path)]
    return ["--index-url", index_url]


def freeze(python: Path) -> dict:
    code, text = _quick([str(python), "-I", "-c", FREEZE], timeout=60)
    if code != 0:
        raise ValueError("Could not read the environment's installed packages: " + text[:200])
    data = json.loads(text)
    return {"python": data["python"], "packages": [{"name": n, "version": v} for n, v in data["packages"]]}


def prepare(packet: dict) -> dict:
    folder, run_dir = _folder(packet), Path(packet["run_dir"])
    stream, stop, deadline = Stream(run_dir), run_dir / STOP, _deadline(packet)
    env_dir = Path(packet["env_dir"])
    if not env_dir.resolve().is_relative_to(folder):
        raise ValueError("The environment folder must be inside the project folder.")
    packages, repos, index_url = list(packet.get("packages") or []), list(packet.get("repos") or []), packet.get("index_url")
    stream.emit("start", action="prepare", cwd=str(folder), env_dir=str(env_dir), packages=packages, index_url=index_url,
                repos=repos, spec=packet.get("spec"))
    lock_file = env_dir / "lock.json"
    try:
        if lock_file.is_file() and venv_python(env_dir).is_file():
            lock = json.loads(lock_file.read_text(encoding="utf-8"))
            if lock.get("spec") == packet.get("spec"):
                stream.emit("note", t="The environment for this plan already exists; it is reused as locked.")
                stream.emit("exit", code=0, state="completed", reused=True)
                return {"ok": True, "action": "prepare", "env": dict(lock, reused=True), "output": stream.summary()}
        env = base_environment()
        work = env_dir.parent
        work.mkdir(parents=True, exist_ok=True)
        ignore = work / ".gitignore"
        if not ignore.exists():
            ignore.write_text("# Research OS experiment environments: not part of the project's history\n*\n", encoding="utf-8")
        python = base_python(packet.get("base_python"))
        uv = None if packet.get("installer") == "pip" else _executable("uv")
        if uv:
            _step([uv, "venv", "--no-config", "--python", python, str(env_dir)], folder, env, stream, deadline, stop,
                  "Creating the environment with uv")
        else:
            _step([python, "-m", "venv", *([] if packages else ["--without-pip"]), str(env_dir)], folder, env, stream, deadline, stop,
                  "Creating the environment with venv")
        vpy = venv_python(env_dir)
        cloned = []
        git = _executable("git") if repos else None
        if repos and not git:
            raise ValueError("The plan lists a git repository, but git is not installed on this computer.")
        hooks = env_dir / "no-hooks"
        hooks.mkdir(exist_ok=True)
        for repo in repos:
            dest = (folder / repo["into"]).resolve()
            if not dest.is_relative_to(folder):
                raise ValueError("A repository must be cloned inside the project folder.")
            safe = [git, "-c", "core.hooksPath=" + str(hooks), "-c", "core.fsmonitor=false", "-c", "advice.detachedHead=false"]
            if not (dest / ".git").exists():
                if dest.exists() and any(dest.iterdir()):
                    raise ValueError(f"{repo['into']} already exists and is not a clone; choose another folder in the plan.")
                _step([*safe, "clone", "--no-checkout", "--", repo["url"], str(dest)], folder, env, stream, deadline, stop,
                      f"Cloning {repo['url']}")
            _step([*safe, "-C", str(dest), "checkout", "--detach", repo["commit"]], folder, env, stream, deadline, stop,
                  f"Checking out the pinned commit {repo['commit'][:12]}")
            code, head = _quick([*safe, "-C", str(dest), "rev-parse", "HEAD"], env=env)
            if code != 0 or head.strip() != repo["commit"]:
                raise ValueError(f"{repo['url']} is not at the pinned commit after checkout.")
            cloned.append({"url": repo["url"], "commit": head.strip(), "into": repo["into"], "install": bool(repo.get("install"))})
            if repo.get("install"):
                local = ["--no-deps", "--no-build-isolation", "--no-index", str(dest)]
                argv = ([uv, "pip", "install", "--no-config", "--python", str(vpy), *local] if uv else
                        [str(vpy), "-m", "pip", "install", "--isolated", "--no-cache-dir", *local])
                _step(argv, folder, env, stream, deadline, stop, f"Installing {repo['into']} (no further downloads)")
        if packages:
            argv = ([uv, "pip", "install", "--no-config", "--python", str(vpy), *_index_args(index_url), *packages] if uv else
                    [str(vpy), "-m", "pip", "install", "--isolated", "--no-cache-dir", *_index_args(index_url), *packages])
            _step(argv, folder, env, stream, deadline, stop, "Installing the plan's packages from " + (index_url or "no index"))
        state = freeze(vpy)
        names = {p["name"].lower().replace("_", "-") for p in state["packages"]}
        missing = [p for p in packages if re.split(r"[\[=<>!~ ;]", p, maxsplit=1)[0].lower().replace("_", "-") not in names]
        if missing:
            raise ValueError("Installed, but these packages are not in the environment: " + ", ".join(missing))
        lock_text = "".join(f"{p['name']}=={p['version']}\n" for p in state["packages"])
        (env_dir / "requirements.lock").write_text(lock_text, encoding="utf-8")
        lock = {"spec": packet.get("spec"), "env_dir": str(env_dir), "python": str(vpy), "python_version": state["python"],
                "installer": "uv" if uv else "pip", "index_url": index_url, "requested": packages, "packages": state["packages"],
                "repos": cloned, "lock_file": str(env_dir / "requirements.lock"), "lock_sha256": sha256(lock_text.encode("utf-8"))}
        lock_file.write_text(json.dumps(lock, indent=1), encoding="utf-8")
        stream.emit("note", t=f"Environment ready: Python {state['python']}, {len(state['packages'])} package(s) locked.")
        stream.emit("exit", code=0, state="completed")
        return {"ok": True, "action": "prepare", "env": lock, "output": stream.summary()}
    except _Stopped as exc:
        stream.emit("exit", code=None, state="stopped", detail=f"Stopped by the person during: {exc}")
        return {"ok": False, "interrupted": True, "stopped": True, "action": "prepare", "error": "Stopped by the person.",
                "output": stream.summary()}
    except (OSError, ValueError, KeyError) as exc:
        stream.emit("exit", code=None, state="failed", detail=str(exc)[:500])
        return {"ok": False, "action": "prepare", "error": str(exc)[:1000], "output": stream.summary()}


def _command(argv: list[str], folder: Path, env_dir: Path) -> list[str]:
    head = argv[0]
    if head == "python":
        return [str(venv_python(env_dir)), *argv[1:]]
    if head in ("manim", "manimgl"):
        found = [p for p in (venv_bin(env_dir) / (head + ".exe"), venv_bin(env_dir) / head) if p.is_file()]
        if not found:
            raise ValueError(f"{head} is not installed in this environment; list it in the plan's packages.")
        return [str(found[0]), *argv[1:]]
    target = (folder / head).resolve(strict=True)
    if not target.is_relative_to(folder) or not target.is_file() or target.suffix.lower() in {".bat", ".cmd", ".ps1"}:
        raise ValueError("A program must be a file inside the project folder (no shell scripts).")
    return [str(target), *argv[1:]]


def run_experiment(packet: dict) -> dict:
    folder, run_dir = _folder(packet), Path(packet["run_dir"])
    limit = max(1024, min(int(packet.get("max_output", MAX_OUTPUT)), 8 * MAX_OUTPUT))
    stream, stop, deadline = Stream(run_dir, limit), run_dir / STOP, _deadline(packet)
    env_dir = Path(packet["env_dir"])
    try:
        cwd = (folder / (packet.get("cwd") or ".")).resolve(strict=True)
        if not cwd.is_relative_to(folder) or not cwd.is_dir():
            raise ValueError("The working folder must be inside the project folder.")
        if not venv_python(env_dir).is_file():
            raise ValueError("The environment is missing; prepare it again.")
        argv = _command(list(packet["argv"]), folder, env_dir)
        scripts = list(dict.fromkeys([*packet.get("code", []), *[a for a in packet["argv"][1:2] if a.endswith(".py")]]))
        code = hashes(folder, [(cwd / s).resolve().relative_to(folder).as_posix() if (cwd / s).resolve().is_relative_to(folder) else s
                               for s in scripts])
        inputs = []
        for row in packet.get("inputs", [])[:8]:
            raw = Path(row["snapshot"]).read_bytes()
            if sha256(raw) != row["revision"]:
                raise ValueError("An input snapshot does not match its recorded revision.")
            target = env_dir / "inputs" / row["revision"][:16] / row["name"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            inputs.append({k: v for k, v in row.items() if k != "snapshot"} | {"path": str(target)})
        env = base_environment({"VIRTUAL_ENV": str(env_dir), "MPLBACKEND": "Agg", "ROS_INPUTS_DIR": str(env_dir / "inputs")})
        env["PATH"] = str(venv_bin(env_dir)) + os.pathsep + env.get("PATH", "")
        before = snapshot(folder, keep_text=True)
        stream.emit("start", action="run", argv=list(packet["argv"]), resolved=argv, cwd=str(cwd),
                    environment={"python": str(venv_python(env_dir)), "variables": sorted(env), "lock_sha256": packet.get("lock_sha256")},
                    code=code, inputs=inputs, parameters=packet.get("parameters") or {})
        status = supervise(argv, cwd, env, stream, deadline, stop)
        files = changes(folder, before, snapshot(folder))
        stream.emit("files", files=[{k: v for k, v in f.items() if k != "diff"} for f in files], truncated=before["truncated"])
        state = ("stopped" if status["stopped"] else "timed_out" if status["timed_out"] else "output_limit" if status["output_limit"]
                 else "completed" if status["code"] == 0 else "failed")
        stream.emit("exit", code=status["code"], state=state, seconds=status["seconds"])
        return {"ok": state == "completed", "interrupted": state == "stopped", "action": "run", "state": state,
                "exit_code": status["code"], "seconds": status["seconds"], "argv": list(packet["argv"]), "cwd": str(cwd),
                "code": code, "inputs": inputs, "files": files, "output": stream.summary(),
                "tail": "".join(stream.tail)[-20000:], "platform": platform.platform(),
                **({"error": {"stopped": "Stopped by the person.", "timed_out": "Time limit reached.",
                              "output_limit": "Output limit reached.", "failed": f"Exited with code {status['code']}."}[state]}
                   if state != "completed" else {})}
    except (OSError, ValueError, KeyError) as exc:
        stream.emit("exit", code=None, state="failed", detail=str(exc)[:500])
        return {"ok": False, "action": "run", "state": "failed", "error": str(exc)[:1000], "output": stream.summary()}


def capabilities(packet: dict | None = None) -> dict:
    """What this computer can run for an experiment, each row observed now: ``tested`` (found, with its version) or
    ``unavailable`` (looked for and not found), with the reason."""
    rows = []

    def row(name, kind, ok, version=None, detail=""):
        rows.append({"name": name, "kind": kind, "status": "tested" if ok else "unavailable", "version": version, "detail": detail})

    try:
        python = base_python((packet or {}).get("base_python"))
        code, text = _quick([python, "-I", "-c", "import platform, venv; print(platform.python_version())"])
        row("python", "runtime", code == 0, text if code == 0 else None, python if code == 0 else "no usable Python: " + text)
        row("venv", "runtime", code == 0, None, "per-workspace environments")
        pip_code, pip_text = _quick([python, "-I", "-m", "pip", "--version"])
        row("pip", "installer", pip_code == 0, pip_text.split()[1] if pip_code == 0 and len(pip_text.split()) > 1 else None, pip_text[:120])
    except ValueError as exc:
        row("python", "runtime", False, None, str(exc))
    for name, flag in (("uv", "--version"), ("git", "--version")):
        exe = _executable(name)
        code, text = _quick([exe, flag]) if exe else (None, "not on PATH")
        row(name, "installer" if name == "uv" else "tool", code == 0, (text.split() or [None])[-1] if code == 0 else None, text[:120])
    try:
        from . import scientific_tools
        for pid, profile in scientific_tools.load_profiles().items():
            probe = scientific_tools.probe(profile)
            seen = {k: v.get("observed_version") for k, v in {**probe["packages"], **probe["commands"]}.items() if v.get("available")}
            row(pid, "pack", probe["available"], ", ".join(f"{k} {v}" for k, v in seen.items()) or None,
                profile["name"] + (" (packages checked in the app's Python)" if profile["python"]["packages"] else ""))
    except Exception as exc:  # a broken pack directory is a reported problem, never a failed listing
        row("scientific-tools", "pack", False, None, f"{type(exc).__name__}: {str(exc)[:200]}")
    try:
        from . import animate
        caps = animate.capabilities()
        usable = [b for b in caps.get("backends") or [] if isinstance(b, dict)]
        row("manim", "tool", bool(usable), ", ".join(f"{b.get('backend')} {b.get('version') or ''}".strip() for b in usable)[:120] or None,
            "animations (ros.lib.animate)" + ("" if usable else ": " + "; ".join(caps.get("notes") or [])[:200]))
    except Exception as exc:
        row("manim", "tool", False, None, f"{type(exc).__name__}: {str(exc)[:200]}")
    return {"ok": True, "action": "capabilities", "rows": rows, "platform": platform.platform(),
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def run(packet: dict) -> dict:
    """Dispatch by the packet's explicit action; an unknown action is an error, never a fall-through to running code."""
    action = packet.get("action")
    if action == "prepare":
        return prepare(packet)
    if action == "run":
        return run_experiment(packet)
    if action == "capabilities":
        return capabilities(packet)
    raise ValueError("Unknown experiment action.")


def main() -> int:
    for _s in (sys.stdin, sys.stdout):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8")
    try:
        request = json.load(sys.stdin)
        packet = request["packet"] if isinstance(request, dict) and request.get("kind") == "experiment" else request
        result = run(packet)
    except Exception as exc:
        result = {"ok": False, "error": str(exc)[:1500]}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
