import json
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import researchforge.research.cli as research_cli
from researchforge.cli import app
from researchforge.research.arxiv_client import ArxivClient
from researchforge.storage.db import open_project_db

FIXTURES = Path(__file__).parent.parent / "fixtures" / "arxiv"


def _fixture_client() -> ArxivClient:
    """Client serving page1 for start=0 and page2 otherwise, no sleeping."""

    def handler(request: httpx.Request) -> httpx.Response:
        page = "search_page1.xml" if request.url.params["start"] == "0" else "search_page2.xml"
        return httpx.Response(200, text=(FIXTURES / page).read_text(encoding="utf-8"))

    return ArxivClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None
    )


@pytest.fixture
def patched_arxiv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(research_cli, "ArxivClient", _fixture_client)


class TestResearchSearchCli:
    def test_search_persists_papers_and_provenance(
        self, cli_runner: CliRunner, initialized_project: Path, patched_arxiv: None
    ) -> None:
        result = cli_runner.invoke(app, ["research", "search", "-q", "all:routing", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["queries"] == ["all:routing"]
        assert payload["selected_count"] > 0
        assert all(0.0 <= p["relevance_score"] <= 1.0 for p in payload["papers"])

        with closing(open_project_db()) as conn:
            papers = conn.execute("SELECT COUNT(*) AS n FROM papers").fetchone()["n"]
            runs = conn.execute("SELECT * FROM search_runs").fetchall()
        assert papers == payload["selected_count"]
        assert len(runs) == 1
        assert json.loads(runs[0]["queries"]) == ["all:routing"]

    def test_search_generates_queries_when_omitted(
        self, cli_runner: CliRunner, initialized_project: Path, patched_arxiv: None
    ) -> None:
        result = cli_runner.invoke(app, ["research", "search", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert len(payload["queries"]) >= 3

    def test_search_requires_defined_project(
        self, cli_runner: CliRunner, isolated_project_dir: Path, patched_arxiv: None
    ) -> None:
        cli_runner.invoke(app, ["init"])
        result = cli_runner.invoke(app, ["research", "search"])

        assert result.exit_code == 1

    def test_status_advances_to_researching(
        self, cli_runner: CliRunner, initialized_project: Path, patched_arxiv: None
    ) -> None:
        cli_runner.invoke(app, ["research", "search", "-q", "all:routing"])

        status = cli_runner.invoke(app, ["status", "--json"])
        payload = json.loads(status.output)
        assert payload["status"] == "researching"
        assert "context" in payload["next_action"]

    def test_rerun_replaces_papers(
        self, cli_runner: CliRunner, initialized_project: Path, patched_arxiv: None
    ) -> None:
        cli_runner.invoke(app, ["research", "search", "-q", "all:routing"])
        result = cli_runner.invoke(app, ["research", "search", "-q", "all:routing"])

        assert result.exit_code == 0
        with closing(open_project_db()) as conn:
            runs = conn.execute("SELECT COUNT(*) AS n FROM search_runs").fetchone()["n"]
        assert runs == 2

    def test_rerun_blocked_when_hypotheses_cite_papers(
        self, cli_runner: CliRunner, initialized_project: Path, patched_arxiv: None
    ) -> None:
        cli_runner.invoke(app, ["research", "search", "-q", "all:routing"])
        # Simulate an imported hypothesis citing a stored paper.
        with closing(open_project_db()) as conn:
            record = {
                "hypothesis_id": "hyp-001",
                "supporting_paper_ids": ["arxiv:2401.12345"],
                "contradicting_paper_ids": [],
            }
            now = datetime.now(UTC).isoformat()
            with conn:
                conn.execute(
                    "INSERT INTO hypotheses VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("hyp-001", "p", "t", "speculative", json.dumps(record), now, now),
                )

        blocked = cli_runner.invoke(app, ["research", "search", "-q", "all:routing"])
        assert blocked.exit_code == 1
        assert "force" in blocked.output.lower()

        forced = cli_runner.invoke(app, ["research", "search", "-q", "all:routing", "--force"])
        assert forced.exit_code == 0


class TestPapersCli:
    def test_list_and_show(
        self, cli_runner: CliRunner, initialized_project: Path, patched_arxiv: None
    ) -> None:
        cli_runner.invoke(app, ["research", "search", "-q", "all:routing"])

        listed = cli_runner.invoke(app, ["papers", "list"])
        assert listed.exit_code == 0
        assert "arxiv:2401.12345" in listed.output

        shown = cli_runner.invoke(app, ["papers", "show", "arxiv:2401.12345", "--json"])
        assert shown.exit_code == 0
        payload = json.loads(shown.output)
        assert payload["title"].startswith("Uncertainty-Aware Routing")

    def test_show_unknown_paper(self, cli_runner: CliRunner, initialized_project: Path) -> None:
        result = cli_runner.invoke(app, ["papers", "show", "arxiv:9999.99999"])
        assert result.exit_code == 1

    def test_list_empty(self, cli_runner: CliRunner, initialized_project: Path) -> None:
        result = cli_runner.invoke(app, ["papers", "list"])
        assert result.exit_code == 0
        assert "No papers" in result.output
