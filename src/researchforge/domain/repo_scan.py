"""Repository scan result models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class CompatibilityStatus(StrEnum):
    READY = "ready"
    SETUP_REQUIRED = "setup_required"
    RESEARCH_ONLY = "research_only"
    UNSUPPORTED = "unsupported"


class GitInfo(BaseModel):
    is_repo: bool = False
    commit: str | None = None
    branch: str | None = None
    remote_url: str | None = None


class ReadmeInfo(BaseModel):
    path: str | None = None
    title: str | None = None
    excerpt: str | None = None


class PythonInfo(BaseModel):
    has_pyproject: bool = False
    has_setup_py: bool = False
    requirements_files: list[str] = Field(default_factory=list)
    package_name: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    python_requires: str | None = None

    @property
    def is_python_project(self) -> bool:
        return self.has_pyproject or self.has_setup_py or bool(self.requirements_files)


class RepoScan(BaseModel):
    scan_id: str
    repo_path: str
    git: GitInfo = Field(default_factory=GitInfo)
    readme: ReadmeInfo = Field(default_factory=ReadmeInfo)
    python: PythonInfo = Field(default_factory=PythonInfo)
    has_dockerfile: bool = False
    test_candidates: list[str] = Field(default_factory=list)
    benchmark_candidates: list[str] = Field(default_factory=list)
    suggested_editable_paths: list[str] = Field(default_factory=list)
    suggested_protected_paths: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    compatibility: CompatibilityStatus
    compatibility_reasons: list[str] = Field(default_factory=list)
    scanned_at: datetime
