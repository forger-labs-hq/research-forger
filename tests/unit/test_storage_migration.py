import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from researchforge.storage.db import SCHEMA_VERSION, ensure_schema, get_connection

_V1_ONLY_DDL = [
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """
    CREATE TABLE projects (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT, objective TEXT,
        repository_metadata TEXT NOT NULL, status TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )
    """,
]

_V2_TABLE_NAMES = {
    "repo_scans",
    "papers",
    "search_runs",
    "landscape",
    "evidence_claims",
    "hypotheses",
}
_V3_TABLE_NAMES = {"contracts", "baseline_runs"}
_V4_TABLE_NAMES = {"experiment_plans", "experiments", "experiment_runs", "experiment_executions"}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {row["name"] for row in rows}


def _build_v1_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    with conn:
        for ddl in _V1_ONLY_DDL:
            conn.execute(ddl)
        conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', '1')")
        now = datetime.now(UTC).isoformat()
        conn.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("abc123", "legacy-project", None, None, "{}", "initialized", now, now),
        )
    conn.close()


def test_v1_db_upgrades_to_current_preserving_data(tmp_path: Path) -> None:
    db_file = tmp_path / "researchforge.db"
    _build_v1_db(db_file)

    conn = get_connection(db_file)
    try:
        ensure_schema(conn)

        assert _table_names(conn) >= _V2_TABLE_NAMES | _V3_TABLE_NAMES | _V4_TABLE_NAMES

        version = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[
            "value"
        ]
        assert version == str(SCHEMA_VERSION)

        row = conn.execute("SELECT * FROM projects").fetchone()
        assert row["id"] == "abc123"
        assert row["name"] == "legacy-project"
    finally:
        conn.close()


def test_fresh_db_gets_current_schema_directly(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "researchforge.db")
    try:
        ensure_schema(conn)

        assert {
            "meta",
            "projects",
        } | _V2_TABLE_NAMES | _V3_TABLE_NAMES | _V4_TABLE_NAMES <= _table_names(conn)
        version = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[
            "value"
        ]
        assert version == str(SCHEMA_VERSION)
    finally:
        conn.close()


def test_ensure_schema_is_idempotent(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "researchforge.db")
    try:
        ensure_schema(conn)
        ensure_schema(conn)  # must not raise
        assert _table_names(conn) >= _V2_TABLE_NAMES | _V3_TABLE_NAMES | _V4_TABLE_NAMES
    finally:
        conn.close()
