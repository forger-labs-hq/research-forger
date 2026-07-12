import pytest

from researchforge.domain.contract import PermissionsSection
from researchforge.execution.path_guard import (
    PathGuardError,
    PathRule,
    check_changed_paths,
    find_overlaps,
    matches_entry,
    normalize_change_path,
)


def _perms(editable: list[str], protected: list[str]) -> PermissionsSection:
    return PermissionsSection(editable_paths=editable, protected_paths=protected)


class TestNormalize:
    @pytest.mark.parametrize("bad", ["/etc/passwd", "~/x", "..", "../x", "a/../../x", "a\\b", ""])
    def test_rejects_escaping_paths(self, bad: str) -> None:
        with pytest.raises(PathGuardError):
            normalize_change_path(bad)

    def test_normalizes_dot_segments(self) -> None:
        assert normalize_change_path("./src/a.py") == "src/a.py"
        assert normalize_change_path("src//b/../a.py") == "src/a.py"


class TestMatching:
    def test_dir_entry_is_segment_aware(self) -> None:
        assert matches_entry("src/a.py", "src/")
        assert matches_entry("src/deep/b.py", "src/")
        assert not matches_entry("src2/a.py", "src/")

    def test_file_entry_is_exact(self) -> None:
        assert matches_entry("Makefile", "Makefile")
        assert not matches_entry("Makefile.bak", "Makefile")


class TestCheckChangedPaths:
    def test_allows_editable_changes(self) -> None:
        result = check_changed_paths(["src/model.py"], _perms(["src/"], ["benchmarks/"]))
        assert result.allowed

    def test_rejects_protected_change(self) -> None:
        result = check_changed_paths(["benchmarks/eval.py"], _perms(["src/"], ["benchmarks/"]))
        assert not result.allowed
        assert result.violations[0].rule is PathRule.PROTECTED
        assert result.violations[0].matched == "benchmarks/"

    def test_rejects_outside_editable(self) -> None:
        result = check_changed_paths(["docs/readme.md"], _perms(["src/"], []))
        assert not result.allowed
        assert result.violations[0].rule is PathRule.NOT_EDITABLE

    def test_empty_editable_allows_all_non_protected(self) -> None:
        result = check_changed_paths(["anything/file.py"], _perms([], ["benchmarks/"]))
        assert result.allowed

    @pytest.mark.parametrize("path", [".researchforge/db", ".git/config", "researchforge.yaml"])
    def test_implicit_protections_always_apply(self, path: str) -> None:
        # Even with empty contract lists (and even listed as editable).
        result = check_changed_paths([path], _perms([], []))
        assert not result.allowed
        result = check_changed_paths(
            [path], _perms([".researchforge/", ".git/", "researchforge.yaml"], [])
        )
        assert not result.allowed

    def test_invalid_path_is_violation_not_crash(self) -> None:
        result = check_changed_paths(["../escape.py"], _perms(["src/"], []))
        assert not result.allowed
        assert result.violations[0].rule is PathRule.INVALID

    def test_dot_prefixed_input_normalized(self) -> None:
        result = check_changed_paths(["./src/a.py"], _perms(["src/"], []))
        assert result.allowed

    def test_multiple_violations_reported(self) -> None:
        result = check_changed_paths(
            ["benchmarks/e.py", "docs/x.md", "src/ok.py"],
            _perms(["src/"], ["benchmarks/"]),
        )
        assert not result.allowed
        assert len(result.violations) == 2


class TestOverlaps:
    def test_nested_overlap_detected(self) -> None:
        assert find_overlaps(["src/"], ["src/core/"]) == [("src/", "src/core/")]
        assert find_overlaps(["src/core/"], ["src/"]) == [("src/core/", "src/")]

    def test_identical_entry_detected(self) -> None:
        assert find_overlaps(["src/"], ["src/"]) == [("src/", "src/")]

    def test_disjoint_paths_no_overlap(self) -> None:
        assert find_overlaps(["src/"], ["benchmarks/"]) == []
