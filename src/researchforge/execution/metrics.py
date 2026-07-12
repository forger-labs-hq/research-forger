"""Benchmark result parsing and validation (spec: benchmark result schema)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from researchforge.domain.contract import ContractSpec

MAX_RESULT_BYTES = 2_000_000


class MetricParseError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def _reject_constant(value: str) -> float:
    raise ValueError(f"non-finite JSON constant not allowed: {value}")


def _require_finite_number(value: object, where: str) -> float:
    # bool is an int subclass — reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{where}: value must be a number, got {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{where}: value must be finite")
    return number


class MetricValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value: float

    @field_validator("value", mode="before")
    @classmethod
    def _numeric(cls, v: object) -> float:
        return _require_finite_number(v, "primary_metric.value")


class MetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    primary_metric: MetricValue
    secondary_metrics: dict[str, float] = Field(default_factory=dict)
    sample_count: int | None = Field(default=None, ge=1)
    seed: int | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("secondary_metrics", mode="before")
    @classmethod
    def _numeric_secondaries(cls, v: object) -> object:
        if isinstance(v, dict):
            return {
                key: _require_finite_number(value, f"secondary_metrics.{key}")
                for key, value in v.items()
            }
        return v


def parse_result_file(path: Path, spec: ContractSpec) -> tuple[MetricResult, list[str]]:
    """Parse and validate a result file against the contract.

    Returns (result, warnings); raises MetricParseError on any violation.
    """
    if not path.is_file():
        raise MetricParseError(
            [
                f"Result file not found at {path} — the evaluation command must write "
                f"'{spec.execution.result_file}' inside the worktree."
            ]
        )
    if path.stat().st_size > MAX_RESULT_BYTES:
        raise MetricParseError([f"Result file exceeds {MAX_RESULT_BYTES} bytes."])

    text = path.read_text(encoding="utf-8")
    try:
        raw = json.loads(text, parse_constant=_reject_constant)
    except ValueError as exc:
        raise MetricParseError([f"Result file is not valid JSON: {exc}"]) from exc

    if not isinstance(raw, dict):
        raise MetricParseError(
            [f"Result file must contain a JSON object, got {type(raw).__name__}."]
        )

    try:
        result = MetricResult.model_validate(raw)
    except ValidationError as exc:
        messages = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"])
            messages.append(f"{location or '<root>'}: {error['msg']}")
        raise MetricParseError(messages) from exc

    expected = spec.objective.primary_metric.name
    if result.primary_metric.name != expected:
        raise MetricParseError(
            [
                f"primary_metric.name is {result.primary_metric.name!r} but the contract "
                f"expects {expected!r}."
            ]
        )

    warnings = []
    reported = {result.primary_metric.name, *result.secondary_metrics}
    for constraint in spec.objective.hard_constraints:
        if constraint.name not in reported:
            warnings.append(
                f"hard constraint {constraint.name!r} was not reported in the result file."
            )
    return result, warnings
