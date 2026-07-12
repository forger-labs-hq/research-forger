import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from researchforge.cli import app

ARTIFACTS = Path(__file__).parent.parent / "fixtures" / "artifacts"

NOVELTY_BLOCKLIST = ("guaranteed novelty", "is novel", "first ever", "unprecedented")


@pytest.fixture
def synthesized_project(
    cli_runner: CliRunner,
    initialized_project: Path,
    patched_arxiv: None,
) -> Path:
    """Project with papers, landscape, and hypotheses all imported."""
    assert cli_runner.invoke(app, ["research", "search", "-q", "all:routing"]).exit_code == 0
    for fixture, command in (
        ("landscape_valid.yaml", ["research", "landscape", "--import"]),
        ("hypotheses_valid.yaml", ["hypotheses", "import"]),
    ):
        target = initialized_project / fixture
        shutil.copy(ARTIFACTS / fixture, target)
        result = cli_runner.invoke(app, [*command, str(target)])
        assert result.exit_code == 0, result.output
    return initialized_project


class TestReportBuild:
    def test_report_written_with_all_sections(
        self, cli_runner: CliRunner, synthesized_project: Path
    ) -> None:
        result = cli_runner.invoke(app, ["report", "build"])

        assert result.exit_code == 0, result.output
        report_path = synthesized_project / ".researchforge" / "reports" / "research-report.md"
        assert report_path.is_file()
        text = report_path.read_text(encoding="utf-8")

        for heading in (
            "# Research Report:",
            "## Methodology and provenance",
            "## Research landscape",
            "## Hypotheses (all speculative until tested)",
            "## Speculation register",
            "## References",
        ):
            assert heading in text

    def test_epistemic_legend_present(
        self, cli_runner: CliRunner, synthesized_project: Path
    ) -> None:
        cli_runner.invoke(app, ["report", "build"])
        text = (
            synthesized_project / ".researchforge" / "reports" / "research-report.md"
        ).read_text(encoding="utf-8")

        assert "Published claim" in text
        assert "Interpretation" in text
        assert "Speculation" in text
        assert "No novelty guarantee" in text
        assert "Novelty has not been established" in text

    def test_unsupported_hypothesis_labeled(
        self, cli_runner: CliRunner, synthesized_project: Path
    ) -> None:
        cli_runner.invoke(app, ["report", "build"])
        text = (
            synthesized_project / ".researchforge" / "reports" / "research-report.md"
        ).read_text(encoding="utf-8")

        # hyp-003 in the fixture has no citations.
        assert "UNSUPPORTED" in text

    def test_cited_papers_appear_in_references(
        self, cli_runner: CliRunner, synthesized_project: Path
    ) -> None:
        cli_runner.invoke(app, ["report", "build"])
        text = (
            synthesized_project / ".researchforge" / "reports" / "research-report.md"
        ).read_text(encoding="utf-8")

        references = text.split("## References")[1]
        for paper_id in ("arxiv:2401.12345", "arxiv:2312.00001", "arxiv:2405.98765"):
            assert paper_id in references

    def test_no_novelty_phrases_in_cli_authored_text(
        self, cli_runner: CliRunner, synthesized_project: Path
    ) -> None:
        cli_runner.invoke(app, ["report", "build"])
        text = (
            synthesized_project / ".researchforge" / "reports" / "research-report.md"
        ).read_text(encoding="utf-8")

        lowered = text.lower()
        for phrase in NOVELTY_BLOCKLIST:
            assert phrase not in lowered

    def test_status_becomes_reported(
        self, cli_runner: CliRunner, synthesized_project: Path
    ) -> None:
        cli_runner.invoke(app, ["report", "build"])

        status = json.loads(cli_runner.invoke(app, ["status", "--json"]).output)
        assert status["status"] == "reported"
        assert "complete" in status["next_action"].lower()

    def test_json_output_and_custom_path(
        self, cli_runner: CliRunner, synthesized_project: Path
    ) -> None:
        target = synthesized_project / "out" / "report.md"
        result = cli_runner.invoke(app, ["report", "build", "--output", str(target), "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["path"] == str(target)
        assert target.is_file()

    def test_requires_papers(self, cli_runner: CliRunner, initialized_project: Path) -> None:
        result = cli_runner.invoke(app, ["report", "build"])
        assert result.exit_code == 1


class TestResumeAcceptance:
    def test_all_data_resumable_across_invocations(
        self, cli_runner: CliRunner, synthesized_project: Path
    ) -> None:
        """Each CLI invocation opens fresh connections — this asserts the
        acceptance criterion that all data survives a CLI restart."""
        papers = json.loads(cli_runner.invoke(app, ["papers", "list", "--json"]).output)
        hypotheses = json.loads(cli_runner.invoke(app, ["hypotheses", "list", "--json"]).output)
        landscape = json.loads(cli_runner.invoke(app, ["research", "landscape", "--json"]).output)
        status = json.loads(cli_runner.invoke(app, ["status", "--json"]).output)

        assert len(papers) > 0
        assert len(hypotheses) == 3
        assert len(landscape["directions"]) == 2
        assert status["counts"]["papers"] == len(papers)
