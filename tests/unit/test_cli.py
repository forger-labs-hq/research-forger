import re

from typer.testing import CliRunner

from researchforge.cli import app

_ANSI_ESCAPES = re.compile(r"\x1b\[[0-9;]*m")


def _plain(output: str) -> str:
    """Strip ANSI escape codes; rich emits them on CI runners even without a TTY."""
    return _ANSI_ESCAPES.sub("", output)


def test_help_lists_all_commands(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("doctor", "init", "status"):
        assert command in _plain(result.output)


def test_doctor_help_mentions_json(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["doctor", "--help"])

    assert result.exit_code == 0
    assert "--json" in _plain(result.output)


def test_init_help_mentions_json(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["init", "--help"])

    assert result.exit_code == 0
    assert "--json" in _plain(result.output)


def test_status_help_mentions_json(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["status", "--help"])

    assert result.exit_code == 0
    assert "--json" in _plain(result.output)


def test_no_args_shows_help(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, [])

    output = _plain(result.output)
    assert "doctor" in output
    assert "init" in output
    assert "status" in output
