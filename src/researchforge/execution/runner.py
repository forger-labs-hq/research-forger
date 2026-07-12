"""Command execution with wall-clock timeout and process-group termination.

POSIX-only: `start_new_session` makes the child its own process group leader
so a timeout kills the whole tree (children and grandchildren included).
Windows support is a known later-phase concern, isolated to this module.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

_KILL_GRACE_SECONDS = 5.0


class CommandOutcome(BaseModel):
    exit_code: int | None = None
    timed_out: bool = False
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.timed_out and self.exit_code == 0


class CommandRunner(Protocol):
    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
        stdout_path: Path,
        stderr_path: Path,
    ) -> CommandOutcome: ...


def shell_argv(command: str) -> list[str]:
    """Contract commands are shell strings; run them via sh -c."""
    return ["sh", "-c", command]


class SubprocessRunner:
    """The real runner. Kills the entire process group on timeout."""

    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
        stdout_path: Path,
        stderr_path: Path,
    ) -> CommandOutcome:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
            process = subprocess.Popen(  # noqa: S603
                argv,
                cwd=cwd,
                env=dict(env),
                stdout=out,
                stderr=err,
                start_new_session=True,
            )
            try:
                exit_code = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                self._kill_group(process)
                return CommandOutcome(
                    exit_code=None,
                    timed_out=True,
                    duration_seconds=time.monotonic() - started,
                )
        return CommandOutcome(
            exit_code=exit_code,
            timed_out=False,
            duration_seconds=time.monotonic() - started,
        )

    @staticmethod
    def _kill_group(process: subprocess.Popen[bytes]) -> None:
        # pid == pgid thanks to start_new_session=True.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=_KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=_KILL_GRACE_SECONDS)
