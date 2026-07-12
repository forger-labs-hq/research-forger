"""Virtual-environment execution support for trusted Python repositories.

Dependency isolation only — not security isolation. The warning below is
displayed verbatim (spec §9.4) before any venv-mode run.
"""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from researchforge.execution.runner import CommandOutcome, CommandRunner

VENV_WARNING = (
    "Virtual-environment mode isolates Python dependencies but does not securely "
    "isolate code from your computer, files, or network. Use it only with "
    "repositories you trust. Choose Docker for stronger isolation."
)

VENV_DIR_NAME = ".venv"


def create_venv(
    worktree: Path,
    runner: CommandRunner,
    *,
    timeout_seconds: float,
    log_dir: Path,
) -> tuple[Path, CommandOutcome]:
    """Create `<worktree>/.venv`; returns (venv python path, outcome)."""
    venv_dir = worktree / VENV_DIR_NAME
    outcome = runner.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        cwd=worktree,
        env=minimal_env(venv_dir=None, forwarded={}),
        timeout_seconds=timeout_seconds,
        stdout_path=log_dir / "venv_create_stdout.log",
        stderr_path=log_dir / "venv_create_stderr.log",
    )
    return venv_dir / "bin" / "python", outcome


def minimal_env(venv_dir: Path | None, forwarded: Mapping[str, str]) -> dict[str, str]:
    """Environment built from scratch: no ambient variables leak through.

    Only explicitly forwarded variables (by name, from the contract) are
    included; `.env` files are never read (spec §9.4 constraints).
    """
    env: dict[str, str] = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
    }
    home = os.environ.get("HOME")
    if home:  # pip needs a cache directory; venv mode's documented trust level
        env["HOME"] = home
    tmpdir = os.environ.get("TMPDIR")
    if tmpdir:
        env["TMPDIR"] = tmpdir
    if venv_dir is not None:
        env["VIRTUAL_ENV"] = str(venv_dir)
        env["PATH"] = f"{venv_dir / 'bin'}:{env['PATH']}"
    env.update(forwarded)
    return env


def forwarded_values(names: list[str]) -> dict[str, str]:
    """Resolve contract-forwarded variable names against the current environment."""
    return {name: os.environ[name] for name in names if name in os.environ}


def venv_fingerprint(
    venv_python: Path,
    runner: CommandRunner,
    *,
    log_dir: Path,
    timeout_seconds: float = 120.0,
) -> tuple[str | None, str | None]:
    """(python version, sha256 of pip freeze output) — best effort."""
    version_out = log_dir / "python_version.log"
    outcome = runner.run(
        [str(venv_python), "--version"],
        cwd=venv_python.parent,
        env=minimal_env(venv_dir=None, forwarded={}),
        timeout_seconds=timeout_seconds,
        stdout_path=version_out,
        stderr_path=log_dir / "python_version_err.log",
    )
    python_version = version_out.read_text(encoding="utf-8").strip() if outcome.ok else None

    freeze_out = log_dir / "pip_freeze.log"
    outcome = runner.run(
        [str(venv_python), "-m", "pip", "freeze", "--all"],
        cwd=venv_python.parent,
        env=minimal_env(venv_dir=None, forwarded={}),
        timeout_seconds=timeout_seconds,
        stdout_path=freeze_out,
        stderr_path=log_dir / "pip_freeze_err.log",
    )
    packages_hash = hashlib.sha256(freeze_out.read_bytes()).hexdigest() if outcome.ok else None
    return python_version, packages_hash
