"""Deliverable entity (spec §12): what ResearchForge produced for the user."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DeliverableKind(StrEnum):
    BRANCH = "branch"
    DRAFT_PR = "draft_pr"
    ENGINEERING_REPORT = "engineering_report"
    RESEARCH_PACKAGE = "research_package"
    DASHBOARD = "dashboard"


class Deliverable(BaseModel):
    deliverable_id: str
    kind: DeliverableKind
    experiment_id: str | None = None
    location: str  # branch name, PR URL, or filesystem path
    commit_sha: str | None = None
    details: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
