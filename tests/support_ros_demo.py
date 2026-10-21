"""A small, complete record for portal tests: two capabilities, a ready bundle with audio and visuals, and items.

Run directly to build one: ``python tests/support_ros_demo.py <record-folder>`` prints the bundle id.
"""
from __future__ import annotations

import io
from pathlib import Path
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import prepare, research  # noqa: E402
from ros.store import Record  # noqa: E402

GOAL, BASE = "capability:variance", "capability:mean"
SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 80"><rect x="10" y="30" width="180" height="4" '
       'fill="#555"/><circle cx="100" cy="32" r="8" fill="#1f5f8b"/></svg>')


def silent_wav(seconds: float = 0.3) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buf.getvalue()


def build(root: Path) -> tuple[Record, str]:
    rec = Record(root)
    rec.put_node(BASE, "capability", title="Mean", retention_target="core")
    rec.put_node(GOAL, "capability", title="Variance", retention_target="core")
    rec.put_edge(GOAL, "requires", BASE)
    rec.put_edge(GOAL, "part-of", "course:stat-demo")
    rec.put_edge(BASE, "part-of", "course:stat-demo")
    probe = [rec.put_item({"kind": "numeric", "prompt": f"Level {d}: $Var({d}X)$ when $Var(X)=1$?", "answer": d * d,
                           "difficulty": d, "concepts": [GOAL], "explanation": f"$Var(aX)=a^2Var(X)$, so {d * d}.",
                           "hints": ["Square the factor."]}) for d in (1, 2, 3)]
    check = rec.put_item({"kind": "choice", "prompt": "Which is $Var(X+5)$?", "options": ["$Var(X)$", "$Var(X)+5$"],
                          "answer": 0, "concepts": [GOAL], "difficulty": 4,
                          "option_feedback": [None, "A shift moves every value equally; spread is unchanged."]})
    mean_check = rec.put_item({"kind": "numeric", "prompt": "Mean of 2 and 4?", "answer": 3, "concepts": [BASE],
                               "difficulty": 1})
    close = rec.put_item({"kind": "free", "prompt": "Explain variance in your own words.",
                          "rubric": {"criteria": ["average squared distance from the mean"]}, "concepts": [GOAL]})
    transfer = rec.put_item({"kind": "free", "prompt": "Why can two portfolios with equal means differ in risk?",
                             "concepts": [GOAL]})
    bundle = "variance-1"
    prepare.create(rec, bundle, "Variance", GOAL)
    d = prepare.bundle_dir(rec, bundle)
    for rel, data in (("audio/mean.wav", silent_wav()), ("audio/var-1.wav", silent_wav()),
                      ("audio/var-2.wav", silent_wav()), ("visuals/mean.svg", SVG.encode()),
                      ("visuals/var.svg", SVG.encode()), ("visuals/mean.result.md", b"Looked at: one point on a line."),
                      ("visuals/var.result.md", b"Looked at: spread around the mean.")):
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_bytes(data)
    plan = prepare.load_plan(rec, bundle)
    plan["nodes"] = [
        {"id": BASE, "title": "Mean", "requires": [], "dynamic": False,
         "segments": [{"id": "mean", "role": "establish", "text": "The mean is the balance point of the values.",
                       "audio": "audio/mean.wav", "claims": [{"text": "definition", "derivation": True}]}],
         "visuals": [{"path": "visuals/mean.svg", "result": "visuals/mean.result.md", "elements": 2}],
         "items": {"check": [mean_check]}},
        {"id": GOAL, "title": "Variance", "requires": [BASE], "dynamic": False,
         "segments": [{"id": "var-1", "role": "motivate", "text": "Two classes can share a mean and still differ.",
                       "audio": "audio/var-1.wav"},
                      {"id": "var-2", "role": "establish",
                       "text": "Variance is the average squared distance from the mean: $Var(X)=E[(X-\\mu)^2]$.",
                       "audio": "audio/var-2.wav", "visual": "visuals/var.svg",
                       "claims": [{"text": "definition", "derivation": True}]}],
         "visuals": [{"path": "visuals/var.svg", "result": "visuals/var.result.md", "elements": 2}],
         "items": {"check": [check]}}]
    plan["items"] = {"probe": probe, "close": [close], "transfer": [transfer], "review": []}
    prepare.save_plan(rec, bundle, plan)
    rec.put_node("experiment:EXP-1", "experiment", title="Fit the width ratio at 50 GeV", status="planned",
                 authorization="awaiting")
    research.add_claim(rec, "width", "Proton showers are about 10% wider than pion showers.", "stat-demo",
                       author="agent:builder", assurance="internal")
    research.record_verdict(rec, "claim:width", "numbers", "PASS", "agent:auditor")
    research.record_verdict(rec, "claim:width", "result-claim", "PASS", "agent:auditor")
    manifest = prepare.check(rec, bundle)
    if not manifest["ready"]:
        raise SystemExit("demo bundle is not ready: " + "; ".join(manifest["missing"]))
    return rec, bundle


if __name__ == "__main__":
    record, bundle_id = build(Path(sys.argv[1]))
    record.close()
    print(bundle_id)
