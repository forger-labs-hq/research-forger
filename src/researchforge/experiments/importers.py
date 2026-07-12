"""Experiment-plan import: validation and persistence (Claude -> CLI).

The enforcement boundary for experiment variants. Mechanical problems
(schema errors, missing/oversized/binary patches, patches that don't apply)
are import errors the author fixes and retries. A patch that touches
protected or non-editable paths is NOT an error: the experiment is persisted
as `rejected` with its violations — a first-class negative result that will
never run (spec: protected-path modification rejected before evaluation).
"""

from __future__ import annotations

import contextlib
import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from researchforge.config.paths import contract_path, experiment_artifacts_dir, experiments_dir
from researchforge.contract.service import check_contract_drift
from researchforge.domain.experiment import (
    Decision,
    DecisionOutcome,
    Experiment,
    ExperimentPlan,
    ExperimentStatus,
)
from researchforge.execution.baseline import BaselineBlockedError, baseline_gate
from researchforge.execution.path_guard import check_changed_paths
from researchforge.execution.worktrees import WorktreeError, WorktreeManager
from researchforge.experiments.context_export import PATCHES_DIR_NAME, ExperimentPlanArtifact
from researchforge.storage.contract_repository import get_active_contract
from researchforge.storage.experiment_repository import (
    insert_plan,
    next_experiment_ids,
    next_plan_id,
)
from researchforge.storage.hypothesis_repository import get_hypothesis
from researchforge.storage.project_repository import get_project
from researchforge.utils.artifact_io import ArtifactLoadError, load_artifact

MAX_PATCH_BYTES = 512_000
PLAN_CHECK_WORKTREE = "plan-check"


@dataclass
class ImportResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _format_validation_error(exc: ValidationError) -> list[str]:
    messages = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        messages.append(f"{location or '<root>'}: {error['msg']}")
    return messages


def _load_patch(
    entry_key: str, patch_file: str, base: Path | None, errors: list[str]
) -> Path | None:
    """Resolve and sanity-check a patch file; returns its path or records errors."""
    patches_root = (experiments_dir(base) / PATCHES_DIR_NAME).resolve()
    candidate = (experiments_dir(base) / patch_file).resolve()
    where = f"experiments.{entry_key}.patch_file"
    if not candidate.is_relative_to(patches_root):
        errors.append(f"{where}: must live inside {patches_root} (got {patch_file!r}).")
        return None
    if not candidate.is_file():
        errors.append(f"{where}: file not found at {candidate}.")
        return None
    if candidate.stat().st_size > MAX_PATCH_BYTES:
        errors.append(f"{where}: exceeds {MAX_PATCH_BYTES} bytes.")
        return None
    raw = candidate.read_bytes()
    if b"\0" in raw:
        errors.append(f"{where}: contains NUL bytes; only text diffs are supported.")
        return None
    if b"GIT binary patch" in raw:
        errors.append(f"{where}: binary patches are not supported.")
        return None
    return candidate


