"""Baseline run models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from researchforge.domain.environment import ExecutionEngine
from researchforge.execution.metrics import MetricResult


class BaselineStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED_SETUP = "failed_setup"
    FAILED_EXECUTION = "failed_execution"
    FAILED_TIMEOUT = "failed_timeout"
    FAILED_INVALID_RESULT = "failed_invalid_result"


class EnvironmentFingerprint(BaseModel):
    platform: str
    execution_mode: ExecutionEngine
    python_version: str | None = None
    docker_image_id: str | None = None
    venv_packages_hash: str | None = None  # sha256 of `pip freeze`
    contract_id: str
    contract_version: int
    commit_sha: str


class BaselineRun(BaseModel):
    baseline_id: str
    contract_id: str
    contract_version: int
    commit_sha: str
    execution_mode: ExecutionEngine
    command: str
    command_kind: str = "full"  # which contract command ran (1C adds "screening")
    status: BaselineStatus
    failure_reason: str | None = None
    metrics: MetricResult | None = None
    warnings: list[str] = Field(default_factory=list)
    fingerprint: EnvironmentFingerprint
    stdout_path: str
    stderr_path: str
    results_path: str | None = None
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
