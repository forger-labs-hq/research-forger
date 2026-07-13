"""Experiment funnel execution: screening -> full, one experiment at a time.

Every stage attempt runs in its own detached worktree at the plan's baseline
commit, with the experiment patch applied and re-checked against the path
guard before any command runs (defense in depth — import already rejected
protected-path patches). Failures never abort the run; results persist under
artifacts after the worktree is removed.
"""

from __future__ import annotations

import contextlib
import platform as platform_module
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from researchforge.config.paths import (
    contract_path,
    experiment_artifacts_dir,
)
from researchforge.config.settings import ResearchSettings, load_settings
from researchforge.contract.service import check_contract_drift
from researchforge.domain.baseline import BaselineRun, BaselineStatus, EnvironmentFingerprint
from researchforge.domain.contract import ExperimentContract, MetricDirection
from researchforge.domain.environment import DockerProbe, EnvironmentResolution
from researchforge.domain.experiment import (
    BenchmarkStage,
    ConstraintResult,
    Decision,
    DecisionOutcome,
    ExecutionArtifacts,
    ExecutionRecordStatus,
    Experiment,
    ExperimentExecution,
    ExperimentPlan,
    ExperimentRunGroup,
    ExperimentStatus,
    PlanStatus,
    RunStatus,
    advance,
    execution_status_from_evaluation,
)
from researchforge.domain.project import Project
from researchforge.domain.repo_scan import CompatibilityStatus
from researchforge.execution import venv_exec
from researchforge.execution.baseline import BaselineBlockedError, _redact_logs, baseline_gate
from researchforge.execution.constraints import evaluate_constraints, violated
from researchforge.execution.environment import probe_docker, resolve_environment
from researchforge.execution.evaluation import run_evaluation
from researchforge.execution.metrics import MetricResult
from researchforge.execution.path_guard import check_changed_paths
from researchforge.execution.runner import CommandRunner, SubprocessRunner
from researchforge.execution.worktrees import WorktreeError, WorktreeManager
from researchforge.storage.baseline_repository import insert_baseline_run
from researchforge.storage.contract_repository import get_active_contract
from researchforge.storage.experiment_repository import (
    get_open_run_for_plan,
    get_plan,
    get_run,
    insert_execution,
    insert_run,
    list_executions,
    list_experiments,
    next_run_id,
    update_execution,
    update_experiment,
    update_plan_status,
    update_run,
)
from researchforge.storage.project_repository import get_project
from researchforge.storage.scan_repository import get_latest_scan


class ExperimentBlockedError(Exception):
    """The run cannot proceed; message is user-facing."""

    def __init__(self, reason: str, resolution: EnvironmentResolution | None = None) -> None:
        self.reason = reason
        self.resolution = resolution
        super().__init__(reason)


@dataclass
class RunPreparation:
    project: Project
    contract: ExperimentContract
    plan: ExperimentPlan
    baseline: BaselineRun
    repo_root: Path
    resolution: EnvironmentResolution
    settings: ResearchSettings


@dataclass
class RunSummary:
    run_id: str
    counts: dict[str, int]
    promising: list[str]
    next_action: str


