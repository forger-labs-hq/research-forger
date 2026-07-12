"""Execution-environment resolution models (spec: compatibility status shape)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from researchforge.domain.repo_scan import CompatibilityStatus


class ExecutionEngine(StrEnum):
    DOCKER = "docker"
    VENV = "venv"
    NONE = "none"


class EnvironmentResolution(BaseModel):
    """Exactly the spec's compatibility yaml shape."""

    status: CompatibilityStatus
    execution_mode: ExecutionEngine
    reasons: list[str] = Field(default_factory=list)
    required_user_actions: list[str] = Field(default_factory=list)


class DockerProbe(BaseModel):
    cli_present: bool
    daemon_running: bool
    version: str | None = None
    error: str | None = None
