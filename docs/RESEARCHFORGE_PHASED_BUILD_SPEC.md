# ResearchForge — Phase-by-Phase Product and Build Specification

**Working tagline:** From papers to proof.  
**Secondary tagline:** Research that runs.  
**Product type:** Open-source, Claude-first research and experimentation tool  
**Initial interface:** Python CLI + Claude Code plugin/skills  
**Initial execution model:** Local execution using Docker when available, with a Python virtual-environment fallback for trusted, simple Python repositories  
**Primary first users:** AI/ML engineers, researchers, open-source maintainers, technical founders, and small engineering teams

---

## 0. Instructions for Claude Code

This document is the source of truth for building ResearchForge.

When implementing it:

1. Work phase by phase.
2. Do not implement later-phase features early unless they are required for a stable interface.
3. Before each phase:
   - inspect the current repository;
   - produce a short implementation plan;
   - identify assumptions and risks;
   - list the files that will be created or changed.
4. After each phase:
   - run unit tests;
   - run the relevant integration test;
   - update documentation;
   - provide a concise completion report;
   - do not move to the next phase until acceptance criteria pass.
5. Prefer small, testable modules and typed interfaces.
6. Never treat an LLM prompt, a Claude skill, or a hook as a security boundary. Security restrictions must also be enforced by Python code.
7. Never claim a research idea is globally novel. Use language such as:
   - “Limited directly matching evidence was found.”
   - “This combination appears underexplored in the reviewed sources.”
   - “Novelty has not been established.”
8. Never claim an improvement until it has been measured against an approved baseline and benchmark.
9. Do not silently change the benchmark, protected paths, test data, primary metric, or hard constraints during an experiment.
10. Keep Phase 1 local-first and open source. Do not build a hosted arbitrary-code sandbox, Kubernetes runner, or enterprise dashboard in Phase 1.

Recommended Claude prompt for each implementation step:

> Read `RESEARCHFORGE_PHASED_BUILD_SPEC.md`. Implement only the next incomplete phase. First show the plan, assumptions, files to change, and tests. Do not implement features assigned to later phases.

---

# 1. Product definition

ResearchForge accepts either:

1. a **research question or new technical idea**, or
2. a **repository plus a desired improvement**.

It then:

1. understands the user’s objective;
2. studies the repository when provided;
3. discovers and organizes relevant research papers;
4. extracts methods, evidence, limitations, and disagreements;
5. proposes evidence-backed, testable hypotheses;
6. helps the user define or confirm a benchmark and success criteria;
7. runs competing experiments against the same baseline;
8. rejects invalid or inferior approaches;
9. validates the strongest results;
10. produces one of two outcomes:
    - a clean feature branch and draft pull request; or
    - a research package containing literature, citations, methodology, experiment evidence, and a paper outline.

## Core promise

> Tell ResearchForge what you want to improve or investigate. It studies the relevant literature, proposes research-backed approaches, benchmarks competing experiments against a controlled baseline, and delivers the strongest supported result with complete evidence.

## Product differentiation

ResearchForge is not merely:

- a paper-search engine;
- an automated code-editing agent;
- a generic optimization loop;
- a chatbot that suggests ideas;
- a CI dashboard.

Its differentiator is the complete evidence chain:

```text
User objective
    ↓
Repository observation
    ↓
Relevant papers
    ↓
Evidence and contradictions
    ↓
Research gap or improvement opportunity
    ↓
Testable hypothesis
    ↓
Implementation variants
    ↓
Controlled benchmark
    ↓
Validated finding
    ↓
Pull request or research package
```

The papers influence **which experiments are worth running**.  
The benchmark determines **which experiments actually work**.

---

# 2. Goals and non-goals

## Goals for Phase 1

ResearchForge Phase 1 must allow a user to:

1. install the tool locally;
2. use it through Claude Code and through a normal CLI;
3. start with an idea or an existing repository;
4. discover relevant arXiv papers;
5. view a structured research landscape rather than a raw paper list;
6. generate evidence-backed hypotheses;
7. define or confirm a measurable objective;
8. establish a frozen baseline;
9. run experiments in isolated local workspaces;
10. use Docker when a suitable Docker environment exists;
11. use a `.venv` fallback for trusted, simple Python repositories;
12. compare every viable experiment against the same benchmark;
13. validate finalists through repeated runs;
14. generate a report;
15. create a clean feature branch and optionally a draft PR;
16. generate a research package when the outcome is a research contribution rather than a software change.

## Non-goals for Phase 1

Phase 1 will not:

- run arbitrary untrusted code in ResearchForge-hosted infrastructure;
- recreate arbitrary microservice architectures;
- support Kubernetes experiments;
- support production deployment;
- merge pull requests automatically;
- guarantee novelty, patentability, or publishability;
- automatically submit papers;
- support physical laboratory experiments;
- deeply index every paper on arXiv;
- redistribute copyrighted paper text;
- support multi-repository distributed experiments;
- manage enterprise secrets or production credentials;
- provide a full web dashboard;
- support every programming language;
- promise 40–100 experiments for every repository.

---

# 3. Product modes

ResearchForge has two primary modes.

## 3.1 Improve Repository mode

The user provides:

- a repository;
- a desired outcome;
- optional constraints;
- an existing benchmark or permission for ResearchForge to suggest one.

Example:

> Improve classification F1 without increasing P95 latency above 250 ms.

ResearchForge should:

1. scan the repository;
2. detect the current implementation and evaluation options;
3. search relevant research;
4. create research directions;
5. propose hypotheses compatible with the repository;
6. establish a baseline;
7. run approved experiments;
8. rank results under the user’s constraints;
9. validate finalists;
10. prepare a clean implementation branch and report.

## 3.2 Explore Research Idea mode

The user provides:

- a research question or technical idea;
- optional domain, constraints, datasets, or repository.

Example:

> Can uncertainty-aware routing outperform fixed routing under strict cost and latency constraints?

ResearchForge should:

1. build a research landscape;
2. identify established approaches;
3. identify contradictions and limitations;
4. identify underexplored combinations or conditions;
5. generate testable hypotheses;
6. recommend baselines, datasets, and metrics;
7. create an experiment blueprint;
8. optionally generate a starter repository;
9. run experiments only when an executable evaluator exists;
10. produce a research package.

