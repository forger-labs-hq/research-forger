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


_BRANCHABLE_STATUSES = frozenset(
    {
        ExperimentStatus.PROMISING,
        ExperimentStatus.REJECTED,
        ExperimentStatus.VALIDATED,
        ExperimentStatus.IMPLEMENTATION_READY,
    }
)


def _resolve_parents(
    conn: sqlite3.Connection,
    artifact: ExperimentPlanArtifact,
    result: ImportResult,
    base: Path | None = None,
) -> tuple[dict[str, list[str]], dict[str, str | None]]:
    """Ancestor patch texts (root->parent, excluding the entry's own patch) and
    the immediate parent's experiment id ('' marks a same-plan key resolved
    to its assigned id later) for every entry.
    """
    from researchforge.storage.experiment_repository import get_experiment

    entries = {entry.key: entry for entry in artifact.experiments}
    chains: dict[str, list[str]] = {}
    parents: dict[str, str | None] = {}

    def db_chain(experiment_id: str, where: str) -> list[str] | None:
        """Patch texts for experiment_id's full ancestor chain, root first."""
        texts: list[str] = []
        seen: set[str] = set()
        current: str | None = experiment_id
        while current is not None:
            if current in seen:
                result.errors.append(f"{where}: parent chain contains a cycle at {current}.")
                return None
            seen.add(current)
            experiment = get_experiment(conn, current)
            if experiment is None:
                result.errors.append(f"{where}: unknown parent experiment {current!r}.")
                return None
            if experiment.status not in _BRANCHABLE_STATUSES:
                result.errors.append(
                    f"{where}: parent {current} is {experiment.status.value} — only "
                    "measured experiments (promising/rejected/validated/"
                    "implementation_ready) can be branched on."
                )
                return None
            texts.append(experiment.patch_text)
            current = experiment.parent_experiment_id
        return list(reversed(texts))

    def entry_chain(key: str, visiting: set[str]) -> list[str] | None:
        """Ancestor patch texts for a same-plan entry key (root first,
        INCLUDING that entry's own patch — it is an ancestor of its children)."""
        if key in visiting:
            result.errors.append(f"experiments.{key}: parent chain contains a cycle.")
            return None
        if key in chains:  # memoized: chain up to (excluding) this entry
            own = _read_entry_patch(entries[key])
            return [*chains[key], own] if own is not None else None
        visiting.add(key)
        entry = entries[key]
        prefix: list[str] = []
        if entry.parent is not None:
            if entry.parent in entries:
                parent_chain = entry_chain(entry.parent, visiting)
                if parent_chain is None:
                    return None
                prefix = parent_chain
            else:
                resolved = db_chain(entry.parent, f"experiments.{key}.parent")
                if resolved is None:
                    return None
                prefix = resolved
        visiting.discard(key)
        chains[key] = prefix
        own = _read_entry_patch(entry)
        return [*prefix, own] if own is not None else None

    def _read_entry_patch(entry: object) -> str | None:
        # Patch files are re-validated in Layer 3; here we only need the text
        # for chain composition, tolerating missing files (Layer 3 reports).
        from researchforge.experiments.context_export import PlannedExperimentEntry

        assert isinstance(entry, PlannedExperimentEntry)
        patches_root = (experiments_dir(base) / PATCHES_DIR_NAME).resolve()
        candidate = (experiments_dir(base) / entry.patch_file).resolve()
        if not candidate.is_relative_to(patches_root):
            return None  # Layer 3 reports the containment violation
        try:
            return candidate.read_text(encoding="utf-8")
        except OSError:
            return None

    for entry in artifact.experiments:
        if entry.parent is None:
            chains[entry.key] = []
            parents[entry.key] = None
            continue
        if entry.parent in entries:
            parent_chain = entry_chain(entry.parent, set())
            if parent_chain is not None:
                chains[entry.key] = parent_chain
            parents[entry.key] = ""  # same-plan; resolved to an id at persist time
        else:
            resolved = db_chain(entry.parent, f"experiments.{entry.key}.parent")
            if resolved is not None:
                chains[entry.key] = resolved
            parents[entry.key] = entry.parent
    return chains, parents


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

    # Layer 2b: resolve `parent:` references (same-plan key or prior exp-NNN)
    # into ancestor patch chains, refusing cycles and unmeasured parents.
    chain_texts_by_key, parent_id_by_key = _resolve_parents(conn, artifact, result, base)
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
    # Entries with a parent get a fresh worktree with the ancestor chain
    # actually applied, so the child's diff is checked against the state it
    # was written for; changed files are the union of the whole chain.
    manager = WorktreeManager(repo_root)
    changed_by_key: dict[str, list[str]] = {}
    try:
        scratch = manager.create(PLAN_CHECK_WORKTREE, baseline.commit_sha, recreate=True)
        for entry in artifact.experiments:
            patch = patch_paths[entry.key]
            chain = chain_texts_by_key.get(entry.key, [])
            if chain:
                scratch = manager.create(PLAN_CHECK_WORKTREE, baseline.commit_sha, recreate=True)
                chain_files: list[str] = []
                chain_ok = True
                for depth, ancestor_text in enumerate(chain):
                    ancestor_patch = scratch / f".rf-ancestor-{depth}.patch"
                    ancestor_patch.write_text(ancestor_text, encoding="utf-8")
                    chain_files.extend(manager.patch_numstat(scratch, ancestor_patch))
                    try:
                        manager.apply_patch(scratch, ancestor_patch)
                    except WorktreeError as exc:
                        result.errors.append(
                            f"experiments.{entry.key}: ancestor patch #{depth + 1} in the "
                            f"parent chain no longer applies — {exc}"
                        )
                        chain_ok = False
                        break
                    finally:
                        ancestor_patch.unlink(missing_ok=True)
                if not chain_ok:
                    continue
                applies, message = manager.apply_patch_check(scratch, patch)
                if not applies:
                    result.errors.append(
                        f"experiments.{entry.key}: patch does not apply on top of its "
                        f"parent chain — {message}"
                    )
                    continue
                own_files = manager.patch_numstat(scratch, patch)
                changed_by_key[entry.key] = sorted(set(chain_files) | set(own_files))
                # Leave a clean baseline worktree for subsequent parentless entries.
                scratch = manager.create(PLAN_CHECK_WORKTREE, baseline.commit_sha, recreate=True)
                continue
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
    id_by_key = {
        entry.key: experiment_id
        for entry, experiment_id in zip(artifact.experiments, experiment_ids, strict=True)
    }
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

        parent_ref = parent_id_by_key.get(entry.key)
        if parent_ref == "":  # same-plan key -> the id assigned in this import
            assert entry.parent is not None
            parent_ref = id_by_key[entry.parent]
        experiments.append(
            Experiment(
                experiment_id=experiment_id,
                plan_id=plan_id,
                hypothesis_id=artifact.hypothesis_id,
                parent_experiment_id=parent_ref,
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
