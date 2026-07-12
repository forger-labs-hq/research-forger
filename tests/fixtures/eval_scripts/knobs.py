"""Fixture evaluator with deterministic knobs read from src/algo.py.

Baseline (no src/algo.py): f1 = 0.80, p95_latency_ms = 100.
A variant patch creates src/algo.py setting IMPROVEMENT / LATENCY.
`--quick` marks the screening subset (same deterministic numbers).
"""

import json
import pathlib
import sys

improvement = 0
latency = 100.0
algo = pathlib.Path("src/algo.py")
if algo.is_file():
    namespace: dict = {}
    exec(algo.read_text(encoding="utf-8"), namespace)  # noqa: S102 — fixture only
    improvement = namespace.get("IMPROVEMENT", 0)
    latency = namespace.get("LATENCY", 100.0)

result = {
    "schema_version": 1,
    "primary_metric": {"name": "f1", "value": round(0.80 + improvement * 0.01, 4)},
    "secondary_metrics": {"p95_latency_ms": float(latency)},
}
pathlib.Path("artifacts").mkdir(exist_ok=True)
pathlib.Path("artifacts/results.json").write_text(json.dumps(result), encoding="utf-8")
print("quick subset" if "--quick" in sys.argv else "full evaluation")