Without executable code, data, and an evaluator, the hypothesis remains **speculative**.

---

# 4. Core product principles

## 4.1 The user defines the outcome

The user normally decides what should improve.

Examples:

- maximize F1;
- minimize cost while keeping quality within 1%;
- reduce latency without lowering recall;
- improve robustness on a specified benchmark;
- investigate whether a proposed method beats selected baselines.

When the user’s request is vague, ResearchForge may suggest objectives and metrics, but the user must confirm them before experimentation.

## 4.2 One approved experiment contract

Every experimental project must have a versioned contract that defines:

- baseline commit;
- setup command;
- evaluation command;
- result format;
- primary metric;
- optimization direction;
- hard constraints;
- secondary metrics;
- editable paths;
- protected paths;
- time and resource limits;
- execution mode;
- network and secret requirements.

## 4.3 Same benchmark, controlled comparison

All experiments in a comparison group must use the same:

- baseline;
- benchmark;
- evaluator;
- dataset version;
- environment definition;
- metric extraction logic;
- hard constraints.

ResearchForge may use a smaller screening subset before the full benchmark, but it must record which benchmark stage produced each result.

## 4.4 Research evidence proposes; experiments decide

Paper evidence helps prioritize ideas. It does not prove that an idea will work in the user’s project.

## 4.5 Negative results are valuable

Rejected experiments must be recorded with:

- hypothesis;
- exact change;
- result;
- failure reason;
- benchmark stage;
- relevant logs;
- environment details.

## 4.6 Human approval at consequential steps

Require explicit approval before:

- creating or changing the experiment contract;
- enabling network access;
- exposing named environment variables;
- starting a high-cost run;
- pushing a branch;
- creating a PR.

## 4.7 Local-first trust model

Phase 1 runs on infrastructure the user controls. ResearchForge Core does not upload source code, datasets, or secrets to a ResearchForge cloud service.

---

# 5. Initial user personas

## Persona A — AI/ML engineer

Wants to improve a measurable model or pipeline outcome using methods grounded in literature.

## Persona B — researcher

Wants to explore a new technical direction, compare it with prior work, design experiments, and generate reproducible research artifacts.

## Persona C — open-source maintainer

Wants a clean, evidence-backed pull request rather than dozens of messy experimental branches.

## Persona D — technical founder

Wants to validate whether an idea is technically promising before spending weeks implementing it.

## Persona E — enterprise research team, later phase

Wants private repositories, internal papers, controlled runners, auditability, approvals, and shared experiment memory.

---

# 6. End-to-end user journeys

## 6.1 Repository improvement journey

```text
Install ResearchForge
    ↓
Open repository in Claude Code
    ↓
Run /researchforge-start
    ↓
Choose “Improve this repository”
    ↓
Describe desired outcome
    ↓
Repository compatibility scan
    ↓
Relevant paper discovery
    ↓
Research landscape and hypotheses
    ↓
Confirm benchmark and constraints
    ↓
Establish baseline
    ↓
Approve experiment batch
    ↓
Run quick screening experiments
    ↓
Run full benchmark on shortlisted candidates
    ↓
Repeat and validate finalists
    ↓
Review trade-offs and recommendation
    ↓
Create clean feature branch
    ↓
Create optional draft PR
    ↓
Export research and experiment report
```

## 6.2 Research idea journey

```text
Install ResearchForge
    ↓
Run /researchforge-start
    ↓
Choose “Explore a research idea”
    ↓
Describe research question
    ↓
Discover and organize relevant papers
    ↓
Review methods, evidence, contradictions, and limitations
    ↓
Generate ranked hypotheses
    ↓
Select one hypothesis
    ↓
Generate baselines, datasets, metrics, and methodology
    ↓
Optionally create starter repository
    ↓
Run experiments when executable
    ↓
Generate research package and paper outline
```

---

# 7. Phase 1 MoSCoW requirements

## 7.1 Must Have

### Installation and interface

- Python package installable with `pip`.
- CLI entry point named `researchforge`.
- Claude Code integration installed through a ResearchForge command.
- Clear `doctor` command for dependency checks.
- Local project state stored under `.researchforge/`.

### Project creation

- Improve Repository mode.
- Explore Research Idea mode.
- Project objective capture.
- User confirmation of metrics and constraints.
- Resume an existing ResearchForge project.

### Repository intelligence

- Read README and common project metadata.
- Detect Python project files.
- Detect Git repository and current commit.
- Detect Dockerfile.
- Detect common test and benchmark scripts.
- Suggest editable and protected paths.
- Return compatibility status:
  - ready for experiments;
  - setup required;
  - research only;
  - unsupported in Phase 1.

### Paper discovery

- arXiv metadata and abstract search.
- Multiple generated search queries.
- Deduplication.
- Relevance ranking against objective and repository.
- Structured paper records.
- Citation metadata.
- Method, reported finding, limitation, and project relevance fields.
- Links from claims and hypotheses back to papers.

### Research synthesis

- Research landscape grouped by approach.
- Supporting and contradicting evidence.
- Research limitations.
- Research-gap language that avoids novelty guarantees.
- Evidence-backed hypotheses.
- Feasibility and expected-cost scoring.

### Benchmarking and experiment contract

- Baseline commit.
- Evaluation command.
- Machine-readable result file.
- Primary metric and direction.
- Hard constraints.
- Secondary metrics.
- Editable paths.
- Protected paths.
- Resource and time limits.
- Versioned `researchforge.yaml`.

### Local experiment engine

- Git worktree per experiment.
- Docker execution when configured and available.
- `.venv` execution fallback for trusted Python projects.
- Frozen baseline.
- Quick screening stage.
- Full benchmark stage.
- Finalist validation stage.
- Complete experiment manifest.
- Timeout and process cleanup.
- Persisted results after workspace deletion.

### Result evaluation

- Compare experiment with baseline.
- Reject hard-constraint violations.
- Rank viable candidates.
- Show Pareto trade-offs when there is no single winner.
- Confidence states:
  - speculative;
  - promising;
  - validated;
  - implementation-ready.

