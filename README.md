# ResearchForge

*From papers to proof.*

ResearchForge turns a research question — or an "improve my repository"
goal — into evidence. It finds relevant papers, helps Claude form testable
hypotheses, benchmarks competing implementations against a frozen baseline
in isolated local workspaces, and delivers the strongest supported result
as a clean branch, an engineering report, or a research package.

Inspired by Andrej Karpathy's
[autoresearch](https://github.com/karpathy/autoresearch), where an agent
autonomously runs training experiments against a fixed benchmark overnight —
ResearchForge generalizes that loop to any repository with a measurable
benchmark, and grounds it in literature: papers → hypotheses → controlled
experiments → a validated, reproducible result.

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

Everything runs on your machine — nothing is uploaded anywhere. "Working on
a repository" just means having it on disk and starting Claude Code from
inside it.

```bash
# 1. Install ResearchForge (no package published yet — from source):
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Go to the repository you want to work on (clone it first if needed)
#    and initialize ResearchForge inside it:
cd path/to/your-repo
researchforge init --claude

# 3. Start Claude Code IN that directory:
claude
```

(Using the desktop app instead? Open that repository folder as the
session's project — a session started from the home screen without a
folder can't see any project's skills.)

Then say what you want:

> `/researchforge-start` — *"Can uncertainty-aware routing outperform fixed
> routing?"* — or — *"Improve this repo's F1 without hurting latency."*

Claude walks the whole journey from there: it runs the CLI, shows you what
it found, and **asks before anything is approved, executed, or shipped**.
If you ever wonder where things stand, `researchforge status` names the
exact next step.

> **Why don't I see `/researchforge-…` in a new session?** Project skills
> load from the directory a session is opened in. Open the session in the
> initialized repository — or run `researchforge claude install --user` once
> to put the skills in `~/.claude/skills/`, where every session sees them.

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
  approaches preserved, a local HTML **dashboard** charting every experiment
  against the baseline (`researchforge dashboard --open`), and shipping — a
  clean local branch, an opt-in draft PR, the engineering report, and a
  research bundle (BibTeX, paper outline, reproducibility data).
  Details: [docs/experiment-mode.md](docs/experiment-mode.md)

## Use without Claude (plain CLI)

Everything works from the terminal alone — the only difference is that the
synthesis steps Claude would do (the landscape, hypotheses, and experiment
patches) become files **you** write, against schemas the CLI exports and
validates. `researchforge status` names the next command at every point.

**Research a question:**

```bash
researchforge project create --mode explore_research_idea --objective "..."
researchforge research search        # arXiv: fetch -> dedup -> rank -> store
researchforge research context       # exports context.json with the schemas
# you write .researchforge/synthesis/landscape.yaml + hypotheses.yaml
researchforge research landscape --import .researchforge/synthesis/landscape.yaml
researchforge hypotheses import .researchforge/synthesis/hypotheses.yaml
researchforge report build           # citation-backed report
```

**Improve a repository:**

```bash
researchforge project create --mode improve_repository --objective "..."
researchforge repo scan
researchforge contract generate      # edit researchforge.yaml, then:
researchforge contract approve       # typed approval -> frozen evaluation
researchforge baseline run
researchforge experiment plan hyp-001   # exports the plan schema + contract
# you write .researchforge/experiments/plan.yaml + patches/*.patch
researchforge experiment import .researchforge/experiments/plan.yaml
researchforge experiment approve plan-001
researchforge experiment run plan-001   # screening -> full funnel
researchforge validate run-001          # repeated runs -> validated
researchforge ship branch && researchforge report build
```

Full walkthroughs: [docs/research-mode.md](docs/research-mode.md) and
[docs/experiment-mode.md](docs/experiment-mode.md).
[docs/claude-mode.md](docs/claude-mode.md) explains exactly what the Claude
skills do and cannot do.

**Start over:** all state is local. `rm -rf .researchforge researchforge.yaml`
resets a project completely (add `researchforge claude uninstall` first if
you want the skills gone too); to redefine just the objective on existing
data, use `researchforge project create --force-update`. Nothing outside
your repository is ever created.

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
