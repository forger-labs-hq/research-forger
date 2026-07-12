import json
from pathlib import Path

from typer.testing import CliRunner

from researchforge.cli import app


def _prepare_contract(cli_runner: CliRunner, repo: Path) -> Path:
    """Generate a draft and make it valid (set a real full_command)."""
    result = cli_runner.invoke(app, ["contract", "generate"])
    assert result.exit_code == 0, result.output
    contract_file = repo / "researchforge.yaml"
    text = contract_file.read_text(encoding="utf-8")
    text = text.replace(
        'full_command: "# TODO: command that writes the result file"',
        'full_command: "python benchmarks/evaluate.py"',
    )
    contract_file.write_text(text, encoding="utf-8")
    return contract_file


class TestGenerate:
    def test_generate_writes_draft_at_repo_root(
        self, cli_runner: CliRunner, improve_project: Path
    ) -> None:
        result = cli_runner.invoke(app, ["contract", "generate"])

        assert result.exit_code == 0, result.output
        assert (improve_project / "researchforge.yaml").is_file()

    def test_generate_refuses_overwrite_without_force(
        self, cli_runner: CliRunner, improve_project: Path
    ) -> None:
        cli_runner.invoke(app, ["contract", "generate"])
        blocked = cli_runner.invoke(app, ["contract", "generate"])
        assert blocked.exit_code == 1
        forced = cli_runner.invoke(app, ["contract", "generate", "--force"])
        assert forced.exit_code == 0

    def test_generate_requires_scan(self, cli_runner: CliRunner, initialized_project: Path) -> None:
        result = cli_runner.invoke(app, ["contract", "generate"])
        assert result.exit_code == 1
        assert "repo scan" in result.output


class TestValidate:
    def test_draft_with_placeholder_fails_validation(
        self, cli_runner: CliRunner, improve_project: Path
    ) -> None:
        cli_runner.invoke(app, ["contract", "generate"])
        result = cli_runner.invoke(app, ["contract", "validate"])
        assert result.exit_code == 1
        assert "full_command" in result.output

    def test_valid_contract_passes(self, cli_runner: CliRunner, improve_project: Path) -> None:
        _prepare_contract(cli_runner, improve_project)
        result = cli_runner.invoke(app, ["contract", "validate", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["status"] == "ok"


class TestApprove:
    def test_typed_approval_creates_version_one(
        self, cli_runner: CliRunner, improve_project: Path
    ) -> None:
        _prepare_contract(cli_runner, improve_project)

        result = cli_runner.invoke(app, ["contract", "approve"], input="approve\n")

        assert result.exit_code == 0, result.output
        assert "version 1" in result.output

        status = json.loads(cli_runner.invoke(app, ["status", "--json"]).output)
        assert status["status"] == "contracted"
        assert status["contract_version"] == 1

    def test_wrong_confirmation_aborts(self, cli_runner: CliRunner, improve_project: Path) -> None:
        _prepare_contract(cli_runner, improve_project)
        result = cli_runner.invoke(app, ["contract", "approve"], input="nope\n")
        assert result.exit_code == 1

        show = cli_runner.invoke(app, ["contract", "show"])
        assert show.exit_code == 1  # nothing approved

    def test_reapprove_unchanged_is_noop(
        self, cli_runner: CliRunner, improve_project: Path
    ) -> None:
        _prepare_contract(cli_runner, improve_project)
        cli_runner.invoke(app, ["contract", "approve", "--yes"])

        again = cli_runner.invoke(app, ["contract", "approve", "--yes", "--json"])
        payload = json.loads(again.output)
        assert payload["created"] is False
        assert payload["contract_version"] == 1

    def test_edited_file_approves_as_version_two(
        self, cli_runner: CliRunner, improve_project: Path
    ) -> None:
        contract_file = _prepare_contract(cli_runner, improve_project)
        cli_runner.invoke(app, ["contract", "approve", "--yes"])

        text = contract_file.read_text(encoding="utf-8")
        contract_file.write_text(
            text.replace("timeout_minutes: 20", "timeout_minutes: 30"), encoding="utf-8"
        )

        # Drift shows up in show + status before re-approval.
        show = cli_runner.invoke(app, ["contract", "show"])
        assert "changed since approval" in show.output

        result = cli_runner.invoke(app, ["contract", "approve", "--yes", "--json"])
        payload = json.loads(result.output)
        assert payload["created"] is True
        assert payload["contract_version"] == 2

    def test_invalid_contract_cannot_be_approved(
        self, cli_runner: CliRunner, improve_project: Path
    ) -> None:
        cli_runner.invoke(app, ["contract", "generate"])  # placeholder full_command
        result = cli_runner.invoke(app, ["contract", "approve", "--yes"])
        assert result.exit_code == 1

    def test_approved_contract_records_commit_sha(
        self, cli_runner: CliRunner, improve_project: Path
    ) -> None:
        _prepare_contract(cli_runner, improve_project)
        cli_runner.invoke(app, ["contract", "approve", "--yes"])

        show = json.loads(cli_runner.invoke(app, ["contract", "show", "--json"]).output)
        assert len(show["baseline_commit"]) == 40
        assert show["spec"]["repository"]["baseline_ref"] == "main"
