import pytest

from researchforge.domain.contract import ConstraintOperator, HardConstraint
from researchforge.domain.experiment import BenchmarkStage
from researchforge.execution.constraints import constraints_ok, evaluate_constraints, violated
from researchforge.execution.metrics import MetricResult


def _metrics(primary: float = 0.8, **secondary: float) -> MetricResult:
    return MetricResult.model_validate(
        {
            "schema_version": 1,
            "primary_metric": {"name": "f1", "value": primary},
            "secondary_metrics": secondary,
        }
    )


def _constraint(name: str, operator: str, value: float) -> HardConstraint:
    return HardConstraint(name=name, operator=ConstraintOperator(operator), value=value)


class TestOperators:
    @pytest.mark.parametrize(
        ("operator", "observed", "threshold", "expected"),
        [
            ("<=", 200.0, 200.0, True),
            ("<=", 200.1, 200.0, False),
            (">=", 0.8, 0.8, True),
            (">=", 0.79, 0.8, False),
            ("<", 199.9, 200.0, True),
            ("<", 200.0, 200.0, False),
            (">", 0.81, 0.8, True),
            (">", 0.8, 0.8, False),
            ("==", 42.0, 42.0, True),
            ("==", 42.0 + 1e-12, 42.0, True),  # isclose tolerance
            ("==", 42.1, 42.0, False),
        ],
    )
    def test_operator_semantics(
        self, operator: str, observed: float, threshold: float, expected: bool
    ) -> None:
        results = evaluate_constraints(
            _metrics(p95_latency_ms=observed),
            [_constraint("p95_latency_ms", operator, threshold)],
            stage=BenchmarkStage.FULL,
        )
        assert results[0].passed is expected

    def test_primary_metric_can_be_constrained(self) -> None:
        results = evaluate_constraints(
            _metrics(primary=0.85),
            [_constraint("f1", ">=", 0.8)],
            stage=BenchmarkStage.FULL,
        )
        assert results[0].passed is True
        assert results[0].observed == 0.85


class TestMissingMetrics:
    def test_screening_missing_metric_is_unevaluable(self) -> None:
        results = evaluate_constraints(
            _metrics(),
            [_constraint("p95_latency_ms", "<=", 200)],
            stage=BenchmarkStage.SCREENING,
        )
        assert results[0].passed is None
        assert "screening" in (results[0].detail or "")
        assert constraints_ok(results)  # None tolerated at screening

    @pytest.mark.parametrize("stage", [BenchmarkStage.FULL, BenchmarkStage.VALIDATION])
    def test_full_and_validation_missing_metric_fails(self, stage: BenchmarkStage) -> None:
        results = evaluate_constraints(
            _metrics(),
            [_constraint("p95_latency_ms", "<=", 200)],
            stage=stage,
        )
        assert results[0].passed is False
        assert not constraints_ok(results)

    def test_no_metrics_at_all(self) -> None:
        results = evaluate_constraints(
            None,
            [_constraint("p95_latency_ms", "<=", 200)],
            stage=BenchmarkStage.FULL,
        )
        assert results[0].passed is False


class TestHelpers:
    def test_violated_lists_only_failures(self) -> None:
        results = evaluate_constraints(
            _metrics(p95_latency_ms=250.0, memory_mb=100.0),
            [
                _constraint("p95_latency_ms", "<=", 200),
                _constraint("memory_mb", "<=", 512),
            ],
            stage=BenchmarkStage.FULL,
        )
        bad = violated(results)
        assert [v.name for v in bad] == ["p95_latency_ms"]
        assert not constraints_ok(results)

    def test_empty_constraints_pass(self) -> None:
        assert constraints_ok(evaluate_constraints(_metrics(), [], stage=BenchmarkStage.FULL))
