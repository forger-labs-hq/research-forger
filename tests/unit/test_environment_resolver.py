import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from researchforge.domain.contract import ContractSpec
from researchforge.domain.environment import DockerProbe, ExecutionEngine
from researchforge.domain.repo_scan import CompatibilityStatus, GitInfo, PythonInfo, RepoScan
from researchforge.execution.environment import probe_docker, resolve_environment

CONTRACTS = Path(__file__).parent.parent / "fixtures" / "contracts"


def _spec(**overrides: object) -> ContractSpec:
    data = yaml.safe_load((CONTRACTS / "example_full.yaml").read_text(encoding="utf-8"))
    execution = data["execution"]
    assert isinstance(execution, dict)
    execution.update(overrides)
    return ContractSpec.model_validate(data)


def _scan(
    *,
    dockerfile: bool = False,
    python: bool = True,
    git: bool = True,
    compatibility: CompatibilityStatus = CompatibilityStatus.READY,
) -> RepoScan:
    return RepoScan(
        scan_id="s1",
        repo_path="/nonexistent/repo",
        git=GitInfo(is_repo=git),
        python=PythonInfo(has_pyproject=python),
        has_dockerfile=dockerfile,
        compatibility=compatibility,
        compatibility_reasons=["scan reason"],
        scanned_at=datetime.now(UTC),
    )


_DOCKER_UP = DockerProbe(cli_present=True, daemon_running=True, version="27.0")
_DOCKER_NO_CLI = DockerProbe(cli_present=False, daemon_running=False, error="docker CLI not found")
_DOCKER_DAEMON_DOWN = DockerProbe(
    cli_present=True, daemon_running=False, error="connection refused"
)


class TestExplicitDocker:
    def test_ready_when_dockerfile_and_daemon(self) -> None:
        resolution = resolve_environment(_spec(mode="docker"), _scan(dockerfile=True), _DOCKER_UP)
        assert resolution.status is CompatibilityStatus.READY
        assert resolution.execution_mode is ExecutionEngine.DOCKER

    def test_no_cli(self) -> None:
        resolution = resolve_environment(
            _spec(mode="docker"), _scan(dockerfile=True), _DOCKER_NO_CLI
        )
        assert resolution.status is CompatibilityStatus.SETUP_REQUIRED
        assert resolution.execution_mode is ExecutionEngine.NONE
        assert any("Install Docker" in a for a in resolution.required_user_actions)

    def test_daemon_down(self) -> None:
        resolution = resolve_environment(
            _spec(mode="docker"), _scan(dockerfile=True), _DOCKER_DAEMON_DOWN
        )
        assert resolution.status is CompatibilityStatus.SETUP_REQUIRED
        assert any("daemon" in a.lower() for a in resolution.required_user_actions)
        assert any("connection refused" in r for r in resolution.reasons)

    def test_no_dockerfile(self) -> None:
        resolution = resolve_environment(_spec(mode="docker"), _scan(dockerfile=False), _DOCKER_UP)
        assert resolution.status is CompatibilityStatus.SETUP_REQUIRED
        assert any("Dockerfile" in a for a in resolution.required_user_actions)


class TestExplicitVenv:
    def test_ready_when_trusted_python(self) -> None:
        resolution = resolve_environment(
            _spec(mode="venv", trusted_repository=True), _scan(), _DOCKER_NO_CLI
        )
        assert resolution.status is CompatibilityStatus.READY
        assert resolution.execution_mode is ExecutionEngine.VENV

    def test_untrusted_blocks(self) -> None:
        resolution = resolve_environment(
            _spec(mode="venv", trusted_repository=False), _scan(), _DOCKER_UP
        )
        assert resolution.status is CompatibilityStatus.SETUP_REQUIRED
        assert any("trusted_repository" in a for a in resolution.required_user_actions)

    def test_not_python_blocks(self) -> None:
        resolution = resolve_environment(
            _spec(mode="venv", trusted_repository=True), _scan(python=False), _DOCKER_UP
        )
        assert resolution.status is CompatibilityStatus.SETUP_REQUIRED
        assert any("metadata" in r for r in resolution.reasons)


class TestAuto:
    def test_prefers_docker(self) -> None:
        resolution = resolve_environment(
            _spec(mode="auto", trusted_repository=True), _scan(dockerfile=True), _DOCKER_UP
        )
        assert resolution.execution_mode is ExecutionEngine.DOCKER

    def test_falls_back_to_venv(self) -> None:
        resolution = resolve_environment(
            _spec(mode="auto", trusted_repository=True), _scan(), _DOCKER_NO_CLI
        )
        assert resolution.status is CompatibilityStatus.READY
        assert resolution.execution_mode is ExecutionEngine.VENV
        assert any("fallback" in r for r in resolution.reasons)

    def test_python_untrusted_gives_both_actions(self) -> None:
        resolution = resolve_environment(
            _spec(mode="auto", trusted_repository=False), _scan(), _DOCKER_NO_CLI
        )
        assert resolution.status is CompatibilityStatus.SETUP_REQUIRED
        joined = " ".join(resolution.required_user_actions)
        assert "trusted_repository" in joined
        assert "Dockerfile" in joined or "Docker" in joined

    def test_research_only_passthrough(self) -> None:
        resolution = resolve_environment(
            _spec(mode="auto"),
            _scan(python=False, git=False, compatibility=CompatibilityStatus.RESEARCH_ONLY),
            _DOCKER_NO_CLI,
        )
        assert resolution.status is CompatibilityStatus.RESEARCH_ONLY
        assert resolution.execution_mode is ExecutionEngine.NONE
        assert "scan reason" in resolution.reasons

    def test_unsupported_passthrough(self) -> None:
        resolution = resolve_environment(
            _spec(mode="auto"),
            _scan(python=False, git=False, compatibility=CompatibilityStatus.UNSUPPORTED),
            _DOCKER_NO_CLI,
        )
        assert resolution.status is CompatibilityStatus.UNSUPPORTED

    def test_every_outcome_has_reasons(self) -> None:
        for probe in (_DOCKER_UP, _DOCKER_NO_CLI, _DOCKER_DAEMON_DOWN):
            for scan in (_scan(), _scan(dockerfile=True), _scan(python=False, git=False)):
                resolution = resolve_environment(_spec(mode="auto"), scan, probe)
                assert resolution.reasons


class TestProbeDocker:
    def test_missing_cli(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda name: None)

        probe = probe_docker()

        assert not probe.cli_present
        assert not probe.daemon_running

    def test_daemon_down(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/docker")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(
                a, 1, stdout="", stderr="Cannot connect to the Docker daemon\n"
            ),
        )

        probe = probe_docker()

        assert probe.cli_present
        assert not probe.daemon_running
        assert probe.error is not None

    def test_daemon_up(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/docker")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="27.0.1\n", stderr=""),
        )

        probe = probe_docker()

        assert probe.daemon_running
        assert probe.version == "27.0.1"
