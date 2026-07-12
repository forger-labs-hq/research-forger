"""The Paper domain entity (spec: required paper schema)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

PAPER_ID_PATTERN = r"^arxiv:\d{4}\.\d{4,5}$"


class EvidenceStrength(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class Paper(BaseModel):
    """An arXiv paper record.

    Retrieval fills the bibliographic fields; landscape import merges the
    synthesis fields (evidence_strength, method_summary, findings,
    limitations, repository_relevance). The hypothesis back-links are
    always computed by the CLI from imported hypotheses — never accepted
    from a synthesis artifact.
    """

    paper_id: str = Field(pattern=PAPER_ID_PATTERN)
    title: str
    authors: list[str]
    published_at: datetime
    updated_at: datetime | None = None
    abstract: str
    source_url: str
    pdf_url: str | None = None
    categories: list[str] = Field(default_factory=list)
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_strength: EvidenceStrength = EvidenceStrength.UNKNOWN
    method_summary: str | None = None
    reported_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    repository_relevance: str | None = None
    supports_hypotheses: list[str] = Field(default_factory=list)
    contradicts_hypotheses: list[str] = Field(default_factory=list)
