"""End-to-end funnel tests on the knob-driven fixture (real venv on CI)."""

import json
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from researchforge.cli import app
from researchforge.storage.db import open_project_db


def _knob_patch(improvement: int, latency: float) -> str:
    return f"""\
diff --git a/src/algo.py b/src/algo.py
new file mode 100644
--- /dev/null
+++ b/src/algo.py
@@ -0,0 +1,2 @@
+IMPROVEMENT = {improvement}
+LATENCY = {latency}
"""


BROKEN_ALGO_PATCH = """\
diff --git a/src/algo.py b/src/algo.py
new file mode 100644
--- /dev/null
+++ b/src/algo.py
@@ -0,0 +1 @@
+this is not python ~~~
"""

PROTECTED_PATCH = """\
diff --git a/benchmarks/cheat.py b/benchmarks/cheat.py
new file mode 100644
--- /dev/null
+++ b/benchmarks/cheat.py
@@ -0,0 +1 @@
+CHEAT = True
"""


def _stage_plan(base: Path, entries: list[tuple[str, str]]) -> Path:
    staging = base / ".researchforge" / "experiments"
    patches = staging / "patches"
    patches.mkdir(parents=True, exist_ok=True)
    lines = [
        "hypothesis_id: hyp-001",
        "approach_summary: Knob variants.",
        "experiments:",
    ]
    for key, patch_text in entries:
        (patches / f"{key}.patch").write_text(patch_text, encoding="utf-8")
        lines += [
            f"  - key: {key}",
            f"    title: Variant {key}",
            f"    change_summary: Set knobs for {key}.",
            f"    patch_file: patches/{key}.patch",
        ]
    plan = staging / "plan.yaml"
    plan.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return plan


@pytest.fixture
def imported_batch(
    cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
) -> dict[str, str]:
    """Four variants: improving, constraint-violating, protected, failing.

    Returns {key: experiment_id}.
    """
    plan = _stage_plan(
        isolated_project_dir,
        [
            ("improve", _knob_patch(5, 150.0)),  # f1 0.85, p95 150 -> promising
            ("hot", _knob_patch(6, 250.0)),  # f1 0.86, p95 250 > 200 -> rejected
            ("cheat", PROTECTED_PATCH),  # rejected at import, never runs
            ("broken", BROKEN_ALGO_PATCH),  # evaluator crashes -> failed_execution
        ],
    )
    result = cli_runner.invoke(app, ["experiment", "import", str(plan)])
    assert result.exit_code == 0, result.output
    approve = cli_runner.invoke(app, ["experiment", "approve", "plan-001", "--yes"])
    assert approve.exit_code == 0, approve.output
    return {"improve": "exp-001", "hot": "exp-002", "cheat": "exp-003", "broken": "exp-004"}


