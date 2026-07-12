"""Semantic validation of researchforge.yaml beyond the pydantic schema."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from researchforge.domain.contract import ContractExecutionMode, ContractSpec, NetworkMode
from researchforge.domain.project import Project, ProjectMode
from researchforge.domain.repo_scan import RepoScan
from researchforge.execution.path_guard import PathGuardError, find_overlaps, normalize_change_path
from researchforge.utils.artifact_io import ArtifactLoadError, load_artifact

_ENV_VAR_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")


@dataclass
class ContractValidation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    spec: ContractSpec | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


def _format_validation_error(exc: ValidationError) -> list[str]:
    messages = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        messages.append(f"{location or '<root>'}: {error['msg']}")
    return messages


def _check_relative_path(value: str, where: str, errors: list[str]) -> None:
    try:
        normalize_change_path(value)
    except PathGuardError as exc:
        errors.append(f"{where}: {exc}")


def validate_spec(
    spec: ContractSpec,
    *,
    project: Project | None,
    scan: RepoScan | None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    objective = spec.objective
    execution = spec.execution
    permissions = spec.permissions

    # Metric and constraint coherence.
    constraint_names = [c.name for c in objective.hard_constraints]
    if len(constraint_names) != len(set(constraint_names)):
        errors.append("objective.hard_constraints: duplicate constraint names.")
    measurable = {objective.primary_metric.name, *objective.secondary_metrics}
    for name in constraint_names:
        if name not in measurable:
            warnings.append(
                f"objective.hard_constraints.{name}: not the primary metric and not in "
                "secondary_metrics — it cannot be measured from the result file."
            )
    if len(objective.secondary_metrics) != len(set(objective.secondary_metrics)):
        errors.append("objective.secondary_metrics: duplicate metric names.")
    if objective.primary_metric.name in objective.secondary_metrics:
        warnings.append("objective.secondary_metrics: repeats the primary metric name; remove it.")
    if objective.primary_metric.name == "primary_metric":
        warnings.append(
            "objective.primary_metric.name: still the wizard placeholder — rename it to "
            "your real metric."
        )

    # Execution.
    if execution.full_command.strip().startswith("#"):
        errors.append(
            "execution.full_command: still a placeholder — set the command that runs "
            "your evaluation and writes the result file."
        )
    if execution.mode is ContractExecutionMode.VENV and not execution.trusted_repository:
        errors.append(
            "execution.mode is 'venv' but trusted_repository is false — venv mode does "
            "not isolate code from your machine; review the repository and set "
            "execution.trusted_repository: true, or use docker."
        )
    _check_relative_path(execution.result_file, "execution.result_file", errors)

    # Permissions.
    if not permissions.editable_paths:
        errors.append("permissions.editable_paths: must list at least one editable path.")
    for entry in [*permissions.editable_paths, *permissions.protected_paths]:
        _check_relative_path(entry.rstrip("/") or entry, "permissions", errors)
    if not errors:  # overlap check only meaningful on normalizable paths
        for editable, protected in find_overlaps(
            permissions.editable_paths, permissions.protected_paths
        ):
            errors.append(
                f"permissions: {editable!r} (editable) overlaps {protected!r} (protected) — "
                "a path cannot be both."
            )
    if scan is not None:
        missing = [
            p for p in scan.suggested_protected_paths if p not in permissions.protected_paths
        ]
        if missing:
            warnings.append(
                f"permissions.protected_paths: scan suggested also protecting "
                f"{', '.join(missing)} (implicit protections still apply to "
                ".researchforge/, .git/, researchforge.yaml)."
            )

    # Secrets and network.
    for name in spec.secrets.forward_environment_variables:
        if not _ENV_VAR_NAME.match(name):
            errors.append(
                f"secrets.forward_environment_variables: {name!r} is not a valid "
                "environment variable name."
            )
    if spec.secrets.forward_environment_variables and spec.network.mode is NetworkMode.NONE:
        warnings.append(
            "secrets: environment variables are forwarded while network.mode is 'none' — "
            "confirm they are needed offline."
        )
    if spec.network.mode is NetworkMode.ENABLED:
        warnings.append(
            "network.mode 'enabled': approving this contract records your consent to "
            "network access during experiment runs."
        )

    # Consistency with the stored project.
    if project is not None:
        if project.mode is not None and spec.project.mode is not ProjectMode(project.mode):
            errors.append(
                f"project.mode: {spec.project.mode.value!r} does not match the stored "
                f"project mode {project.mode.value!r}."
            )
        if spec.project.name != project.name:
            warnings.append(
                f"project.name: {spec.project.name!r} differs from the stored project "
                f"name {project.name!r}."
            )
        if project.mode is ProjectMode.EXPLORE_RESEARCH_IDEA and project.repository.path is None:
            errors.append(
                "project: explore_research_idea without a repository — attach one with "
                "`researchforge repo scan <path>` before contracting experiments."
            )

    if spec.validation.require_existing_tests and scan is not None and not scan.test_candidates:
        warnings.append(
            "validation.require_existing_tests is true but the repository scan found no "
            "tests — baseline may be blocked until tests exist or this is set to false."
        )

    return errors, warnings


def validate_contract_file(
    path: Path,
    *,
    project: Project | None,
    scan: RepoScan | None,
) -> ContractValidation:
    result = ContractValidation()
    try:
        raw = load_artifact(path)
    except ArtifactLoadError as exc:
        result.errors.append(str(exc))
        return result

    try:
        spec = ContractSpec.model_validate(raw)
    except ValidationError as exc:
        result.errors.extend(_format_validation_error(exc))
        return result

    errors, warnings = validate_spec(spec, project=project, scan=scan)
    result.errors.extend(errors)
    result.warnings.extend(warnings)
    if result.ok:
        result.spec = spec
    return result