### Outputs

- Markdown research report.
- Machine-readable JSON results.
- Experiment table.
- Rejected-experiment history.
- Reproduction instructions.
- Clean feature branch.
- Optional draft PR using GitHub CLI.
- Research package with BibTeX and paper outline.

## 7.2 Should Have

- User-provided paper URL or PDF ingestion.
- GitHub Actions workflow generation.
- HTML report.
- Repeated winner validation.
- Ablation-plan generation.
- Resume interrupted runs.
- Experiment and time budgets.
- Automatic chart generation from recorded results.
- `gh` CLI integration.
- Starter repository generation for research-only ideas.
- Support for one user-approved external network mode.
- Explicit environment-variable forwarding by name.
- Cached Docker build layers.
- Configurable screening and full benchmark commands.

## 7.3 Could Have

- Semantic Scholar or OpenAlex integration.
- Public shareable reports.
- Local browser UI.
- Parallel local workers.
- GitLab support.
- MCP server.
- Codex integration.
- Research alerts.
- Community experiment templates.
- Limited GPU support.
- Multi-objective visualizations.
- Public reproducibility gallery.

## 7.4 Won’t Have in Phase 1

- Hosted arbitrary-code sandbox.
- General microservice reconstruction.
- Docker Compose orchestration beyond a user-supplied custom adapter.
- Kubernetes.
- Multi-repository experiments.
- Automatic merge or deployment.
- Enterprise SSO/RBAC.
- Internal-document connectors.
- Organization-wide research graph.
- Guaranteed novelty or paper acceptance.
- Automatic paper submission.

---

# 8. Recommended implementation phases

---

## Phase 0 — Repository foundation

### Objective

Create a maintainable Python project with typed domain models, a CLI shell, persistence conventions, and tests.

### Deliverables

```text
researchforge/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/researchforge/
│   ├── __init__.py
│   ├── cli.py
│   ├── config/
│   ├── domain/
│   ├── storage/
│   └── utils/
├── tests/
│   ├── unit/
│   └── fixtures/
└── docs/
    └── architecture.md
```

### Technical choices

- Python 3.11+.
- Typer or Click for CLI.
- Pydantic for schemas and configuration.
- SQLite for local project metadata.
- JSON/JSONL for portable run artifacts.
- `pytest` for tests.
- `ruff` and a type checker.
- Apache-2.0 recommended for the open-source license.

### CLI shell

```bash
researchforge --help
researchforge doctor
researchforge init
researchforge status
```

### Acceptance criteria

- Package installs in a clean virtual environment.
- CLI help works.
- `researchforge doctor` checks Python, Git, Docker, and GitHub CLI.
- `researchforge init` creates `.researchforge/`.
- Unit tests pass.
- CI runs lint, type checks, and tests.

---

## Phase 1A — Research intelligence MVP

### Objective

Provide value without running experiments: understand the objective, discover relevant papers, construct a research landscape, and propose hypotheses.

### Must implement

1. Project creation.
2. Improve Repository and Explore Research Idea modes.
3. Repository scanner.
4. arXiv search client.
5. Paper ranking.
6. Evidence records.
7. Research landscape.
8. Hypothesis schema and generation workflow.
9. Research-only Markdown report.

### Important architectural decision

Because this is Claude-first, Phase 1A should avoid requiring a separate model API key.

Use this division:

- Python CLI:
  - repository scanning;
  - arXiv retrieval;
  - deduplication;
  - structured context generation;
  - schema validation;
  - persistence.
- Claude Code skill:
  - synthesis;
  - research-direction grouping;
  - hypothesis generation;
  - explanation;
  - writing validated structured artifacts.

The plugin should ask Claude to write structured JSON/YAML that the Python package validates before saving.

### Research pipeline

```text
User objective
    ↓
Repository keywords and concepts
    ↓
Generate 3–8 search queries
    ↓
Retrieve 100–300 metadata candidates
    ↓
Deduplicate
    ↓
Rank titles and abstracts
    ↓
Select 20–40 relevant papers
    ↓
Deeply synthesize 8–15 strongest papers
    ↓
Create research landscape
    ↓
Generate 3–7 hypotheses
```

### Required paper schema

```yaml
paper_id: arxiv:xxxx.xxxxx
title: string
authors:
  - string
published_at: datetime
updated_at: datetime | null
abstract: string
source_url: string
pdf_url: string | null
categories:
  - string
relevance_score: 0.0
evidence_strength: low | medium | high | unknown
method_summary: string
reported_findings:
  - string
limitations:
  - string
repository_relevance: string | null
supports_hypotheses:
  - hypothesis_id
contradicts_hypotheses:
  - hypothesis_id
```

### Required hypothesis schema

```yaml
hypothesis_id: hyp-001
title: string
claim: string
rationale: string
supporting_paper_ids:
  - string
contradicting_paper_ids:
  - string
repository_observations:
  - string
expected_impact:
  metric: string | null
  direction: increase | decrease | unknown
feasibility: low | medium | high
estimated_effort: low | medium | high
estimated_experiment_count: integer | null
novelty_confidence: low | medium | unknown
status: speculative
proposed_experiment: string
limitations:
  - string
```

### Acceptance criteria

- User can create a research-only project.
- User can scan one repository.
- Tool finds and stores relevant arXiv records.
- Every hypothesis cites at least one evidence record or is explicitly labeled unsupported.
- Report distinguishes:
  - published claims;
  - ResearchForge interpretation;
  - proposed hypothesis;
  - unverified speculation.
- No novelty guarantee appears.
- All data can be resumed after restarting the CLI.

---

## Phase 1B — Experiment contract and baseline

### Objective

Convert a hypothesis into a measurable experiment without yet implementing a broad autonomous loop.

### Must implement

1. Experiment-contract wizard.
2. `researchforge.yaml` validation.
3. Git worktree manager.
4. Environment resolver.
5. Baseline runner.
6. Metric parser.
7. Baseline artifact storage.

### Environment resolver order

```text
Explicit config
    ↓
Existing Dockerfile and Docker available
    ↓
Simple Python project eligible for .venv
    ↓
Research-only / setup-required result
```

