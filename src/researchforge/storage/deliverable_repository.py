"""Persistence for deliverables."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from researchforge.domain.deliverable import Deliverable, DeliverableKind


def insert_deliverable(conn: sqlite3.Connection, project_id: str, deliverable: Deliverable) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO deliverables
                (deliverable_id, project_id, kind, experiment_id, location, record, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deliverable.deliverable_id,
                project_id,
                deliverable.kind.value,
                deliverable.experiment_id,
                deliverable.location,
                deliverable.model_dump_json(),
                datetime.now(UTC).isoformat(),
            ),
        )


def record_deliverable_once(
    conn: sqlite3.Connection, project_id: str, deliverable: Deliverable
) -> None:
    """Insert unless a deliverable of the same kind and location already exists.

    Rebuildable outputs (reports, packages) overwrite the same path; recording
    every rebuild would accumulate duplicate rows.
    """
    row = conn.execute(
        "SELECT 1 FROM deliverables WHERE project_id = ? AND kind = ? AND location = ?",
        (project_id, deliverable.kind.value, deliverable.location),
    ).fetchone()
    if row is None:
        insert_deliverable(conn, project_id, deliverable)


def list_deliverables(
    conn: sqlite3.Connection,
    kind: DeliverableKind | None = None,
    experiment_id: str | None = None,
) -> list[Deliverable]:
    query = "SELECT record FROM deliverables"
    clauses = []
    params: list[str] = []
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind.value)
    if experiment_id is not None:
        clauses.append("experiment_id = ?")
        params.append(experiment_id)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at"
    rows = conn.execute(query, params).fetchall()
    return [Deliverable.model_validate_json(row["record"]) for row in rows]


def get_branch_deliverable(
    conn: sqlite3.Connection, experiment_id: str | None = None
) -> Deliverable | None:
    branches = list_deliverables(conn, kind=DeliverableKind.BRANCH, experiment_id=experiment_id)
    return branches[-1] if branches else None