class TestFunnelEndToEnd:
    def test_full_funnel(
        self,
        cli_runner: CliRunner,
        funnel_project: Path,
        isolated_project_dir: Path,
        imported_batch: dict[str, str],
    ) -> None:
        result = cli_runner.invoke(app, ["experiment", "run", "plan-001", "--json"])

        assert result.exit_code == 0, result.output
        summary = json.loads(result.output)
        assert summary["run_id"] == "run-001"
        assert summary["promising"] == [imported_batch["improve"]]
        assert summary["counts"]["promising"] == 1
        assert summary["counts"]["rejected"] == 2  # constraint violator + protected
        assert summary["counts"]["failed_execution"] == 1
        assert "validate run-001" in summary["next_action"]

        experiments = json.loads(cli_runner.invoke(app, ["experiment", "list", "--json"]).output)[
            "experiments"
        ]
        by_id = {e["experiment_id"]: e for e in experiments}

        improve = by_id[imported_batch["improve"]]
        assert improve["status"] == "promising"
        assert "not yet validated" in improve["decision"]["reason"]

        hot = by_id[imported_batch["hot"]]
        assert hot["status"] == "rejected"
        assert "p95_latency_ms" in hot["decision"]["reason"]  # visibly rejected

        cheat = by_id[imported_batch["cheat"]]
        assert cheat["status"] == "rejected"  # never ran (import-time)

        broken = by_id[imported_batch["broken"]]
        assert broken["status"] == "failed_execution"

        # The protected experiment truly never ran: no executions recorded.
        with closing(open_project_db()) as conn:
            rows = conn.execute(
                "SELECT COUNT(*) AS n FROM experiment_executions WHERE experiment_id = ?",
                (imported_batch["cheat"],),
            ).fetchone()
        assert rows["n"] == 0

    def test_screening_ran_before_full_and_artifacts_persist(
        self,
        cli_runner: CliRunner,
        funnel_project: Path,
        isolated_project_dir: Path,
        imported_batch: dict[str, str],
    ) -> None:
        assert cli_runner.invoke(app, ["experiment", "run", "plan-001"]).exit_code == 0

        with closing(open_project_db()) as conn:
            rows = conn.execute(
                "SELECT benchmark_stage, status FROM experiment_executions "
                "WHERE experiment_id = ? ORDER BY created_at",
                (imported_batch["improve"],),
            ).fetchall()
        stages = [row["benchmark_stage"] for row in rows]
        assert stages == ["screening", "full"]

        # Screening baseline stored separately with kind=screening.
        with closing(open_project_db()) as conn:
            kinds = [
                row[0]
                for row in conn.execute(
                    "SELECT json_extract(record, '$.command_kind') FROM baseline_runs"
                )
            ]
        assert kinds.count("screening") == 1
        assert kinds.count("full") == 1

        # Worktrees cleaned up; artifacts persist.
        worktrees = funnel_project / ".researchforge" / "worktrees"
        leftover = [p.name for p in worktrees.iterdir()] if worktrees.is_dir() else []
        assert all("exp-" not in name for name in leftover), leftover

        exp_artifacts = (
            funnel_project
            / ".researchforge"
            / "artifacts"
            / "experiments"
            / "run-001"
            / imported_batch["improve"]
        )
        for stage_dir in ("screening-a1", "full-a1"):
            assert (exp_artifacts / stage_dir / "manifest.json").is_file()
            assert (exp_artifacts / stage_dir / "diff.patch").is_file()
            assert (exp_artifacts / stage_dir / "results.json").is_file()

        manifest = json.loads(
            (exp_artifacts / "full-a1" / "manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["benchmark_stage"] == "full"
        assert manifest["changed_files"] == ["src/algo.py"]
        assert manifest["metrics"]["primary_metric"]["value"] == 0.85
        assert manifest["constraints"][0]["passed"] is True
        assert manifest["commands"] == ["python benchmarks/evaluate.py"]

    def test_rerun_refused_while_completed_and_gates_hold(
        self,
        cli_runner: CliRunner,
        funnel_project: Path,
        isolated_project_dir: Path,
        imported_batch: dict[str, str],
    ) -> None:
        assert cli_runner.invoke(app, ["experiment", "run", "plan-001"]).exit_code == 0

        again = cli_runner.invoke(app, ["experiment", "run", "plan-001"])
        assert again.exit_code == 1
        assert "completed" in again.output

    def test_unapproved_plan_refused(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        plan = _stage_plan(isolated_project_dir, [("improve", _knob_patch(5, 150.0))])
        assert cli_runner.invoke(app, ["experiment", "import", str(plan)]).exit_code == 0

        result = cli_runner.invoke(app, ["experiment", "run", "plan-001"])

        assert result.exit_code == 1
        assert "not approved" in result.output


class TestResume:
    def test_resume_recovers_interrupted_run(
        self,
        cli_runner: CliRunner,
        funnel_project: Path,
        isolated_project_dir: Path,
        imported_batch: dict[str, str],
    ) -> None:
        """Simulate a mid-run crash: run group open, one execution stuck
        `running`, its experiment stuck `running`, others still approved."""
        from datetime import UTC, datetime
        from uuid import uuid4

        from researchforge.domain.environment import ExecutionEngine
        from researchforge.domain.experiment import (
            ExperimentRunGroup,
            ExperimentStatus,
        )
        from researchforge.storage.experiment_repository import (
            get_experiment,
            insert_run,
            list_experiments,
            update_experiment,
        )
        from researchforge.storage.project_repository import get_project

        with closing(open_project_db()) as conn:
            project = get_project(conn)
            assert project is not None
            insert_run(
                conn,
                project.id,
                ExperimentRunGroup(
                    run_id="run-001",
                    plan_id="plan-001",
                    execution_mode=ExecutionEngine.VENV,
                    started_at=datetime.now(UTC),
                ),
            )
            # First experiment was mid-flight when the process died.
            improve = get_experiment(conn, imported_batch["improve"])
            assert improve is not None
            update_experiment(conn, improve.model_copy(update={"status": ExperimentStatus.RUNNING}))
            # Leave a stale `running` execution row for it.
            from researchforge.domain.baseline import EnvironmentFingerprint
            from researchforge.domain.experiment import (
                BenchmarkStage,
                ExecutionArtifacts,
                ExecutionRecordStatus,
                ExperimentExecution,
            )
            from researchforge.storage.experiment_repository import insert_execution

            insert_execution(
                conn,
                project.id,
                ExperimentExecution(
                    execution_id=uuid4().hex,
                    experiment_id=imported_batch["improve"],
                    run_id="run-001",
                    hypothesis_id="hyp-001",
                    baseline_commit="a" * 40,
                    execution_mode=ExecutionEngine.VENV,
                    benchmark_stage=BenchmarkStage.SCREENING,
                    attempt=1,
                    change_summary="s",
                    started_at=datetime.now(UTC),
                    status=ExecutionRecordStatus.RUNNING,
                    artifacts=ExecutionArtifacts(diff_path="d", stdout_path="o", stderr_path="e"),
                    fingerprint=EnvironmentFingerprint(
                        platform="test",
                        execution_mode=ExecutionEngine.VENV,
                        contract_id="c",
                        contract_version=1,
                        commit_sha="a" * 40,
                    ),
                ),
            )

        result = cli_runner.invoke(app, ["experiment", "resume", "run-001", "--json"])

        assert result.exit_code == 0, result.output
        summary = json.loads(result.output)
        assert summary["promising"] == [imported_batch["improve"]]
        assert summary["counts"]["rejected"] == 2
        assert summary["counts"]["failed_execution"] == 1

        # The stale execution was marked interrupted; the retry used attempt 2.
        with closing(open_project_db()) as conn:
            rows = conn.execute(
                "SELECT benchmark_stage, attempt, status FROM experiment_executions "
                "WHERE experiment_id = ? ORDER BY created_at",
                (imported_batch["improve"],),
            ).fetchall()
        by_stage_attempt = {(r["benchmark_stage"], r["attempt"]): r["status"] for r in rows}
        assert by_stage_attempt[("screening", 1)] == "failed_execution"  # interrupted
        assert by_stage_attempt[("screening", 2)] == "succeeded"
        assert by_stage_attempt[("full", 2)] == "succeeded"

        with closing(open_project_db()) as conn:
            experiments = list_experiments(conn, "plan-001")
        assert all(
            e.status.value in ("promising", "rejected", "failed_execution") for e in experiments
        )

    def test_resume_completed_run_is_noop(
        self,
        cli_runner: CliRunner,
        funnel_project: Path,
        isolated_project_dir: Path,
        imported_batch: dict[str, str],
    ) -> None:
        assert cli_runner.invoke(app, ["experiment", "run", "plan-001"]).exit_code == 0

        result = cli_runner.invoke(app, ["experiment", "resume", "run-001", "--json"])

        assert result.exit_code == 0
        summary = json.loads(result.output)
        assert summary["counts"]["promising"] == 1
