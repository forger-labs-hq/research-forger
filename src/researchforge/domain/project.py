"""The Project domain entity.

Phase 0 only models `Project` — the minimum needed for `init`/`status` to have
something to persist. The remaining entities from the phased spec (Paper,
EvidenceClaim, Hypothesis, ExperimentContract, ExperimentRun, Finding,
Deliverable) are introduced in later phases as their features are built.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ProjectMode(StrEnum):
    """Which of ResearchForge's two product modes a project follows."""

    IMPROVE_REPOSITORY = "improve_repository"
    EXPLORE_RESEARCH_IDEA = "explore_research_idea"


class ProjectStatus(StrEnum):
    """Lifecycle status of a project. Additional values arrive in later phases."""

    INITIALIZED = "initialized"
    DEFINED = "defined"  # mode + objective captured
    RESEARCHING = "researching"  # papers retrieved and stored
    SYNTHESIZED = "synthesized"  # landscape + hypotheses imported
    REPORTED = "reported"  # research report generated
    CONTRACTED = "contracted"  # experiment contract approved
    BASELINED = "baselined"  # baseline run succeeded
    VALIDATED = "validated"  # at least one experiment validated


class RepositoryMetadata(BaseModel):
    """Optional pointers to the repository a project is attached to, if any."""

    path: str | None = None
    remote_url: str | None = None
    default_branch: str | None = None


class Project(BaseModel):
    """A single ResearchForge project as persisted under `.researchforge/`."""

    id: str
    name: str
    mode: ProjectMode | None = None
    objective: str | None = None
    repository: RepositoryMetadata = Field(default_factory=RepositoryMetadata)
    status: ProjectStatus = ProjectStatus.INITIALIZED
    created_at: datetime
    updated_at: datetime
