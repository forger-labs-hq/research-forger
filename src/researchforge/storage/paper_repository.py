"""Persistence for papers and search runs."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

from researchforge.domain.paper import Paper


def upsert_paper(conn: sqlite3.Connection, project_id: str, paper: Paper) -> None:
    now = datetime.now(UTC).isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO papers
                (paper_id, project_id, title, published_at, relevance_score,
                 record, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id) DO UPDATE SET
                title = excluded.title,
                relevance_score = excluded.relevance_score,
                record = excluded.record,
                updated_at = excluded.updated_at
            """,
            (
                paper.paper_id,
                project_id,
                paper.title,
                paper.published_at.isoformat(),
                paper.relevance_score,
                paper.model_dump_json(),
                now,
                now,
            ),
        )


def get_paper(conn: sqlite3.Connection, paper_id: str) -> Paper | None:
    row = conn.execute("SELECT record FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
    return Paper.model_validate_json(row["record"]) if row is not None else None


def list_papers(conn: sqlite3.Connection, limit: int | None = None) -> list[Paper]:
    sql = "SELECT record FROM papers ORDER BY relevance_score DESC, paper_id"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return [Paper.model_validate_json(row["record"]) for row in conn.execute(sql)]


def paper_ids(conn: sqlite3.Connection) -> set[str]:
    return {row["paper_id"] for row in conn.execute("SELECT paper_id FROM papers")}


def delete_all_papers(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("DELETE FROM papers")


def cited_paper_ids(conn: sqlite3.Connection) -> set[str]:
    """Paper ids referenced by any stored hypothesis."""
    cited: set[str] = set()
    for row in conn.execute("SELECT record FROM hypotheses"):
        record = json.loads(row["record"])
        cited.update(record.get("supporting_paper_ids", []))
        cited.update(record.get("contradicting_paper_ids", []))
    return cited


def record_search_run(
    conn: sqlite3.Connection,
    project_id: str,
    *,
    queries: list[str],
    fetched_count: int,
    deduped_count: int,
    selected_count: int,
) -> str:
    run_id = uuid4().hex
    with conn:
        conn.execute(
            """
            INSERT INTO search_runs
                (run_id, project_id, queries, fetched_count, deduped_count,
                 selected_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                project_id,
                json.dumps(queries),
                fetched_count,
                deduped_count,
                selected_count,
                datetime.now(UTC).isoformat(),
            ),
        )
    return run_id


def list_search_runs(conn: sqlite3.Connection) -> list[dict[str, object]]:
    rows = conn.execute("SELECT * FROM search_runs ORDER BY created_at").fetchall()
    return [
        {
            "run_id": row["run_id"],
            "queries": json.loads(row["queries"]),
            "fetched_count": row["fetched_count"],
            "deduped_count": row["deduped_count"],
            "selected_count": row["selected_count"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