### Compatibility status

```yaml
status: ready | setup_required | research_only | unsupported
execution_mode: docker | venv | none
reasons:
  - string
required_user_actions:
  - string
```

### Acceptance criteria

- User can create and approve `researchforge.yaml`.
- Protected paths cannot be changed by an experiment patch.
- Baseline runs in a separate worktree.
- Baseline result is machine-readable and stored.
- Baseline commit and environment fingerprint are recorded.
- A failed baseline blocks experimentation.
- The tool explains exactly why a repository is not ready.

---

## Phase 1C — Local controlled experiment engine

### Objective

Run several controlled implementation variants, benchmark them, and identify viable candidates.

### Initial scope

- One Git repository.
- One target Python project or single Dockerized service.
- CPU-first.
- One evaluation contract.
- Five to ten experiments by default.
- One experiment at a time initially.
- User-owned and trusted repository.
- No general Compose or Kubernetes orchestration.

### Experiment funnel

```text
Candidate hypotheses and variants
        ↓
Quick screening benchmark for every runnable experiment
        ↓
Full benchmark for shortlisted candidates
        ↓
Repeated validation for finalists
        ↓
One recommendation or a trade-off frontier
```

### Default stages

#### Stage 1 — Quick screening

Run:

- build/import check;
- minimal tests;
- small representative benchmark subset;
- primary metric;
- critical hard constraints.

#### Stage 2 — Full benchmark

Run:

- complete evaluation set;
- all primary and secondary metrics;
- regression tests;
- resource measurements where supported.

#### Stage 3 — Validation

Run:

- repeated executions;
- multiple seeds when relevant;
- clean environment rebuild;
- ablation comparison;
- simple-baseline comparison;
- confidence and variance summary.

### Experiment states

```text
planned
approved
preparing
running
failed_setup
failed_execution
rejected
promising
validating
validated
implementation_ready
cancelled
```

### Required experiment manifest

```yaml
experiment_id: exp-001
run_id: run-001
hypothesis_id: hyp-001
baseline_commit: git-sha
parent_experiment_id: null
execution_mode: docker
benchmark_stage: screening
change_summary: string
changed_files:
  - path
commands:
  - string
started_at: datetime
completed_at: datetime | null
status: string
metrics:
  primary:
    name: f1
    value: 0.84
  secondary: {}
constraints:
  - name: p95_latency_ms
    passed: true
artifacts:
  diff_path: string
  stdout_path: string
  stderr_path: string
  results_path: string
decision:
  outcome: keep | reject | investigate
  reason: string
```

### Ranking rules

1. Reject experiments that:
   - fail setup;
   - fail required tests;
   - change protected files;
   - produce invalid metrics;
   - violate a hard constraint.
2. Rank remaining experiments primarily by the approved objective.
3. Present trade-offs when secondary metrics differ materially.
4. Do not call a one-off result “validated.”
5. Keep the original evaluator immutable.

### Acceptance criteria

- At least three synthetic experiment variants can run end to end in fixtures.
- Every runnable experiment uses a separate worktree.
- Results persist after worktree cleanup.
- The tool can recover from timeout and terminate child processes.
- A protected-file modification is rejected before evaluation.
- A hard-constraint violation is visibly rejected.
- Finalists are rerun before becoming validated.

---

## Phase 1D — Shipping and research outputs

### Objective

Turn validated findings into usable engineering or research deliverables.

### Repository outcome

ResearchForge should:

1. start from the frozen baseline commit;
2. reconstruct only the selected final change;
3. add or update tests;
4. rerun validation;
5. create a clean branch;
6. create an explanatory commit;
7. optionally create a draft PR through `gh`.

Suggested branch:

```text
researchforge/<short-hypothesis-name>
```

### Draft PR contents

- objective;
- current baseline;
- papers that motivated the approach;
- experiments attempted;
- rejected approaches;
- validated metrics;
- constraints;
- changed files;
- reproduction command;
- risks and limitations;
- ResearchForge report path.

### Research contribution outcome

Generate:

```text
research-output/
├── research_report.md
├── related_work.md
├── evidence_matrix.csv
├── citations.bib
├── hypotheses.md
├── methodology.md
├── limitations.md
├── paper_outline.md
├── reproducibility.md
├── experiments/
│   ├── run_manifest.json
│   ├── results.csv
│   └── rejected_experiments.md
└── figures/
```

### Paper outline

The outline may include:

1. proposed title options;
2. problem statement;
3. research question;
4. related work;
5. identified gap;
6. proposed method;
7. experimental setup;
8. results;
9. ablations;
10. discussion;
11. limitations;
12. future work;
13. citation mapping.

Only recorded experiment data may be used in the results section.

### Acceptance criteria

- Winning experiment can be reconstructed from baseline.
- Final branch excludes failed experiment history.
- Draft PR is opt-in.
- `citations.bib` includes valid metadata for cited papers.
- Research report links every finding to experiments and evidence.
- Reproduction instructions work in a clean test fixture.

---

## Phase 1E — Claude Code experience

### Objective

Make the complete workflow usable from Claude Code without forcing users to remember CLI details.

### Installation target

```bash
pip install researchforge
researchforge init --claude
```

The command should:

- initialize `.researchforge/`;
- install or generate project-level Claude skills;
- create safe default settings;
- show the commands available;
- avoid overwriting existing Claude configuration without approval.

### Suggested Claude skills

```text
/researchforge-start
/researchforge-doctor
/researchforge-papers
/researchforge-landscape
/researchforge-hypotheses
/researchforge-baseline
/researchforge-plan
/researchforge-run
/researchforge-results
/researchforge-validate
/researchforge-ship
/researchforge-paper
```

### Initial integration model

Use Claude skills to orchestrate the local CLI.

Do not require an MCP server in Phase 1.

The skills should:

1. gather user intent;
2. call deterministic CLI commands;
3. read structured JSON outputs;
4. ask Claude to synthesize or implement within strict schemas;
5. pass structured artifacts back to the CLI for validation;
6. ask for approval before execution and shipping;
7. summarize progress and final results in Claude.

### Safety requirement

