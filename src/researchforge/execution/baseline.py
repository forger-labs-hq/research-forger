"""Baseline orchestration: worktree -> environment -> run -> parse -> persist.

Execution always uses the STORED approved contract snapshot, never the disk
yaml (which may have drifted). A failed baseline is persisted and blocks
experimentation via `baseline_gate`.
"""

from __future__ import annotations

import os
import platform as platform_module
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from researchforge.config.paths import artifacts_dir, contract_path
from researchforge.contract.service import check_contract_drift
from researchforge.domain.baseline import BaselineRun, BaselineStatus, EnvironmentFingerprint
from researchforge.domain.contract import ContractSpec, ExperimentContract, NetworkMode
from researchforge.domain.environment import DockerProbe, EnvironmentResolution, ExecutionEngine
from researchforge.domain.project import Project, ProjectStatus
from researchforge.domain.repo_scan import CompatibilityStatus
from researchforge.execution import docker_exec, venv_exec
from researchforge.execution.environment import probe_docker, resolve_environment
from researchforge.execution.metrics import MetricParseError, MetricResult, parse_result_file
from researchforge.execution.runner import CommandRunner, SubprocessRunner, shell_argv
from researchforge.execution.worktrees import WorktreeManager
from researchforge.project.service import touch_project_status
from researchforge.storage.baseline_repository import (
    get_latest_baseline,
    insert_baseline_run,
)
from researchforge.storage.contract_repository import get_active_contract
from researchforge.storage.project_repository import get_project
from researchforge.storage.scan_repository import get_latest_scan

BASELINE_WORKTREE = "baseline"


class BaselineBlockedError(Exception):
    """Baseline cannot run (or has not succeeded); message is user-facing."""

    def __init__(self, reason: str, resolution: EnvironmentResolution | None = None) -> None:
        self.reason = reason
        self.resolution = resolution
        super().__init__(reason)


@dataclass
class BaselinePreparation:
    project: Project
    contract: ExperimentContract
    repo_root: Path
    resolution: EnvironmentResolution


def prepare_baseline(
    conn: sqlite3.Connection, docker: DockerProbe | None = None
) -> BaselinePreparation:
    """Load contract + scan, check drift, resolve the environment."""
    project = get_project(conn)
    if project is None:
        raise BaselineBlockedError("No project found. Run `researchforge project create` first.")
    contract = get_active_contract(conn)
    if contract is None:
        raise BaselineBlockedError(
            "No approved contract. Run `researchforge contract approve` first."
        )
    repo_root = Path(project.repository.path) if project.repository.path else Path.cwd()
    if check_contract_drift(conn, contract_path(repo_root)):
        raise BaselineBlockedError(
            "researchforge.yaml changed since approval — run `researchforge contract "
            f"approve` to create contract version {contract.contract_version + 1}."
        )
    scan = get_latest_scan(conn)
    if scan is None:
        raise BaselineBlockedError("No repository scan. Run `researchforge repo scan` first.")

    resolution = resolve_environment(contract.spec, scan, docker or probe_docker())
    return BaselinePreparation(
        project=project, contract=contract, repo_root=repo_root, resolution=resolution
    )


def _redact_logs(paths: list[Path], secrets: dict[str, str]) -> None:
    """Replace forwarded secret values with <redacted:NAME> in persisted logs."""
    if not secrets:
        return
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for name, value in secrets.items():
            if value:
                text = text.replace(value, f"<redacted:{name}>")
        path.write_text(text, encoding="utf-8")


