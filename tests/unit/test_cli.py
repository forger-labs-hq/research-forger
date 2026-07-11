from typer.testing import CliRunner

from researchforge.cli import app


def test_help_lists_all_commands(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("doctor", "init", "status"):
        assert command in result.output


def test_doctor_help_mentions_json(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["doctor", "--help"])

    assert result.exit_code == 0
    assert "--json" in result.output


def test_init_help_mentions_json(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["init", "--help"])

    assert result.exit_code == 0
    assert "--json" in result.output


def test_status_help_mentions_json(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["status", "--help"])

    assert result.exit_code == 0
    assert "--json" in result.output


def test_no_args_shows_help(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, [])

    assert "doctor" in result.output
    assert "init" in result.output
    assert "status" in result.output