def prepare_run(
    conn: sqlite3.Connection,
    plan_id: str,
    docker: DockerProbe | None = None,
    *,
    allow_completed: bool = False,
) -> RunPreparation:
    """All gates, in order, each with an exact explanation."""
    project = get_project(conn)
    if project is None:
        raise ExperimentBlockedError("No project found. Run `researchforge project create`.")
    contract = get_active_contract(conn)
    if contract is None:
        raise ExperimentBlockedError("No approved contract. Run `researchforge contract approve`.")
    repo_root = Path(project.repository.path) if project.repository.path else Path.cwd()
    if check_contract_drift(conn, contract_path(repo_root)):
        raise ExperimentBlockedError(
            "researchforge.yaml changed since approval — re-approve before running experiments."
        )
    try:
        baseline = baseline_gate(conn)
    except BaselineBlockedError as exc:
        raise ExperimentBlockedError(str(exc)) from None

    plan = get_plan(conn, plan_id)
    if plan is None:
        raise ExperimentBlockedError(
            f"Unknown plan: {plan_id}. See `researchforge experiment list`."
        )
    if plan.status is PlanStatus.PLANNED:
        raise ExperimentBlockedError(
            f"{plan_id} is not approved — run `researchforge experiment approve {plan_id}`."
        )
    blocked_states = (
        (PlanStatus.CANCELLED,) if allow_completed else (PlanStatus.COMPLETED, PlanStatus.CANCELLED)
    )
    if plan.status in blocked_states:
        raise ExperimentBlockedError(f"{plan_id} is {plan.status.value} — plan a new batch.")
    if plan.contract_version != contract.contract_version:
        raise ExperimentBlockedError(
            f"{plan_id} was planned against contract v{plan.contract_version} but "
            f"v{contract.contract_version} is active — re-plan and re-import (stale plan)."
        )
    if plan.baseline_id != baseline.baseline_id:
        raise ExperimentBlockedError(
            f"{plan_id} was planned against baseline {plan.baseline_id[:12]} but the "
            "latest successful baseline differs — re-plan and re-import (stale plan)."
        )

    scan = get_latest_scan(conn)
    if scan is None:
        raise ExperimentBlockedError("No repository scan. Run `researchforge repo scan`.")
    resolution = resolve_environment(contract.spec, scan, docker or probe_docker())
    if resolution.status is not CompatibilityStatus.READY:
        raise ExperimentBlockedError("The repository is not ready for execution.", resolution)
    if resolution.execution_mode is not baseline.fingerprint.execution_mode:
        raise ExperimentBlockedError(
            f"Environment mode changed: the baseline ran in "
            f"{baseline.fingerprint.execution_mode.value} but "
            f"{resolution.execution_mode.value} would be used now — results would not "
            "be comparable. Re-run `researchforge baseline run` or restore the "
            "original environment."
        )

    return RunPreparation(
        project=project,
        contract=contract,
        plan=plan,
        baseline=baseline,
        repo_root=repo_root,
        resolution=resolution,
        settings=load_settings(),
    )


def _run_screening_baseline(
    conn: sqlite3.Connection, prep: RunPreparation, run_id: str, runner: CommandRunner
) -> BaselineRun:
    """Execute the screening command at the baseline commit (spec §4.3:
    screening metrics are only comparable to a screening-stage baseline)."""
    spec = prep.contract.spec
    assert spec.execution.screening_command is not None
    manager = WorktreeManager(prep.repo_root)
    worktree = manager.create(
        f"{run_id}-screening-baseline", prep.plan.baseline_commit, recreate=True
    )
    baseline_id = uuid4().hex
    run_artifacts = experiment_artifacts_dir(prep.repo_root) / run_id / "screening-baseline"
    run_artifacts.mkdir(parents=True, exist_ok=True)
    secrets = venv_exec.forwarded_values(spec.secrets.forward_environment_variables)
    started_at = datetime.now(UTC)

    outcome = run_evaluation(
        spec=spec,
        engine=prep.resolution.execution_mode,
        command=spec.execution.screening_command,
        worktree=worktree,
        run_artifacts=run_artifacts,
        runner=runner,
        secrets=secrets,
        timeout_seconds=spec.execution.timeout_minutes * 60.0,
        fingerprint=EnvironmentFingerprint(
            platform=platform_module.platform(),
            execution_mode=prep.resolution.execution_mode,
            contract_id=prep.contract.contract_id,
            contract_version=prep.contract.contract_version,
            commit_sha=prep.plan.baseline_commit,
        ),
        name_slug=f"sb-{baseline_id[:12]}",
    )
    _redact_logs(sorted(run_artifacts.glob("*.log")), secrets)
    manager.remove(f"{run_id}-screening-baseline")

    completed_at = datetime.now(UTC)
    status_map = {
        "succeeded": BaselineStatus.SUCCEEDED,
        "failed_setup": BaselineStatus.FAILED_SETUP,
        "failed_tests": BaselineStatus.FAILED_EXECUTION,
        "failed_execution": BaselineStatus.FAILED_EXECUTION,
        "failed_timeout": BaselineStatus.FAILED_TIMEOUT,
        "failed_invalid_result": BaselineStatus.FAILED_INVALID_RESULT,
    }
    run = BaselineRun(
        baseline_id=baseline_id,
        contract_id=prep.contract.contract_id,
        contract_version=prep.contract.contract_version,
        commit_sha=prep.plan.baseline_commit,
        execution_mode=prep.resolution.execution_mode,
        command=spec.execution.screening_command,
        command_kind="screening",
        status=status_map[outcome.status.value],
        failure_reason=outcome.failure_reason,
        metrics=outcome.metrics,
        warnings=outcome.warnings,
        fingerprint=outcome.fingerprint,
        stdout_path=str(run_artifacts / "stdout.log"),
        stderr_path=str(run_artifacts / "stderr.log"),
        results_path=outcome.results_path,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=(completed_at - started_at).total_seconds(),
    )
    (run_artifacts / "baseline_run.json").write_text(run.model_dump_json(indent=2), "utf-8")
    insert_baseline_run(conn, prep.project.id, run)
    return run


