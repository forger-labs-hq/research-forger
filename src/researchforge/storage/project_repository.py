"""CRUD for `Project`, centralizing row <-> model conversion.

Phase 0 assumes exactly one project per `.researchforge/` directory, so
`get_project` returns the single stored row (or `None` if none exists yet).
"""

from __future__ import annotations

import sqlite3

from researchforge.domain.project import Project, ProjectMode, ProjectStatus, RepositoryMetadata


def _row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        mode=ProjectMode(row["mode"]) if row["mode"] is not None else None,
        objective=row["objective"],
        repository=RepositoryMetadata.model_validate_json(row["repository_metadata"]),
        status=ProjectStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def insert_project(conn: sqlite3.Connection, project: Project) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO projects
                (id, name, mode, objective, repository_metadata, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project.id,
                project.name,
                project.mode.value if project.mode is not None else None,
                project.objective,
                project.repository.model_dump_json(),
                project.status.value,
                project.created_at.isoformat(),
                project.updated_at.isoformat(),
            ),
        )


def get_project(conn: sqlite3.Connection) -> Project | None:
    row = conn.execute("SELECT * FROM projects LIMIT 1").fetchone()
    return _row_to_project(row) if row is not None else None


def update_project(conn: sqlite3.Connection, project: Project) -> None:
    with conn:
        conn.execute(
            """
            UPDATE projects
            SET name = ?, mode = ?, objective = ?, repository_metadata = ?,
                status = ?, created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                project.name,
                project.mode.value if project.mode is not None else None,
                project.objective,
                project.repository.model_dump_json(),
                project.status.value,
                project.created_at.isoformat(),
                project.updated_at.isoformat(),
                project.id,
            ),
        )
