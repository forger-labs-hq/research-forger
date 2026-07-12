from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from researchforge.cli import app
from researchforge.domain.repo_scan import CompatibilityStatus
from researchforge.repository.scanner import scan_repository

RepoFactory = Callable[..., Path]


class TestCompatibilityDecision:
    def test_ready(self, repo_factory: RepoFactory) -> None:
        repo = repo_factory(pyproject=True, tests_dir=True)
        scan = scan_repository(repo)
        assert scan.compatibility == CompatibilityStatus.READY

    def test_setup_required_without_tests_or_benchmarks(self, repo_factory: RepoFactory) -> None:
        repo = repo_factory(pyproject=True)
        scan = scan_repository(repo)
        assert scan.compatibility == CompatibilityStatus.SETUP_REQUIRED

    def test_unsupported_python_without_git(self, repo_factory: RepoFactory) -> None:
        repo = repo_factory(git=False, pyproject=True)
        scan = scan_repository(repo)
        assert scan.compatibility == CompatibilityStatus.UNSUPPORTED

    def test_unsupported_git_without_python(self, repo_factory: RepoFactory) -> None:
        repo = repo_factory(git=True)
        scan = scan_repository(repo)
        assert scan.compatibility == CompatibilityStatus.UNSUPPORTED

    def test_research_only_for_bare_directory(self, repo_factory: RepoFactory) -> None:
        repo = repo_factory(git=False)
        scan = scan_repository(repo)
        assert scan.compatibility == CompatibilityStatus.RESEARCH_ONLY

    def test_reasons_are_always_present(self, repo_factory: RepoFactory) -> None:
        scan = scan_repository(repo_factory(git=False))
        assert scan.compatibility_reasons


class TestDetection:
    def test_git_info(self, repo_factory: RepoFactory) -> None:
        scan = scan_repository(repo_factory())
        assert scan.git.is_repo
        assert scan.git.commit is not None
        assert scan.git.branch == "main"

    def test_pyproject_metadata(self, repo_factory: RepoFactory) -> None:
        scan = scan_repository(repo_factory(pyproject=True))
        assert scan.python.package_name == "demo-pkg"
        assert scan.python.python_requires == ">=3.12"
        assert "numpy>=1.26" in scan.python.dependencies

    def test_readme_title_and_excerpt(self, repo_factory: RepoFactory) -> None:
        scan = scan_repository(
            repo_factory(readme="# Demo Project\n\nClassifies things with ML.\n")
        )
        assert scan.readme.title == "Demo Project"
        assert scan.readme.excerpt is not None
        assert "Classifies" in scan.readme.excerpt

    def test_dockerfile_and_benchmarks(self, repo_factory: RepoFactory) -> None:
        scan = scan_repository(repo_factory(pyproject=True, benchmarks_dir=True, dockerfile=True))
        assert scan.has_dockerfile
        assert "benchmarks/" in scan.benchmark_candidates

    def test_protected_paths_include_researchforge_and_tests(
        self, repo_factory: RepoFactory
    ) -> None:
        scan = scan_repository(repo_factory(pyproject=True, tests_dir=True, benchmarks_dir=True))
        assert ".researchforge/" in scan.suggested_protected_paths
        assert "tests/" in scan.suggested_protected_paths
        assert "benchmarks/" in scan.suggested_protected_paths

    def test_keywords_from_package_and_deps(self, repo_factory: RepoFactory) -> None:
        scan = scan_repository(
            repo_factory(pyproject=True, readme="# Classifier\nAn F1-optimized classifier.")
        )
        assert "demo" in scan.keywords or "demo-pkg" in " ".join(scan.keywords)
        assert "numpy" in scan.keywords


class TestRepoScanCli:
    def test_scan_persists_and_updates_project(
        self, cli_runner: CliRunner, initialized_project: Path, repo_factory: RepoFactory
    ) -> None:
        repo = repo_factory(pyproject=True, tests_dir=True)

        result = cli_runner.invoke(app, ["repo", "scan", str(repo)])
        assert result.exit_code == 0
        assert "ready" in result.output

        import json

        show = cli_runner.invoke(app, ["project", "show", "--json"])
        payload = json.loads(show.output)
        assert payload["repository"]["path"] == str(repo.resolve())

    def test_scan_without_project_fails(
        self, cli_runner: CliRunner, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(app, ["repo", "scan", str(isolated_project_dir)])
        assert result.exit_code == 1

    def test_unsupported_is_exit_zero(
        self, cli_runner: CliRunner, initialized_project: Path, repo_factory: RepoFactory
    ) -> None:
        repo = repo_factory(git=True)  # git but no python → unsupported

        result = cli_runner.invoke(app, ["repo", "scan", str(repo)])
        assert result.exit_code == 0
        assert "unsupported" in result.output
