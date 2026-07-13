"""Ship-branch tests: pure units + real-git/real-venv end to end."""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from researchforge.cli import app
from researchforge.shipping.branch import ShipBlockedError, derive_branch_name


class TestDeriveBranchName:
    def test_slug_from_title(self) -> None:
        name = derive_branch_name("Caching improves F1 cheaply", lambda n: False)
        assert name == "researchforge/caching-improves-f1-cheaply"

    def test_punctuation_and_case(self) -> None:
        name = derive_branch_name("Faster?! (v2) — Routing/Caching", lambda n: False)
        assert name == "researchforge/faster-v2-routing-caching"

    def test_truncation(self) -> None:
        name = derive_branch_name("x" * 100, lambda n: False)
        assert len(name) <= len("researchforge/") + 40

    def test_collision_suffix(self) -> None:
        taken = {"researchforge/cache", "researchforge/cache-2"}
        name = derive_branch_name("cache", lambda n: n in taken)
        assert name == "researchforge/cache-3"

    def test_override_must_be_free(self) -> None:
        with pytest.raises(ShipBlockedError, match="already exists"):
            derive_branch_name("t", lambda n: True, override="feature/x")

    def test_empty_title_falls_back(self) -> None:
        name = derive_branch_name("!!!", lambda n: False)
        assert name == "researchforge/experiment"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


class TestShipBranchEndToEnd:
    def test_ship_creates_clean_branch(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        head_before = _git(validated_project, "rev-parse", "HEAD")
        branch_before = _git(validated_project, "branch", "--show-current")
        status_before = _git(validated_project, "status", "--porcelain")

        result = cli_runner.invoke(app, ["ship", "branch", "--yes", "--json"])

        assert result.exit_code == 0, result.output
        ship = json.loads(result.output)
        assert ship["experiment_id"] == "exp-001"
        assert ship["branch"] == "researchforge/caching-improves-f1-cheaply"
        assert ship["changed_files"] == ["src/algo.py"]
        assert ship["preship_primary_value"] == 0.85

        # Clean single commit on the frozen baseline.
        branch_sha = _git(validated_project, "rev-parse", ship["branch"])
        assert branch_sha == ship["commit_sha"]
        parent = _git(validated_project, "rev-parse", f"{ship['branch']}^")
        assert parent == ship["baseline_commit"]
        diff = _git(
            validated_project, "diff", "--name-only", ship["baseline_commit"], ship["branch"]
        )
        assert diff == "src/algo.py"

        # Failed-experiment history excluded: the losing variant appears nowhere.
        content = _git(validated_project, "show", f"{ship['branch']}:src/algo.py")
        assert "IMPROVEMENT = 5" in content
        assert "IMPROVEMENT = 6" not in content
        log = _git(validated_project, "log", "--oneline", ship["branch"])
        assert len(log.splitlines()) == 2  # baseline init + the one shipped commit

        # Commit message is explanatory, from records.
        message = _git(validated_project, "log", "-1", "--format=%B", ship["branch"])
        assert "Hypothesis:  hyp-001" in message
        assert "Pre-ship:" in message
        assert "no new tests authored" in message

        # User checkout untouched, nothing pushed (no remotes configured at all).
        assert _git(validated_project, "rev-parse", "HEAD") == head_before
        assert _git(validated_project, "branch", "--show-current") == branch_before
        assert _git(validated_project, "status", "--porcelain") == status_before

        # Experiment transitioned; pre-ship manifest recorded as validation-a3.
        shown = json.loads(
            cli_runner.invoke(app, ["experiment", "show", "exp-001", "--json"]).output
        )
        assert shown["status"] == "implementation_ready"
        preship_manifest = (
            validated_project
            / ".researchforge"
            / "artifacts"
            / "experiments"
            / "run-001"
            / "exp-001"
            / "validation-a3"
            / "manifest.json"
        )
        assert preship_manifest.is_file()

        status = json.loads(cli_runner.invoke(app, ["status", "--json"]).output)
        assert "report build" in status["next_action"]

    def test_second_ship_blocked(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        assert cli_runner.invoke(app, ["ship", "branch", "--yes"]).exit_code == 0

        again = cli_runner.invoke(app, ["ship", "branch", "--yes"])

        assert again.exit_code == 1
        assert "already shipped" in again.output

    def test_typed_confirmation_declined(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(app, ["ship", "branch"], input="no\n")

        assert result.exit_code == 1
        branches = _git(validated_project, "branch", "--list", "researchforge/*")
        assert branches == ""

    def test_branch_override(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(
            app, ["ship", "branch", "--yes", "--branch", "researchforge/custom-name"]
        )
        assert result.exit_code == 0, result.output
        assert _git(validated_project, "rev-parse", "--verify", "researchforge/custom-name")

    def test_ship_without_validated_experiment_blocked(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(app, ["ship", "branch", "--yes"])
        assert result.exit_code == 1
        assert "No validated experiment" in result.output

    def test_allow_branch_creation_false_blocks(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        # Flip the shipping flag and re-approve (creates contract v2)...
        contract_file = validated_project / "researchforge.yaml"
        contract_file.write_text(
            contract_file.read_text(encoding="utf-8").replace(
                "allow_branch_creation: true", "allow_branch_creation: false"
            ),
            encoding="utf-8",
        )
        assert cli_runner.invoke(app, ["contract", "approve", "--yes"]).exit_code == 0

        result = cli_runner.invoke(app, ["ship", "branch", "--yes"])

        assert result.exit_code == 1
        # Blocked — either by the shipping flag or by plan staleness vs contract v2;
        # both are refusals before any git mutation.
        branches = _git(validated_project, "branch", "--list", "researchforge/*")
        assert branches == ""
