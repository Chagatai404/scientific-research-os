"""Disposable real-content workspace fixture and loopback server; no personal vault or runner."""
from pathlib import Path
import json
import os
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["ROS_NO_VAULT"] = "1"
from ros import api, handouts, serve
from support_ros_demo import build


if os.environ.get("ROS_WORKSPACE_FAKE") == "1":
    def fake_engine(request, timeout=200):
        if request["action"] == "catalog":
            return {"ok": True, "models": [{"id": "codex:gpt-6.1-sol", "label": "GPT-6.1 Sol", "provider": "Fixture", "reasoning_efforts": ["low", "medium", "high", "xhigh", "max"]}, {"id": "claude:sonnet", "label": "Claude Sonnet", "provider": "Fixture", "reasoning_efforts": []}],
                    "default_model": "codex:gpt-6.1-sol", "default_effort": "medium",
                    "voice": {"kokoro": True, "whisper": True, "label": "Fixture voice"}, "notice": "Deterministic test adapter; no provider calls."}
        if request["action"] == "reply":
            if any(message.get("content") == "Reply exactly READY." for message in request.get("messages", [])):
                return {"ok": True, "text": "READY", "model": request["model"]}
            return {"ok": True, "text": "Let’s start with the idea. **Variance measures spread.** What do you already know about the mean?", "model": request["model"]}
        if request["action"] == "transcribe":
            return {"ok": True, "text": "A locally transcribed question"}
        if request["action"] == "speech":
            from support_ros_demo import silent_wav
            path = Path(request["root"]) / "audio" / "fixture.wav"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(silent_wav())
            return {"ok": True, "audio": "audio/fixture.wav", "seconds": 0.3}
        return {"ok": False, "error": "Unsupported fixture operation"}
    serve._engine = fake_engine


def fixture(root):
    os.environ["ROS_HOME"] = str(root)
    # The browser switches to this advertised record; strict record lookup must not invent it.
    from ros.store import Record
    user=Record(root/'projects'/'me')
    if not user.node('project:me'):user.put_node('project:me','project',title='Knowledge')
    user.close()
    if (root / "projects" / "demo" / "events.jsonl").exists():
        from ros.store import Record
        rec = Record(root / "projects" / "demo")
        lessons = [n["id"] for n in rec.nodes(type="lesson") if n["id"].startswith("lesson:")]
        return rec, "handout:variance-reading", lessons[-1]
    rec, bundle = build(root / "projects" / "demo")
    source = handouts.create(rec, "lecture", ["capability:variance"], "Variance, from intuition to evidence", "variance-reading")
    text = '''A sample measures **spread**, with [[Mean|the mean]] as its reference. See [@stats].

1. Find the centre.
   - Preserve the units.
   - Separate the sample from the population.
     1. Check the assumptions.
2. Compare the squared deviations.

:::definition
Variance is the expected squared distance from the mean: $\\sigma^2 = E[(X-\\mu)^2]$.
:::

$$
s^2 = \\frac{1}{n-1} \\sum_{i=1}^{n}(x_i-\\bar{x})^2
$$

![Spread around a centre](figures/spread.svg "A schematic, not experimental evidence")

| Quantity | Expression | Interpretation |
| --- | --- | --- |
| Sample | $s^2$ | An estimate, with sampling uncertainty |
| Population | $\\sigma^2$ | A model quantity |

```python
values = [2, 4, 6]
mean = sum(values) / len(values)
long_filename = "a_very_long_scientific_artifact_filename_that_must_remain_inside_its_code_frame.csv"
```

This is a teaching derivation[^scope].

An explicitly anchored paragraph remains addressable. ^fixture-stable

:::example A preserved legacy title
Work from the recorded assumptions.
=== solution
The worked solution remains collapsed until requested.
:::

[^scope]: It is not an accepted scientific claim.

<script>window.untrustedExecuted = true</script>

[Unsafe link](javascript:alert%281%29)
'''
    handouts.write(rec, source["handout"], "lecture", text, "fixture-author", derivation=True,
                   sources=[{"key": "stats", "text": "Fixture teaching source, section 2. A synthetic example for rendering tests."}])
    handouts.write(rec, source["handout"], "gist", "Understand spread, its units and its limits.", "fixture-author", derivation=True)
    handouts.add_file(rec, source["handout"], "figures/spread.svg", text='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 160"><rect width="600" height="160" fill="#eff6f3"/><path d="M40 110H560 M300 30V130" stroke="#799f93"/><g fill="#24796b"><circle cx="140" cy="100" r="8"/><circle cx="230" cy="75" r="8"/><circle cx="300" cy="45" r="8"/><circle cx="370" cy="75" r="8"/><circle cx="460" cy="100" r="8"/></g></svg>')
    rec.put_edge(source["handout"], "about", "capability:variance", provenance="author")
    started = api.call("start", rec, bundle=bundle)
    rec.put_node("source:legacy", "source", title="A preserved source", text="An immutable imported source.", legacy=True)
    return rec, source["handout"], started["lesson"]


if __name__ == "__main__":
    root = Path(sys.argv[1])
    rec, document, lesson = fixture(root)
    if len(sys.argv) > 2 and sys.argv[2] == "--append-question":
        try:
            print(json.dumps(api.call("ask", rec, lesson=lesson, text=sys.argv[3])), flush=True)
        finally:
            api.release()
            rec.close()
        raise SystemExit(0)
    if len(sys.argv) > 2 and sys.argv[2] == "--seed-due":
        try:
            import ros.store as store
            store.now = lambda: "2026-09-01T10:00:00Z"   # a miss recorded long ago leaves a review due now
            step = api.call("next", rec, lesson=lesson)
            print(json.dumps(api.call("answer", rec, lesson=lesson, item=step["item"], dont_know=True)), flush=True)
        finally:
            api.release()
            rec.close()
        raise SystemExit(0)
    test_vault = root / "test-vault"
    test_vault.mkdir(exist_ok=True)
    server = serve._bind(rec, int(sys.argv[2]) if len(sys.argv) > 2 else 0)
    print(json.dumps({"url": f"http://127.0.0.1:{server.server_address[1]}/", "document": document, "lesson": lesson, "vault": str(test_vault)}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        api.release()
        rec.close()
