import json
from contextlib import closing
from pathlib import Path

from typer.testing import CliRunner

from researchforge.cli import app
from researchforge.config.paths import researchforge_dir
from researchforge.storage.db import get_connection


def test_init_creates_db_with_one_project_row(
    cli_runner: CliRunner, isolated_project_dir: Path
) -> None:
    result = cli_runner.invoke(app, ["init"])

    assert result.exit_code == 0

    db_file = researchforge_dir(isolated_project_dir) / "researchforge.db"
    assert db_file.is_file()

    with closing(get_connection(db_file)) as conn:
        rows = conn.execute("SELECT * FROM projects").fetchall()
    assert len(rows) == 1
    assert rows[0]["name"] == isolated_project_dir.name
    assert rows[0]["status"] == "initialized"


def test_init_is_idempotent(cli_runner: CliRunner, isolated_project_dir: Path) -> None:
    first = cli_runner.invoke(app, ["init"])
    second = cli_runner.invoke(app, ["init"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "already" in second.output.lower()

    db_file = researchforge_dir(isolated_project_dir) / "researchforge.db"
    with closing(get_connection(db_file)) as conn:
        rows = conn.execute("SELECT * FROM projects").fetchall()
    assert len(rows) == 1


def test_init_does_not_create_later_phase_subdirectories(
    cli_runner: CliRunner, isolated_project_dir: Path
) -> None:
    cli_runner.invoke(app, ["init"])

    root = researchforge_dir(isolated_project_dir)
    for name in ("worktrees", "artifacts", "papers", "reports"):
        assert not (root / name).exists()


def test_init_json_output(cli_runner: CliRunner, isolated_project_dir: Path) -> None:
    result = cli_runner.invoke(app, ["init", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["name"] == isolated_project_dir.name
    assert payload["status"] == "initialized"
