from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from researchforge.domain.project import Project
from researchforge.research.arxiv_client import ArxivClient

ARXIV_FIXTURES = Path(__file__).parent / "fixtures" / "arxiv"


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Run a test with `cwd` set to an isolated temp directory."""
    monkeypatch.chdir(tmp_path)
    yield tmp_path


@pytest.fixture
def sample_project() -> Project:
    now = datetime.now(UTC)
    return Project(id="abc123", name="sample-project", created_at=now, updated_at=now)


def _fixture_arxiv_client() -> ArxivClient:
    """Client serving fixture pages (page1 for start=0, page2 otherwise), no sleeping."""

    def handler(request: httpx.Request) -> httpx.Response:
        page = "search_page1.xml" if request.url.params["start"] == "0" else "search_page2.xml"
        return httpx.Response(200, text=(ARXIV_FIXTURES / page).read_text(encoding="utf-8"))

    return ArxivClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None
    )


@pytest.fixture
def patched_arxiv(monkeypatch: pytest.MonkeyPatch) -> None:
    import researchforge.research.cli as research_cli

    monkeypatch.setattr(research_cli, "ArxivClient", _fixture_arxiv_client)


@pytest.fixture
def initialized_project(cli_runner: CliRunner, isolated_project_dir: Path) -> Path:
    """An isolated cwd with a defined explore-mode project."""
    from researchforge.cli import app

    result = cli_runner.invoke(
        app,
        [
            "project",
            "create",
            "--mode",
            "explore_research_idea",
            "--objective",
            "Can uncertainty-aware routing outperform fixed routing?",
        ],
    )
    assert result.exit_code == 0, result.output
    return isolated_project_dir
