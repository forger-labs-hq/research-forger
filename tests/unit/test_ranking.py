"""Pure ranking/Pareto tests, including the spec §15.4 example table."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml

from researchforge.domain.baseline import BaselineRun, BaselineStatus, EnvironmentFingerprint
from researchforge.domain.contract import ContractSpec, MetricDirection
from researchforge.domain.environment import ExecutionEngine
from researchforge.domain.experiment import (
    BenchmarkStage,
    Decision,
    DecisionOutcome,
    ExecutionArtifacts,
    ExecutionRecordStatus,
    Experiment,
    ExperimentExecution,
    ExperimentStatus,
)
from researchforge.execution.metrics import MetricResult
from researchforge.execution.ranking import (
    ONE_OFF_CAVEAT,
    build_ranking_report,
    dominates,
    inferred_directions,
    relative_improvement_pct,
    signed_improvement,
)

CONTRACTS = Path(__file__).parent.parent / "fixtures" / "contracts"


def _spec() -> ContractSpec:
    """The spec §10 example: maximize quality_score; average_cost_usd <= 0.02."""
    data = yaml.safe_load((CONTRACTS / "example_full.yaml").read_text(encoding="utf-8"))
    return ContractSpec.model_validate(data)


def _metrics(quality: float, latency: float, cost: float) -> MetricResult:
    return MetricResult.model_validate(
        {
            "schema_version": 1,
            "primary_metric": {"name": "quality_score", "value": quality},
            "secondary_metrics": {"p95_latency_ms": latency, "average_cost_usd": cost},
        }
    )


def _baseline(quality: float = 0.810, latency: float = 180.0, cost: float = 0.012) -> BaselineRun:
    now = datetime.now(UTC)
    return BaselineRun(
        baseline_id="b1",
        contract_id="c1",
        contract_version=1,
        commit_sha="a" * 40,
        execution_mode=ExecutionEngine.VENV,
        command="eval",
        status=BaselineStatus.SUCCEEDED,
        metrics=_metrics(quality, latency, cost),
        fingerprint=EnvironmentFingerprint(
            platform="test",
            execution_mode=ExecutionEngine.VENV,
            contract_id="c1",
            contract_version=1,
            commit_sha="a" * 40,
        ),
        stdout_path="s",
        stderr_path="e",
        started_at=now,
        completed_at=now,
        duration_seconds=1.0,
    )


def _experiment(experiment_id: str, status: ExperimentStatus, reason: str = "r") -> Experiment:
    now = datetime.now(UTC)
    return Experiment(
        experiment_id=experiment_id,
        plan_id="plan-001",
        hypothesis_id="hyp-001",
        title=f"Candidate {experiment_id[-1].upper()}",
        change_summary="c",
        patch_text="p",
        patch_sha256="0" * 64,
        status=status,
        decision=Decision(
            outcome=DecisionOutcome.KEEP
            if status in (ExperimentStatus.PROMISING, ExperimentStatus.VALIDATED)
            else DecisionOutcome.REJECT,
            reason=reason,
        ),
        created_at=now,
        updated_at=now,
    )


def _execution(experiment_id: str, metrics: MetricResult) -> ExperimentExecution:
    now = datetime.now(UTC)
    return ExperimentExecution(
        execution_id=uuid4().hex,
        experiment_id=experiment_id,
        run_id="run-001",
        hypothesis_id="hyp-001",
        baseline_commit="a" * 40,
        execution_mode=ExecutionEngine.VENV,
        benchmark_stage=BenchmarkStage.FULL,
        attempt=1,
        change_summary="c",
        started_at=now,
        completed_at=now,
        status=ExecutionRecordStatus.SUCCEEDED,
        metrics=metrics,
        artifacts=ExecutionArtifacts(diff_path="d", stdout_path="o", stderr_path="e"),
        fingerprint=EnvironmentFingerprint(
            platform="test",
            execution_mode=ExecutionEngine.VENV,
            contract_id="c1",
            contract_version=1,
            commit_sha="a" * 40,
        ),
    )


class TestPureHelpers:
    def test_signed_improvement_directions(self) -> None:
        assert signed_improvement(0.8, 0.85, MetricDirection.MAXIMIZE) > 0
        assert signed_improvement(0.8, 0.75, MetricDirection.MAXIMIZE) < 0
        assert signed_improvement(200, 150, MetricDirection.MINIMIZE) > 0
        assert signed_improvement(200, 250, MetricDirection.MINIMIZE) < 0

    def test_relative_improvement_zero_baseline_guard(self) -> None:
        assert relative_improvement_pct(0.0, 1.0, MetricDirection.MAXIMIZE) is None
        pct = relative_improvement_pct(0.8, 0.84, MetricDirection.MAXIMIZE)
        assert pct is not None and abs(pct - 5.0) < 1e-9

    def test_inferred_directions_from_operators(self) -> None:
        directions = inferred_directions(_spec())
        assert directions["quality_score"] is MetricDirection.MAXIMIZE
        assert directions["average_cost_usd"] is MetricDirection.MINIMIZE
        # quality_regression is <= constrained -> minimize
        assert directions["quality_regression"] is MetricDirection.MINIMIZE
        # p95_latency_ms is only a secondary with no constraint -> no direction
        assert "p95_latency_ms" not in directions

    def test_dominates(self) -> None:
        directions = {
            "quality_score": MetricDirection.MAXIMIZE,
            "average_cost_usd": MetricDirection.MINIMIZE,
        }
        better = {"quality_score": 0.85, "average_cost_usd": 0.01}
        worse = {"quality_score": 0.84, "average_cost_usd": 0.012}
        tradeoff = {"quality_score": 0.86, "average_cost_usd": 0.02}
        assert dominates(better, worse, directions)
        assert not dominates(worse, better, directions)
        assert not dominates(better, tradeoff, directions)  # tradeoff wins on quality
        assert not dominates(tradeoff, better, directions)  # better wins on cost


class TestSpec154Example:
    """Spec §15.4: A rejected (cost constraint); B quality candidate; C
    efficiency candidate — B and C both on the frontier."""

    def _report(self):  # noqa: ANN202
        baseline = _baseline()
        experiments = [
            _experiment("exp-001", ExperimentStatus.REJECTED, "hard constraint average_cost_usd"),
            _experiment("exp-002", ExperimentStatus.PROMISING),
            _experiment("exp-003", ExperimentStatus.PROMISING),
        ]
        executions = [
            _execution("exp-001", _metrics(0.852, 340.0, 0.020)),
            _execution("exp-002", _metrics(0.841, 195.0, 0.014)),
            _execution("exp-003", _metrics(0.838, 172.0, 0.011)),
        ]
        return build_ranking_report(
            "run-001",
            baseline,
            experiments,
            executions,
            _spec(),
            tradeoff_material_pct=5.0,
        )

    def test_rejected_history_complete(self) -> None:
        report = self._report()
        rejected_ids = [row.experiment_id for row in report.rejected]
        assert rejected_ids == ["exp-001"]
        assert "average_cost_usd" in (report.rejected[0].decision.reason or "")

    def test_candidates_ranked_by_primary(self) -> None:
        report = self._report()
        assert [row.experiment_id for row in report.candidates] == ["exp-002", "exp-003"]
        assert report.candidates[0].primary_delta_pct is not None

    def test_both_on_pareto_frontier_no_single_winner(self) -> None:
        report = self._report()
        # B is better on quality; C is better on cost -> both non-dominated.
        assert set(report.pareto_ids) == {"exp-002", "exp-003"}
        assert report.single_winner is None
        assert any("average_cost_usd" in note for note in report.trade_off_notes)

    def test_one_off_caveat_present_for_promising(self) -> None:
        report = self._report()
        assert ONE_OFF_CAVEAT in report.caveats

    def test_undirected_secondary_note(self) -> None:
        report = self._report()
        assert any("p95_latency_ms" in caveat for caveat in report.caveats)


class TestSingleWinner:
    def test_dominant_candidate_collapses_frontier(self) -> None:
        baseline = _baseline()
        experiments = [
            _experiment("exp-001", ExperimentStatus.PROMISING),
            _experiment("exp-002", ExperimentStatus.PROMISING),
        ]
        executions = [
            _execution("exp-001", _metrics(0.86, 150.0, 0.010)),  # better on both
            _execution("exp-002", _metrics(0.84, 190.0, 0.015)),
        ]
        report = build_ranking_report(
            "run-001", baseline, experiments, executions, _spec(), tradeoff_material_pct=5.0
        )
        assert report.pareto_ids == ["exp-001"]
        assert report.single_winner == "exp-001"

    def test_validated_confidence_and_no_caveat(self) -> None:
        baseline = _baseline()
        experiments = [_experiment("exp-001", ExperimentStatus.VALIDATED)]
        executions = [_execution("exp-001", _metrics(0.86, 150.0, 0.010))]
        report = build_ranking_report(
            "run-001", baseline, experiments, executions, _spec(), tradeoff_material_pct=5.0
        )
        assert report.candidates[0].confidence == "validated"
        assert ONE_OFF_CAVEAT not in report.caveats
