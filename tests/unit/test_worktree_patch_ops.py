from collections.abc import Callable
from pathlib import Path

import pytest

from researchforge.execution.worktrees import WorktreeManager

RepoFactory = Callable[..., Path]

NEW_FILE_PATCH = """\
diff --git a/src/algo.py b/src/algo.py
new file mode 100644
--- /dev/null
+++ b/src/algo.py
@@ -0,0 +1,2 @@
+IMPROVEMENT = 1
+LATENCY = 100
"""

BROKEN_PATCH = """\
diff --git a/src/missing.py b/src/missing.py
--- a/src/missing.py
+++ b/src/missing.py
@@ -1 +1 @@
-does not exist
+new line
"""


@pytest.fixture
def worktree(repo_factory: RepoFactory, tmp_path: Path) -> tuple[WorktreeManager, Path]:
    repo = repo_factory(requirements=True)
    manager = WorktreeManager(repo)
    return manager, manager.create("plan-check", "main")


def _write_patch(tmp_path: Path, text: str) -> Path:
    patch = tmp_path / "change.patch"
    patch.write_text(text, encoding="utf-8")
    return patch


class TestPatchOps:
    def test_check_and_apply_new_file_patch(
        self, worktree: tuple[WorktreeManager, Path], tmp_path: Path
    ) -> None:
        manager, tree = worktree
        patch = _write_patch(tmp_path, NEW_FILE_PATCH)

        applies, message = manager.apply_patch_check(tree, patch)
        assert applies, message

        assert manager.patch_numstat(tree, patch) == ["src/algo.py"]

        manager.apply_patch(tree, patch)
        assert (tree / "src" / "algo.py").read_text() == "IMPROVEMENT = 1\nLATENCY = 100\n"

    def test_check_reports_git_error_for_broken_patch(
        self, worktree: tuple[WorktreeManager, Path], tmp_path: Path
    ) -> None:
        manager, tree = worktree
        patch = _write_patch(tmp_path, BROKEN_PATCH)

        applies, message = manager.apply_patch_check(tree, patch)

        assert not applies
        assert "missing.py" in message

    def test_changed_paths_lists_untracked_and_modified(
        self, worktree: tuple[WorktreeManager, Path], tmp_path: Path
    ) -> None:
        manager, tree = worktree
        manager.apply_patch(tree, _write_patch(tmp_path, NEW_FILE_PATCH))
        (tree / "requirements.txt").write_text("requests\nnumpy\n", encoding="utf-8")

        changed = set(manager.changed_paths(tree))

        assert "src/algo.py" in changed
        assert "requirements.txt" in changed

    def test_changed_paths_clean_tree_is_empty(
        self, worktree: tuple[WorktreeManager, Path]
    ) -> None:
        manager, tree = worktree
        assert manager.changed_paths(tree) == []