Claude may propose a patch, but the ResearchForge Python engine must independently verify:

- changed paths;
- contract version;
- protected paths;
- result schema;
- execution limits;
- approval state.

### Acceptance criteria

- A user can complete both primary journeys from Claude Code.
- Skills do not require copying long prompts manually.
- CLI remains independently usable.
- Failed validation is explained in Claude.
- Claude cannot bypass protected-path enforcement through instructions.

---

## Phase 1F — Open-source beta release

### Objective

Launch a narrow but complete product.

### Supported repositories

- Git repository.
- Python 3.11+.
- Single project or single target service.
- Existing Dockerfile or simple Python dependency metadata.
- Machine-readable benchmark result.
- Bounded runtime.
- User-owned/trusted code.
- No required production infrastructure.

### Trial experience for open source

The open-source package does not need an artificial five-day limit.

Instead, use a generous local core and reserve hosted conveniences for later premium plans.

### Launch demo

A strong launch demo should show:

1. a user enters an objective;
2. ResearchForge finds relevant papers;
3. it proposes three evidence-backed hypotheses;
4. the user confirms a benchmark;
5. five to ten variants run;
6. failed experiments are preserved;
7. one result is validated;
8. a clean branch and report are created.

### Beta success criteria

- At least 10 external users install it.
- At least 5 complete a research landscape.
- At least 3 establish a baseline.
- At least 2 complete an experiment batch.
- At least 1 generates a useful branch or research package.
- Setup failures are categorized and measurable.

---

# 9. Local execution and sandbox strategy

## 9.1 Important distinction

ResearchForge Phase 1 provides **local experiment isolation**, not a hardened hostile-code sandbox.

Docker improves process and dependency isolation, but users should still run only repositories they trust.  
A Python `.venv` is dependency isolation, not security isolation.

Display this clearly in the product.

## 9.2 Workspace isolation

Every baseline and experiment uses a Git worktree:

```text
.repository/
├── normal user working tree/
└── .researchforge/
    ├── worktrees/
    │   ├── baseline/
    │   └── run-001/
    │       ├── exp-001/
    │       ├── exp-002/
    │       └── exp-003/
    ├── artifacts/
    ├── papers/
    ├── reports/
    └── researchforge.db
```

Benefits:

- user’s current branch remains untouched;
- experiments can be deleted safely;
- diffs are easy to capture;
- baseline and experiments share Git history;
- final change can be reconstructed cleanly.

## 9.3 Docker mode — preferred when available

Use Docker when:

- `execution.mode` is explicitly `docker`; or
- a suitable Dockerfile exists and the user approves it.

### Docker preparation

1. Create experiment worktree.
2. Build image from the worktree.
3. Allow network during image build only when dependencies must be downloaded.
4. Cache image layers.
5. Run evaluation container with strict defaults.
6. Mount only:
   - experiment worktree;
   - a dedicated artifact directory.
7. Never mount:
   - the Docker socket;
   - the user’s home directory;
   - SSH directories;
   - cloud credential directories;
   - unrelated repositories.

### Docker runtime defaults

Use the conceptual equivalent of:

```text
--rm
--cpus=<approved-limit>
--memory=<approved-limit>
--pids-limit=<approved-limit>
--network=none
--security-opt=no-new-privileges
--cap-drop=ALL
--user=<non-root-user>
```

Where compatible, also use:

- read-only root filesystem;
- temporary writable `/tmp`;
- no privileged mode;
- no host network;
- timeout enforced outside the container.

### Network-requiring projects

Many AI repositories call model APIs.

For those:

1. default to no network;
2. detect likely network requirements;
3. ask the user explicitly;
4. record approval in the experiment contract;
5. forward only named environment variables;
6. never save secret values;
7. keep logs redacted;
8. mark results as dependent on external services.

Phase 1 may support:

```yaml
network:
  mode: none | enabled
secrets:
  forward_environment_variables:
    - ANTHROPIC_API_KEY
```

Domain-level egress allowlisting is not required in Phase 1.

### Docker limitations

- Docker is not a guarantee against hostile code.
- Platform behavior differs across Linux, macOS, and Windows.
- Rootless Docker is recommended on supported Linux systems.
- Docker Desktop users rely on Docker Desktop’s VM and security model.
- ResearchForge must not claim stronger isolation than it provides.

## 9.4 Python `.venv` fallback

Use `.venv` mode only when:

- the repository is trusted by the user;
- it is a simple Python project;
- it does not require system services;
- it does not require container-only dependencies;
- the user accepts the lower isolation level.

### `.venv` flow

1. Create experiment worktree.
2. Create a dedicated virtual environment inside the worktree or run directory.
3. Install dependencies from lockfile or approved dependency files.
4. Run setup and evaluation commands in a subprocess.
5. Enforce timeout.
6. Kill the whole process group on cancellation or timeout.
7. Store stdout, stderr, results, and resource information.
8. Delete the environment after artifacts are persisted.

### `.venv` warning

Display:

> Virtual-environment mode isolates Python dependencies but does not securely isolate code from your computer, files, or network. Use it only with repositories you trust. Choose Docker for stronger isolation.

### `.venv` constraints

Phase 1 does not promise reliable cross-platform memory or CPU isolation for `.venv` mode. It must enforce:

- wall-clock timeout;
- process-group termination;
- working-directory isolation;
- explicit environment-variable forwarding;
- no automatic loading of arbitrary local `.env` files.

## 9.5 Research-only mode

No execution environment is created when:

- there is no repository;
- there is no evaluator;
- the baseline fails;
- the repository requires unsupported infrastructure.

ResearchForge should still produce:

- literature landscape;
- hypotheses;
- benchmark recommendations;
- experiment methodology;
- starter repository option.

## 9.6 Unsupported Phase 1 examples

Return a clear “setup required” or “unsupported” state for:

- many dependent microservices;
- required Kubernetes cluster;
- production databases;
- private service mesh;
- multiple repositories;
- mandatory internal network;
- destructive infrastructure commands;
- unbounded training jobs;
- benchmark requiring manual judgment with no evaluator.

---

# 10. Example `researchforge.yaml`

