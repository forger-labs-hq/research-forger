from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from researchforge.contract.render import render_contract_yaml
from researchforge.domain.contract import (
    ConstraintOperator,
    ContractSpec,
    HardConstraint,
    MetricDirection,
)

CONTRACTS = Path(__file__).parent.parent / "fixtures" / "contracts"


def _load_example() -> dict[str, object]:
    data = yaml.safe_load((CONTRACTS / "example_full.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


class TestContractSpec:
    def test_spec_example_parses(self) -> None:
        spec = ContractSpec.model_validate(_load_example())

        assert spec.version == 1
        assert spec.project.name == "adaptive-routing-study"
        assert spec.objective.primary_metric.direction is MetricDirection.MAXIMIZE
        assert len(spec.objective.hard_constraints) == 2
        assert spec.objective.hard_constraints[0].operator is ConstraintOperator.LE
        assert spec.execution.screening_command is not None
        assert spec.permissions.protected_paths == ["benchmarks/", "test_data/", "evaluator/"]
        assert spec.shipping.allow_draft_pr is False

    def test_unknown_top_level_key_rejected(self) -> None:
        data = _load_example()
        data["novelty"] = "guaranteed"
        with pytest.raises(ValidationError):
            ContractSpec.model_validate(data)

    def test_unknown_nested_key_rejected(self) -> None:
        data = _load_example()
        execution = data["execution"]
        assert isinstance(execution, dict)
        execution["gpu_limit"] = 1
        with pytest.raises(ValidationError):
            ContractSpec.model_validate(data)

    def test_version_must_be_one(self) -> None:
        data = _load_example()
        data["version"] = 2
        with pytest.raises(ValidationError):
            ContractSpec.model_validate(data)

    def test_constraint_value_must_be_finite(self) -> None:
        with pytest.raises(ValidationError):
            HardConstraint(name="x", operator=ConstraintOperator.LE, value=float("nan"))
        with pytest.raises(ValidationError):
            HardConstraint(name="x", operator=ConstraintOperator.LE, value=float("inf"))

    def test_render_round_trip(self) -> None:
        spec = ContractSpec.model_validate(_load_example())
        rendered = render_contract_yaml(spec)
        reparsed = ContractSpec.model_validate(yaml.safe_load(rendered))
        assert reparsed == spec
