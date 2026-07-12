"""Project lifecycle operations."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from researchforge.domain.project import (
    Project,
    ProjectMode,
    ProjectStatus,
)
from researchforge.storage.project_repository import get_project, insert_project, update_project


class ProjectExistsError(Exception):
    """A defined project already exists; pass force to overwrite mode/objective."""

    def __init__(self, project: Project) -> None:
        self.project = project
        super().__init__(f"Project '{project.name}' is already defined.")


def ensure_project(conn: sqlite3.Connection, name: str) -> Project:
    """Return the stored project, creating a bare initialized one if absent."""
    project = get_project(conn)
    if project is not None:
        return project
    now = datetime.now(UTC)
    project = Project(
        id=uuid4().hex,
        name=name,
        status=ProjectStatus.INITIALIZED,
        created_at=now,
        updated_at=now,
    )
    insert_project(conn, project)
    return project


def define_project(
    conn: sqlite3.Connection,
    *,
    mode: ProjectMode,
    objective: str,
    name: str | None = None,
    repo_path: Path | None = None,
    force_update: bool = False,
) -> Project:
    """Set mode and objective on the single project, creating it if needed.

    Raises ProjectExistsError when the project is already defined and
    `force_update` is not set — callers surface this as the resume path.
    """
    default_name = name or Path.cwd().name
    project = ensure_project(conn, default_name)

    already_defined = project.mode is not None and project.objective is not None
    if already_defined and not force_update:
        raise ProjectExistsError(project)

    repository = project.repository
    if repo_path is not None:
        repository = repository.model_copy(update={"path": str(repo_path.resolve())})

    updated = project.model_copy(
        update={
            "name": name or project.name,
            "mode": mode,
            "objective": objective,
            "repository": repository,
            "status": ProjectStatus.DEFINED,
            "updated_at": datetime.now(UTC),
        }
    )
    update_project(conn, updated)
    return updated


def touch_project_status(conn: sqlite3.Connection, status: ProjectStatus) -> Project:
    """Advance the project's status (idempotent for repeat operations)."""
    project = get_project(conn)
    if project is None:
        raise ValueError("No project found; run `researchforge project create` first.")
    updated = project.model_copy(update={"status": status, "updated_at": datetime.now(UTC)})
    update_project(conn, updated)
    return updated
