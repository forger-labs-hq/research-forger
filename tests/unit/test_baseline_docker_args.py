"""Docker argv construction — no docker needed, pure assertions."""

from pathlib import Path

import yaml

from researchforge.domain.contract import ContractSpec, NetworkMode
from researchforge.execution.docker_exec import docker_run_argv

CONTRACTS = Path(__file__).parent.parent / "fixtures" / "contracts"


def _execution() -> ContractSpec:
    data = yaml.safe_load((CONTRACTS / "example_full.yaml").read_text(encoding="utf-8"))
    return ContractSpec.model_validate(data)


def _argv(network: NetworkMode = NetworkMode.NONE, forwarded: list[str] | None = None) -> list[str]:
    spec = _execution()
    return docker_run_argv(
        image="researchforge-baseline:abc",
        container_name="researchforge-bl-abc",
        worktree=Path("/tmp/worktree"),
        artifacts=Path("/tmp/artifacts"),
        execution=spec.execution,
        network=network,
        forwarded_names=forwarded or [],
        command="python benchmarks/evaluate.py",
    )


class TestDockerRunArgv:
    def test_spec_runtime_defaults_present(self) -> None:
        argv = _argv()

        assert "--rm" in argv
        assert "--network=none" in argv
        assert "--cap-drop=ALL" in argv
        assert "--security-opt=no-new-privileges" in argv
        assert "--cpus=2" in argv
        assert "--memory=4096m" in argv
        assert "--memory-swap=4096m" in argv
        assert "--pids-limit=256" in argv
        assert "--read-only" in argv
        assert "/tmp" in argv[argv.index("--tmpfs") + 1]

    def test_network_bridge_only_when_contract_enabled(self) -> None:
        assert "--network=bridge" in _argv(NetworkMode.ENABLED)
        assert "--network=none" in _argv(NetworkMode.NONE)

    def test_only_worktree_and_artifacts_mounted(self) -> None:
        argv = _argv()
        mounts = [argv[i + 1] for i, token in enumerate(argv) if token == "-v"]
        # Paths are resolved (macOS: /tmp -> /private/tmp); compare resolved.
        expected = [
            f"{Path('/tmp/worktree').resolve()}:/workspace",
            f"{Path('/tmp/artifacts').resolve()}:/rf-artifacts",
        ]
        assert mounts == expected

    def test_secret_names_are_value_less(self) -> None:
        argv = _argv(forwarded=["ANTHROPIC_API_KEY"])
        index = argv.index("-e")
        assert argv[index + 1] == "ANTHROPIC_API_KEY"
        assert "=" not in argv[index + 1]  # value never in argv

    def test_command_runs_via_shell_in_workspace(self) -> None:
        argv = _argv()
        assert argv[-3:] == ["sh", "-lc", "python benchmarks/evaluate.py"]
        assert argv[argv.index("-w") + 1] == "/workspace"