def start_run(
    conn: sqlite3.Connection,
    plan_id: str,
    *,
    runner: CommandRunner | None = None,
    docker: DockerProbe | None = None,
) -> tuple[RunPreparation, ExperimentRunGroup]:
    """Create a run group and its screening baseline (if configured)."""
    prep = prepare_run(conn, plan_id, docker)
    open_run = get_open_run_for_plan(conn, plan_id)
    if open_run is not None:
        raise ExperimentBlockedError(
            f"{open_run.run_id} is already in progress for {plan_id} — use "
            f"`researchforge experiment resume {open_run.run_id}`."
        )

    active_runner: CommandRunner = runner or SubprocessRunner()
    run = ExperimentRunGroup(
        run_id=next_run_id(conn),
        plan_id=plan_id,
        execution_mode=prep.resolution.execution_mode,
        started_at=datetime.now(UTC),
    )
    insert_run(conn, prep.project.id, run)
    update_plan_status(conn, plan_id, PlanStatus.RUNNING)

    if prep.contract.spec.execution.screening_command is not None:
        screening_baseline = _run_screening_baseline(conn, prep, run.run_id, active_runner)
        run = run.model_copy(update={"screening_baseline_id": screening_baseline.baseline_id})
        if screening_baseline.status is not BaselineStatus.SUCCEEDED:
            run = run.model_copy(
                update={
                    "status": RunStatus.COMPLETED,
                    "completed_at": datetime.now(UTC),
                    "warnings": [
                        "Screening baseline failed "
                        f"({screening_baseline.status.value}: "
                        f"{screening_baseline.failure_reason}) — screening comparisons "
                        "would be meaningless, so no experiments were run."
                    ],
                }
            )
        update_run(conn, run)
    return prep, run


def _screening_decision(
    metrics: MetricResult | None,
    constraint_results: list[ConstraintResult],
    screening_baseline: BaselineRun | None,
    direction: MetricDirection,
    settings: ResearchSettings,
) -> Decision:
    """Shortlist rule: valid metrics, no violated evaluated constraint, and
    primary not catastrophically worse than the screening baseline."""
    assert metrics is not None  # caller checks evaluation succeeded
    bad = violated(constraint_results)
    if bad:
        names = ", ".join(f"{v.name} ({v.detail})" for v in bad)
        return Decision(
            outcome=DecisionOutcome.REJECT, reason=f"hard constraint violated at screening: {names}"
        )
    if screening_baseline is not None and screening_baseline.metrics is not None:
        base_value = screening_baseline.metrics.primary_metric.value
        candidate = metrics.primary_metric.value
        margin = settings.screening_reject_margin_pct / 100.0
        if base_value != 0:
            if direction is MetricDirection.MAXIMIZE:
                worse = (base_value - candidate) / abs(base_value)
            else:
                worse = (candidate - base_value) / abs(base_value)
            if worse > margin:
                return Decision(
                    outcome=DecisionOutcome.REJECT,
                    reason=(
                        f"screening primary metric {candidate} is {worse * 100.0:.1f}% worse "
                        f"than the screening baseline {base_value} "
                        f"(> {settings.screening_reject_margin_pct}% margin)"
                    ),
                )
    return Decision(outcome=DecisionOutcome.KEEP, reason="passed screening")