```yaml
version: 1

project:
  name: adaptive-routing-study
  mode: improve_repository

objective:
  description: >
    Reduce average inference cost while keeping quality within
    one percentage point of the current baseline.
  primary_metric:
    name: quality_score
    direction: maximize
  hard_constraints:
    - name: average_cost_usd
      operator: <=
      value: 0.02
    - name: quality_regression
      operator: <=
      value: 0.01
  secondary_metrics:
    - p95_latency_ms
    - average_cost_usd

repository:
  baseline_ref: main

execution:
  mode: auto
  trusted_repository: true
  setup_command: python -m pip install -e .
  screening_command: python benchmarks/evaluate.py --subset screening
  full_command: python benchmarks/evaluate.py --subset full
  result_file: artifacts/results.json
  timeout_minutes: 20
  cpu_limit: 2
  memory_mb: 4096
  max_experiments: 8

permissions:
  editable_paths:
    - src/
    - config/
  protected_paths:
    - benchmarks/
    - test_data/
    - evaluator/

network:
  mode: none

secrets:
  forward_environment_variables: []

validation:
  repeat_finalists: 3
  require_existing_tests: true

shipping:
  allow_branch_creation: true
  allow_draft_pr: false
```

---

# 11. Benchmark result schema

Evaluation commands should write JSON such as:

```json
{
  "schema_version": 1,
  "primary_metric": {
    "name": "quality_score",
    "value": 0.842
  },
  "secondary_metrics": {
    "p95_latency_ms": 188.4,
    "average_cost_usd": 0.014
  },
  "sample_count": 1200,
  "seed": 42,
  "metadata": {
    "dataset_version": "benchmark-v2",
    "notes": "full evaluation"
  }
}
```

ResearchForge should reject:

- missing primary metric;
- wrong metric name;
- non-numeric values;
- NaN/Infinity;
- incompatible schema version;
- results generated after protected evaluator changes.

---

# 12. Domain model

Minimum entities:

## Project

- id;
- name;
- mode;
- objective;
- repository metadata;
- status;
- created and updated timestamps.

## Paper

- metadata;
- abstract;
- relevance;
- extracted methods;
- findings;
- limitations.

## EvidenceClaim

- claim;
- source paper;
- evidence type;
- support or contradiction;
- extraction confidence.

## Hypothesis

- claim;
- rationale;
- supporting and contradicting evidence;
- applicability;
- experiment plan;
- confidence.

## ExperimentContract

- immutable approved evaluation definition;
- version;
- approval timestamp.

## ExperimentRun

- exact environment;
- patch;
- commands;
- metrics;
- constraints;
- result;
- logs.

## Finding

- conclusion;
- supporting experiments;
- supporting papers;
- confidence;
- limitations;
- applicability conditions.

## Deliverable

- report;
- branch;
- PR;
- research package;
- reproducibility bundle.

---

# 13. CLI specification

```bash
researchforge doctor
researchforge init
researchforge status

researchforge project create
researchforge repo scan
researchforge research search
researchforge research landscape
researchforge hypotheses list
researchforge hypotheses show HYPOTHESIS_ID

researchforge contract generate
researchforge contract validate
researchforge baseline run

researchforge experiment plan HYPOTHESIS_ID
researchforge experiment run PLAN_ID
researchforge experiment resume RUN_ID
researchforge results show RUN_ID
researchforge validate RUN_ID

researchforge report build
researchforge ship branch
researchforge ship pr
researchforge paper package

researchforge claude install
researchforge claude uninstall
```

All important commands should support:

```bash
--json
```

This lets Claude skills use structured outputs reliably.

---

# 14. Detailed user stories and acceptance criteria

## US-01 — Start a project from Claude

**As a user**, I want to start ResearchForge from Claude Code so that I do not need to understand the CLI.

### Acceptance criteria

- `/researchforge-start` asks whether the user wants repository improvement or research exploration.
- It captures the objective.
- It calls the CLI with structured parameters.
- It shows the created project ID and next action.

---

## US-02 — Explore a research idea without code

**As a researcher**, I want to enter a research question and receive a structured view of prior work.

### Acceptance criteria

- At least three distinct paper-search queries are generated.
- Duplicate papers are removed.
- Papers are grouped by method or research direction.
- Limitations and contradictions are visible.
- ResearchForge generates testable hypotheses.
- Hypotheses are marked speculative until tested.

---

## US-03 — Connect an existing repository

**As an engineer**, I want ResearchForge to understand my repository before suggesting changes.

### Acceptance criteria

- Current Git commit is recorded.
- README and common Python metadata are scanned.
- Existing tests and benchmark candidates are listed.
- Docker compatibility is reported.
- The tool suggests editable and protected paths.
- User can correct the scan.

---

## US-04 — Define what should improve

**As a user**, I want to define the desired outcome and constraints so that ResearchForge does not optimize the wrong thing.

### Acceptance criteria

- Primary metric is required before experiments.
- Direction is required.
- Hard constraints are explicit.
- ResearchForge can suggest metrics.
- User approval is recorded.
- Any later change creates a new contract version.

---

## US-05 — Review papers relevant to my project

**As an engineer**, I want to understand why each paper matters to my codebase.

### Acceptance criteria

Each paper view shows:

- method;
- reported result;
- limitations;
- repository relevance;
- hypotheses supported;
- source link.

---

## US-06 — Generate research-backed hypotheses

**As a user**, I want ResearchForge to propose several approaches rather than one unchallenged answer.

### Acceptance criteria

- Three to seven hypotheses are produced by default.
- Supporting evidence is listed.
- Contradicting evidence is listed when available.
- Expected impact and feasibility are scored.
- Proposed experiment is concrete.
- Unsupported claims are labeled.

---

## US-07 — Establish a baseline

**As a user**, I want the current repository measured before modifications.

### Acceptance criteria

- Baseline runs in a separate worktree.
- Exact commit, command, environment, and result are stored.
- Failed baseline blocks experiments.
- Baseline is immutable within the run.

---

## US-08 — Run experiments locally

**As a user**, I want experiments isolated from my normal working tree.

### Acceptance criteria

