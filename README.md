# ResearchForge

*From papers to proof.*

ResearchForge is an open-source, Claude-first research and experimentation
CLI. It studies relevant literature, maps promising methods to your idea or
repository, creates testable hypotheses, and benchmarks competing
implementations against a controlled baseline in local, isolated workspaces.

**Status:** open-source beta (Phase 1 complete). The full local pipeline —
research intelligence (arXiv discovery, landscape, hypotheses), the
experiment contract + baseline, a controlled experiment funnel (screening →
full → validation) over Claude-authored patch variants, shipping (clean
branch, opt-in draft PR, engineering report, research package) — drivable
end-to-end from Claude Code. See
[docs/RESEARCHFORGE_PHASED_BUILD_SPEC.md](docs/RESEARCHFORGE_PHASED_BUILD_SPEC.md)
for the roadmap, [docs/architecture.md](docs/architecture.md) for code
layout, and [docs/security.md](docs/security.md) for the security model and
honest limitations.

## Install

No package is published yet. Install from source in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Use from Claude Code (recommended)

```bash
researchforge init --claude     # initialize + install project skills
```

Then, in Claude Code, start with `/researchforge-start` — the skills walk
both journeys below, calling the CLI with `--json` and asking you before
every approval, run, and ship step. See
[docs/claude-mode.md](docs/claude-mode.md) for details and the safety model
(skills are UX; all enforcement is in the Python engine).

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

## Try the demo

[docs/demo.md](docs/demo.md) runs the full journey against
[examples/simple-python](examples/simple-python/README.md) — a deterministic
benchmark where one variant genuinely improves F1, one violates the latency
constraint, and one fails (and all three are preserved in the record).
[examples/docker-python](examples/docker-python/README.md) is the same demo
under Docker isolation.

## Supported repositories (beta)

The improve-repository journey currently expects:

- a **git** repository with **user-owned or trusted code** (isolation is
  local, not a hostile-code sandbox — [docs/security.md](docs/security.md));
- a **Python 3.11+** single project or single target service;
- an existing **Dockerfile** or simple Python dependency metadata
  (`requirements.txt` / `pyproject.toml`);
- a **machine-readable benchmark** (a command that writes JSON metrics)
  with **bounded runtime**;
- no production infrastructure required.

The explore-research-idea journey works anywhere. Repositories outside this
matrix are reported honestly by `researchforge repo scan` rather than
half-supported.

## Beta feedback

This is a narrow-but-complete beta — reports shape what gets built next.
Use the issue templates ([bug](.github/ISSUE_TEMPLATE/bug_report.yml),
[setup failure](.github/ISSUE_TEMPLATE/setup_failure.yml),
[beta feedback](.github/ISSUE_TEMPLATE/beta_feedback.yml)). Optionally,
`researchforge analytics enable` records **local-only** coarse events —
nothing is transmitted — and `researchforge analytics show` computes the
beta metrics you can choose to include in a report.

## License

Apache-2.0 — see [LICENSE](LICENSE).
