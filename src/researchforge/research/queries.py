"""Deterministic fallback search-query generation.

Claude normally supplies queries (the highest-leverage retrieval step);
this fallback guarantees the CLI works standalone with at least
`settings.min_queries` distinct queries derived from the objective and
repository keywords.
"""

from __future__ import annotations

from researchforge.config.settings import ResearchSettings
from researchforge.domain.repo_scan import RepoScan
from researchforge.research.text import tokenize


def generate_queries(
    objective: str,
    scan: RepoScan | None,
    settings: ResearchSettings,
) -> list[str]:
    objective_tokens = tokenize(objective)
    repo_keywords = list(scan.keywords[:6]) if scan is not None else []

    candidates: list[str] = []

    def add(query: str) -> None:
        cleaned = " ".join(query.split())
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    # 1. The objective phrase itself (most specific).
    add(" ".join(objective_tokens[:8]))

    # 2. Adjacent keyword pairs from the objective.
    for first, second in zip(objective_tokens, objective_tokens[1:], strict=False):
        add(f"{first} {second}")

    # 3. Objective head terms + evaluation-oriented suffixes.
    head = " ".join(objective_tokens[:3])
    if head:
        add(f"{head} benchmark")
        add(f"{head} evaluation")

    # 4. Repository keywords crossed with the objective head.
    for keyword in repo_keywords:
        if keyword not in objective_tokens:
            add(f"{keyword} {head}" if head else keyword)

    clamped = candidates[: settings.max_queries]
    # Guarantee the configured minimum by padding with single keywords.
    if len(clamped) < settings.min_queries:
        for token in objective_tokens + repo_keywords:
            if len(clamped) >= settings.min_queries:
                break
            if token not in clamped:
                clamped.append(token)
    return clamped