def import_experiment_plan(
    conn: sqlite3.Connection, path: Path, *, base: Path | None = None
) -> tuple[ImportResult, ExperimentPlan | None]:
    result = ImportResult()

    # Layer 1: parse + schema.
    try:
        raw = load_artifact(path)
    except ArtifactLoadError as exc:
        result.errors.append(str(exc))
        return result, None
    try:
        artifact = ExperimentPlanArtifact.model_validate(raw)
    except ValidationError as exc:
        result.errors.extend(_format_validation_error(exc))
        return result, None

    # Layer 2: gates.
    project = get_project(conn)
    if project is None:
        result.errors.append("No project found. Run `researchforge project create` first.")
        return result, None
    contract = get_active_contract(conn)
    if contract is None:
        result.errors.append("No approved contract. Run `researchforge contract approve`.")
        return result, None
    repo_root = Path(project.repository.path) if project.repository.path else Path.cwd()
    if check_contract_drift(conn, contract_path(repo_root)):
        result.errors.append(
            "researchforge.yaml changed since approval — re-approve before planning experiments."
        )
        return result, None
    try:
        baseline = baseline_gate(conn)
    except BaselineBlockedError as exc:
        result.errors.append(str(exc))
        return result, None
    if get_hypothesis(conn, artifact.hypothesis_id) is None:
        result.errors.append(
            f"hypothesis_id: unknown hypothesis {artifact.hypothesis_id!r} — "
            "see `researchforge hypotheses list`."
        )
        return result, None

    max_experiments = contract.spec.execution.max_experiments
    if len(artifact.experiments) > max_experiments:
        result.errors.append(
            f"experiments: {len(artifact.experiments)} provided; the contract allows "
            f"at most {max_experiments} (execution.max_experiments)."
        )
    keys = [entry.key for entry in artifact.experiments]
    if len(keys) != len(set(keys)):
        result.errors.append("experiments: duplicate keys.")
    if result.errors:
        return result, None

    # Layer 3: patch files.
    patch_paths: dict[str, Path] = {}
    for entry in artifact.experiments:
        candidate = _load_patch(entry.key, entry.patch_file, base, result.errors)
        if candidate is not None:
            patch_paths[entry.key] = candidate
    if result.errors:
        return result, None

    # Layer 4: apply-check + changed-path extraction in a scratch worktree.
    manager = WorktreeManager(repo_root)
    changed_by_key: dict[str, list[str]] = {}
    try:
        scratch = manager.create(PLAN_CHECK_WORKTREE, baseline.commit_sha, recreate=True)
        for entry in artifact.experiments:
            patch = patch_paths[entry.key]
            applies, message = manager.apply_patch_check(scratch, patch)
            if not applies:
                result.errors.append(
                    f"experiments.{entry.key}: patch does not apply at baseline "
                    f"{baseline.commit_sha[:12]} — {message}"
                )
                continue
            changed_by_key[entry.key] = manager.patch_numstat(scratch, patch)
    except WorktreeError as exc:
        result.errors.append(f"Could not prepare the patch-check worktree: {exc}")
        return result, None
    finally:
        with contextlib.suppress(WorktreeError):
            manager.remove(PLAN_CHECK_WORKTREE)
    if result.errors:
        return result, None

    # Layer 5: path guard per experiment (violations => rejected record, not error).
    now = datetime.now(UTC)
    plan_id = next_plan_id(conn)
    experiment_ids = next_experiment_ids(conn, len(artifact.experiments))
    experiments: list[Experiment] = []
    seen_hashes: dict[str, str] = {}
    runnable = 0
    for entry, experiment_id in zip(artifact.experiments, experiment_ids, strict=True):
        patch_text = patch_paths[entry.key].read_text(encoding="utf-8")
        digest = hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
        if digest in seen_hashes:
            result.warnings.append(
                f"experiments.{entry.key}: patch is identical to "
                f"{seen_hashes[digest]} — duplicate variant?"
            )
        seen_hashes.setdefault(digest, entry.key)

        changed = changed_by_key[entry.key]
        guard = check_changed_paths(changed, contract.spec.permissions)
        status = ExperimentStatus.PLANNED
        decision = None
        if not guard.allowed:
            status = ExperimentStatus.REJECTED
            details = ", ".join(
                f"{violation.path} ({violation.rule.value})" for violation in guard.violations
            )
            decision = Decision(
                outcome=DecisionOutcome.REJECT,
                reason=f"changes protected or non-editable paths: {details}",
            )
            result.warnings.append(
                f"experiments.{entry.key} ({experiment_id}): {decision.reason} — "
                "recorded as rejected; it will not run."
            )
        else:
            runnable += 1

        experiments.append(
            Experiment(
                experiment_id=experiment_id,
                plan_id=plan_id,
                hypothesis_id=artifact.hypothesis_id,
                title=entry.title,
                change_summary=entry.change_summary,
                patch_text=patch_text,
                patch_sha256=digest,
                changed_files=changed,
                path_violations=guard.violations,
                expected_effect=entry.expected_effect,
                status=status,
                decision=decision,
                created_at=now,
                updated_at=now,
            )
        )

    if runnable == 0:
        result.errors.append(
            "experiments: every variant was rejected by the path guard — nothing to run. "
            "Author changes inside editable_paths only."
        )
        return result, None

    # Layer 6: transactional persist + patch copies into artifacts.
    plan = ExperimentPlan(
        plan_id=plan_id,
        hypothesis_id=artifact.hypothesis_id,
        contract_id=contract.contract_id,
        contract_version=contract.contract_version,
        baseline_id=baseline.baseline_id,
        baseline_commit=baseline.commit_sha,
        approach_summary=artifact.approach_summary,
        source_file=str(path),
        created_at=now,
        updated_at=now,
    )
    insert_plan(conn, project.id, plan, experiments)
    for experiment in experiments:
        target_dir = experiment_artifacts_dir(repo_root) / plan_id / experiment.experiment_id
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "change.patch").write_text(experiment.patch_text, encoding="utf-8")
    return result, plan
