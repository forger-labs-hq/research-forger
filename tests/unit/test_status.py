import json
from pathlib import Path

from typer.testing import CliRunner

from researchforge.cli import app


def test_status_before_init_exits_one(cli_runner: CliRunner, isolated_project_dir: Path) -> None:
    result = cli_runner.invoke(app, ["status"])

    assert result.exit_code == 1
    assert "init" in result.output.lower()


def test_status_after_init_exits_zero(cli_runner: CliRunner, isolated_project_dir: Path) -> None:
    cli_runner.invoke(app, ["init"])

    result = cli_runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert isolated_project_dir.name in result.output
    assert "initialized" in result.output.lower()


def test_status_json_after_init(cli_runner: CliRunner, isolated_project_dir: Path) -> None:
    init_result = cli_runner.invoke(app, ["init", "--json"])
    created = json.loads(init_result.output)

    result = cli_runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["id"] == created["id"]
    assert payload["name"] == created["name"]
    assert payload["status"] == "initialized"
