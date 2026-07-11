import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from researchforge.domain.project import Project, ProjectMode, RepositoryMetadata
from researchforge.storage.db import SCHEMA_VERSION, get_connection, initialize_schema
from researchforge.storage.project_repository import get_project, insert_project, update_project


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = get_connection(tmp_path / "researchforge.db")
    try:
        yield connection
    finally:
        connection.close()


def _make_project(**overrides: object) -> Project:
    now = datetime.now(UTC)
    defaults: dict[str, object] = {
        "id": "abc123",
        "name": "my-project",
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return Project(**defaults)  # type: ignore[arg-type]


def test_initialize_schema_creates_tables_idempotently(conn: sqlite3.Connection) -> None:
    initialize_schema(conn)
    initialize_schema(conn)  # idempotent — must not raise

    tables = {
        row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"meta", "projects"} <= tables

    version = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[
        "value"
    ]
    assert version == str(SCHEMA_VERSION)


def test_get_project_on_empty_db_returns_none(conn: sqlite3.Connection) -> None:
    initialize_schema(conn)

    assert get_project(conn) is None


def test_insert_and_get_project_round_trip(conn: sqlite3.Connection) -> None:
    initialize_schema(conn)

    project = _make_project(
        mode=ProjectMode.IMPROVE_REPOSITORY,
        objective="Reduce cost.",
        repository=RepositoryMetadata(path="/tmp/repo", remote_url="git@example.com:x/y.git"),
    )
    insert_project(conn, project)

    fetched = get_project(conn)
    assert fetched == project


def test_update_project_persists_changes(conn: sqlite3.Connection) -> None:
    initialize_schema(conn)

    project = _make_project()
    insert_project(conn, project)

    updated = project.model_copy(update={"objective": "New objective"})
    update_project(conn, updated)

    fetched = get_project(conn)
    assert fetched is not None
    assert fetched.objective == "New objective"


def test_get_connection_creates_parent_directories(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "researchforge.db"
    connection = get_connection(nested)
    try:
        assert isinstance(connection, sqlite3.Connection)
        assert nested.parent.is_dir()
    finally:
        connection.close()
