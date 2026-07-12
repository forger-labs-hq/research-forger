"""Contract draft generation from the stored project and repository scan."""

from __future__ import annotations

import re

from researchforge.domain.contract import (
    ContractSpec,
    ExecutionSection,
    MetricDirection,
    ObjectiveSection,
    PermissionsSection,
    PrimaryMetric,
    ProjectSection,
    RepositorySection,
)
from researchforge.domain.project import Project, ProjectMode
from researchforge.domain.repo_scan import RepoScan

FULL_COMMAND_PLACEHOLDER = "# TODO: command that writes the result file"

# Keyword → (metric name, direction). First match in the objective text wins.
_MINIMIZE_KEYWORDS = (
    ("latency", "latency_ms"),
    ("cost", "average_cost_usd"),
    ("loss", "loss"),
    ("perplexity", "perplexity"),
    ("memory", "memory_mb"),
    ("error", "error_rate"),
    ("time", "runtime_seconds"),
)
_MAXIMIZE_KEYWORDS = (
    ("f1", "f1"),
    ("accuracy", "accuracy"),
    ("quality", "quality_score"),
    ("throughput", "throughput"),
    ("recall", "recall"),
    ("precision", "precision"),
    ("bleu", "bleu"),
    ("rouge", "rouge"),
    ("score", "score"),
)


def guess_primary_metric(objective_text: str) -> PrimaryMetric:
    lowered = objective_text.lower()
    # Maximize keywords first: objectives like "improve F1 without increasing
    # latency" name the optimization target before the constraint.
    for keyword, name in _MAXIMIZE_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered):
            return PrimaryMetric(name=name, direction=MetricDirection.MAXIMIZE)
    for keyword, name in _MINIMIZE_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered):
            return PrimaryMetric(name=name, direction=MetricDirection.MINIMIZE)
    return PrimaryMetric(name="primary_metric", direction=MetricDirection.MAXIMIZE)


def guess_commands(scan: RepoScan) -> tuple[str | None, str]:
    """Best-effort (setup_command, full_command-or-placeholder)."""
    setup: str | None = None
    if scan.python.has_pyproject or scan.python.has_setup_py:
        setup = "python -m pip install -e ."
    elif scan.python.requirements_files:
        setup = f"python -m pip install -r {scan.python.requirements_files[0]}"

    full = FULL_COMMAND_PLACEHOLDER
    for candidate in scan.benchmark_candidates:
        if candidate.endswith(".py"):
            full = f"python {candidate}"
            break
    return setup, full


def build_draft_spec(project: Project, scan: RepoScan) -> ContractSpec:
    if project.mode is None or project.objective is None:
        raise ValueError("Project mode and objective must be set before generating a contract.")

    setup_command, full_command = guess_commands(scan)
    return ContractSpec(
        version=1,
        project=ProjectSection(name=project.name, mode=ProjectMode(project.mode)),
        objective=ObjectiveSection(
            description=project.objective,
            primary_metric=guess_primary_metric(project.objective),
        ),
        repository=RepositorySection(baseline_ref=scan.git.branch or "main"),
        execution=ExecutionSection(
            setup_command=setup_command,
            full_command=full_command,
        ),
        permissions=PermissionsSection(
            editable_paths=list(scan.suggested_editable_paths) or ["src/"],
            protected_paths=list(scan.suggested_protected_paths),
        ),
    )
