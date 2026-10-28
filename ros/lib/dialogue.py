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


REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_MODEL = "codex:gpt-6.1-sol"


def codex_executable():
    """Prefer the installed Windows desktop runtime, then the command on PATH.

    Only the host's fixed application directory is searched, one level deep.
    No executable path or command is accepted from a conversation request.
    """
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        candidates = []
        try:
            for path in (local / "OpenAI" / "Codex" / "bin").glob("*/codex.exe"):
                try:
                    if path.is_file(): candidates.append((path.stat().st_mtime_ns, str(path)))
                except OSError:
                    continue
        except OSError:
            pass
        if candidates:
            return max(candidates)[1]
    return shutil.which("codex") or shutil.which("codex.cmd")


def provider_failure(provider, done):
    """Classify CLI failures without returning any provider diagnostics."""
    diagnostics = (str(done.stderr or "") + "\n" + str(done.stdout or "")).lower()
    if any(marker in diagnostics for marker in ("model_not_found", "model not found", "not supported when using codex with a chatgpt account")):
        return "The selected model is unavailable through this CLI login. Choose another listed model or check model access in your terminal."
    if any(marker in diagnostics for marker in ("unauthorized", "authentication", "not logged in", "login required", "invalid_api_key")):
        return "The provider login needs attention. Sign in through its CLI in your terminal, then try again."
    if any(marker in diagnostics for marker in ("quota", "rate_limit", "rate limit", "usage limit")):
        return "The provider's usage limit was reached. Check your account limit or try again later."
    return f"{provider} could not complete the request (exit {done.returncode}). Check its login and model access in your terminal."


def codex_models():
    """Read public model metadata only; never inspect the CLI's authentication files."""
    models = []
    path = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "models_cache.json"
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        for item in cached.get("models", []):
            if item.get("visibility") == "hide": continue
            name = item.get("slug", "")
            if not isinstance(name, str) or not re.fullmatch(r"gpt-[A-Za-z0-9_.-]{1,90}", name):
                continue
            efforts = [level for level in REASONING_EFFORTS if any(
                isinstance(row, dict) and row.get("effort") == level for row in item.get("supported_reasoning_levels", []))]
            if not efforts:
                continue
            model = {"id": "codex:" + name, "label": str(item.get("display_name") or name)[:100],
                     "provider": "Codex", "reasoning_efforts": efforts}
            existing = next((i for i, row in enumerate(models) if row["id"] == model["id"]), None)
            if existing is None: models.append(model)
            elif model["id"] != DEFAULT_MODEL: models[existing] = model
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return models


def voice_pack():
    """The voice engines shipped inside the installed app (Python, Kokoro, faster-whisper and both models), or None.
    ROS_VOICE_PACK names one explicitly; the frozen backend looks beside itself, at <install>/resources/voice."""
    for candidate in (os.environ.get("ROS_VOICE_PACK"), Path(sys.executable).resolve().parents[2] / "voice" if getattr(sys, "frozen", False) else None):
        if candidate and (Path(candidate) / "python" / "python.exe").is_file():
            return Path(candidate)
    return None


def voice_paths():
    """Where the Kokoro environment, Kokoro model files and Whisper environment are: a path you set, else the bundled pack, else ~/voice-envs."""
    pack, base = voice_pack(), Path.home() / "voice-envs"
    def choose(name, bundled, fallback):
        return Path(os.environ.get(name) or (pack / bundled if pack else fallback))
    return (choose("ROS_KOKORO_ENV", "kokoro", base / "kokoro"), choose("ROS_KOKORO_MODELS", Path("models") / "kokoro", base / "kokoro-models"),
            choose("ROS_WHISPER_ENV", "whisper", base / "whisper"))


def whisper_model():
    """The bundled 'small' model folder when there is one (no download, works offline), else the model's name."""
    pack = voice_pack()
    return str(pack / "models" / "whisper-small") if pack and (pack / "models" / "whisper-small" / "model.bin").is_file() else "small"


def ollama_model(item):
    """Keep the provider's exact model id while making local choices readable."""
    if not isinstance(item, dict): return None
    name = item.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,100}", name): return None
    family, separator, variant = name.partition(":")
    def title(token):
        if token.lower() in ("cpu", "gpu", "fp16", "fp32"): return token.upper()
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?[bk]", token, flags=re.I): return token.upper()
        return token[:1].upper() + token[1:]
    label = " ".join(title(token) for token in re.split(r"[-_/]", family))
    if separator: label += " · " + " ".join(title(token) for token in re.split(r"[-_:/]", variant))
    model = {"id": "ollama:" + name, "label": label, "provider": "Local", "reasoning_efforts": []}
    details = item.get("details")
    if isinstance(details, dict):
        for key in ("parameter_size", "quantization_level"):
            value = details.get(key)
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_. -]{1,40}", value): model[key] = value
    if isinstance(item.get("size"), int) and item["size"] >= 0: model["size_bytes"] = item["size"]
    return model


