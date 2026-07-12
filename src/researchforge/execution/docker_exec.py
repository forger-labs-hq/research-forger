"""Docker execution support (spec: Docker runtime defaults).

Docker is driven through the CLI via the shared CommandRunner, so the docker
path is unit-testable with fakes. Secret values never appear in argv: `-e
NAME` (value-less) makes docker inherit the variable from our process
environment.

Never mounted: the docker socket, the user's home, SSH or cloud credential
directories — structurally impossible because argv construction only ever
receives the worktree and the artifact directory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from researchforge.domain.contract import ExecutionSection, NetworkMode
from researchforge.execution.runner import CommandOutcome, CommandRunner

PIDS_LIMIT = 256
WORKSPACE_MOUNT = "/workspace"
ARTIFACTS_MOUNT = "/rf-artifacts"


def build_image(
    worktree: Path,
    tag: str,
    runner: CommandRunner,
    *,
    timeout_seconds: float,
    log_dir: Path,
) -> CommandOutcome:
    """`docker build` — network is permitted during image build only (spec §9.3)."""
    return runner.run(
        ["docker", "build", "--tag", tag, str(worktree)],
        cwd=worktree,
        env=dict(os.environ),  # docker CLI needs its normal env (DOCKER_HOST etc.)
        timeout_seconds=timeout_seconds,
        stdout_path=log_dir / "docker_build_stdout.log",
        stderr_path=log_dir / "docker_build_stderr.log",
    )


def docker_run_argv(
    *,
    image: str,
    container_name: str,
    worktree: Path,
    artifacts: Path,
    execution: ExecutionSection,
    network: NetworkMode,
    forwarded_names: list[str],
    command: str,
) -> list[str]:
    """The exact `docker run` argv implementing the spec's runtime defaults."""
    argv = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        f"--network={'bridge' if network is NetworkMode.ENABLED else 'none'}",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        f"--cpus={execution.cpu_limit:g}",
        f"--memory={execution.memory_mb}m",
        f"--memory-swap={execution.memory_mb}m",
        f"--pids-limit={PIDS_LIMIT}",
        "--read-only",
        "--tmpfs",
        "/tmp",
        "-v",
        f"{worktree.resolve()}:{WORKSPACE_MOUNT}",
        "-v",
        f"{artifacts.resolve()}:{ARTIFACTS_MOUNT}",
        "-w",
        WORKSPACE_MOUNT,
    ]
    if sys.platform.startswith("linux"):
        argv.append(f"--user={os.getuid()}:{os.getgid()}")
    for name in forwarded_names:
        argv += ["-e", name]  # value-less: inherited from our env, never in argv
    argv += [image, "sh", "-lc", command]
    return argv


def image_id(tag: str, runner: CommandRunner, *, log_dir: Path) -> str | None:
    out_path = log_dir / "docker_image_id.log"
    outcome = runner.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", tag],
        cwd=Path.cwd(),
        env=dict(os.environ),
        timeout_seconds=30,
        stdout_path=out_path,
        stderr_path=log_dir / "docker_image_id_err.log",
    )
    if not outcome.ok:
        return None
    return out_path.read_text(encoding="utf-8").strip() or None


def force_remove_container(name: str, runner: CommandRunner, *, log_dir: Path) -> None:
    """Kill a container after a client-side timeout (timeout is enforced outside
    the container; killing the docker-run client alone does not stop it)."""
    runner.run(
        ["docker", "rm", "-f", name],
        cwd=Path.cwd(),
        env=dict(os.environ),
        timeout_seconds=30,
        stdout_path=log_dir / "docker_rm_stdout.log",
        stderr_path=log_dir / "docker_rm_stderr.log",
    )
