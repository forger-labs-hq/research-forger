"""Persistence for repository scans. The latest scan replaces prior ones."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from researchforge.domain.repo_scan import RepoScan


def save_scan(conn: sqlite3.Connection, project_id: str, scan: RepoScan) -> None:
    with conn:
        conn.execute("DELETE FROM repo_scans WHERE project_id = ?", (project_id,))
        conn.execute(
            """
            INSERT INTO repo_scans (scan_id, project_id, compatibility, record, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                scan.scan_id,
                project_id,
                scan.compatibility.value,
                scan.model_dump_json(),
                datetime.now(UTC).isoformat(),
            ),
        )


def get_latest_scan(conn: sqlite3.Connection) -> RepoScan | None:
    row = conn.execute("SELECT record FROM repo_scans ORDER BY created_at DESC LIMIT 1").fetchone()
    return RepoScan.model_validate_json(row["record"]) if row is not None else None
