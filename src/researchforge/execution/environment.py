"""Execution-environment resolution (spec order: explicit config → Docker →
.venv → research-only / setup-required)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from researchforge.domain.contract import ContractExecutionMode, ContractSpec
from researchforge.domain.environment import DockerProbe, EnvironmentResolution, ExecutionEngine
from researchforge.domain.repo_scan import CompatibilityStatus, RepoScan

_DOCKER_INSTALL_HINT = "Install Docker: https://docs.docker.com/get-docker/"
_DOCKER_START_HINT = "Start the Docker daemon (e.g. open Docker Desktop) and re-run."
_TRUST_HINT = (
    "Review the repository, then set execution.trusted_repository: true in "
    "researchforge.yaml and re-approve the contract."
)


def probe_docker() -> DockerProbe:
    """Check for the docker CLI and a responding daemon (at resolve time)."""
    executable = shutil.which("docker")
    if executable is None:
        return DockerProbe(cli_present=False, daemon_running=False, error="docker CLI not found")
    try:
        result = subprocess.run(
            [executable, "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return DockerProbe(cli_present=True, daemon_running=False, error=str(exc))
    if result.returncode != 0:
        return DockerProbe(
            cli_present=True,
            daemon_running=False,
            error=result.stderr.strip().splitlines()[0] if result.stderr.strip() else None,
        )
    return DockerProbe(cli_present=True, daemon_running=True, version=result.stdout.strip() or None)


def _has_dockerfile(spec_or_scan_path: str) -> bool:
    return (Path(spec_or_scan_path) / "Dockerfile").is_file()


def _docker_ready(scan: RepoScan, docker: DockerProbe) -> tuple[bool, list[str], list[str]]:
    """(usable, reasons, required_actions) for the docker path."""
    reasons: list[str] = []
    actions: list[str] = []
    has_dockerfile = scan.has_dockerfile or _has_dockerfile(scan.repo_path)

    if not has_dockerfile:
        reasons.append("No Dockerfile found in the repository.")
        actions.append("Add a Dockerfile, or set execution.mode to auto/venv.")
        return False, reasons, actions
    reasons.append("Dockerfile found.")
    if not docker.cli_present:
        reasons.append("Docker CLI not found on PATH.")
        actions.append(_DOCKER_INSTALL_HINT)
        return False, reasons, actions
    if not docker.daemon_running:
        detail = f": {docker.error}" if docker.error else ""
        reasons.append(f"Docker daemon not responding{detail}.")
        actions.append(_DOCKER_START_HINT)
        return False, reasons, actions
    reasons.append(f"Docker daemon running (server {docker.version or 'unknown'}).")
    return True, reasons, actions


def _venv_ready(spec: ContractSpec, scan: RepoScan) -> tuple[bool, list[str], list[str]]:
    reasons: list[str] = []
    actions: list[str] = []
    if not scan.python.is_python_project:
        reasons.append(
            "venv mode requires Python project metadata (pyproject.toml / setup.py / "
            "requirements files)."
        )
        actions.append("Add Python project metadata, or use docker mode.")
        return False, reasons, actions
    if not spec.execution.trusted_repository:
        reasons.append(
            "execution.trusted_repository is false — venv mode does not isolate code "
            "from your machine."
        )
        actions.append(_TRUST_HINT)
        return False, reasons, actions
    reasons.append("Python project detected and repository marked trusted.")
    return True, reasons, actions


def resolve_environment(
    spec: ContractSpec, scan: RepoScan, docker: DockerProbe
) -> EnvironmentResolution:
    """Pure decision function; every outcome explains itself."""
    mode = spec.execution.mode

    if mode is ContractExecutionMode.DOCKER:
        usable, reasons, actions = _docker_ready(scan, docker)
        reasons.insert(0, "execution.mode is 'docker' (explicit).")
        if usable:
            return EnvironmentResolution(
                status=CompatibilityStatus.READY,
                execution_mode=ExecutionEngine.DOCKER,
                reasons=reasons,
            )
        return EnvironmentResolution(
            status=CompatibilityStatus.SETUP_REQUIRED,
            execution_mode=ExecutionEngine.NONE,
            reasons=reasons,
            required_user_actions=actions,
        )

    if mode is ContractExecutionMode.VENV:
        usable, reasons, actions = _venv_ready(spec, scan)
        reasons.insert(0, "execution.mode is 'venv' (explicit).")
        if usable:
            return EnvironmentResolution(
                status=CompatibilityStatus.READY,
                execution_mode=ExecutionEngine.VENV,
                reasons=reasons,
            )
        return EnvironmentResolution(
            status=CompatibilityStatus.SETUP_REQUIRED,
            execution_mode=ExecutionEngine.NONE,
            reasons=reasons,
            required_user_actions=actions,
        )

    # auto: prefer docker, fall back to venv, then explain.
    docker_usable, docker_reasons, docker_actions = _docker_ready(scan, docker)
    if docker_usable:
        return EnvironmentResolution(
            status=CompatibilityStatus.READY,
            execution_mode=ExecutionEngine.DOCKER,
            reasons=["execution.mode is 'auto': Docker preferred.", *docker_reasons],
        )

    venv_usable, venv_reasons, venv_actions = _venv_ready(spec, scan)
    if venv_usable:
        return EnvironmentResolution(
            status=CompatibilityStatus.READY,
            execution_mode=ExecutionEngine.VENV,
            reasons=[
                "execution.mode is 'auto': Docker unavailable, using venv fallback.",
                *docker_reasons,
                *venv_reasons,
            ],
        )

    if scan.python.is_python_project or scan.git.is_repo:
        return EnvironmentResolution(
            status=CompatibilityStatus.SETUP_REQUIRED,
            execution_mode=ExecutionEngine.NONE,
            reasons=["execution.mode is 'auto': no usable engine.", *docker_reasons, *venv_reasons],
            required_user_actions=[*docker_actions, *venv_actions],
        )

    status = (
        CompatibilityStatus.RESEARCH_ONLY
        if scan.compatibility is CompatibilityStatus.RESEARCH_ONLY
        else CompatibilityStatus.UNSUPPORTED
    )
    return EnvironmentResolution(
        status=status,
        execution_mode=ExecutionEngine.NONE,
        reasons=[
            "execution.mode is 'auto': no usable engine.",
            *docker_reasons,
            *venv_reasons,
            *scan.compatibility_reasons,
        ],
        required_user_actions=[*docker_actions, *venv_actions],
    )