def catalog():
    models = []
    if codex_executable():
        models += codex_models()
    if shutil.which("claude") or shutil.which("claude.cmd"):
        models += [{"id": "claude:" + name, "label": label, "provider": "Claude", "reasoning_efforts": []} for name, label in
                   (("sonnet", "Claude Sonnet"), ("opus", "Claude Opus"), ("haiku", "Claude Haiku"))]
    ollama = {"available": False, "models": 0, "hint": "Start Ollama on this computer, then refresh models."}
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=0.5) as response:
            local = json.load(response)
        if isinstance(local, dict) and isinstance(local.get("models"), list):
            choices = [choice for item in local["models"][:30] if (choice := ollama_model(item))]
            models += choices
            ollama = {"available": True, "models": len(choices),
                      "hint": "Installed local models are ready to select." if choices else "Ollama is running; no installed models were found."}
    except (OSError, ValueError):
        pass
    kokoro, weights, whisper = voice_paths()
    def installed(env, module):
        return any((env / sub / module).exists() for sub in ("site-packages", "Lib/site-packages", "lib/python3.11/site-packages", "lib/python3.12/site-packages"))
    ready = installed(kokoro, "kokoro_onnx") and (weights / "kokoro-v1.0.onnx").is_file() and (weights / "voices-v1.0.bin").is_file()
    return {"models": models, "default_model": DEFAULT_MODEL, "default_effort": "medium", "ollama": ollama, "voice": {"kokoro": ready, "whisper": installed(whisper, "faster_whisper"),
                                          "language": "en", "label": "Kokoro · Heart / Sky" if ready else "Kokoro needs setup"},
            "notice": "CLI model choices use your existing provider login. Availability is checked by the provider when you send. Local models stay on this computer."}


def reply(request):
    model = request["model"]
    if model == "codex:default": model = DEFAULT_MODEL
    if not re.fullmatch(r"(codex|claude|ollama|compatible):[A-Za-z0-9_.:/-]{1,100}", model):
        raise ValueError("choose a supported provider and model")
    provider, name = model.split(":", 1)
    effort = request.get("effort", "medium")
    if effort not in REASONING_EFFORTS:
        raise ValueError("reasoning effort must be low, medium, high, xhigh or max")
    if provider != "codex" and effort != "medium":
        raise ValueError("reasoning effort selection is currently supported only for Codex models")
    messages = request["messages"][-30:]
    system = ("You are the Research OS learning and research companion. Respond conversationally in Markdown. "
              "Start helping in the first response: a short explanation or one focused question and an actionable next step. "
              "Use only the provided context. Do not call tools, inspect files, run commands or access the network. "
              "Never approve plans, accept claims, waive ownership, claim a background task was completed, or treat confidence as mastery. "
              "Distinguish hypotheses from evidence. Agent preparation tasks may still be pending; state that honestly. "
              "Keep the researcher's immediate goal central. Context: " + json.dumps(request.get("context", {}), ensure_ascii=False))
    if provider == 'compatible' or provider=='ollama' and request.get('endpoint'):
        from . import providers
        import threading
        chunks=[]
        result=providers.local({'model':model,'system':system,'messages':messages,'endpoint':request.get('endpoint'),'steps':0,'deadline':60},chunks.append,None,threading.Event(),lambda _:None)
        return {'text':''.join(chunks),'model':model,'effort':None}
    if provider == "ollama":
        payload = json.dumps({"model": name, "messages": [{"role": "system", "content": system}, *messages], "stream": False}).encode()
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as response:
            return {"text": json.load(response)["message"]["content"], "model": model, "effort": None}
    transcript = system + "\n\n" + "\n\n".join(m["role"].upper() + ": " + m["content"] for m in messages)
    executable = codex_executable() if provider == "codex" else shutil.which(provider) or shutil.which(provider + ".cmd")
    if not executable:
        raise ValueError(f"{provider} is not installed on this computer")
    with tempfile.TemporaryDirectory(prefix="ros-chat-") as folder:
        if provider == "codex":
            output = Path(folder) / "reply.md"
            argv = [executable, "exec", "--ignore-user-config", "--sandbox", "read-only", "--ephemeral", "--skip-git-repo-check",
                    "--disable", "shell_tool", "-c", 'model_reasoning_effort="' + effort + '"', "--color", "never", "--output-last-message", str(output)]
            argv += ["--model", name]
            argv += ["-"]
        else:
            argv = [executable, "--print", "--output-format", "json", "--model", name, "--tools", "", "--strict-mcp-config",
                    "--mcp-config", '{"mcpServers":{}}', "--no-session-persistence", "--setting-sources", ""]
        done = subprocess.run(argv, input=transcript, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=folder,
                              timeout=180, **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        if done.returncode:
            # CLI diagnostics can contain account details. Keep them out of the record and browser.
            raise ValueError(provider_failure(provider, done))
        if provider == "codex":
            text = output.read_text(encoding="utf-8") if output.exists() else done.stdout
        else:
            result = json.loads(done.stdout)
            if result.get("is_error"): raise ValueError("Claude could not complete this request. Check its login or usage limit.")
            text = result.get("result", "")
        if not text.strip(): raise ValueError("The model returned no response. Your message is saved; try again.")
        return {"text": text[:60000], "model": model, "effort": effort if provider == "codex" else None}


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
        result = voice.transcribe(path, [str(whisper)], lang=request.get("language") or None, model=whisper_model())
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
