"""Deterministic relevance ranking: TF-IDF cosine over titles and abstracts.

Scores are advisory — they estimate topical relevance to the user's
objective from metadata only, and are never treated as evidence strength.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import UTC, datetime

from researchforge.domain.repo_scan import RepoScan
from researchforge.research.arxiv_client import ArxivEntry
from researchforge.research.text import tokenize

TITLE_WEIGHT = 3.0
ABSTRACT_WEIGHT = 1.0
REPO_KEYWORD_WEIGHT = 2.0
RECENCY_BONUS = 0.02
RECENCY_HALF_LIFE_YEARS = 5.0


def build_query_document(objective: str, scan: RepoScan | None, queries: list[str]) -> list[str]:
    """Token multiset representing what the user is looking for."""
    tokens = tokenize(objective)
    if scan is not None:
        for keyword in scan.keywords:
            tokens.extend([keyword] * int(REPO_KEYWORD_WEIGHT))
    for query in queries:
        tokens.extend(tokenize(query))
    return tokens


def _entry_tokens(entry: ArxivEntry) -> dict[str, float]:
    counts: dict[str, float] = {}
    for token in tokenize(entry.title):
        counts[token] = counts.get(token, 0.0) + TITLE_WEIGHT
    for token in tokenize(entry.abstract):
        counts[token] = counts.get(token, 0.0) + ABSTRACT_WEIGHT
    return counts


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(weight * b[token] for token, weight in a.items() if token in b)
    norm_a = math.sqrt(sum(w * w for w in a.values()))
    norm_b = math.sqrt(sum(w * w for w in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _recency_bonus(entry: ArxivEntry, now: datetime) -> float:
    age_years = max((now - entry.published_at).days / 365.25, 0.0)
    return RECENCY_BONUS * math.exp(-age_years / RECENCY_HALF_LIFE_YEARS)


def rank_candidates(
    entries: list[ArxivEntry],
    query_tokens: list[str],
    now: datetime | None = None,
) -> list[tuple[ArxivEntry, float]]:
    """Rank entries by TF-IDF cosine similarity to the query document.

    Returns (entry, score) pairs sorted by score desc with fully
    deterministic tie-breaking; scores are min-max normalized to [0, 1].
    """
    if not entries:
        return []
    current_time = now or datetime.now(UTC)

    # IDF over the fetched candidate set (self-contained, deterministic).
    doc_count = len(entries)
    doc_frequency: Counter[str] = Counter()
    entry_counts: list[dict[str, float]] = []
    for entry in entries:
        counts = _entry_tokens(entry)
        entry_counts.append(counts)
        doc_frequency.update(counts.keys())
    idf = {token: math.log((1 + doc_count) / (1 + df)) + 1.0 for token, df in doc_frequency.items()}

    query_counter = Counter(query_tokens)
    query_vector = {token: count * idf.get(token, 1.0) for token, count in query_counter.items()}

    raw_scores: list[float] = []
    for entry, counts in zip(entries, entry_counts, strict=True):
        vector = {token: weight * idf[token] for token, weight in counts.items()}
        raw_scores.append(_cosine(query_vector, vector) + _recency_bonus(entry, current_time))

    low, high = min(raw_scores), max(raw_scores)
    span = high - low
    normalized = [(s - low) / span if span > 0 else 0.5 for s in raw_scores]

    scored = list(zip(entries, normalized, strict=True))
    scored.sort(key=lambda pair: (-pair[1], -pair[0].published_at.timestamp(), pair[0].arxiv_id))
    return scored
