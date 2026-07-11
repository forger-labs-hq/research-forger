"""Research landscape artifact models (Claude-authored, CLI-validated)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from researchforge.domain.evidence import EvidenceClaim
from researchforge.domain.paper import EvidenceStrength

DIRECTION_ID_PATTERN = r"^dir-\d{3}$"


class PaperAnnotation(BaseModel):
    """Deep synthesis of one paper (spec: 8-15 strongest papers)."""

    model_config = ConfigDict(extra="forbid")

    paper_id: str
    evidence_strength: EvidenceStrength
    method_summary: str = Field(min_length=1)
    reported_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    repository_relevance: str | None = None


class ResearchDirection(BaseModel):
    """A group of papers sharing an approach or research direction."""

    model_config = ConfigDict(extra="forbid")

    direction_id: str = Field(pattern=DIRECTION_ID_PATTERN)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    paper_ids: list[str] = Field(min_length=1)
    established_findings: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    underexplored_aspects: list[str] = Field(default_factory=list)


class ResearchLandscape(BaseModel):
    """The full landscape artifact Claude writes and the CLI validates."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    directions: list[ResearchDirection] = Field(min_length=1)
    paper_annotations: list[PaperAnnotation] = Field(default_factory=list)
    evidence: list[EvidenceClaim] = Field(default_factory=list)