def _full_decision(
    metrics: MetricResult | None,
    constraint_results: list[ConstraintResult],
    full_baseline: BaselineRun,
    direction: MetricDirection,
) -> tuple[Decision, ExperimentStatus]:
    assert metrics is not None
    bad = violated(constraint_results)
    if bad:
        names = ", ".join(f"{v.name} ({v.detail})" for v in bad)
        return (
            Decision(outcome=DecisionOutcome.REJECT, reason=f"hard constraint violated: {names}"),
            ExperimentStatus.REJECTED,
        )
    assert full_baseline.metrics is not None
    base_value = full_baseline.metrics.primary_metric.value
    candidate = metrics.primary_metric.value
    improved = (
        candidate > base_value if direction is MetricDirection.MAXIMIZE else candidate < base_value
    )
    if improved:
        return (
            Decision(
                outcome=DecisionOutcome.KEEP,
                reason=(
                    f"primary metric improved vs baseline ({base_value} -> {candidate}); "
                    "one controlled run — not yet validated"
                ),
            ),
            ExperimentStatus.PROMISING,
        )
    return (
        Decision(
            outcome=DecisionOutcome.REJECT,
            reason=f"primary metric did not improve vs baseline ({base_value} -> {candidate})",
        ),
        ExperimentStatus.REJECTED,
    )


def execute_stage(
    conn: sqlite3.Connection,
    prep: RunPreparation,
    run: ExperimentRunGroup,
    experiment: Experiment,
    stage: BenchmarkStage,
    attempt: int,
    runner: CommandRunner,
    *,
    extra_env: dict[str, str] | None = None,
) -> ExperimentExecution:
    """Run one stage attempt in a fresh worktree; persists the execution row
    (inserted as `running` first so interruptions are detectable)."""
    spec = prep.contract.spec
    command = (
        spec.execution.screening_command
        if stage is BenchmarkStage.SCREENING
        else spec.execution.full_command
    )
    assert command is not None
    worktree_name = f"{run.run_id}-{experiment.experiment_id}-{stage.value}-a{attempt}"
    run_artifacts = (
        experiment_artifacts_dir(prep.repo_root)
        / run.run_id
        / experiment.experiment_id
        / f"{stage.value}-a{attempt}"
    )
    run_artifacts.mkdir(parents=True, exist_ok=True)
    diff_path = run_artifacts / "diff.patch"
    diff_path.write_text(experiment.patch_text, encoding="utf-8")

    execution = ExperimentExecution(
        execution_id=uuid4().hex,
        experiment_id=experiment.experiment_id,
        run_id=run.run_id,
        hypothesis_id=experiment.hypothesis_id,
        baseline_commit=prep.plan.baseline_commit,
        parent_experiment_id=experiment.parent_experiment_id,
        execution_mode=prep.resolution.execution_mode,
        benchmark_stage=stage,
        attempt=attempt,
        change_summary=experiment.change_summary,
        changed_files=experiment.changed_files,
        commands=[],
        started_at=datetime.now(UTC),
        status=ExecutionRecordStatus.RUNNING,
        artifacts=ExecutionArtifacts(
            diff_path=str(diff_path),
            stdout_path=str(run_artifacts / "stdout.log"),
            stderr_path=str(run_artifacts / "stderr.log"),
        ),
        fingerprint=EnvironmentFingerprint(
            platform=platform_module.platform(),
            execution_mode=prep.resolution.execution_mode,
            contract_id=prep.contract.contract_id,
            contract_version=prep.contract.contract_version,
            commit_sha=prep.plan.baseline_commit,
        ),
    )
    insert_execution(conn, prep.project.id, execution)

    manager = WorktreeManager(prep.repo_root)
    secrets = venv_exec.forwarded_values(spec.secrets.forward_environment_variables)
    try:
        worktree = manager.create(worktree_name, prep.plan.baseline_commit, recreate=True)
        try:
            manager.apply_patch(worktree, diff_path)
        except WorktreeError as exc:
            execution = execution.model_copy(
                update={
                    "status": ExecutionRecordStatus.FAILED_SETUP,
                    "failure_reason": f"patch failed to apply: {exc}",
                    "completed_at": datetime.now(UTC),
                }
            )
            update_execution(conn, execution)
            return execution

        # Defense in depth: re-check what actually changed, and refuse symlinks.
        changed_now = manager.changed_paths(worktree)
        guard = check_changed_paths(changed_now, spec.permissions)
        symlinks = [path for path in changed_now if (worktree / path).is_symlink()]
        if not guard.allowed or symlinks:
            details = ", ".join(
                [f"{v.path} ({v.rule.value})" for v in guard.violations]
                + [f"{s} (symlink)" for s in symlinks]
            )
            execution = execution.model_copy(
                update={
                    "status": ExecutionRecordStatus.REJECTED_PATHS,
                    "failure_reason": f"applied patch touches disallowed paths: {details}",
                    "completed_at": datetime.now(UTC),
                }
            )
            update_execution(conn, execution)
            return execution

        outcome = run_evaluation(
            spec=spec,
            engine=prep.resolution.execution_mode,
            command=command,
            worktree=worktree,
            run_artifacts=run_artifacts,
            runner=runner,
            secrets=secrets,
            timeout_seconds=spec.execution.timeout_minutes * 60.0,
            fingerprint=execution.fingerprint,
            name_slug=f"{experiment.experiment_id}-{stage.value}-a{attempt}",
            test_command=spec.execution.test_command,
            extra_env=extra_env,
        )
        constraint_results = (
            evaluate_constraints(outcome.metrics, spec.objective.hard_constraints, stage=stage)
            if outcome.ok
            else []
        )
        _redact_logs(sorted(run_artifacts.glob("*.log")), secrets)
        completed_at = datetime.now(UTC)
        execution = execution.model_copy(
            update={
                "status": execution_status_from_evaluation(outcome.status),
                "failure_reason": outcome.failure_reason,
                "metrics": outcome.metrics,
                "constraints": constraint_results,
                "commands": outcome.commands,
                "warnings": outcome.warnings,
                "fingerprint": outcome.fingerprint,
                "completed_at": completed_at,
                "duration_seconds": (completed_at - execution.started_at).total_seconds(),
                "artifacts": execution.artifacts.model_copy(
                    update={"results_path": outcome.results_path}
                ),
            }
        )
        update_execution(conn, execution)
        return execution
    finally:
        with contextlib.suppress(WorktreeError):
            manager.remove(worktree_name)
        (run_artifacts / "manifest.json").write_text(
            execution.model_dump_json(indent=2), encoding="utf-8"
        )


