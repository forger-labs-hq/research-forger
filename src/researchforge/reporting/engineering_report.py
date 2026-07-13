"""Engineering report (spec §16, first list) — the full evidence chain from
objective through validated recommendation, from recorded data only."""

from __future__ import annotations

from datetime import UTC, datetime

from researchforge import __version__
from researchforge.domain.baseline import BaselineRun
from researchforge.domain.contract import ExperimentContract
from researchforge.domain.deliverable import Deliverable, DeliverableKind
from researchforge.domain.experiment import (
    Experiment,
    ExperimentExecution,
    ExperimentPlan,
    ExperimentStatus,
)
from researchforge.domain.hypothesis import Hypothesis
from researchforge.domain.landscape import ResearchLandscape
from researchforge.domain.paper import Paper
from researchforge.domain.project import Project
from researchforge.domain.repo_scan import RepoScan
from researchforge.execution.ranking import RankingReport
from researchforge.reporting.research_report import (
    EPISTEMIC_LEGEND,
    hypothesis_section,
    landscape_sections,
    references_section,
)

TESTS_HONESTY_NOTE = (
    "Existing tests were executed via the contract test_command where configured; "
    "no new tests were authored by ResearchForge."
)


def reproduction_steps(contract: ExperimentContract, plans: list[ExperimentPlan]) -> list[str]:
    """The exact command sequence that reproduces the recorded results."""
    steps = [
        "researchforge contract approve",
        "researchforge baseline run",
    ]
    for plan in plans:
        steps += [
            f"researchforge experiment plan {plan.hypothesis_id}",
            "researchforge experiment import .researchforge/experiments/plan.yaml",
            f"researchforge experiment approve {plan.plan_id} --yes",
            f"researchforge experiment run {plan.plan_id}",
        ]
    steps.append("researchforge validate <run-id>")
    steps.append("researchforge ship branch")
    return steps


