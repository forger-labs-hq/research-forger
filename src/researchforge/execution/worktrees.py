"""Git worktree management for baseline and experiment isolation.

Worktrees live under `.researchforge/worktrees/` and are always created
detached at a resolved commit — no branches are created or moved, so the
user's working tree and branches are never touched.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from researchforge.config.paths import worktrees_dir

_VALID_NAME = re.compile(r"^[a-zA-Z0-9._-]+$")
_GIT_TIMEOUT_S = 60


class WorktreeError(Exception):
    """A git worktree operation failed; message includes git's stderr."""


class WorktreeManager:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.worktrees_root = worktrees_dir(self.repo_root)

    def _git(self, *args: str, timeout: float = _GIT_TIMEOUT_S) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_root), *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WorktreeError(f"git {' '.join(args)} failed to run: {exc}") from exc
        if result.returncode != 0:
            raise WorktreeError(
                f"git {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}"
            )
        return result.stdout.strip()

    def _path_for(self, name: str) -> Path:
        if name in (".", "..") or not _VALID_NAME.match(name):
            raise WorktreeError(f"Invalid worktree name: {name!r}")
        path = (self.worktrees_root / name).resolve()
        if not path.is_relative_to(self.worktrees_root) or path == self.worktrees_root:
            raise WorktreeError(f"Worktree path escapes the worktrees directory: {name!r}")
        return path

    def resolve_ref(self, ref: str) -> str:
        """Resolve any ref to a full commit sha."""
        return self._git("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")

    def create(self, name: str, ref: str, *, recreate: bool = False) -> Path:
        """Create a detached worktree at `ref`; returns its path."""
        path = self._path_for(name)
        if path.exists():
            if not recreate:
                raise WorktreeError(f"Worktree {name!r} already exists at {path}.")
            self.remove(name)
        sha = self.resolve_ref(ref)
        self.ensure_ignored()  # keep the user's `git status` clean
        self.worktrees_root.mkdir(parents=True, exist_ok=True)
        self._git("worktree", "add", "--detach", str(path), sha)
        return path

    def remove(self, name: str) -> None:
        """Remove a worktree, falling back to rmtree + prune if git refuses."""
        path = self._path_for(name)
        if not path.exists():
            self._git("worktree", "prune")
            return
        try:
            self._git("worktree", "remove", "--force", str(path))
        except WorktreeError:
            shutil.rmtree(path, ignore_errors=True)
        self._git("worktree", "prune")

    def list_names(self) -> list[str]:
        if not self.worktrees_root.is_dir():
            return []
        return sorted(p.name for p in self.worktrees_root.iterdir() if p.is_dir())

    def ensure_ignored(self) -> None:
        """Make git ignore `.researchforge/` via .git/info/exclude (local-only)."""
        git_dir = Path(self._git("rev-parse", "--git-common-dir"))
        if not git_dir.is_absolute():
            git_dir = self.repo_root / git_dir
        exclude = git_dir / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        entry = ".researchforge/"
        existing = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        if entry not in existing.splitlines():
            with exclude.open("a", encoding="utf-8") as handle:
                if existing and not existing.endswith("\n"):
                    handle.write("\n")
                handle.write(f"{entry}\n")
