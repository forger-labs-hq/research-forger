from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from researchforge.domain.project import (
    Project,
    ProjectMode,
    ProjectStatus,
    RepositoryMetadata,
)


def _now() -> datetime:
    return datetime.now(UTC)


def test_project_requires_id_name_and_timestamps() -> None:
    with pytest.raises(ValidationError):
        Project()  # type: ignore[call-arg]


def test_project_defaults() -> None:
    now = _now()
    project = Project(id="abc123", name="my-project", created_at=now, updated_at=now)

    assert project.mode is None
    assert project.objective is None
    assert project.status == ProjectStatus.INITIALIZED
    assert project.repository == RepositoryMetadata()


def test_repository_metadata_all_optional() -> None:
    metadata = RepositoryMetadata()

    assert metadata.path is None
    assert metadata.remote_url is None
    assert metadata.default_branch is None


def test_project_json_round_trip() -> None:
    now = _now()
    project = Project(
        id="abc123",
        name="my-project",
        mode=ProjectMode.IMPROVE_REPOSITORY,
        objective="Reduce latency without lowering recall.",
        repository=RepositoryMetadata(path="/tmp/repo", default_branch="main"),
        created_at=now,
        updated_at=now,
    )

    dumped = project.model_dump()
    restored = Project(**dumped)

    assert restored == project


def test_project_mode_enum_values() -> None:
    assert ProjectMode.IMPROVE_REPOSITORY.value == "improve_repository"
    assert ProjectMode.EXPLORE_RESEARCH_IDEA.value == "explore_research_idea"
