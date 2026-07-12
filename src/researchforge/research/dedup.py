"""Candidate deduplication."""

from __future__ import annotations

import re
from collections.abc import Iterable

from researchforge.research.arxiv_client import ArxivEntry

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalized_title(title: str) -> str:
    return _NON_ALNUM.sub("", title.casefold())


def deduplicate_entries(entries: Iterable[ArxivEntry]) -> list[ArxivEntry]:
    """Drop duplicates by canonical arXiv id (keeping the highest version),
    then by normalized title. Order-stable and deterministic."""
    by_id: dict[str, ArxivEntry] = {}
    order: list[str] = []
    for entry in entries:
        existing = by_id.get(entry.arxiv_id)
        if existing is None:
            by_id[entry.arxiv_id] = entry
            order.append(entry.arxiv_id)
        elif (entry.version or 0) > (existing.version or 0):
            by_id[entry.arxiv_id] = entry

    seen_titles: set[str] = set()
    result: list[ArxivEntry] = []
    for arxiv_id in order:
        entry = by_id[arxiv_id]
        title_key = _normalized_title(entry.title)
        if title_key and title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        result.append(entry)
    return result
