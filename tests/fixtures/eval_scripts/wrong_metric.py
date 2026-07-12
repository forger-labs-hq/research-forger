"""Fixture evaluator: reports a metric name the contract doesn't expect."""

import json
import pathlib

pathlib.Path("artifacts").mkdir(exist_ok=True)
result = {"schema_version": 1, "primary_metric": {"name": "not_the_metric", "value": 1.0}}
pathlib.Path("artifacts/results.json").write_text(json.dumps(result), encoding="utf-8")
