# ResearchForge

*From papers to proof.*

ResearchForge turns a research question — or an "improve my repository"
goal — into evidence. It finds relevant papers, helps Claude form testable
hypotheses, benchmarks competing implementations against a frozen baseline
in isolated local workspaces, and delivers the strongest supported result
as a clean branch, an engineering report, or a research package.

## How it works

Three parties with strict roles:

| Who | Does what |
|---|---|
| **You** | set the objective; approve the benchmark contract, each experiment plan, and anything that ships |
| **Claude** (in Claude Code) | reads the papers, writes the research landscape, hypotheses, and experiment patches; explains results |
| **The Python engine** | everything that must be trustworthy: search, validation, isolated execution, ranking, shipping — no prompt can bypass it |

No model API key is required — Claude Code *is* the model. Every artifact
Claude writes is schema-validated before it is stored, every experiment
runs in a detached git worktree (your checkout is never touched), and
"validated" is only ever earned by repeated benchmark runs.

## Get started (two minutes)

```bash
# 1. Install (no package published yet — from source):
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. In the repository you want to work on:
researchforge init --claude
```

Then open that repository in Claude Code and say what you want:

> `/researchforge-start` — *"Can uncertainty-aware routing outperform fixed
> routing?"* — or — *"Improve this repo's F1 without hurting latency."*

Claude walks the whole journey from there: it runs the CLI, shows you what
it found, and **asks before anything is approved, executed, or shipped**.
If you ever wonder where things stand, `researchforge status` names the
exact next step.

## See it work first

[docs/demo.md](docs/demo.md) is a ten-minute, fully offline walkthrough
against [examples/simple-python](examples/simple-python/README.md) — a
deterministic benchmark where one variant genuinely improves F1, one is
rejected for violating the latency budget, and one fails (all three stay in
the record). [examples/docker-python](examples/docker-python/README.md) is
the same demo under Docker isolation.

## What you get

- **Explore a research idea** → an arXiv-backed research landscape, graded
  evidence (published claim vs interpretation vs speculation), testable
  hypotheses, and a citation-backed report.
  Details: [docs/research-mode.md](docs/research-mode.md)
- **Improve a repository** → all of the above, plus: an approved benchmark
  contract, a frozen baseline, a screening → full → validation experiment
  funnel over Claude-authored patches, Pareto-ranked results with rejected
  approaches preserved, and shipping — a clean local branch, an opt-in
  draft PR, the engineering report, and a research bundle (BibTeX, paper
  outline, reproducibility data).
  Details: [docs/experiment-mode.md](docs/experiment-mode.md)

Prefer the terminal? Every step is a plain CLI command with `--json`
output — the journeys above are documented command-by-command in those same
docs, and [docs/claude-mode.md](docs/claude-mode.md) explains exactly what
the Claude skills do and cannot do.

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

## More documentation

- [docs/demo.md](docs/demo.md) — the launch demo, step by step
- [docs/claude-mode.md](docs/claude-mode.md) — working from Claude Code
- [docs/research-mode.md](docs/research-mode.md) — the research journey (CLI)
- [docs/experiment-mode.md](docs/experiment-mode.md) — contract, funnel, shipping (CLI)
- [docs/security.md](docs/security.md) — security model and honest limitations
- [docs/architecture.md](docs/architecture.md) — code layout
- [docs/RESEARCHFORGE_PHASED_BUILD_SPEC.md](docs/RESEARCHFORGE_PHASED_BUILD_SPEC.md) — the product spec

## License

Apache-2.0 — see [LICENSE](LICENSE).
