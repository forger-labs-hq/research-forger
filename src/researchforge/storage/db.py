"""SQLite connection and schema management for local project state.

Schema history:
- v1 (Phase 0): ``meta``, ``projects``.
- v2 (Phase 1A): ``repo_scans``, ``papers``, ``search_runs``, ``landscape``,
  ``evidence_claims``, ``hypotheses``.
- v3 (Phase 1B): ``contracts``, ``baseline_runs``.
- v4 (Phase 1C): ``experiment_plans``, ``experiments``, ``experiment_runs``,
  ``experiment_executions``.

All migrations are additive ``CREATE TABLE IF NOT EXISTS`` statements, so
``ensure_schema`` can run on every connection open and silently upgrade
older databases.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from researchforge.config.paths import db_path

SCHEMA_VERSION = 4

_V1_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        mode TEXT,
        objective TEXT,
        repository_metadata TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
]

_V2_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS repo_scans (
        scan_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        compatibility TEXT NOT NULL,
        record TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS papers (
        paper_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        title TEXT NOT NULL,
        published_at TEXT NOT NULL,
        relevance_score REAL NOT NULL,
        record TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS search_runs (
        run_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        queries TEXT NOT NULL,
        fetched_count INTEGER NOT NULL,
        deduped_count INTEGER NOT NULL,
        selected_count INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS landscape (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        record TEXT NOT NULL,
        source_file TEXT,
        imported_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence_claims (
        evidence_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        paper_id TEXT NOT NULL,
        evidence_type TEXT NOT NULL,
        record TEXT NOT NULL,
        imported_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS hypotheses (
        hypothesis_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        title TEXT NOT NULL,
        status TEXT NOT NULL,
        record TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
]

_V3_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS contracts (
        contract_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        contract_version INTEGER NOT NULL,
        source_sha256 TEXT NOT NULL,
        baseline_commit TEXT NOT NULL,
        approved_at TEXT NOT NULL,
        record TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (project_id, contract_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS baseline_runs (
        baseline_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        contract_id TEXT NOT NULL,
        contract_version INTEGER NOT NULL,
        commit_sha TEXT NOT NULL,
        execution_mode TEXT NOT NULL,
        status TEXT NOT NULL,
        record TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
]

_V4_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS experiment_plans (
        plan_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        hypothesis_id TEXT NOT NULL,
        contract_id TEXT NOT NULL,
        contract_version INTEGER NOT NULL,
        baseline_id TEXT NOT NULL,
        status TEXT NOT NULL,
        record TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS experiments (
        experiment_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        plan_id TEXT NOT NULL,
        hypothesis_id TEXT NOT NULL,
        status TEXT NOT NULL,
        record TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_runs (
        run_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        plan_id TEXT NOT NULL,
        status TEXT NOT NULL,
        record TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_executions (
        execution_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        experiment_id TEXT NOT NULL,
        benchmark_stage TEXT NOT NULL,
        attempt INTEGER NOT NULL,
        status TEXT NOT NULL,
        record TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (experiment_id, benchmark_stage, attempt)
    )
    """,
]

_MIGRATIONS: dict[int, list[str]] = {
    1: _V1_TABLES,
    2: _V2_TABLES,
    3: _V3_TABLES,
    4: _V4_TABLES,
}


def get_connection(path: Path) -> sqlite3.Connection:
    """Open a sqlite connection at `path`, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create any missing tables and record the current schema version."""
    with conn:
        for version in sorted(_MIGRATIONS):
            if version <= SCHEMA_VERSION:
                for ddl in _MIGRATIONS[version]:
                    conn.execute(ddl)
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )


def initialize_schema(conn: sqlite3.Connection) -> None:
    """Backward-compatible alias for `ensure_schema`."""
    ensure_schema(conn)


def open_project_db(base: Path | None = None) -> sqlite3.Connection:
    """Open (and, if needed, upgrade) the project database under `base`."""
    conn = get_connection(db_path(base))
    ensure_schema(conn)
    return conn
