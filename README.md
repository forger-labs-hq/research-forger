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

# 2. Go to the directory you want to work in (a repository to improve, or
#    ANY folder for pure research — clone/create it first if needed)
#    and initialize ResearchForge inside it:
cd path/to/your-project
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

Everything is **directory-scoped**: the database, worktrees, artifacts, and
dashboard live under the folder you initialized — which can be anywhere on
disk, not just next to this repo. Point a command at another project with
`researchforge -C /path/to/project <command>` (like `git -C`), and print
the full location map with `researchforge paths`.

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

## Watch your experiments (dashboard + live monitor)

Two ways to *see* how experiments perform against the baseline:

```bash
researchforge dashboard --open       # one self-contained HTML snapshot
```

A single static file (no server, no JS libraries, nothing leaves your
machine) with an autoresearch-style **progress chart** — every experiment as
a chronological dot, kept improvements annotated, a running-best step
line — plus per-experiment bars vs the baseline, the trade-off scatter with
the hard-constraint line, the funnel with drop-offs, and validation spread.

```bash
pip install "researchforge[serve]"
researchforge serve --background     # always-on monitor at http://127.0.0.1:9000
```

A local web monitor that follows runs **as they happen**: overview with the
next action, research state (papers, landscape directions, hypotheses), a
per-run experiments table that refreshes every 3 seconds while a run is in
progress, the live chart dashboard, and a JSON API (`/api/state`). Once the
extra is installed, `experiment run`/`start` auto-start it and print the
URL; if port 9000 is taken it picks a free one and tells you. Manage it
with `researchforge serve --status` / `--stop`. The server opens the
database **read-only** and binds 127.0.0.1 only by default — watching can
never interfere with a run.

## Journey A — research an idea

You have a question; ResearchForge grounds it in literature. From Claude
Code, `/researchforge-start` with your question does all of this; the CLI
equivalent (where **you** write the synthesis files against exported
schemas) is:

```bash
researchforge project create --mode explore_research_idea --objective "..."
researchforge research search        # arXiv: fetch -> dedup -> rank -> store
researchforge research context       # exports context.json with the schemas
# Claude (or you) writes landscape.yaml + hypotheses.yaml — validated on import:
researchforge research landscape --import .researchforge/synthesis/landscape.yaml
researchforge hypotheses import .researchforge/synthesis/hypotheses.yaml
researchforge report build           # citation-backed report
researchforge paper package          # optional: BibTeX, outline, evidence matrix
```

**You end up with:** a research landscape (directions + graded evidence:
published claim vs interpretation vs speculation), testable hypotheses, a
citation-backed Markdown report, and optionally a full research bundle.
Details: [docs/research-mode.md](docs/research-mode.md)

## Journey B — improve a repository

Everything in Journey A, then benchmarked experiments on your code. Every
consequential step is **your** typed approval — Claude cannot approve, run,
or ship anything by itself.

**1. Define and freeze the evaluation:**

```bash
researchforge project create --mode improve_repository --objective "..."
researchforge repo scan
researchforge contract generate      # edit researchforge.yaml, then:
researchforge contract approve       # YOUR approval -> immutable contract
researchforge baseline run           # frozen reference measurement
```

**2. Run experiments** (Claude writes `plan.yaml` + one patch per variant
after `researchforge experiment plan hyp-001`; manually you write them
against the exported schema):

```bash
researchforge experiment start .researchforge/experiments/plan.yaml
# = import + ONE typed approval (shows worst-case wall time) + run
```

**3. Inspect and validate:**

```bash
researchforge results show run-001   # ranking, trade-offs, rejections
researchforge validate run-001       # repeated runs earn "validated"
```

**4. Accept the result → what ships (and how the PR happens):**

```bash
researchforge ship branch    # clean LOCAL branch on the frozen baseline —
                             # one commit, nothing pushed, inspect with git
researchforge report build   # engineering report: the full evidence chain
researchforge ship pr        # OPT-IN: push + open a DRAFT PR on YOUR repo
```

`ship pr` is how the pull request gets created, and it only works when all
three gates open: `shipping.allow_draft_pr: true` in the **approved**
contract, the **`gh` CLI authenticated** to your remote, and a typed
`push` confirmation from you. It pushes exactly one branch and opens a
**draft** PR for human review — nothing is ever pushed without those
gates. Prefer full control? Stop after `ship branch` and push/PR yourself
with plain git. Details: [docs/experiment-mode.md](docs/experiment-mode.md)

**Open-source repositories (no push access):** cloned someone else's repo?
`ship pr` detects that you can't push to origin and switches to the fork
workflow — behind a typed `fork` confirmation that spells out exactly what
happens: a **public fork** is created (or reused) under your GitHub
account, one branch is pushed *to the fork*, and a **draft** PR is opened
on the upstream repository. One caveat to review first: if you committed a
benchmark locally to establish the baseline, that commit is part of your
branch's history and **will appear in the PR** — check `git log` (the CLI
warns you when the branch carries extra commits). And read the project's
CONTRIBUTING.md before opening PRs on repos you don't maintain — a draft
PR with a reproducible, validated improvement is a good contribution; ten
of them are spam.

### Managing experiment runs

| I want to… | Command |
|---|---|
| start a batch (one command) | `researchforge experiment start plan.yaml` |
| watch it live | `researchforge serve --background` (URL is printed) |
| stop a running batch | **Ctrl-C** — always safe (isolated worktrees) |
| continue an interrupted run | `researchforge experiment resume run-001` |
| discard an interrupted run | `researchforge experiment abandon run-001` |
| run another batch | `researchforge experiment plan hyp-002` → start again |
| see what's next, always | `researchforge status` |
| reset the whole project | `rm -rf .researchforge researchforge.yaml` |

Everything is local; nothing outside your repository is ever created. To
redefine just the objective on existing data:
`researchforge project create --force-update`.
[docs/claude-mode.md](docs/claude-mode.md) explains exactly what the Claude
skills do and cannot do.

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