def _set_experiment(
    conn: sqlite3.Connection,
    experiment: Experiment,
    status: ExperimentStatus,
    decision: Decision | None = None,
) -> Experiment:
    updated = experiment.model_copy(
        update={
            "status": advance(experiment.status, status),
            "decision": decision if decision is not None else experiment.decision,
        }
    )
    update_experiment(conn, updated)
    return updated


def _run_one_experiment(
    conn: sqlite3.Connection,
    prep: RunPreparation,
    run: ExperimentRunGroup,
    experiment: Experiment,
    screening_baseline: BaselineRun | None,
    runner: CommandRunner,
    *,
    attempt: int = 1,
) -> Experiment:
    """Screening (if configured) then full benchmark for one experiment."""
    spec = prep.contract.spec
    direction = spec.objective.primary_metric.direction
    experiment = _set_experiment(conn, experiment, ExperimentStatus.PREPARING)

    if spec.execution.screening_command is not None:
        experiment = _set_experiment(conn, experiment, ExperimentStatus.RUNNING)
        screening = execute_stage(
            conn, prep, run, experiment, BenchmarkStage.SCREENING, attempt, runner
        )
        if screening.status is ExecutionRecordStatus.REJECTED_PATHS:
            return _set_experiment(
                conn,
                experiment,
                ExperimentStatus.REJECTED,
                Decision(outcome=DecisionOutcome.REJECT, reason=screening.failure_reason or ""),
            )
        if screening.status is ExecutionRecordStatus.FAILED_SETUP:
            return _set_experiment(
                conn,
                experiment,
                ExperimentStatus.FAILED_SETUP,
                Decision(outcome=DecisionOutcome.REJECT, reason=screening.failure_reason or ""),
            )
        if screening.status is ExecutionRecordStatus.FAILED_TESTS:
            return _set_experiment(
                conn,
                experiment,
                ExperimentStatus.REJECTED,
                Decision(
                    outcome=DecisionOutcome.REJECT,
                    reason=f"failed required tests: {screening.failure_reason}",
                ),
            )
        if screening.status is ExecutionRecordStatus.FAILED_INVALID_RESULT:
            return _set_experiment(
                conn,
                experiment,
                ExperimentStatus.REJECTED,
                Decision(
                    outcome=DecisionOutcome.REJECT,
                    reason=f"invalid metrics: {screening.failure_reason}",
                ),
            )
        if screening.status is not ExecutionRecordStatus.SUCCEEDED:
            return _set_experiment(
                conn,
                experiment,
                ExperimentStatus.FAILED_EXECUTION,
                Decision(outcome=DecisionOutcome.REJECT, reason=screening.failure_reason or ""),
            )
        decision = _screening_decision(
            screening.metrics,
            screening.constraints,
            screening_baseline,
            direction,
            prep.settings,
        )
        screening = screening.model_copy(update={"decision": decision})
        update_execution(conn, screening)
        if decision.outcome is DecisionOutcome.REJECT:
            return _set_experiment(conn, experiment, ExperimentStatus.REJECTED, decision)
    else:
        experiment = _set_experiment(conn, experiment, ExperimentStatus.RUNNING)

    full = execute_stage(conn, prep, run, experiment, BenchmarkStage.FULL, attempt, runner)
    if full.status is ExecutionRecordStatus.REJECTED_PATHS:
        return _set_experiment(
            conn,
            experiment,
            ExperimentStatus.REJECTED,
            Decision(outcome=DecisionOutcome.REJECT, reason=full.failure_reason or ""),
        )
    if full.status is ExecutionRecordStatus.FAILED_SETUP:
        return _set_experiment(
            conn,
            experiment,
            ExperimentStatus.FAILED_SETUP,
            Decision(outcome=DecisionOutcome.REJECT, reason=full.failure_reason or ""),
        )
    if full.status is ExecutionRecordStatus.FAILED_TESTS:
        return _set_experiment(
            conn,
            experiment,
            ExperimentStatus.REJECTED,
            Decision(
                outcome=DecisionOutcome.REJECT,
                reason=f"failed required tests: {full.failure_reason}",
            ),
        )
    if full.status is ExecutionRecordStatus.FAILED_INVALID_RESULT:
        return _set_experiment(
            conn,
            experiment,
            ExperimentStatus.REJECTED,
            Decision(
                outcome=DecisionOutcome.REJECT, reason=f"invalid metrics: {full.failure_reason}"
            ),
        )
    if full.status is not ExecutionRecordStatus.SUCCEEDED:
        return _set_experiment(
            conn,
            experiment,
            ExperimentStatus.FAILED_EXECUTION,
            Decision(outcome=DecisionOutcome.REJECT, reason=full.failure_reason or ""),
        )

    decision, final_status = _full_decision(
        full.metrics, full.constraints, prep.baseline, direction
    )
    full = full.model_copy(update={"decision": decision})
    update_execution(conn, full)
    return _set_experiment(conn, experiment, final_status, decision)


