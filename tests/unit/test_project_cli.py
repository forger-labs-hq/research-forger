import json
from pathlib import Path

from typer.testing import CliRunner

from researchforge.cli import app


def test_create_defines_project(cli_runner: CliRunner, isolated_project_dir: Path) -> None:
    result = cli_runner.invoke(
        app,
        [
            "project",
            "create",
            "--mode",
            "explore_research_idea",
            "--objective",
            "Investigate adaptive routing.",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["mode"] == "explore_research_idea"
    assert payload["objective"] == "Investigate adaptive routing."
    assert payload["status"] == "defined"


def test_create_implicitly_initializes(cli_runner: CliRunner, isolated_project_dir: Path) -> None:
    assert not (isolated_project_dir / ".researchforge").exists()

    result = cli_runner.invoke(
        app,
        ["project", "create", "--mode", "improve_repository", "--objective", "Improve F1."],
    )

    assert result.exit_code == 0
    assert (isolated_project_dir / ".researchforge" / "researchforge.db").is_file()


def test_create_resumes_when_already_defined(
    cli_runner: CliRunner, initialized_project: Path
) -> None:
    result = cli_runner.invoke(
        app,
        ["project", "create", "--mode", "improve_repository", "--objective", "Different."],
    )

    assert result.exit_code == 0
    assert "resuming" in result.output.lower()
    # Original definition retained
    show = cli_runner.invoke(app, ["project", "show", "--json"])
    payload = json.loads(show.output)
    assert payload["mode"] == "explore_research_idea"


def test_create_force_update_redefines(cli_runner: CliRunner, initialized_project: Path) -> None:
    result = cli_runner.invoke(
        app,
        [
            "project",
            "create",
            "--mode",
            "improve_repository",
            "--objective",
            "New objective.",
            "--force-update",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["mode"] == "improve_repository"
    assert payload["objective"] == "New objective."


def test_create_prompts_for_missing_fields(
    cli_runner: CliRunner, isolated_project_dir: Path
) -> None:
    result = cli_runner.invoke(
        app,
        ["project", "create"],
        input="explore_research_idea\nStudy routing.\n",
    )

    assert result.exit_code == 0


def test_create_rejects_invalid_prompted_mode(
    cli_runner: CliRunner, isolated_project_dir: Path
) -> None:
    result = cli_runner.invoke(app, ["project", "create"], input="bogus_mode\n")

    assert result.exit_code == 1
    assert "invalid mode" in result.output.lower()


def test_create_rejects_empty_objective(cli_runner: CliRunner, isolated_project_dir: Path) -> None:
    result = cli_runner.invoke(
        app,
        ["project", "create", "--mode", "explore_research_idea", "--objective", "   "],
    )

    assert result.exit_code == 1


def test_show_without_project(cli_runner: CliRunner, isolated_project_dir: Path) -> None:
    result = cli_runner.invoke(app, ["project", "show"])

    assert result.exit_code == 1


def test_status_next_action_progression(cli_runner: CliRunner, initialized_project: Path) -> None:
    result = cli_runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["counts"] == {"papers": 0, "hypotheses": 0, "landscape": 0}
    assert "research search" in payload["next_action"]
