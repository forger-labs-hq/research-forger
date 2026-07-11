"""The Hypothesis domain entity (spec: required hypothesis schema)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, computed_field

HYPOTHESIS_ID_PATTERN = r"^hyp-\d{3}$"


class ImpactDirection(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"
    UNKNOWN = "unknown"


class Level(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class NoveltyConfidence(StrEnum):
    """Deliberately has no HIGH member: a novelty guarantee is unrepresentable."""

    LOW = "low"
    MEDIUM = "medium"
    UNKNOWN = "unknown"


class HypothesisStatus(StrEnum):
    """Only `speculative` exists in Phase 1A; experiment phases add more."""

    SPECULATIVE = "speculative"


class ExpectedImpact(BaseModel):
    metric: str | None = None
    direction: ImpactDirection = ImpactDirection.UNKNOWN


class Hypothesis(BaseModel):
    hypothesis_id: str = Field(pattern=HYPOTHESIS_ID_PATTERN)
    title: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    supporting_paper_ids: list[str] = Field(default_factory=list)
    contradicting_paper_ids: list[str] = Field(default_factory=list)
    repository_observations: list[str] = Field(default_factory=list)
    expected_impact: ExpectedImpact = Field(default_factory=ExpectedImpact)
    feasibility: Level
    estimated_effort: Level
    estimated_experiment_count: int | None = Field(default=None, ge=1)
    novelty_confidence: NoveltyConfidence
    status: HypothesisStatus = HypothesisStatus.SPECULATIVE
    proposed_experiment: str = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_status(self) -> Literal["supported", "unsupported"]:
        """Derived, never author-supplied: cites evidence or is labeled unsupported."""
        return "supported" if self.supporting_paper_ids else "unsupported"
