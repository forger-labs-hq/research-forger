# simple-python — the ResearchForge launch demo target

A deliberately small sentiment classifier with a deterministic benchmark, so
the full ResearchForge journey runs offline in minutes and produces the same
numbers on every machine. See [docs/demo.md](../../docs/demo.md) for the
walkthrough.

- `src/classifier.py` — keyword classifier with two real weaknesses.
- `src/config.py` — the tunable settings experiments patch.
- `benchmarks/evaluate.py` — writes `artifacts/results.json` with `f1` and a
  deterministic `p95_latency_ms` proxy; `--quick` is the screening subset.
- `researchforge.example.yaml` — a ready-to-review contract (copy to
  `researchforge.yaml`); latency budget: `p95_latency_ms <= 200`.

Known behaviors (why it demos well):

| Change in `src/config.py` | f1 | p95_latency_ms | Outcome |
|---|---|---|---|
| baseline | 0.75 | 72 | frozen reference |
| `NORMALIZE = True` | 0.90 | 72 | the winner |
| `NGRAM_EXPANSION = True` | 0.82 | 312 | better f1, **violates the constraint** |
| a broken import | — | — | recorded failure |

Try it:

```bash
cp -r examples/simple-python /tmp/demo && cd /tmp/demo
git init -b main && git add . && git commit -m "baseline"
researchforge init --claude    # then drive it from Claude Code, or:
cp researchforge.example.yaml researchforge.yaml
```
