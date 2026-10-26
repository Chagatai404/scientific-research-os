"""Deterministic sparse/dense neighbourhood benchmark. No models or personal records."""
from pathlib import Path
import json
import os
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ros import api
from ros.store import Record


def run(size, dense):
    with tempfile.TemporaryDirectory() as folder:
        rec = Record(Path(folder))
        try:
            for i in range(size): rec.put_node(f"concept:{i}", "concept", title=f"Concept {i}")
            if dense:
                for i in range(min(size, 150)):
                    for j in range(i + 1, min(size, i + 24)): rec.put_edge(f"concept:{i}", "supports", f"concept:{j}", provenance="synthetic", verified=False)
            else:
                for i in range(size - 1): rec.put_edge(f"concept:{i}", "requires", f"concept:{i + 1}")
            timings = []
            for _ in range(12):
                start = time.perf_counter()
                data = api.call("workspace_graph", rec, focus="concept:0", depth=3, limit=120)
                timings.append((time.perf_counter() - start) * 1000)
            return {"fixture": "dense" if dense else "sparse", "record_nodes": size, "visible_nodes": len(data["nodes"]),
                    "visible_edges": len(data["edges"]), "bounded": data["bounded"], "first_ms": round(timings[0], 2),
                    "median_ms": round(statistics.median(timings[1:]), 2), "payload_bytes": len(json.dumps(data).encode())}
        finally:
            rec.close()


if __name__ == "__main__":
    os.environ["ROS_NO_VAULT"] = "1"
    print(json.dumps([run(1200, False), run(1200, True)], indent=2))
