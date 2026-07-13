# ResearchForge

*From papers to proof.*

ResearchForge is an open-source, Claude-first research and experimentation
CLI. It studies relevant literature, maps promising methods to your idea or
repository, creates testable hypotheses, and benchmarks competing
implementations against a controlled baseline in local, isolated workspaces.

**Status:** Phase 1D — the full local pipeline. Research intelligence
(arXiv discovery, landscape, hypotheses), the experiment contract +
baseline, a controlled experiment funnel (screening → full → validation)
over Claude-authored patch variants, and shipping: a clean branch
reconstructed from the baseline, an opt-in draft PR, the engineering
report, and a research package. Claude Code skills arrive in Phase 1E. See
[docs/RESEARCHFORGE_PHASED_BUILD_SPEC.md](docs/RESEARCHFORGE_PHASED_BUILD_SPEC.md)
for the roadmap, [docs/architecture.md](docs/architecture.md) for code
layout, and [docs/research-mode.md](docs/research-mode.md) for the research
workflow.

## Install

No package is published yet. Install from source in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Quickstart — explore a research idea

```bash
researchforge doctor
researchforge project create --mode explore_research_idea \
  --objective "Can uncertainty-aware routing outperform fixed routing?"
researchforge research search          # arXiv: fetch → dedup → rank → store
researchforge papers list
researchforge research context         # export bundle for Claude synthesis
# Claude writes landscape.yaml + hypotheses.yaml (see docs/research-mode.md)
researchforge research landscape --import .researchforge/synthesis/landscape.yaml
researchforge hypotheses import .researchforge/synthesis/hypotheses.yaml
researchforge report build             # citation-backed Markdown report
```

## Quickstart — improve a repository

```bash
researchforge project create --mode improve_repository --objective "Improve F1 ..."
researchforge repo scan
researchforge contract generate     # edit researchforge.yaml, then:
researchforge contract approve      # typed approval -> immutable contract
researchforge baseline run          # frozen baseline in an isolated worktree
researchforge experiment plan hyp-001
# Claude writes plan.yaml + patches/ (see docs/experiment-mode.md)
researchforge experiment import .researchforge/experiments/plan.yaml
researchforge experiment approve plan-001
researchforge experiment run plan-001    # screening -> full, one at a time
researchforge results show run-001       # ranking, Pareto trade-offs, rejections
researchforge validate run-001           # repeated runs -> validated
researchforge ship branch                # clean local branch (never pushed)
researchforge report build               # engineering report
researchforge ship pr                    # opt-in: push + DRAFT PR via gh
researchforge paper package              # research bundle (BibTeX, outline, data)
```

`researchforge status` always shows the next step. Every command supports
`--json`. See [docs/experiment-mode.md](docs/experiment-mode.md) for the
isolation and safety guarantees.

## License

Apache-2.0 — see [LICENSE](LICENSE).
