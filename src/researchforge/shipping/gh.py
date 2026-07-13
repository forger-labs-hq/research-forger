"""GitHub CLI seam for `ship pr`.

Short foreground calls with captured output (unlike the evaluation
CommandRunner, which streams to log files). Everything goes through the
injectable ProcessRunner so tests never touch the network or a real gh.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class ProcessResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class ProcessRunner(Protocol):
    def run(
        self, argv: list[str], *, cwd: Path, timeout_seconds: float = 60.0
    ) -> ProcessResult: ...


class SubprocessProcessRunner:
    def run(self, argv: list[str], *, cwd: Path, timeout_seconds: float = 60.0) -> ProcessResult:
        try:
            completed = subprocess.run(  # noqa: S603
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ProcessResult(exit_code=124, stdout="", stderr=str(exc))
        return ProcessResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class GhError(Exception):
    """A gh/git remote operation failed; message includes the tool's output."""


class GhClient:
    def __init__(self, runner: ProcessRunner | None = None) -> None:
        self._runner = runner or SubprocessProcessRunner()

    def available(self) -> bool:
        return shutil.which("gh") is not None

    def auth_ok(self, cwd: Path) -> bool:
        return self._runner.run(["gh", "auth", "status"], cwd=cwd).ok

    def default_remote_exists(self, cwd: Path) -> bool:
        return self._runner.run(["git", "remote", "get-url", "origin"], cwd=cwd).ok

    def push_branch(self, cwd: Path, branch: str) -> None:
        """Push exactly this one branch ref — never --force, never anything else."""
        result = self._runner.run(
            ["git", "push", "--set-upstream", "origin", f"refs/heads/{branch}"],
            cwd=cwd,
            timeout_seconds=300.0,
        )
        if not result.ok:
            raise GhError(f"git push failed: {result.stderr.strip() or result.stdout.strip()}")

    def create_draft_pr(
        self,
        cwd: Path,
        *,
        branch: str,
        title: str,
        body_file: Path,
        base: str | None,
    ) -> str:
        """Open a DRAFT pull request; returns its URL."""
        argv = [
            "gh",
            "pr",
            "create",
            "--draft",
            "--head",
            branch,
            "--title",
            title,
            "--body-file",
            str(body_file),
        ]
        if base is not None:
            argv += ["--base", base]
        result = self._runner.run(argv, cwd=cwd, timeout_seconds=120.0)
        if not result.ok:
            raise GhError(f"gh pr create failed: {result.stderr.strip() or result.stdout.strip()}")
        url = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        if not url.startswith("http"):
            raise GhError(f"gh pr create did not return a URL (got {url!r}).")
        return url
