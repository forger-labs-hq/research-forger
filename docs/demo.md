# The launch demo — papers to proof in eight steps

This walkthrough runs the complete improve-repository journey against
[`examples/simple-python`](../examples/simple-python/README.md) — a
deterministic benchmark, so your numbers will match this page. Drive it from
Claude Code (recommended) or the raw CLI; both are shown.

## Setup

```bash
pip install -e ".[dev]"                      # from the ResearchForge checkout
cp -r examples/simple-python /tmp/demo && cd /tmp/demo
git init -b main && git add . && git commit -m "baseline"
researchforge init --claude                  # or plain `researchforge init`
```

In Claude Code, open `/tmp/demo` and say what you want; the skills take it
from there. The CLI equivalents follow each step.

## 1. Enter an objective

> `/researchforge-start` — "Improve this classifier's F1 without exceeding
> the latency budget."

```bash
researchforge project create --mode improve_repository \
  --objective "Improve sentiment classification F1 without exceeding the latency budget"
researchforge repo scan .
```

## 2. Find relevant papers

> `/researchforge-papers` — searches arXiv from the objective + scan.

```bash
researchforge research search
researchforge papers list
```

## 3. Get evidence-backed hypotheses

> `/researchforge-landscape` then `/researchforge-hypotheses` — Claude
> synthesizes within the exported schema; the engine validates every field.

```bash
researchforge research context
# Claude writes landscape.yaml + hypotheses.yaml (docs/research-mode.md)
researchforge research landscape --import .researchforge/synthesis/landscape.yaml
researchforge hypotheses import .researchforge/synthesis/hypotheses.yaml
```

## 4. Confirm the benchmark

> `/researchforge-baseline` — review the contract **yourself**; approval is
> a typed confirmation.

```bash
cp researchforge.example.yaml researchforge.yaml
researchforge contract validate
researchforge contract approve        # typed approval -> immutable contract
researchforge baseline run            # frozen: f1 = 0.75, p95 = 72 ms
```

## 5. Run competing variants

> `/researchforge-plan` then `/researchforge-run` — Claude writes one patch
> per variant against `src/config.py`; protected paths (`benchmarks/`) are
> enforced at import and again at run time.

```bash
researchforge experiment plan hyp-001
# Claude writes plan.yaml + patches/ (docs/experiment-mode.md)
researchforge experiment import .researchforge/experiments/plan.yaml
researchforge experiment approve plan-001
researchforge experiment run plan-001       # screening -> full, one at a time
```

With the three canonical variants: `NORMALIZE = True` reaches **f1 0.90**
inside the budget; `NGRAM_EXPANSION = True` reaches f1 0.82 but **312 ms >
200 ms** — rejected on the hard constraint; a broken import **fails** and is
recorded.

## 6. Failures are preserved

> `/researchforge-results` — losers are findings, not noise.

```bash
researchforge results show run-001    # ranking, the violation, the failure
```

## 7. Validate the winner

> `/researchforge-validate` — repeated full runs earn the word "validated".

```bash
researchforge validate run-001
```

## 8. Clean branch and report

> `/researchforge-ship` — one clean commit on the frozen baseline, local
> only; the report is the full evidence chain.

```bash
researchforge ship branch             # researchforge/<hypothesis-slug>
git log --oneline researchforge/*    # single commit on the baseline
researchforge report build            # .researchforge/reports/engineering-report.md
researchforge paper package           # optional: the research bundle
```

`researchforge status` names the next step at every point. The same demo
runs in Docker isolation via
[`examples/docker-python`](../examples/docker-python/README.md).
