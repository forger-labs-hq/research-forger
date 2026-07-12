"""Persistence for hypotheses."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from researchforge.domain.hypothesis import Hypothesis


def replace_hypotheses(
    conn: sqlite3.Connection, project_id: str, hypotheses: list[Hypothesis]
) -> None:
    now = datetime.now(UTC).isoformat()
    with conn:
        conn.execute("DELETE FROM hypotheses WHERE project_id = ?", (project_id,))
        for hypothesis in hypotheses:
            conn.execute(
                """
                INSERT INTO hypotheses
                    (hypothesis_id, project_id, title, status, record, imported_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hypothesis.hypothesis_id,
                    project_id,
                    hypothesis.title,
                    hypothesis.status.value,
                    hypothesis.model_dump_json(),
                    now,
                    now,
                ),
            )


def list_hypotheses(conn: sqlite3.Connection) -> list[Hypothesis]:
    rows = conn.execute("SELECT record FROM hypotheses ORDER BY hypothesis_id").fetchall()
    return [Hypothesis.model_validate_json(row["record"]) for row in rows]


def get_hypothesis(conn: sqlite3.Connection, hypothesis_id: str) -> Hypothesis | None:
    row = conn.execute(
        "SELECT record FROM hypotheses WHERE hypothesis_id = ?", (hypothesis_id,)
    ).fetchone()
    return Hypothesis.model_validate_json(row["record"]) if row is not None else None
