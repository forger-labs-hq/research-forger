"""The EvidenceClaim domain entity."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from researchforge.domain.hypothesis import Level

EVIDENCE_ID_PATTERN = r"^ev-\d{3}$"


class EvidenceType(StrEnum):
    """Epistemic category of a claim; powers the report's four-way distinction."""

    PUBLISHED_CLAIM = "published_claim"  # stated in the paper itself
    INTERPRETATION = "interpretation"  # ResearchForge/Claude reading of it
    SPECULATION = "speculation"  # not grounded in the retrieved text


class EvidenceClaim(BaseModel):
    evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    paper_id: str
    claim: str = Field(min_length=1)
    evidence_type: EvidenceType
    extraction_confidence: Level
