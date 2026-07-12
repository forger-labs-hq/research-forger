# ResearchForge

*From papers to proof.*

ResearchForge is an open-source, Claude-first research and experimentation
CLI. It studies relevant literature, maps promising methods to your idea or
repository, creates testable hypotheses, and benchmarks competing
implementations against a controlled baseline in local, isolated workspaces.

**Status:** Phase 1A — research intelligence MVP. Project creation,
repository scanning, arXiv discovery, research landscape + hypotheses (via
the Claude synthesis handshake), and a research-only Markdown report. No
experiment execution yet (that's Phase 1B/1C). See
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

For an existing repository, use `--mode improve_repository` and run
`researchforge repo scan` after project creation. `researchforge status`
always shows the next step. Every command supports `--json`.

## License

Apache-2.0 — see [LICENSE](LICENSE).