def _next_attempt(conn: sqlite3.Connection, run_id: str, experiment_id: str) -> int:
    attempts = [
        execution.attempt
        for execution in list_executions(conn, run_id=run_id, experiment_id=experiment_id)
    ]
    return max(attempts, default=0) + 1


def _summarize(
    conn: sqlite3.Connection, run: ExperimentRunGroup, prep: RunPreparation
) -> RunSummary:
    return _summarize_paths(conn, run, prep.repo_root)


def _summarize_paths(
    conn: sqlite3.Connection, run: ExperimentRunGroup, repo_root: Path
) -> RunSummary:
    experiments = list_experiments(conn, run.plan_id)
    counts: dict[str, int] = {}
    for experiment in experiments:
        counts[experiment.status.value] = counts.get(experiment.status.value, 0) + 1
    promising = [e.experiment_id for e in experiments if e.status is ExperimentStatus.PROMISING]
    next_action = (
        f"researchforge validate {run.run_id}"
        if promising
        else "No promising experiments — plan a new batch with `researchforge experiment plan`."
    )
    summary = RunSummary(
        run_id=run.run_id, counts=counts, promising=promising, next_action=next_action
    )
    summary_path = experiment_artifacts_dir(repo_root) / run.run_id / "run_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    import json as json_module

    summary_path.write_text(
        json_module.dumps(
            {
                "run_id": summary.run_id,
                "counts": summary.counts,
                "promising": summary.promising,
                "next_action": summary.next_action,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return summary


def execute_run(
    conn: sqlite3.Connection,
    prep: RunPreparation,
    run: ExperimentRunGroup,
    *,
    runner: CommandRunner | None = None,
) -> RunSummary:
    """One experiment at a time; a failure never aborts the run."""
    active_runner: CommandRunner = runner or SubprocessRunner()
    screening_baseline: BaselineRun | None = None
    if run.screening_baseline_id is not None:
        from researchforge.storage.baseline_repository import get_latest_baseline

        screening_baseline = get_latest_baseline(conn, command_kind="screening")

    if run.status is RunStatus.IN_PROGRESS:
        for experiment in list_experiments(conn, run.plan_id):
            if experiment.status is not ExperimentStatus.APPROVED:
                continue
            _run_one_experiment(conn, prep, run, experiment, screening_baseline, active_runner)
        run = run.model_copy(
            update={"status": RunStatus.COMPLETED, "completed_at": datetime.now(UTC)}
        )
        update_run(conn, run)
        update_plan_status(conn, run.plan_id, PlanStatus.COMPLETED)
    return _summarize(conn, run, prep)


def resume_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    runner: CommandRunner | None = None,
    docker: DockerProbe | None = None,
) -> RunSummary:
    """Recover an interrupted run: stale executions are marked failed, and
    interrupted or still-approved experiments get a fresh attempt."""
    run = get_run(conn, run_id)
    if run is None:
        raise ExperimentBlockedError(f"Unknown run: {run_id}.")
    if run.status is not RunStatus.IN_PROGRESS:
        # Completed/cancelled runs need no gates — just report their state.
        project = get_project(conn)
        assert project is not None
        repo_root = Path(project.repository.path) if project.repository.path else Path.cwd()
        return _summarize_paths(conn, run, repo_root)
    prep = prepare_run(conn, run.plan_id, docker)
    active_runner: CommandRunner = runner or SubprocessRunner()

    # Mark stale executions (process died mid-stage) as interrupted.
    interrupted_experiments: set[str] = set()
    for execution in list_executions(conn, run_id=run_id):
        if execution.status is ExecutionRecordStatus.RUNNING:
            update_execution(
                conn,
                execution.model_copy(
                    update={
                        "status": ExecutionRecordStatus.FAILED_EXECUTION,
                        "failure_reason": "interrupted (process terminated mid-stage)",
                        "completed_at": datetime.now(UTC),
                    }
                ),
            )
            interrupted_experiments.add(execution.experiment_id)

    screening_baseline: BaselineRun | None = None
    if run.screening_baseline_id is not None:
        from researchforge.storage.baseline_repository import get_latest_baseline

        screening_baseline = get_latest_baseline(conn, command_kind="screening")

    for experiment in list_experiments(conn, run.plan_id):
        # Runs are sequential, so PREPARING/RUNNING on resume always means the
        # previous process died mid-experiment — reset for a fresh attempt.
        if experiment.status in (ExperimentStatus.PREPARING, ExperimentStatus.RUNNING):
            experiment = experiment.model_copy(update={"status": ExperimentStatus.APPROVED})
            update_experiment(conn, experiment)
        if experiment.status is ExperimentStatus.APPROVED:
            attempt = _next_attempt(conn, run_id, experiment.experiment_id)
            _run_one_experiment(
                conn,
                prep,
                run,
                experiment,
                screening_baseline,
                active_runner,
                attempt=attempt,
            )

    run = run.model_copy(update={"status": RunStatus.COMPLETED, "completed_at": datetime.now(UTC)})
    update_run(conn, run)
    update_plan_status(conn, run.plan_id, PlanStatus.COMPLETED)
    return _summarize(conn, run, prep)
