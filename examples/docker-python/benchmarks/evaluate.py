"""Benchmark: sentiment F1 + deterministic latency proxy.

Writes the machine-readable result ResearchForge's contract expects:

    artifacts/results.json
    {"schema_version": 1,
     "primary_metric": {"name": "f1", "value": ...},
     "secondary_metrics": {"p95_latency_ms": ...}}

`--quick` evaluates the screening subset (the first 10 samples).
"""

import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.classifier import cost_units, predict  # noqa: E402

MS_PER_UNIT = 12.0

# (text, label) — fixed dataset; the first 10 rows are the screening subset.
DATASET = [
    ("great service and fast shipping", "pos"),
    ("the food was excellent", "pos"),
    ("I love this product", "pos"),
    ("Good value for the price", "pos"),
    ("Excellent build quality!", "pos"),
    ("really nice experience overall", "pos"),
    ("not bad at all, actually solid", "pos"),
    ("Love the design and the finish.", "pos"),
    ("good stuff, would buy again", "pos"),
    ("the support team was great to work with", "pos"),
    ("terrible customer support", "neg"),
    ("the quality is poor", "neg"),
    ("I hate the new update", "neg"),
    ("awful packaging, arrived broken", "neg"),
    ("bad experience from start to finish", "neg"),
    ("Poor documentation and confusing setup", "neg"),
    ("the app is slow and buggy", "neg"),
    ("Terrible! Would not recommend.", "neg"),
    ("not good, honestly quite disappointing", "neg"),
    ("hate how it crashes constantly", "neg"),
]


def f1_for_pos(samples: list[tuple[str, str]]) -> float:
    tp = fp = fn = 0
    for text, label in samples:
        predicted = predict(text)
        if predicted == "pos" and label == "pos":
            tp += 1
        elif predicted == "pos" and label == "neg":
            fp += 1
        elif predicted == "neg" and label == "pos":
            fn += 1
    if tp == 0:
        return 0.0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    return 2 * precision * recall / (precision + recall)


def p95_latency_ms(samples: list[tuple[str, str]]) -> float:
    costs = sorted(cost_units(text) for text, _ in samples)
    index = min(math.ceil(0.95 * len(costs)) - 1, len(costs) - 1)
    return costs[index] * MS_PER_UNIT


def main() -> None:
    quick = "--quick" in sys.argv
    samples = DATASET[:10] if quick else DATASET
    result = {
        "schema_version": 1,
        "primary_metric": {"name": "f1", "value": round(f1_for_pos(samples), 4)},
        "secondary_metrics": {"p95_latency_ms": p95_latency_ms(samples)},
    }
    pathlib.Path("artifacts").mkdir(exist_ok=True)
    pathlib.Path("artifacts/results.json").write_text(json.dumps(result), encoding="utf-8")
    print("screening subset" if quick else "full evaluation", "->", result["primary_metric"])


if __name__ == "__main__":
    main()
