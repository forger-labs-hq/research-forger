import subprocess
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from researchforge.domain.project import Project
from researchforge.research.arxiv_client import ArxivClient

ARXIV_FIXTURES = Path(__file__).parent / "fixtures" / "arxiv"

RepoFactory = Callable[..., Path]


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
def repo_factory(tmp_path_factory: pytest.TempPathFactory) -> RepoFactory:
    """Build a throwaway repository directory with configurable traits."""

    def _build(
        *,
        git: bool = True,
        pyproject: bool = False,
        requirements: bool = False,
        tests_dir: bool = False,
        benchmarks_dir: bool = False,
        dockerfile: bool = False,
        readme: str | None = None,
        eval_script: str | None = None,
    ) -> Path:
        repo = tmp_path_factory.mktemp("repo")
        if pyproject:
            (repo / "pyproject.toml").write_text(
                '[project]\nname = "demo-pkg"\nrequires-python = ">=3.12"\n'
                'dependencies = ["numpy>=1.26", "scikit-learn"]\n',
                encoding="utf-8",
            )
        if requirements:
            (repo / "requirements.txt").write_text("requests\n", encoding="utf-8")
        if tests_dir:
            (repo / "tests").mkdir()
            (repo / "tests" / ".keep").write_text("", encoding="utf-8")
        if benchmarks_dir:
            (repo / "benchmarks").mkdir()
            (repo / "benchmarks" / ".keep").write_text("", encoding="utf-8")
        if eval_script is not None:
            (repo / "benchmarks").mkdir(exist_ok=True)
            (repo / "benchmarks" / "evaluate.py").write_text(eval_script, encoding="utf-8")
        if dockerfile:
            (repo / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
        if readme is not None:
            (repo / "README.md").write_text(readme, encoding="utf-8")
        if git:
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True
            )
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            (repo / ".keep").write_text("", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
        return repo

    return _build


@pytest.fixture
def improve_project(
    cli_runner: CliRunner, isolated_project_dir: Path, repo_factory: RepoFactory
) -> Path:
    """Improve-mode project with a scanned, ready fixture repository.

    Returns the fixture repo path; the project db lives in the isolated cwd.
    """
    from researchforge.cli import app

    repo = repo_factory(pyproject=True, tests_dir=True, benchmarks_dir=True)
    result = cli_runner.invoke(
        app,
        [
            "project",
            "create",
            "--mode",
            "improve_repository",
            "--objective",
            "Improve classification F1 without increasing latency",
        ],
    )
    assert result.exit_code == 0, result.output
    scan = cli_runner.invoke(app, ["repo", "scan", str(repo)])
    assert scan.exit_code == 0, scan.output
    return repo


EVAL_SCRIPTS = Path(__file__).parent / "fixtures" / "eval_scripts"

CONTRACT_TEMPLATE = """\
version: 1
project:
  name: {name}
  mode: improve_repository
objective:
  description: "Improve classification F1 without increasing latency"
  primary_metric:
    name: f1
    direction: maximize
  hard_constraints: []
  secondary_metrics:
    - p95_latency_ms
repository:
  baseline_ref: main
execution:
  mode: auto
  trusted_repository: true
  setup_command: null
  full_command: "python benchmarks/evaluate.py"
  result_file: artifacts/results.json
  timeout_minutes: 5
  cpu_limit: 1
  memory_mb: 1024
  max_experiments: 4
permissions:
  editable_paths:
    - src/
  protected_paths:
    - benchmarks/
network:
  mode: none
secrets:
  forward_environment_variables: []
validation:
  repeat_finalists: 2
  require_existing_tests: false
shipping:
  allow_branch_creation: true
  allow_draft_pr: false
"""


@pytest.fixture
def contracted_project(
    cli_runner: CliRunner,
    isolated_project_dir: Path,
    repo_factory: RepoFactory,
) -> Path:
    """Improve-mode project with a scanned repo, eval script, and approved contract.

    Returns the fixture repo path. The repo has no Dockerfile, so the auto
    resolver deterministically lands on venv (trusted, python via requirements).
    """
    from researchforge.cli import app

    repo = repo_factory(
        requirements=True,
        eval_script=(EVAL_SCRIPTS / "good.py").read_text(encoding="utf-8"),
    )
    (repo / "src").mkdir(exist_ok=True)
    result = cli_runner.invoke(
        app,
        [
            "project",
            "create",
            "--mode",
            "improve_repository",
            "--objective",
            "Improve classification F1 without increasing latency",
        ],
    )
    assert result.exit_code == 0, result.output
    assert cli_runner.invoke(app, ["repo", "scan", str(repo)]).exit_code == 0

    contract_file = repo / "researchforge.yaml"
    contract_file.write_text(CONTRACT_TEMPLATE.format(name=repo.name), encoding="utf-8")
    approve = cli_runner.invoke(app, ["contract", "approve", "--yes"])
    assert approve.exit_code == 0, approve.output
    return repo


@pytest.fixture
def baselined_project(cli_runner: CliRunner, contracted_project: Path) -> Path:
    """Contracted project with a stored hypothesis and a successful venv baseline.

    Returns the fixture repo path (cwd holds the project db and staging dirs).
    """
    from contextlib import closing
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime

    from researchforge.cli import app
    from researchforge.domain.hypothesis import (
        Hypothesis,
        Level,
        NoveltyConfidence,
    )
    from researchforge.storage.db import open_project_db
    from researchforge.storage.hypothesis_repository import replace_hypotheses
    from researchforge.storage.project_repository import get_project

    _ = _datetime.now(_UTC)
    hypothesis = Hypothesis(
        hypothesis_id="hyp-001",
        title="Caching improves F1 cheaply",
        claim="Memoizing hot paths improves F1 without latency cost.",
        rationale="Fixture rationale.",
        feasibility=Level.HIGH,
        estimated_effort=Level.LOW,
        novelty_confidence=NoveltyConfidence.UNKNOWN,
        proposed_experiment="Apply caching variants and benchmark.",
    )
    with closing(open_project_db()) as conn:
        project = get_project(conn)
        assert project is not None
        replace_hypotheses(conn, project.id, [hypothesis])

    result = cli_runner.invoke(app, ["baseline", "run"])
    assert result.exit_code == 0, result.output
    return contracted_project


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