def run_baseline(
    conn: sqlite3.Connection,
    *,
    runner: CommandRunner | None = None,
    docker: DockerProbe | None = None,
) -> BaselineRun:
    """Run the baseline; persists a BaselineRun for every terminal status."""
    prep = prepare_baseline(conn, docker)
    if prep.resolution.status is not CompatibilityStatus.READY:
        raise BaselineBlockedError("The repository is not ready for execution.", prep.resolution)

    engine = prep.resolution.execution_mode
    spec = prep.contract.spec
    active_runner: CommandRunner = runner or SubprocessRunner()

    manager = WorktreeManager(prep.repo_root)
    worktree = manager.create(BASELINE_WORKTREE, spec.repository.baseline_ref, recreate=True)
    commit_sha = manager.resolve_ref(spec.repository.baseline_ref)

    baseline_id = uuid4().hex
    run_artifacts = artifacts_dir(prep.repo_root) / "baseline" / baseline_id
    run_artifacts.mkdir(parents=True, exist_ok=True)

    secrets = venv_exec.forwarded_values(spec.secrets.forward_environment_variables)
    timeout_seconds = spec.execution.timeout_minutes * 60.0
    started_at = datetime.now(UTC)

    fingerprint = EnvironmentFingerprint(
        platform=platform_module.platform(),
        execution_mode=engine,
        contract_id=prep.contract.contract_id,
        contract_version=prep.contract.contract_version,
        commit_sha=commit_sha,
    )

    status: BaselineStatus
    failure_reason: str | None = None
    metrics: MetricResult | None = None
    warnings: list[str] = []
    stdout_path = run_artifacts / "stdout.log"
    stderr_path = run_artifacts / "stderr.log"
    results_path: str | None = None

    if commit_sha != prep.contract.baseline_commit:
        warnings.append(
            f"baseline_ref {spec.repository.baseline_ref!r} moved since approval "
            f"({prep.contract.baseline_commit[:12]} -> {commit_sha[:12]}); the current "
            "commit is recorded as fact."
        )

    if engine is ExecutionEngine.VENV:
        status, failure_reason, metrics, warnings_run, results_path, fingerprint = _run_venv(
            spec=spec,
            worktree=worktree,
            run_artifacts=run_artifacts,
            runner=active_runner,
            secrets=secrets,
            timeout_seconds=timeout_seconds,
            fingerprint=fingerprint,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
    else:
        status, failure_reason, metrics, warnings_run, results_path, fingerprint = _run_docker(
            spec=spec,
            worktree=worktree,
            run_artifacts=run_artifacts,
            runner=active_runner,
            secrets=secrets,
            timeout_seconds=timeout_seconds,
            fingerprint=fingerprint,
            baseline_id=baseline_id,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
    warnings.extend(warnings_run)

    _redact_logs(sorted(run_artifacts.glob("*.log")), secrets)

    completed_at = datetime.now(UTC)
    run = BaselineRun(
        baseline_id=baseline_id,
        contract_id=prep.contract.contract_id,
        contract_version=prep.contract.contract_version,
        commit_sha=commit_sha,
        execution_mode=engine,
        command=spec.execution.full_command,
        status=status,
        failure_reason=failure_reason,
        metrics=metrics,
        warnings=warnings,
        fingerprint=fingerprint,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        results_path=results_path,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=(completed_at - started_at).total_seconds(),
    )
    (run_artifacts / "baseline_run.json").write_text(run.model_dump_json(indent=2), "utf-8")
    (run_artifacts / "fingerprint.json").write_text(fingerprint.model_dump_json(indent=2), "utf-8")
    insert_baseline_run(conn, prep.project.id, run)
    if status is BaselineStatus.SUCCEEDED:
        touch_project_status(conn, ProjectStatus.BASELINED)
    return run


def _finalize_result(
    spec: ContractSpec,
    worktree: Path,
    run_artifacts: Path,
) -> tuple[BaselineStatus, str | None, MetricResult | None, list[str], str | None]:
    """Copy and parse the result file after a successful evaluation command."""
    source = worktree / spec.execution.result_file
    copied: str | None = None
    if source.is_file():
        target = run_artifacts / "results.json"
        shutil.copyfile(source, target)
        copied = str(target)
    try:
        metrics, warnings = parse_result_file(source, spec)
    except MetricParseError as exc:
        return (
            BaselineStatus.FAILED_INVALID_RESULT,
            "; ".join(exc.errors),
            None,
            [],
            copied,
        )
    return BaselineStatus.SUCCEEDED, None, metrics, warnings, copied


def _run_venv(
    *,
    spec: ContractSpec,
    worktree: Path,
    run_artifacts: Path,
    runner: CommandRunner,
    secrets: dict[str, str],
    timeout_seconds: float,
    fingerprint: EnvironmentFingerprint,
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[
    BaselineStatus, str | None, MetricResult | None, list[str], str | None, EnvironmentFingerprint
]:
    venv_python, outcome = venv_exec.create_venv(
        worktree, runner, timeout_seconds=timeout_seconds, log_dir=run_artifacts
    )
    if not outcome.ok:
        return (
            BaselineStatus.FAILED_SETUP,
            "Failed to create the virtual environment; see venv_create_stderr.log.",
            None,
            [],
            None,
            fingerprint,
        )

    env = venv_exec.minimal_env(venv_python.parent.parent, secrets)

    if spec.execution.setup_command:
        setup_outcome = runner.run(
            shell_argv(spec.execution.setup_command),
            cwd=worktree,
            env=env,
            timeout_seconds=timeout_seconds,
            stdout_path=run_artifacts / "setup_stdout.log",
            stderr_path=run_artifacts / "setup_stderr.log",
        )
        if not setup_outcome.ok:
            reason = (
                "Setup command timed out."
                if setup_outcome.timed_out
                else f"Setup command exited {setup_outcome.exit_code}; see setup_stderr.log."
            )
            return BaselineStatus.FAILED_SETUP, reason, None, [], None, fingerprint

    eval_outcome = runner.run(
        shell_argv(spec.execution.full_command),
        cwd=worktree,
        env=env,
        timeout_seconds=timeout_seconds,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )

    python_version, packages_hash = venv_exec.venv_fingerprint(
        venv_python, runner, log_dir=run_artifacts
    )
    fingerprint = fingerprint.model_copy(
        update={"python_version": python_version, "venv_packages_hash": packages_hash}
    )
    # Persist artifacts first, then drop the venv (spec §9.4 step 8).
    shutil.rmtree(worktree / venv_exec.VENV_DIR_NAME, ignore_errors=True)

    if eval_outcome.timed_out:
        return (
            BaselineStatus.FAILED_TIMEOUT,
            f"Evaluation timed out after {timeout_seconds:.0f}s.",
            None,
            [],
            None,
            fingerprint,
        )
    if eval_outcome.exit_code != 0:
        return (
            BaselineStatus.FAILED_EXECUTION,
            f"Evaluation command exited {eval_outcome.exit_code}; see stderr.log.",
            None,
            [],
            None,
            fingerprint,
        )

    final = _finalize_result(spec, worktree, run_artifacts)
    return (*final, fingerprint)


def _run_docker(
    *,
    spec: ContractSpec,
    worktree: Path,
    run_artifacts: Path,
    runner: CommandRunner,
    secrets: dict[str, str],
    timeout_seconds: float,
    fingerprint: EnvironmentFingerprint,
    baseline_id: str,
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[
    BaselineStatus, str | None, MetricResult | None, list[str], str | None, EnvironmentFingerprint
]:
    tag = f"researchforge-baseline:{baseline_id[:12]}"
    build_outcome = docker_exec.build_image(
        worktree, tag, runner, timeout_seconds=timeout_seconds, log_dir=run_artifacts
    )
    if not build_outcome.ok:
        reason = (
            "Docker build timed out."
            if build_outcome.timed_out
            else f"Docker build exited {build_outcome.exit_code}; see docker_build_stderr.log."
        )
        return BaselineStatus.FAILED_SETUP, reason, None, [], None, fingerprint

    fingerprint = fingerprint.model_copy(
        update={"docker_image_id": docker_exec.image_id(tag, runner, log_dir=run_artifacts)}
    )

    command = spec.execution.full_command
    if spec.execution.setup_command:
        command = f"{spec.execution.setup_command} && {command}"

    container_name = f"researchforge-bl-{baseline_id[:12]}"
    argv = docker_exec.docker_run_argv(
        image=tag,
        container_name=container_name,
        worktree=worktree,
        artifacts=run_artifacts,
        execution=spec.execution,
        network=spec.network.mode if spec.network else NetworkMode.NONE,
        forwarded_names=list(secrets),
        command=command,
    )
    eval_outcome = runner.run(
        argv,
        cwd=worktree,
        env={**os.environ, **secrets},
        timeout_seconds=timeout_seconds,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    if eval_outcome.timed_out:
        docker_exec.force_remove_container(container_name, runner, log_dir=run_artifacts)
        return (
            BaselineStatus.FAILED_TIMEOUT,
            f"Evaluation timed out after {timeout_seconds:.0f}s; container removed.",
            None,
            [],
            None,
            fingerprint,
        )
    if eval_outcome.exit_code != 0:
        return (
            BaselineStatus.FAILED_EXECUTION,
            f"Container exited {eval_outcome.exit_code}; see stderr.log.",
            None,
            [],
            None,
            fingerprint,
        )

    final = _finalize_result(spec, worktree, run_artifacts)
    return (*final, fingerprint)


def baseline_gate(conn: sqlite3.Connection) -> BaselineRun:
    """Phase 1C's entry check: raises unless the latest baseline succeeded."""
    latest = get_latest_baseline(conn)
    if latest is None:
        raise BaselineBlockedError("No baseline has been run. Run `researchforge baseline run`.")
    if latest.status is not BaselineStatus.SUCCEEDED:
        raise BaselineBlockedError(
            f"The latest baseline failed ({latest.status.value}): {latest.failure_reason} "
            "— experiments are blocked until a baseline succeeds."
        )
    return latest
