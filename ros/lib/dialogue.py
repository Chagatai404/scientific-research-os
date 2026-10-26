"""Optional conversation/voice adapter. No Research OS imports and no record writes.

Invoked with JSON on stdin by the portal, outside the registry lock. No shell,
no credentials in outputs, no implicit model requests during discovery.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request


def voice_paths():
    base = Path.home() / "voice-envs"
    return (Path(os.environ.get("ROS_KOKORO_ENV") or base / "kokoro"),
            Path(os.environ.get("ROS_KOKORO_MODELS") or base / "kokoro-models"),
            Path(os.environ.get("ROS_WHISPER_ENV") or base / "whisper"))


def catalog():
    models = []
    if shutil.which("codex") or shutil.which("codex.cmd"):
        models += [{"id": "codex:" + name, "label": label, "provider": "Codex"} for name, label in
                   (("default", "Codex · default"), ("gpt-6.1-sol", "GPT-6.1 Sol"), ("gpt-6-luna", "GPT-6 Luna"))]
    if shutil.which("claude") or shutil.which("claude.cmd"):
        models += [{"id": "claude:" + name, "label": label, "provider": "Claude"} for name, label in
                   (("sonnet", "Claude Sonnet"), ("opus", "Claude Opus"), ("haiku", "Claude Haiku"))]
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=0.5) as response:
            local = json.load(response)
        models += [{"id": "ollama:" + m["name"], "label": m["name"], "provider": "Local"} for m in local.get("models", [])[:30]]
    except (OSError, ValueError):
        pass
    kokoro, weights, whisper = voice_paths()
    def installed(env, module):
        return any((env / sub / module).exists() for sub in ("Lib/site-packages", "lib/python3.11/site-packages", "lib/python3.12/site-packages"))
    ready = installed(kokoro, "kokoro_onnx") and (weights / "kokoro-v1.0.onnx").is_file() and (weights / "voices-v1.0.bin").is_file()
    return {"models": models, "voice": {"kokoro": ready, "whisper": installed(whisper, "faster_whisper"),
                                          "language": "en", "label": "Kokoro · Heart / Sky" if ready else "Kokoro needs setup"},
            "notice": "CLI model choices use your existing provider login. Availability is checked by the provider when you send. Local models stay on this computer."}


def reply(request):
    model = request["model"]
    if not re.fullmatch(r"(codex|claude|ollama):[A-Za-z0-9_.:/-]{1,100}", model):
        raise ValueError("choose a supported provider and model")
    provider, name = model.split(":", 1)
    messages = request["messages"][-30:]
    system = ("You are the Research OS learning and research companion. Respond conversationally in Markdown. "
              "Start helping in the first response: a short explanation or one focused question and an actionable next step. "
              "Use only the provided context. Do not call tools, inspect files, run commands or access the network. "
              "Never approve plans, accept claims, waive ownership, claim a background task was completed, or treat confidence as mastery. "
              "Distinguish hypotheses from evidence. Agent preparation tasks may still be pending; state that honestly. "
              "Keep the researcher's immediate goal central. Context: " + json.dumps(request.get("context", {}), ensure_ascii=False))
    if provider == "ollama":
        payload = json.dumps({"model": name, "messages": [{"role": "system", "content": system}, *messages], "stream": False}).encode()
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as response:
            return {"text": json.load(response)["message"]["content"], "model": model}
    transcript = system + "\n\n" + "\n\n".join(m["role"].upper() + ": " + m["content"] for m in messages)
    executable = shutil.which(provider) or shutil.which(provider + ".cmd")
    if not executable:
        raise ValueError(f"{provider} is not installed on this computer")
    with tempfile.TemporaryDirectory(prefix="ros-chat-") as folder:
        if provider == "codex":
            output = Path(folder) / "reply.md"
            argv = [executable, "exec", "--ignore-user-config", "--sandbox", "read-only", "--ephemeral", "--skip-git-repo-check",
                    "--disable", "shell_tool", "-c", 'model_reasoning_effort="medium"', "--color", "never", "--output-last-message", str(output)]
            if name != "default": argv += ["--model", name]
            argv += ["-"]
        else:
            argv = [executable, "--print", "--output-format", "json", "--model", name, "--tools", "", "--strict-mcp-config",
                    "--mcp-config", '{"mcpServers":{}}', "--no-session-persistence", "--setting-sources", ""]
        done = subprocess.run(argv, input=transcript, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=folder,
                              timeout=180, **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        if done.returncode:
            # CLI diagnostics can contain account details. Keep them out of the record and browser.
            raise ValueError(f"{provider} could not complete the request (exit {done.returncode}). Check its login and model access in your terminal.")
        if provider == "codex":
            text = output.read_text(encoding="utf-8") if output.exists() else done.stdout
        else:
            result = json.loads(done.stdout)
            if result.get("is_error"): raise ValueError("Claude could not complete this request. Check its login or usage limit.")
            text = result.get("result", "")
        if not text.strip(): raise ValueError("The model returned no response. Your message is saved; try again.")
        return {"text": text[:60000], "model": model}


def speech(request):
    from . import voice
    kokoro, weights, _ = voice_paths()
    root = Path(request["root"]).resolve()
    text = str(request["text"])[:12000]
    result = voice.speak(root, text, "en", "kokoro", [str(kokoro)], {"model_dir": str(weights)}, directory="audio")
    return {"audio": result["audio"], "seconds": result["seconds"]}


def transcribe(request):
    from . import voice
    _, _, whisper = voice_paths()
    data = base64.b64decode(request["audio"], validate=True)
    if len(data) > 12 << 20: raise ValueError("recording is too large (12 MB maximum)")
    with tempfile.TemporaryDirectory(prefix="ros-dictate-") as folder:
        path = Path(folder) / "recording.webm"
        path.write_bytes(data)
        result = voice.transcribe(path, [str(whisper)], lang=request.get("language") or None)
    return {"text": result.get("text", "")}


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        action = request.get("action", "reply")
        result = {"catalog": lambda _: catalog(), "reply": reply, "speech": speech, "transcribe": transcribe}[action](request)
        print(json.dumps({"ok": True, **result}, ensure_ascii=True))
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else "The local provider did not complete the request. Check its setup and try again."
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=True))