- Every experiment gets a separate worktree.
- Docker is used when selected.
- `.venv` warning appears when selected.
- Timeout works.
- Protected paths cannot change.
- Artifacts persist after cleanup.

---

## US-09 — Compare all experiments fairly

**As a user**, I want all viable experiments compared against the same baseline.

### Acceptance criteria

- Every experiment identifies benchmark stage.
- Invalid metrics are rejected.
- Hard constraints are enforced.
- Screening and full results are not mixed without labels.
- Finalists are validated repeatedly.

---

## US-10 — Understand failures

**As a user**, I want to know why approaches failed so that I do not repeat them.

### Acceptance criteria

- Failed and rejected experiments remain searchable.
- Failure reason is categorized.
- Diff, logs, and metrics are retained.
- Report includes rejected approaches.

---

## US-11 — Receive a clean implementation

**As a maintainer**, I want a clean branch rather than dozens of experiment branches.

### Acceptance criteria

- Final branch starts from baseline.
- Only winning implementation is applied.
- Tests and benchmark pass.
- Failed branches are not pushed.
- PR is draft and opt-in.

---

## US-12 — Produce a research package

**As a researcher**, I want reproducible evidence and citation material.

### Acceptance criteria

- BibTeX file is generated.
- Related-work matrix is generated.
- Methodology is based on approved contract.
- Results use recorded data only.
- Limitations are included.
- Reproduction instructions are included.

---

# 15. Result selection and experiment quality

## 15.1 Primary objective

Examples:

- maximize accuracy;
- maximize F1;
- minimize latency;
- minimize cost;
- minimize training loss;
- maximize throughput.

## 15.2 Hard constraints

Examples:

- P95 latency below 300 ms;
- cost below $0.02;
- memory below 4 GB;
- no test regressions;
- safety metric not lower than baseline.

## 15.3 Secondary metrics

Examples:

- precision and recall;
- memory;
- code complexity;
- compute time;
- cost;
- stability.

## 15.4 Candidate selection

ResearchForge should calculate a viability status, not hide trade-offs behind one magic score.

Example:

| Candidate | Quality | P95 latency | Cost | Decision |
|---|---:|---:|---:|---|
| Baseline | 0.810 | 180 ms | $0.012 | Current |
| A | 0.852 | 340 ms | $0.020 | Rejected: latency |
| B | 0.841 | 195 ms | $0.014 | Quality candidate |
| C | 0.838 | 172 ms | $0.011 | Efficiency candidate |

When several candidates are valid, show a Pareto frontier and ask the user to choose the preferred trade-off.

## 15.5 Confidence states

### Speculative

Supported by reasoning or literature but not tested.

### Promising

Improved in at least one controlled run.

### Validated

Repeated successfully under the approved benchmark and constraints.

### Implementation-ready

Validated, reconstructed cleanly, tested, documented, and ready for review.

---

# 16. Report structure

## Engineering report

1. Objective.
2. Repository and baseline.
3. Research reviewed.
4. Research directions.
5. Hypotheses.
6. Experiment contract.
7. Experiments attempted.
8. Rejected approaches.
9. Full benchmark results.
10. Validation results.
11. Trade-offs.
12. Recommended implementation.
13. Risks and limitations.
14. Exact reproduction steps.
15. Commits and artifact paths.
16. Future experiments.

## Research report

1. Research question.
2. Search strategy.
3. Literature landscape.
4. Established methods.
5. Conflicting findings.
6. Limitations in prior work.
7. Proposed gap or underexplored condition.
8. Hypotheses.
9. Baselines and methodology.
10. Experimental setup.
11. Results.
12. Ablations.
13. Discussion.
14. Limitations.
15. Future work.
16. Citation map.

---

# 17. Open-source, premium, and enterprise boundaries

## ResearchForge Core — open source

Include:

- Python CLI;
- Claude Code skills/plugin assets;
- local repository scanner;
- arXiv discovery;
- research landscape;
- hypothesis generation workflow;
- local Git worktrees;
- Docker runner;
- `.venv` runner;
- evaluation loop;
- Markdown report;
- feature branch creation;
- GitHub CLI draft PR;
- research package;
- single-user local history.

## ResearchForge Pro — later

Potential paid features:

- hosted project dashboard;
- managed paper index;
- scheduled overnight runs;
- parallel experiment orchestration;
- persistent remote artifact storage;
- private share links;
- team workspaces;
- shared research memory;
- paper alerts;
- GitHub App;
- usage and cost analytics;
- remote MCP access;
- advanced source connectors.

## ResearchForge Enterprise — later, demand-led

Potential enterprise features:

- customer-hosted runner;
- code and datasets remain in customer environment;
- SSO/SAML;
- RBAC;
- audit logs;
- approval workflows;
- internal paper and document sources;
- private package registries;
- private model endpoints;
- retention policies;
- VPC/private networking;
- multi-repository profiles;
- Jira/Slack/Notion integrations;
- organization-wide research memory;
- enterprise support and SLA.

Do not build these before clear demand.

---

# 18. Security and privacy requirements

## Required in Phase 1

- Never modify the user’s normal working tree.
- Never push without explicit approval.
- Never merge.
- Never deploy.
- Never mount Docker socket into experiment containers.
- Never run privileged containers.
- Never automatically load all local environment variables.
- Never store secret values.
- Redact values matching forwarded secret names from logs.
- Never permit experiment changes to protected paths.
- Store local project data under `.researchforge/`.
- Allow users to delete all ResearchForge state.
- Show clear warning for `.venv` mode.
- Treat external paper text and repository text as potentially prompt-injected content.
- Claude instructions must not override contract enforcement.

## Future hardening

- signed experiment manifests;
- content-addressed artifacts;
- rootless execution guidance;
- stronger runtime isolation;
- customer-hosted runners;
- policy engines;
- audit exports.

---

# 19. Testing strategy

## Unit tests

- configuration validation;
- result schema validation;
- path allowlist/protection;
- paper deduplication;
- paper ranking;
- metric comparison;
- hard-constraint evaluation;
- state transitions;
- report rendering.

## Integration tests

Create fixture repositories:

