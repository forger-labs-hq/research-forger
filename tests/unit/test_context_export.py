import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from researchforge.cli import app
from researchforge.domain.landscape import ResearchLandscape
from researchforge.research.context_export import HypothesesArtifact


@pytest.fixture
def project_with_papers(
    cli_runner: CliRunner,
    initialized_project: Path,
    patched_arxiv: None,
) -> Path:
    result = cli_runner.invoke(app, ["research", "search", "-q", "all:routing"])
    assert result.exit_code == 0, result.output
    return initialized_project


class TestResearchContext:
    def test_writes_bundle_with_papers_and_schemas(
        self, cli_runner: CliRunner, project_with_papers: Path
    ) -> None:
        result = cli_runner.invoke(app, ["research", "context"])

        assert result.exit_code == 0, result.output
        bundle_path = project_with_papers / ".researchforge" / "synthesis" / "context.json"
        assert bundle_path.is_file()

        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        assert bundle["project"]["objective"]
        assert len(bundle["papers"]) > 0
        assert all("abstract" in p for p in bundle["papers"])
        # Embedded schemas must match the models the importers enforce.
        assert bundle["expected_artifacts"]["landscape_schema"] == (
            ResearchLandscape.model_json_schema()
        )
        assert bundle["expected_artifacts"]["hypotheses_schema"] == (
            HypothesesArtifact.model_json_schema()
        )

    def test_instructions_include_untrusted_content_rule(
        self, cli_runner: CliRunner, project_with_papers: Path
    ) -> None:
        result = cli_runner.invoke(app, ["research", "context", "--json"])

        bundle = json.loads(result.output)
        joined = " ".join(bundle["instructions"]).lower()
        assert "untrusted" in joined
        assert "never claim novelty" in joined

    def test_requires_stored_papers(self, cli_runner: CliRunner, initialized_project: Path) -> None:
        result = cli_runner.invoke(app, ["research", "context"])

        assert result.exit_code == 1
        assert "research search" in result.output

    def test_custom_output_path(self, cli_runner: CliRunner, project_with_papers: Path) -> None:
        target = project_with_papers / "custom" / "ctx.json"
        result = cli_runner.invoke(app, ["research", "context", "--output", str(target)])

        assert result.exit_code == 0
        assert target.is_file()
