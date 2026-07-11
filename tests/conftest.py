from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from researchforge.domain.project import Project


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
