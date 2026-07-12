"""Hard-constraint evaluation against reported metrics (pure)."""

from __future__ import annotations

import math

from researchforge.domain.contract import ConstraintOperator, HardConstraint
from researchforge.domain.experiment import BenchmarkStage, ConstraintResult
from researchforge.execution.metrics import MetricResult

_EQ_REL_TOL = 1e-9


def _observed(metrics: MetricResult, name: str) -> float | None:
    if metrics.primary_metric.name == name:
        return metrics.primary_metric.value
    return metrics.secondary_metrics.get(name)


def _apply(operator: ConstraintOperator, observed: float, threshold: float) -> bool:
    match operator:
        case ConstraintOperator.LE:
            return observed <= threshold
        case ConstraintOperator.GE:
            return observed >= threshold
        case ConstraintOperator.LT:
            return observed < threshold
        case ConstraintOperator.GT:
            return observed > threshold
        case ConstraintOperator.EQ:
            return math.isclose(observed, threshold, rel_tol=_EQ_REL_TOL)


def evaluate_constraints(
    metrics: MetricResult | None,
    constraints: list[HardConstraint],
    *,
    stage: BenchmarkStage,
) -> list[ConstraintResult]:
    """Evaluate every contract constraint against the reported metrics.

    A constraint whose metric was not reported is unevaluable: at the
    screening stage that yields ``passed=None`` (subsets may not measure
    everything); at full/validation stages it fails (``passed=False``) —
    an unverifiable constraint cannot pass (spec: invalid metrics reject).
    """
    results: list[ConstraintResult] = []
    for constraint in constraints:
        observed = _observed(metrics, constraint.name) if metrics is not None else None
        if observed is None:
            if stage is BenchmarkStage.SCREENING:
                results.append(
                    ConstraintResult(
                        name=constraint.name,
                        operator=constraint.operator,
                        threshold=constraint.value,
                        observed=None,
                        passed=None,
                        detail="not measured by the screening subset",
                    )
                )
            else:
                results.append(
                    ConstraintResult(
                        name=constraint.name,
                        operator=constraint.operator,
                        threshold=constraint.value,
                        observed=None,
                        passed=False,
                        detail="constraint metric not reported in the result file",
                    )
                )
            continue
        passed = _apply(constraint.operator, observed, constraint.value)
        results.append(
            ConstraintResult(
                name=constraint.name,
                operator=constraint.operator,
                threshold=constraint.value,
                observed=observed,
                passed=passed,
                detail=None
                if passed
                else f"{observed} {constraint.operator.value} {constraint.value} is false",
            )
        )
    return results


def constraints_ok(results: list[ConstraintResult]) -> bool:
    """No constraint definitively failed (None is tolerated — screening only)."""
    return all(result.passed is not False for result in results)


def violated(results: list[ConstraintResult]) -> list[ConstraintResult]:
    return [result for result in results if result.passed is False]
