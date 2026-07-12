import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from researchforge.execution.worktrees import WorktreeError, WorktreeManager

RepoFactory = Callable[..., Path]


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _porcelain(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


class TestWorktreeManager:
    def test_create_detached_worktree(self, repo_factory: RepoFactory) -> None:
        repo = repo_factory(pyproject=True)
        manager = WorktreeManager(repo)
        original_head = _head(repo)
        original_status = _porcelain(repo)

        path = manager.create("baseline", "main")

        assert path == (repo / ".researchforge" / "worktrees" / "baseline").resolve()
        assert path.is_dir()
        assert (path / "pyproject.toml").is_file()
        # Worktree is detached at the resolved commit.
        assert _head(path) == manager.resolve_ref("main")
        branch = subprocess.run(
            ["git", "-C", str(path), "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert branch == ""  # detached
        # User tree provably untouched.
        assert _head(repo) == original_head
        assert _porcelain(repo) == original_status

    def test_resolve_ref_full_sha(self, repo_factory: RepoFactory) -> None:
        repo = repo_factory()
        sha = WorktreeManager(repo).resolve_ref("main")
        assert len(sha) == 40

    def test_unknown_ref_raises_with_stderr(self, repo_factory: RepoFactory) -> None:
        repo = repo_factory()
        with pytest.raises(WorktreeError, match="rev-parse"):
            WorktreeManager(repo).resolve_ref("no-such-branch")

    def test_create_existing_requires_recreate(self, repo_factory: RepoFactory) -> None:
        repo = repo_factory()
        manager = WorktreeManager(repo)
        manager.create("baseline", "main")

        with pytest.raises(WorktreeError, match="already exists"):
            manager.create("baseline", "main")

        path = manager.create("baseline", "main", recreate=True)
        assert path.is_dir()

    def test_remove_deletes_and_prunes(self, repo_factory: RepoFactory) -> None:
        repo = repo_factory()
        manager = WorktreeManager(repo)
        path = manager.create("exp-001", "main")

        manager.remove("exp-001")

        assert not path.exists()
        listed = subprocess.run(
            ["git", "-C", str(repo), "worktree", "list"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "exp-001" not in listed

    @pytest.mark.parametrize("bad", ["../escape", "a/b", ".", "", "name with space"])
    def test_invalid_names_refused(self, repo_factory: RepoFactory, bad: str) -> None:
        manager = WorktreeManager(repo_factory())
        with pytest.raises(WorktreeError):
            manager.create(bad, "main")

    def test_list_names(self, repo_factory: RepoFactory) -> None:
        manager = WorktreeManager(repo_factory())
        assert manager.list_names() == []
        manager.create("baseline", "main")
        manager.create("exp-001", "main")
        assert manager.list_names() == ["baseline", "exp-001"]

    def test_ensure_ignored_idempotent(self, repo_factory: RepoFactory) -> None:
        repo = repo_factory()
        manager = WorktreeManager(repo)

        manager.ensure_ignored()
        manager.ensure_ignored()

        exclude = repo / ".git" / "info" / "exclude"
        content = exclude.read_text(encoding="utf-8")
        assert content.splitlines().count(".researchforge/") == 1
        # And it works: a worktree under .researchforge/ doesn't dirty status.
        manager.create("baseline", "main")
        assert ".researchforge" not in _porcelain(repo)
