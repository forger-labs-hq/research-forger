"""Fixture evaluator: writes a valid spec-shaped results.json deterministically."""

import json
import pathlib

pathlib.Path("artifacts").mkdir(exist_ok=True)
result = {
    "schema_version": 1,
    "primary_metric": {"name": "f1", "value": 0.84},
    "secondary_metrics": {"p95_latency_ms": 120.5},
    "sample_count": 100,
    "seed": 42,
    "metadata": {"dataset_version": "fixture-v1"},
}
pathlib.Path("artifacts/results.json").write_text(json.dumps(result), encoding="utf-8")
print("evaluation complete")
