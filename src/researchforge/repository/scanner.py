"""Repository compatibility scanner.

Reads only: never modifies the scanned repository. All detection is
best-effort — missing metadata degrades a field to None/empty, never raises.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from researchforge.domain.repo_scan import (
    CompatibilityStatus,
    GitInfo,
    PythonInfo,
    ReadmeInfo,
    RepoScan,
)

README_EXCERPT_CHARS = 2000
_KEYWORD_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
    ]
)
_BENCHMARK_PATTERN = re.compile(r"bench|eval|perf", re.IGNORECASE)
_TEST_DIR_NAMES = ("tests", "test")
_PROTECTED_DEFAULTS = ("tests/", ".github/", ".researchforge/")


def _run_git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def scan_git(repo: Path) -> GitInfo:
    inside = _run_git(repo, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        return GitInfo(is_repo=False)
    return GitInfo(
        is_repo=True,
        commit=_run_git(repo, "rev-parse", "HEAD"),
        branch=_run_git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        remote_url=_run_git(repo, "remote", "get-url", "origin"),
    )


def scan_readme(repo: Path) -> ReadmeInfo:
    for name in ("README.md", "README.rst", "README.txt", "README"):
        candidate = repo / name
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            title = None
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    title = stripped.lstrip("#").strip()
                    break
                if stripped and title is None:
                    title = stripped
                    break
            return ReadmeInfo(path=name, title=title, excerpt=text[:README_EXCERPT_CHARS])
    return ReadmeInfo()


def scan_python(repo: Path) -> PythonInfo:
    info = PythonInfo(
        has_pyproject=(repo / "pyproject.toml").is_file(),
        has_setup_py=(repo / "setup.py").is_file(),
        requirements_files=sorted(p.name for p in repo.glob("requirements*.txt") if p.is_file()),
    )
    if info.has_pyproject:
        try:
            data = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return info
        project = data.get("project", {})
        if isinstance(project, dict):
            deps = project.get("dependencies", [])
            info = info.model_copy(
                update={
                    "package_name": project.get("name"),
                    "python_requires": project.get("requires-python"),
                    "dependencies": [d for d in deps if isinstance(d, str)]
                    if isinstance(deps, list)
                    else [],
                }
            )
    return info


def _find_test_candidates(repo: Path) -> list[str]:
    candidates = []
    for name in _TEST_DIR_NAMES:
        if (repo / name).is_dir():
            candidates.append(f"{name}/")
    for config in ("pytest.ini", "tox.ini", "noxfile.py"):
        if (repo / config).is_file():
            candidates.append(config)
    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        try:
            if "[tool.pytest" in pyproject.read_text(encoding="utf-8"):
                candidates.append("pyproject.toml [tool.pytest]")
        except OSError:
            pass
    return candidates


def _find_benchmark_candidates(repo: Path) -> list[str]:
    candidates = []
    for entry in sorted(repo.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir() and _BENCHMARK_PATTERN.search(entry.name):
            candidates.append(f"{entry.name}/")
    scripts_dir = repo / "scripts"
    if scripts_dir.is_dir():
        candidates.extend(
            f"scripts/{p.name}"
            for p in sorted(scripts_dir.iterdir())
            if p.is_file() and _BENCHMARK_PATTERN.search(p.name)
        )
    return candidates


def _extract_keywords(
    repo: Path, readme: ReadmeInfo, python: PythonInfo, limit: int = 25
) -> list[str]:
    seen: dict[str, None] = {}

    def add(text: str | None) -> None:
        if not text:
            return
        for token in re.split(r"[^a-zA-Z0-9]+", text.lower()):
            if len(token) >= 3 and token not in _KEYWORD_STOPWORDS and token not in seen:
                seen[token] = None

    add(python.package_name or repo.name)
    add(readme.title)
    for dep in python.dependencies:
        add(re.split(r"[<>=!\[~;]", dep, maxsplit=1)[0])
    if readme.excerpt:
        add(readme.excerpt[:500])
    return list(seen)[:limit]


def _suggest_paths(repo: Path, python: PythonInfo) -> tuple[list[str], list[str]]:
    editable = []
    for name in ("src", python.package_name or "", "lib", "app", "config"):
        if name and (repo / name).is_dir() and f"{name}/" not in editable:
            editable.append(f"{name}/")
    protected = [p for p in _PROTECTED_DEFAULTS if (repo / p.rstrip("/")).exists()]
    if ".researchforge/" not in protected:
        protected.append(".researchforge/")
    for bench in ("benchmarks/", "benchmark/", "evaluator/", "test_data/"):
        if (repo / bench.rstrip("/")).is_dir() and bench not in protected:
            protected.append(bench)
    return editable, protected


def _decide_compatibility(
    git: GitInfo, python: PythonInfo, tests: list[str], benchmarks: list[str]
) -> tuple[CompatibilityStatus, list[str]]:
    reasons = []
    if not git.is_repo:
        reasons.append("Not a Git repository — experiments require Git worktrees.")
    if not python.is_python_project:
        reasons.append("No Python project metadata found (pyproject.toml/setup.py/requirements).")

    if not git.is_repo and not python.is_python_project:
        reasons.append("Research-only mode is still available.")
        return CompatibilityStatus.RESEARCH_ONLY, reasons
    if not git.is_repo or not python.is_python_project:
        return CompatibilityStatus.UNSUPPORTED, reasons

    if tests or benchmarks:
        reasons.append("Python project with Git and evaluation candidates detected.")
        return CompatibilityStatus.READY, reasons

    reasons.append(
        "No test or benchmark candidates detected — a benchmark command must be "
        "configured before experiments (Phase 1B)."
    )
    return CompatibilityStatus.SETUP_REQUIRED, reasons


def scan_repository(repo_path: Path) -> RepoScan:
    """Scan a repository directory; read-only, never raises on missing metadata."""
    repo = repo_path.resolve()
    git = scan_git(repo)
    readme = scan_readme(repo)
    python = scan_python(repo)
    tests = _find_test_candidates(repo)
    benchmarks = _find_benchmark_candidates(repo)
    editable, protected = _suggest_paths(repo, python)
    compatibility, reasons = _decide_compatibility(git, python, tests, benchmarks)

    return RepoScan(
        scan_id=uuid4().hex,
        repo_path=str(repo),
        git=git,
        readme=readme,
        python=python,
        has_dockerfile=(repo / "Dockerfile").is_file(),
        test_candidates=tests,
        benchmark_candidates=benchmarks,
        suggested_editable_paths=editable,
        suggested_protected_paths=protected,
        keywords=_extract_keywords(repo, readme, python),
        compatibility=compatibility,
        compatibility_reasons=reasons,
        scanned_at=datetime.now(UTC),
    )