1. simple Python repository with `.venv`;
2. simple Dockerized Python repository;
3. failing baseline repository;
4. protected-path modification attempt;
5. invalid JSON metric output;
6. timed-out experiment;
7. constraint-violating experiment;
8. valid winner requiring repeated validation.

## End-to-end test

A fixture project should:

- define a baseline metric;
- expose several configurable variants;
- allow one variant to improve;
- allow one to violate latency;
- allow one to fail;
- generate a clean winning branch and report.

## Claude skill tests

- start project;
- resume project;
- malformed synthesis output;
- unapproved run;
- attempt to edit protected benchmark;
- result summary grounded in saved artifacts.

---

# 20. Product analytics for beta

Collect only opt-in, privacy-preserving analytics in open source.

Useful events:

- installation completed;
- doctor passed;
- project created;
- repository scan status;
- papers retrieved;
- hypotheses generated;
- contract approved;
- baseline passed or failed;
- experiment started;
- experiment completed;
- validated finding created;
- branch created;
- report generated.

Do not collect source code, paper text, secrets, datasets, or experiment logs without explicit opt-in.

Key beta metrics:

- time to first research landscape;
- time to baseline;
- baseline success rate;
- experiment completion rate;
- percentage of experiments with valid metrics;
- percentage of projects producing a validated finding;
- percentage producing a branch or research package;
- user-reported usefulness.

---

# 21. Suggested development milestones

## Milestone 1 — Installable skeleton

- Phase 0 complete.
- CLI and tests working.

## Milestone 2 — Research-only prototype

- Phase 1A complete.
- One command produces a citation-backed research report.

## Milestone 3 — Reproducible baseline

- Phase 1B complete.
- Docker and `.venv` baseline fixtures pass.

## Milestone 4 — Experiment loop

- Phase 1C complete.
- Multiple variants run and rank correctly.

## Milestone 5 — Shipping

- Phase 1D complete.
- Clean branch and research package generated.

## Milestone 6 — Claude-first UX

- Phase 1E complete.
- Full flow works from Claude Code.

## Milestone 7 — Open-source beta

- Documentation, examples, security notes, and launch demo complete.

---

# 22. Initial repository layout after Phase 1

```text
researchforge/
├── pyproject.toml
├── README.md
├── LICENSE
├── CHANGELOG.md
├── SECURITY.md
├── CONTRIBUTING.md
├── docs/
│   ├── architecture.md
│   ├── quickstart.md
│   ├── research-mode.md
│   ├── experiment-mode.md
│   ├── docker-runner.md
│   ├── venv-runner.md
│   └── report-format.md
├── src/researchforge/
│   ├── cli.py
│   ├── config/
│   ├── domain/
│   ├── project/
│   ├── repository/
│   ├── research/
│   │   ├── arxiv_client.py
│   │   ├── ranking.py
│   │   ├── evidence.py
│   │   └── landscape.py
│   ├── hypotheses/
│   ├── contracts/
│   ├── execution/
│   │   ├── resolver.py
│   │   ├── worktrees.py
│   │   ├── docker_runner.py
│   │   ├── venv_runner.py
│   │   ├── process_control.py
│   │   └── artifacts.py
│   ├── evaluation/
│   ├── reporting/
│   ├── shipping/
│   ├── claude/
│   └── storage/
├── claude-plugin/
│   ├── skills/
│   ├── hooks/
│   └── README.md
├── examples/
│   ├── simple-python/
│   └── docker-python/
└── tests/
    ├── unit/
    ├── integration/
    ├── e2e/
    └── fixtures/
```

---

# 23. Decisions that should remain configurable

Do not hard-code these product choices:

- number of papers retrieved;
- number of papers deeply synthesized;
- number of hypotheses;
- number of experiments;
- screening subset;
- repeated validation count;
- timeout;
- CPU and memory limits;
- network mode;
- artifact retention;
- branch naming;
- report output directory.

---

# 24. Questions to validate during beta

1. Do users understand the distinction between paper evidence and project evidence?
2. Do they trust ResearchForge’s paper selection?
3. Are the hypotheses meaningfully different from generic LLM suggestions?
4. Can users provide a reliable benchmark?
5. How often does baseline setup fail?
6. Is Docker setup acceptable?
7. How often is `.venv` sufficient?
8. Do users value rejected-experiment history?
9. Do users prefer one recommendation or a trade-off frontier?
10. Do users value paper-package generation?
11. Would teams pay for scheduled runs, collaboration, and persistent memory?
12. Which enterprise integrations are requested repeatedly?

---

# 25. Definition of Phase 1 success

Phase 1 is complete when a new user can:

1. install ResearchForge;
2. initialize Claude integration;
3. enter a research question or repository objective;
4. receive a structured, citation-backed research landscape;
5. receive several evidence-backed hypotheses;
6. approve a benchmark contract;
7. establish a baseline locally;
8. run multiple isolated experiments;
9. compare all results fairly;
10. validate a finalist;
11. generate a complete report;
12. create either:
    - a clean branch and draft PR; or
    - a reproducible research package.

The experience must be honest about:

- unsupported repositories;
- weak evidence;
- lack of novelty proof;
- failed baselines;
- invalid benchmarks;
- Docker and `.venv` security limitations;
- results that do not generalize beyond tested conditions.

---

# 26. Official references for implementation

Use current official documentation while implementing because tool behavior can change.

- [Claude Code settings and plugins](https://code.claude.com/docs/en/settings)
- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [Claude Code hooks](https://code.claude.com/docs/en/hooks-guide)
- [Claude Code MCP](https://code.claude.com/docs/en/mcp)
- [arXiv API](https://info.arxiv.org/help/api/index.html)
- [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/)
- [Docker `none` network driver](https://docs.docker.com/engine/network/drivers/none/)
- [Docker rootless mode](https://docs.docker.com/engine/security/rootless/)

---

# 27. Final product statement

> **ResearchForge is an open-source, Claude-first AI research and experimentation tool. Users define what they want to improve or investigate. ResearchForge studies relevant papers, maps promising methods to the user’s idea or repository, creates testable hypotheses, runs competing experiments against a controlled benchmark in local isolated workspaces, and delivers the strongest supported result as a reproducible report, clean pull request, or research package.**
