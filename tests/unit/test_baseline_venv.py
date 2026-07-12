"""CI-friendly end-to-end venv baseline: real worktree, real venv, real run."""

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from researchforge.cli import app


class TestVenvBaseline:
    def test_baseline_succeeds_end_to_end(
        self, cli_runner: CliRunner, contracted_project: Path
    ) -> None:
        original_status = subprocess.run(
            ["git", "-C", str(contracted_project), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        result = cli_runner.invoke(app, ["baseline", "run", "--json"])

        assert result.exit_code == 0, result.output
        run = json.loads(result.output)
        assert run["status"] == "succeeded"
        assert run["execution_mode"] == "venv"
        assert run["metrics"]["primary_metric"]["name"] == "f1"
        assert run["metrics"]["primary_metric"]["value"] == 0.84
        assert len(run["commit_sha"]) == 40

        # Fingerprint recorded.
        fingerprint = run["fingerprint"]
        assert fingerprint["python_version"] is not None
        assert fingerprint["venv_packages_hash"] is not None
        assert fingerprint["contract_version"] == 1
        assert fingerprint["commit_sha"] == run["commit_sha"]

        # Baseline ran in a separate worktree; the venv was cleaned up after.
        worktree = contracted_project / ".researchforge" / "worktrees" / "baseline"
        assert worktree.is_dir()
        assert not (worktree / ".venv").exists()

        # Artifacts persisted.
        artifacts = Path(run["stdout_path"]).parent
        assert (artifacts / "results.json").is_file()
        assert (artifacts / "fingerprint.json").is_file()
        assert (artifacts / "baseline_run.json").is_file()
        assert "evaluation complete" in Path(run["stdout_path"]).read_text(encoding="utf-8")

        # User tree untouched.
        current_status = subprocess.run(
            ["git", "-C", str(contracted_project), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert current_status == original_status

    def test_status_reaches_baselined_and_show_works(
        self, cli_runner: CliRunner, contracted_project: Path
    ) -> None:
        assert cli_runner.invoke(app, ["baseline", "run"]).exit_code == 0

        status = json.loads(cli_runner.invoke(app, ["status", "--json"]).output)
        assert status["status"] == "baselined"
        assert "experiment plan" in status["next_action"]

        shown = json.loads(cli_runner.invoke(app, ["baseline", "show", "--json"]).output)
        assert shown["status"] == "succeeded"

    def test_venv_warning_displayed(self, cli_runner: CliRunner, contracted_project: Path) -> None:
        result = cli_runner.invoke(app, ["baseline", "run"])
        assert "does not securely isolate" in result.output

    def test_check_only_resolves_without_running(
        self, cli_runner: CliRunner, contracted_project: Path
    ) -> None:
        result = cli_runner.invoke(app, ["baseline", "run", "--check", "--json"])

        assert result.exit_code == 0, result.output
        resolution = json.loads(result.output)
        assert resolution["status"] == "ready"
        assert resolution["execution_mode"] == "venv"
        # Nothing ran.
        assert not (contracted_project / ".researchforge" / "artifacts").exists()

    def test_failing_evaluation_blocks_and_persists(
        self, cli_runner: CliRunner, contracted_project: Path
    ) -> None:
        evaluate = contracted_project / "benchmarks" / "evaluate.py"
        failing = Path(__file__).parent.parent / "fixtures" / "eval_scripts" / "failing.py"
        evaluate.write_text(failing.read_text(encoding="utf-8"), encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(contracted_project), "commit", "-aqm", "break eval"], check=True
        )

        result = cli_runner.invoke(app, ["baseline", "run", "--json"])

        assert result.exit_code == 1
        run = json.loads(result.output)
        assert run["status"] == "failed_execution"
        assert "exited 3" in run["failure_reason"]
        # ref moved since approval → recorded as warning, actual sha wins.
        assert any("moved since approval" in w for w in run["warnings"])

        status = json.loads(cli_runner.invoke(app, ["status", "--json"]).output)
        assert "Baseline failed" in status["next_action"]

    def test_wrong_metric_name_is_invalid_result(
        self, cli_runner: CliRunner, contracted_project: Path
    ) -> None:
        evaluate = contracted_project / "benchmarks" / "evaluate.py"
        wrong = Path(__file__).parent.parent / "fixtures" / "eval_scripts" / "wrong_metric.py"
        evaluate.write_text(wrong.read_text(encoding="utf-8"), encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(contracted_project), "commit", "-aqm", "wrong metric"], check=True
        )

        result = cli_runner.invoke(app, ["baseline", "run", "--json"])

        assert result.exit_code == 1
        run = json.loads(result.output)
        assert run["status"] == "failed_invalid_result"
        assert "expects 'f1'" in run["failure_reason"]

    def test_drifted_contract_blocks_baseline(
        self, cli_runner: CliRunner, contracted_project: Path
    ) -> None:
        contract_file = contracted_project / "researchforge.yaml"
        contract_file.write_text(
            contract_file.read_text(encoding="utf-8").replace(
                "timeout_minutes: 5", "timeout_minutes: 9"
            ),
            encoding="utf-8",
        )

        result = cli_runner.invoke(app, ["baseline", "run"])

        assert result.exit_code == 1
        assert "changed since approval" in result.output
