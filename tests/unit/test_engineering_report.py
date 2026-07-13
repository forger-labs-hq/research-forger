"""Engineering report + research package tests on the validated fixture."""

import csv
import json
from pathlib import Path

from typer.testing import CliRunner

from researchforge.cli import app

SECTION_HEADERS = [
    "## 1. Objective",
    "## 2. Repository and baseline",
    "## 3. Research reviewed",
    "## 4. Research directions",
    "## 5. Hypotheses",
    "## 6. Experiment contract",
    "## 7. Experiments attempted",
    "## 8. Rejected approaches",
    "## 9. Full benchmark results",
    "## 10. Validation results",
    "## 11. Trade-offs",
    "## 12. Recommended implementation",
    "## 13. Risks and limitations",
    "## 14. Exact reproduction steps",
    "## 15. Commits and artifact paths",
    "## 16. Future experiments",
]


class TestEngineeringReport:
    def test_report_has_all_sections_and_recorded_numbers(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(app, ["report", "build", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["kind"] == "engineering"
        text = Path(payload["path"]).read_text(encoding="utf-8")

        for header in SECTION_HEADERS:
            assert header in text, header

        # Recorded numbers only.
        assert "f1: 0.8" in text  # baseline
        assert "f1=0.85" in text  # winner
        assert "exp-002" in text  # rejected variant listed with reason
        assert "p95_latency_ms" in text
        assert "no new tests were authored" in text.lower()
        assert "researchforge validate <run-id>" in text  # reproduction steps
        # No validated winner shipped yet -> recommendation says so.
        assert "Not yet shipped" in text

    def test_shipped_branch_appears_in_report(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        assert cli_runner.invoke(app, ["ship", "branch", "--yes"]).exit_code == 0
        result = cli_runner.invoke(app, ["report", "build", "--json"])
        text = Path(json.loads(result.output)["path"]).read_text(encoding="utf-8")

        assert "researchforge/caching-improves-f1-cheaply" in text
        assert "Not yet shipped" not in text

    def test_research_only_report_unchanged(
        self, cli_runner: CliRunner, initialized_project: Path, patched_arxiv: None
    ) -> None:
        # Explore-mode project with papers only -> research report as before.
        assert cli_runner.invoke(app, ["research", "search", "-q", "all:routing"]).exit_code == 0
        result = cli_runner.invoke(app, ["report", "build", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["kind"] == "research"
        assert payload["path"].endswith("research-report.md")


class TestNextActionChain:
    def test_chain_through_shipping(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        status = json.loads(cli_runner.invoke(app, ["status", "--json"]).output)
        assert "ship branch" in status["next_action"]

        assert cli_runner.invoke(app, ["ship", "branch", "--yes"]).exit_code == 0
        status = json.loads(cli_runner.invoke(app, ["status", "--json"]).output)
        assert "report build" in status["next_action"]

        assert cli_runner.invoke(app, ["report", "build"]).exit_code == 0
        status = json.loads(cli_runner.invoke(app, ["status", "--json"]).output)
        assert "ship pr" in status["next_action"]


class TestResearchPackage:
    def test_package_full_contents(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(app, ["paper", "package", "--json"])

        # funnel fixture has no papers -> gate blocks; use explore fixture below.
        assert result.exit_code == 1
        assert "No papers" in result.output

    def test_package_from_research_project(
        self,
        cli_runner: CliRunner,
        initialized_project: Path,
        patched_arxiv: None,
    ) -> None:
        import shutil

        artifacts = Path(__file__).parent.parent / "fixtures" / "artifacts"
        assert cli_runner.invoke(app, ["research", "search", "-q", "all:routing"]).exit_code == 0
        for fixture, command in (
            ("landscape_valid.yaml", ["research", "landscape", "--import"]),
            ("hypotheses_valid.yaml", ["hypotheses", "import"]),
        ):
            target = initialized_project / fixture
            shutil.copy(artifacts / fixture, target)
            assert cli_runner.invoke(app, [*command, str(target)]).exit_code == 0

        result = cli_runner.invoke(app, ["paper", "package", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        output_dir = Path(payload["output_dir"])
        assert output_dir == initialized_project / ".researchforge" / "research-output"

        expected = {
            "research_report.md",
            "related_work.md",
            "evidence_matrix.csv",
            "citations.bib",
            "hypotheses.md",
            "methodology.md",
            "limitations.md",
            "paper_outline.md",
            "reproducibility.md",
            "experiments/results.csv",
            "experiments/rejected_experiments.md",
            "experiments/run_manifest.json",
            "figures/README.md",
        }
        assert expected <= set(payload["files"])
        for relative in expected:
            assert (output_dir / relative).is_file(), relative

        # citations.bib: one entry per cited paper, balanced braces, key fields.
        bib = (output_dir / "citations.bib").read_text(encoding="utf-8")
        assert bib.count("@misc{") == 3  # landscape+hypotheses cite 3 papers
        assert bib.count("{") == bib.count("}")
        for field in ("title", "author", "year", "eprint", "archivePrefix", "url"):
            assert field in bib

        # evidence_matrix.csv: header + one row per evidence claim.
        with (output_dir / "evidence_matrix.csv").open() as handle:
            rows = list(csv.reader(handle))
        assert len(rows) == 1 + 3  # header + 3 claims in the fixture landscape

        # No-experiment placeholders are honest.
        outline = (output_dir / "paper_outline.md").read_text(encoding="utf-8")
        assert "No recorded experiments" in outline
        manifest = json.loads(
            (output_dir / "experiments" / "run_manifest.json").read_text(encoding="utf-8")
        )
        assert manifest == []

    def test_package_with_experiments(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        """Inject a paper + landscape-free run: package with experiment data."""
        from contextlib import closing
        from datetime import UTC, datetime

        from researchforge.domain.paper import Paper
        from researchforge.storage.db import open_project_db
        from researchforge.storage.paper_repository import upsert_paper
        from researchforge.storage.project_repository import get_project

        with closing(open_project_db()) as conn:
            project = get_project(conn)
            assert project is not None
            upsert_paper(
                conn,
                project.id,
                Paper(
                    paper_id="arxiv:2401.12345",
                    title="A Study",
                    authors=["A. Author"],
                    published_at=datetime(2024, 1, 15, tzinfo=UTC),
                    abstract="We study caching.",
                    source_url="https://arxiv.org/abs/2401.12345",
                ),
            )

        result = cli_runner.invoke(app, ["paper", "package", "--json"])

        assert result.exit_code == 0, result.output
        output_dir = Path(json.loads(result.output)["output_dir"])

        # results.csv has header + all recorded executions.
        with (output_dir / "experiments" / "results.csv").open() as handle:
            rows = list(csv.reader(handle))
        assert rows[0][:4] == ["experiment_id", "stage", "attempt", "status"]
        assert len(rows) > 4  # screening/full/validation attempts recorded

        # run_manifest.json re-validates as executions.
        from researchforge.domain.experiment import ExperimentExecution

        manifest = json.loads(
            (output_dir / "experiments" / "run_manifest.json").read_text(encoding="utf-8")
        )
        parsed = [ExperimentExecution.model_validate(item) for item in manifest]
        assert len(parsed) == len(rows) - 1

        rejected = (output_dir / "experiments" / "rejected_experiments.md").read_text(
            encoding="utf-8"
        )
        assert "exp-002" in rejected

        outline = (output_dir / "paper_outline.md").read_text(encoding="utf-8")
        assert "## 13. Citation mapping" in outline
        repro = (output_dir / "reproducibility.md").read_text(encoding="utf-8")
        assert "researchforge experiment run plan-001" in repro
        assert "sha256" in repro or "patch" in repro.lower()
