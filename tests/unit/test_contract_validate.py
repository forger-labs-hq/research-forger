from datetime import UTC, datetime
from pathlib import Path

import yaml

from researchforge.contract.validate import validate_contract_file, validate_spec
from researchforge.domain.contract import ContractSpec
from researchforge.domain.project import Project, ProjectMode, RepositoryMetadata
from researchforge.domain.repo_scan import CompatibilityStatus, GitInfo, PythonInfo, RepoScan

CONTRACTS = Path(__file__).parent.parent / "fixtures" / "contracts"


def _spec(**overrides: object) -> ContractSpec:
    data = yaml.safe_load((CONTRACTS / "example_full.yaml").read_text(encoding="utf-8"))
    for dotted, value in overrides.items():
        cursor = data
        parts = dotted.split("__")
        for part in parts[:-1]:
            cursor = cursor[part]
        cursor[parts[-1]] = value
    return ContractSpec.model_validate(data)


def _project(mode: ProjectMode = ProjectMode.IMPROVE_REPOSITORY) -> Project:
    now = datetime.now(UTC)
    return Project(
        id="p1",
        name="adaptive-routing-study",
        mode=mode,
        objective="Reduce cost",
        repository=RepositoryMetadata(path="/tmp/repo"),
        created_at=now,
        updated_at=now,
    )


def _scan(**overrides: object) -> RepoScan:
    defaults: dict[str, object] = {
        "scan_id": "s1",
        "repo_path": "/tmp/repo",
        "git": GitInfo(is_repo=True, branch="main"),
        "python": PythonInfo(has_pyproject=True),
        "test_candidates": ["tests/"],
        "suggested_protected_paths": ["tests/", ".researchforge/"],
        "compatibility": CompatibilityStatus.READY,
        "scanned_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return RepoScan(**defaults)  # type: ignore[arg-type]


def _errors(spec: ContractSpec, project: Project | None = None, scan: RepoScan | None = None):
    return validate_spec(spec, project=project, scan=scan)


class TestSemanticRules:
    def test_example_is_clean(self) -> None:
        errors, _ = _errors(_spec(), _project(), _scan())
        assert errors == []

    def test_duplicate_constraint_names(self) -> None:
        spec = _spec()
        spec.objective.hard_constraints.append(spec.objective.hard_constraints[0])
        errors, _ = _errors(spec)
        assert any("duplicate constraint" in e for e in errors)

    def test_unmeasurable_constraint_warns(self) -> None:
        spec = _spec(
            objective__hard_constraints=[
                {"name": "unmeasured_thing", "operator": "<=", "value": 1.0}
            ]
        )
        _, warnings = _errors(spec)
        assert any("unmeasured_thing" in w for w in warnings)

    def test_duplicate_secondary_metrics(self) -> None:
        spec = _spec(objective__secondary_metrics=["a", "a"])
        errors, _ = _errors(spec)
        assert any("duplicate metric" in e for e in errors)

    def test_primary_in_secondary_warns(self) -> None:
        spec = _spec(objective__secondary_metrics=["quality_score"])
        _, warnings = _errors(spec)
        assert any("repeats the primary" in w for w in warnings)

    def test_placeholder_metric_warns(self) -> None:
        spec = _spec(objective__primary_metric={"name": "primary_metric", "direction": "maximize"})
        _, warnings = _errors(spec)
        assert any("placeholder" in w for w in warnings)

    def test_placeholder_full_command_rejected(self) -> None:
        spec = _spec(execution__full_command="# TODO: command that writes the result file")
        errors, _ = _errors(spec)
        assert any("full_command" in e for e in errors)

    def test_venv_requires_trust(self) -> None:
        spec = _spec(execution__mode="venv", execution__trusted_repository=False)
        errors, _ = _errors(spec)
        assert any("trusted_repository" in e for e in errors)

    def test_result_file_must_stay_inside_worktree(self) -> None:
        for bad in ("../outside.json", "/abs/results.json"):
            spec = _spec(execution__result_file=bad)
            errors, _ = _errors(spec)
            assert any("result_file" in e for e in errors), bad

    def test_editable_paths_required(self) -> None:
        spec = _spec(permissions__editable_paths=[])
        errors, _ = _errors(spec)
        assert any("editable_paths" in e for e in errors)

    def test_editable_protected_overlap_rejected(self) -> None:
        spec = _spec(
            permissions__editable_paths=["src/"],
            permissions__protected_paths=["src/core/"],
        )
        errors, _ = _errors(spec)
        assert any("overlaps" in e for e in errors)

    def test_missing_suggested_protection_warns(self) -> None:
        spec = _spec(permissions__protected_paths=["benchmarks/"])
        _, warnings = _errors(spec, scan=_scan())
        assert any("tests/" in w for w in warnings)

    def test_invalid_env_var_name(self) -> None:
        spec = _spec(secrets__forward_environment_variables=["lower-case!"])
        errors, _ = _errors(spec)
        assert any("environment variable name" in e for e in errors)

    def test_network_enabled_warns_about_consent(self) -> None:
        spec = _spec(network__mode="enabled")
        _, warnings = _errors(spec)
        assert any("consent" in w for w in warnings)

    def test_mode_mismatch_with_project_rejected(self) -> None:
        spec = _spec(project__mode="explore_research_idea")
        errors, _ = _errors(spec, _project(ProjectMode.IMPROVE_REPOSITORY))
        assert any("does not match" in e for e in errors)

    def test_name_mismatch_warns(self) -> None:
        spec = _spec(project__name="other-name")
        _, warnings = _errors(spec, _project())
        assert any("differs from" in w for w in warnings)

    def test_require_tests_without_tests_warns(self) -> None:
        _, warnings = _errors(_spec(), scan=_scan(test_candidates=[]))
        assert any("found no" in w for w in warnings)


class TestValidateFile:
    def test_missing_file(self, tmp_path: Path) -> None:
        result = validate_contract_file(tmp_path / "nope.yaml", project=None, scan=None)
        assert not result.ok

    def test_schema_error_reported_with_field(self, tmp_path: Path) -> None:
        target = tmp_path / "researchforge.yaml"
        target.write_text("version: 1\nproject: {name: x}\n", encoding="utf-8")
        result = validate_contract_file(target, project=None, scan=None)
        assert not result.ok
        assert any("mode" in e for e in result.errors)

    def test_valid_file_returns_spec(self, tmp_path: Path) -> None:
        target = tmp_path / "researchforge.yaml"
        target.write_text(
            (CONTRACTS / "example_full.yaml").read_text(encoding="utf-8"), encoding="utf-8"
        )
        result = validate_contract_file(target, project=None, scan=None)
        assert result.ok
        assert result.spec is not None
