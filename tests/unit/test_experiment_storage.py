import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from researchforge.domain.baseline import BaselineRun, BaselineStatus, EnvironmentFingerprint
from researchforge.domain.environment import ExecutionEngine
from researchforge.domain.experiment import (
    Experiment,
    ExperimentPlan,
    ExperimentRunGroup,
    ExperimentStatus,
    PlanStatus,
)
from researchforge.storage.baseline_repository import (
    get_latest_baseline,
    get_latest_successful_baseline,
    insert_baseline_run,
)
from researchforge.storage.db import ensure_schema, get_connection
from researchforge.storage.experiment_repository import (
    get_experiment,
    get_open_run_for_plan,
    get_plan,
    insert_plan,
    insert_run,
    list_experiments,
    next_experiment_ids,
    next_plan_id,
    next_run_id,
    update_experiment,
    update_plan_status,
    update_run,
)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = get_connection(tmp_path / "researchforge.db")
    ensure_schema(connection)
    try:
        yield connection
    finally:
        connection.close()


def _now() -> datetime:
    return datetime.now(UTC)


def _plan(plan_id: str = "plan-001") -> ExperimentPlan:
    return ExperimentPlan(
        plan_id=plan_id,
        hypothesis_id="hyp-001",
        contract_id="c1",
        contract_version=1,
        baseline_id="b1",
        baseline_commit="a" * 40,
        approach_summary="Try things.",
        source_file="plan.yaml",
        created_at=_now(),
        updated_at=_now(),
    )


def _experiment(experiment_id: str = "exp-001", plan_id: str = "plan-001") -> Experiment:
    return Experiment(
        experiment_id=experiment_id,
        plan_id=plan_id,
        hypothesis_id="hyp-001",
        title="Variant",
        change_summary="Change a thing.",
        patch_text="diff --git a/src/x.py b/src/x.py\n",
        patch_sha256="0" * 64,
        changed_files=["src/x.py"],
        created_at=_now(),
        updated_at=_now(),
    )


def _baseline(kind: str, status: BaselineStatus = BaselineStatus.SUCCEEDED) -> BaselineRun:
    from uuid import uuid4

    return BaselineRun(
        baseline_id=uuid4().hex,
        contract_id="c1",
        contract_version=1,
        commit_sha="a" * 40,
        execution_mode=ExecutionEngine.VENV,
        command="python eval.py",
        command_kind=kind,
        status=status,
        fingerprint=EnvironmentFingerprint(
            platform="test",
            execution_mode=ExecutionEngine.VENV,
            contract_id="c1",
            contract_version=1,
            commit_sha="a" * 40,
        ),
        stdout_path="s",
        stderr_path="e",
        started_at=_now(),
        completed_at=_now(),
        duration_seconds=1.0,
    )


class TestIdSequences:
    def test_first_ids(self, conn: sqlite3.Connection) -> None:
        assert next_plan_id(conn) == "plan-001"
        assert next_run_id(conn) == "run-001"
        assert next_experiment_ids(conn, 3) == ["exp-001", "exp-002", "exp-003"]

    def test_ids_advance_after_insert(self, conn: sqlite3.Connection) -> None:
        insert_plan(conn, "p", _plan(), [_experiment("exp-001"), _experiment("exp-002")])
        assert next_plan_id(conn) == "plan-002"
        assert next_experiment_ids(conn, 1) == ["exp-003"]


class TestPlanRoundTrip:
    def test_insert_and_get(self, conn: sqlite3.Connection) -> None:
        insert_plan(conn, "p", _plan(), [_experiment()])
        fetched = get_plan(conn, "plan-001")
        assert fetched is not None
        assert fetched.hypothesis_id == "hyp-001"
        assert fetched.status is PlanStatus.PLANNED

        experiments = list_experiments(conn, "plan-001")
        assert len(experiments) == 1
        assert experiments[0].patch_text.startswith("diff --git")

    def test_update_plan_status(self, conn: sqlite3.Connection) -> None:
        insert_plan(conn, "p", _plan(), [_experiment()])
        update_plan_status(conn, "plan-001", PlanStatus.APPROVED)
        fetched = get_plan(conn, "plan-001")
        assert fetched is not None
        assert fetched.status is PlanStatus.APPROVED

    def test_transactional_insert(self, conn: sqlite3.Connection) -> None:
        # Second experiment with duplicate id must roll back everything.
        with pytest.raises(sqlite3.IntegrityError):
            insert_plan(conn, "p", _plan(), [_experiment("exp-001"), _experiment("exp-001")])
        assert get_plan(conn, "plan-001") is None
        assert list_experiments(conn) == []


class TestExperimentUpdate:
    def test_status_update_persists(self, conn: sqlite3.Connection) -> None:
        insert_plan(conn, "p", _plan(), [_experiment()])
        experiment = get_experiment(conn, "exp-001")
        assert experiment is not None
        update_experiment(conn, experiment.model_copy(update={"status": ExperimentStatus.APPROVED}))
        fetched = get_experiment(conn, "exp-001")
        assert fetched is not None
        assert fetched.status is ExperimentStatus.APPROVED


class TestRunGroups:
    def test_open_run_lookup(self, conn: sqlite3.Connection) -> None:
        insert_plan(conn, "p", _plan(), [_experiment()])
        run = ExperimentRunGroup(
            run_id="run-001",
            plan_id="plan-001",
            execution_mode=ExecutionEngine.VENV,
            started_at=_now(),
        )
        insert_run(conn, "p", run)
        assert get_open_run_for_plan(conn, "plan-001") is not None

        from researchforge.domain.experiment import RunStatus

        update_run(conn, run.model_copy(update={"status": RunStatus.COMPLETED}))
        assert get_open_run_for_plan(conn, "plan-001") is None


class TestBaselineKindFilter:
    def test_screening_baseline_never_satisfies_gate(self, conn: sqlite3.Connection) -> None:
        insert_baseline_run(conn, "p", _baseline("full"))
        insert_baseline_run(conn, "p", _baseline("screening"))

        latest = get_latest_baseline(conn)
        assert latest is not None
        assert latest.command_kind == "full"

        successful = get_latest_successful_baseline(conn)
        assert successful is not None
        assert successful.command_kind == "full"

        screening = get_latest_baseline(conn, command_kind="screening")
        assert screening is not None
        assert screening.command_kind == "screening"