def build_engineering_report(
    project: Project,
    scan: RepoScan | None,
    landscape: ResearchLandscape | None,
    papers: list[Paper],
    hypotheses: list[Hypothesis],
    contract: ExperimentContract,
    baseline: BaselineRun,
    plans: list[ExperimentPlan],
    experiments: list[Experiment],
    executions: list[ExperimentExecution],
    ranking: RankingReport | None,
    deliverables: list[Deliverable],
) -> str:
    spec = contract.spec
    primary = spec.objective.primary_metric.name
    papers_by_id = {p.paper_id: p for p in papers}
    assert baseline.metrics is not None
    lines: list[str] = []

    # 1. Objective
    lines += [
        f"# Engineering Report: {project.name}",
        "",
        f"- **Generated:** {datetime.now(UTC).isoformat(timespec='seconds')} "
        f"(ResearchForge {__version__})",
        "",
        "## 1. Objective",
        "",
        spec.objective.description.strip(),
        "",
        f"Primary metric: **{primary}** ({spec.objective.primary_metric.direction.value}).",
        "",
    ]

    # 2. Repository and baseline
    lines += ["## 2. Repository and baseline", ""]
    if scan is not None:
        lines.append(f"- Repository: `{scan.repo_path}`")
    lines += [
        f"- Baseline commit: `{contract.baseline_commit}`",
        f"- Environment: {baseline.execution_mode.value} ({baseline.fingerprint.platform})",
        f"- {primary}: {baseline.metrics.primary_metric.value}",
    ]
    for name, value in baseline.metrics.secondary_metrics.items():
        lines.append(f"- {name}: {value}")
    lines.append("")

    # 3-4. Research reviewed / directions
    lines += ["## 3. Research reviewed", ""]
    if papers:
        lines.append(f"{len(papers)} paper(s) retrieved and stored; see References.")
    else:
        lines.append("No papers recorded for this project.")
    lines.append("")
    lines += ["## 4. Research directions", ""]
    lines += landscape_sections(landscape, papers_by_id)[2:] or ["None recorded.", ""]

    # 5. Hypotheses
    lines += ["## 5. Hypotheses", ""]
    if hypotheses:
        for hypothesis in hypotheses:
            lines.extend(hypothesis_section(hypothesis))
    else:
        lines += ["None recorded.", ""]

    # 6. Experiment contract
    lines += [
        "## 6. Experiment contract",
        "",
        f"- Contract: `{contract.contract_id}` v{contract.contract_version} "
        f"(approved {contract.approved_at.date().isoformat()})",
        f"- Evaluation: `{spec.execution.full_command}` -> `{spec.execution.result_file}`",
    ]
    if spec.execution.screening_command:
        lines.append(f"- Screening: `{spec.execution.screening_command}`")
    if spec.execution.test_command:
        lines.append(f"- Tests: `{spec.execution.test_command}`")
    for constraint in spec.objective.hard_constraints:
        lines.append(
            f"- Hard constraint: {constraint.name} {constraint.operator.value} {constraint.value}"
        )
    lines += [
        f"- Limits: {spec.execution.timeout_minutes} min timeout, "
        f"{spec.execution.cpu_limit:g} CPU, {spec.execution.memory_mb} MB, "
        f"max {spec.execution.max_experiments} experiments",
        f"- Validation policy: {spec.validation.repeat_finalists} repeated finalist run(s)",
        f"- Shipping: branch={'allowed' if spec.shipping.allow_branch_creation else 'off'}, "
        f"draft PR={'allowed' if spec.shipping.allow_draft_pr else 'off'}",
        "",
    ]

    # 7. Experiments attempted
    lines += [
        "## 7. Experiments attempted",
        "",
        "| Experiment | Title | Status | Stage reached | Result |",
        "|---|---|---|---|---|",
    ]
    stage_by_experiment: dict[str, str] = {}
    value_by_experiment: dict[str, str] = {}
    for execution in executions:
        stage_by_experiment[execution.experiment_id] = execution.benchmark_stage.value
        if execution.metrics is not None:
            value_by_experiment[execution.experiment_id] = (
                f"{primary}={execution.metrics.primary_metric.value}"
            )
    for experiment in experiments:
        lines.append(
            f"| {experiment.experiment_id} | {experiment.title} | "
            f"{experiment.status.value} | "
            f"{stage_by_experiment.get(experiment.experiment_id, 'never ran')} | "
            f"{value_by_experiment.get(experiment.experiment_id, '—')} |"
        )
    lines.append("")

    # 8. Rejected approaches
    lines += ["## 8. Rejected approaches", ""]
    non_viable = [
        e
        for e in experiments
        if e.status
        in (
            ExperimentStatus.REJECTED,
            ExperimentStatus.FAILED_SETUP,
            ExperimentStatus.FAILED_EXECUTION,
            ExperimentStatus.CANCELLED,
        )
    ]
    if non_viable:
        for experiment in non_viable:
            reason = experiment.decision.reason if experiment.decision else experiment.status.value
            lines.append(
                f"- **{experiment.experiment_id}** ({experiment.title}): "
                f"{experiment.change_summary} — {reason}"
            )
    else:
        lines.append("None.")
    lines.append("")

    # 9-10. Full benchmark + validation results
    lines += ["## 9. Full benchmark results", ""]
    fulls = [e for e in executions if e.benchmark_stage.value == "full"]
    if fulls:
        for execution in fulls:
            rendered = (
                str(execution.metrics.primary_metric.value)
                if execution.metrics is not None
                else "invalid"
            )
            lines.append(
                f"- {execution.experiment_id} (attempt {execution.attempt}): "
                f"{execution.status.value}, {primary}={rendered}"
            )
    else:
        lines.append("No full-benchmark executions recorded.")
    lines.append("")
    lines += ["## 10. Validation results", ""]
    validations = [e for e in executions if e.benchmark_stage.value == "validation"]
    if validations:
        for execution in validations:
            rendered = (
                str(execution.metrics.primary_metric.value)
                if execution.metrics is not None
                else "invalid"
            )
            lines.append(
                f"- {execution.experiment_id} attempt {execution.attempt}: "
                f"{execution.status.value}, {primary}={rendered}"
            )
    else:
        lines.append("No validation runs recorded — no result may be called validated.")
    lines.append("")

    # 11. Trade-offs
    lines += ["## 11. Trade-offs", ""]
    if ranking is not None and ranking.candidates:
        if len(ranking.pareto_ids) > 1:
            lines.append(f"Pareto frontier: {', '.join(ranking.pareto_ids)}.")
        for note in ranking.trade_off_notes:
            lines.append(f"- {note}")
        for caveat in ranking.caveats:
            lines.append(f"- {caveat}")
        if ranking.single_winner:
            lines.append(f"Single winner: **{ranking.single_winner}**.")
    else:
        lines.append("No viable candidates to compare.")
    lines.append("")

    # 12. Recommended implementation
    lines += ["## 12. Recommended implementation", ""]
    shipped = [d for d in deliverables if d.kind is DeliverableKind.BRANCH]
    winners = [
        e
        for e in experiments
        if e.status in (ExperimentStatus.VALIDATED, ExperimentStatus.IMPLEMENTATION_READY)
    ]
    if winners:
        winner = winners[-1]
        lines += [
            f"**{winner.experiment_id} — {winner.title}**: {winner.change_summary}",
            "",
            f"Changed files: {', '.join(f'`{f}`' for f in winner.changed_files)}",
        ]
        if shipped:
            lines.append(
                f"Shipped as branch `{shipped[-1].location}` "
                f"(commit `{(shipped[-1].commit_sha or '')[:12]}`)."
            )
        else:
            lines.append("Not yet shipped — run `researchforge ship branch`.")
    else:
        lines.append("No validated implementation to recommend.")
    lines.append("")

    # 13. Risks and limitations
    lines += ["## 13. Risks and limitations", ""]
    for hypothesis in hypotheses:
        for limitation in hypothesis.limitations:
            lines.append(f"- {limitation}")
    lines += [
        f"- Results were measured on a single machine in "
        f"{baseline.execution_mode.value} mode; they may not generalize beyond the "
        "tested conditions.",
        f"- {TESTS_HONESTY_NOTE}",
        "",
        "### How to read this report",
        "",
        EPISTEMIC_LEGEND,
        "",
    ]

    # 14. Reproduction
    lines += ["## 14. Exact reproduction steps", "", "```bash"]
    lines += reproduction_steps(contract, plans)
    lines += ["```", ""]

    # 15. Commits and artifact paths
    lines += [
        "## 15. Commits and artifact paths",
        "",
        f"- Baseline commit: `{contract.baseline_commit}`",
    ]
    for deliverable in deliverables:
        sha = f" (commit `{deliverable.commit_sha[:12]}`)" if deliverable.commit_sha else ""
        lines.append(f"- {deliverable.kind.value}: {deliverable.location}{sha}")
    lines += [
        "- Experiment artifacts: `.researchforge/artifacts/experiments/`",
        "- Baseline artifacts: `.researchforge/artifacts/baseline/`",
        "",
    ]

    # 16. Future experiments
    lines += ["## 16. Future experiments", ""]
    future: list[str] = []
    validated_hypotheses = {
        e.hypothesis_id
        for e in experiments
        if e.status in (ExperimentStatus.VALIDATED, ExperimentStatus.IMPLEMENTATION_READY)
    }
    for hypothesis in hypotheses:
        if hypothesis.hypothesis_id not in validated_hypotheses:
            future.append(
                f"- {hypothesis.hypothesis_id} ({hypothesis.title}) has no validated "
                "experiment yet."
            )
    for experiment in experiments:
        if experiment.decision is not None and experiment.decision.outcome.value == "investigate":
            future.append(
                f"- {experiment.experiment_id}: marked investigate — {experiment.decision.reason}"
            )
    lines += future or ["None recorded."]
    lines.append("")

    lines += references_section(landscape, hypotheses, papers_by_id)
    return "\n".join(lines)
