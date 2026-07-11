"""Tests for the pure research functions: dedup, ranking, queries."""

from datetime import UTC, datetime

from researchforge.config.settings import ResearchSettings
from researchforge.research.arxiv_client import ArxivEntry
from researchforge.research.dedup import deduplicate_entries
from researchforge.research.queries import generate_queries
from researchforge.research.ranking import build_query_document, rank_candidates
from researchforge.research.text import tokenize


def _entry(
    arxiv_id: str,
    title: str,
    abstract: str = "",
    version: int | None = 1,
    year: int = 2024,
) -> ArxivEntry:
    return ArxivEntry(
        arxiv_id=arxiv_id,
        version=version,
        title=title,
        abstract=abstract,
        authors=["A"],
        published_at=datetime(year, 6, 1, tzinfo=UTC),
        categories=["cs.LG"],
        primary_category="cs.LG",
        source_url=f"http://arxiv.org/abs/{arxiv_id}v{version or 1}",
    )


class TestTokenize:
    def test_drops_stopwords_and_short_tokens(self) -> None:
        tokens = tokenize("We propose a new method to do routing of LLMs")
        assert "propose" not in tokens
        assert "the" not in tokens
        assert "routing" in tokens
        assert "llms" in tokens

    def test_lowercases_and_splits_punctuation(self) -> None:
        assert tokenize("Cost-Efficient Routing!") == ["cost", "efficient", "routing"]


class TestDedup:
    def test_keeps_highest_version_for_same_id(self) -> None:
        v1 = _entry("2401.12345", "Routing Study", version=1)
        v3 = _entry("2401.12345", "Routing Study", version=3)
        result = deduplicate_entries([v1, v3])
        assert len(result) == 1
        assert result[0].version == 3

    def test_deduplicates_by_normalized_title(self) -> None:
        a = _entry("2401.11111", "Uncertainty-Aware Routing")
        b = _entry("2402.22222", "uncertainty aware routing")
        result = deduplicate_entries([a, b])
        assert len(result) == 1
        assert result[0].arxiv_id == "2401.11111"

    def test_order_stable(self) -> None:
        entries = [_entry(f"240{i}.0000{i}", f"Paper {i}") for i in range(1, 6)]
        result = deduplicate_entries(entries)
        assert [e.arxiv_id for e in result] == [e.arxiv_id for e in entries]


class TestRanking:
    def test_relevant_entry_ranks_first(self) -> None:
        relevant = _entry(
            "2401.11111",
            "Uncertainty-aware routing for cost reduction",
            "Routing by uncertainty lowers inference cost.",
        )
        irrelevant = _entry(
            "2402.22222",
            "Protein folding with transformers",
            "We fold proteins.",
        )
        query = build_query_document("reduce inference cost with uncertainty routing", None, [])
        ranked = rank_candidates([irrelevant, relevant], query)
        assert ranked[0][0].arxiv_id == "2401.11111"

    def test_title_match_beats_abstract_match(self) -> None:
        title_match = _entry("2401.11111", "Quantization for fast inference", "Generic text here.")
        abstract_match = _entry(
            "2402.22222", "A study of methods", "We discuss quantization briefly."
        )
        query = build_query_document("quantization", None, [])
        ranked = rank_candidates([abstract_match, title_match], query)
        assert ranked[0][0].arxiv_id == "2401.11111"

    def test_scores_within_bounds(self) -> None:
        entries = [_entry(f"240{i}.0000{i}", f"Paper about topic {i}") for i in range(1, 6)]
        ranked = rank_candidates(entries, ["topic"])
        assert all(0.0 <= score <= 1.0 for _, score in ranked)

    def test_deterministic(self) -> None:
        entries = [
            _entry("2401.11111", "Routing A", "cost"),
            _entry("2402.22222", "Routing B", "cost"),
            _entry("2403.33333", "Routing C", "cost"),
        ]
        query = ["routing", "cost"]
        now = datetime(2026, 1, 1, tzinfo=UTC)
        first = rank_candidates(entries, query, now=now)
        second = rank_candidates(list(entries), query, now=now)
        assert [(e.arxiv_id, s) for e, s in first] == [(e.arxiv_id, s) for e, s in second]

    def test_empty_input(self) -> None:
        assert rank_candidates([], ["anything"]) == []

    def test_repo_keywords_weighted_into_query(self) -> None:
        from researchforge.domain.repo_scan import CompatibilityStatus, RepoScan

        scan = RepoScan(
            scan_id="s",
            repo_path="/tmp/x",
            keywords=["classifier"],
            compatibility=CompatibilityStatus.READY,
            scanned_at=datetime.now(UTC),
        )
        tokens = build_query_document("improve accuracy", scan, [])
        assert tokens.count("classifier") == 2  # weighted x2


class TestQueryGeneration:
    def test_at_least_three_distinct_queries(self) -> None:
        queries = generate_queries(
            "Can uncertainty-aware routing outperform fixed routing?",
            None,
            ResearchSettings(),
        )
        assert len(queries) >= 3
        assert len(set(queries)) == len(queries)

    def test_respects_max_queries(self) -> None:
        settings = ResearchSettings(max_queries=4)
        queries = generate_queries(
            "improve classification F1 without increasing latency on the benchmark",
            None,
            settings,
        )
        assert len(queries) <= 4

    def test_repo_keywords_influence_queries(self) -> None:
        from researchforge.domain.repo_scan import CompatibilityStatus, RepoScan

        scan = RepoScan(
            scan_id="s",
            repo_path="/tmp/x",
            keywords=["transformers", "sklearn"],
            compatibility=CompatibilityStatus.READY,
            scanned_at=datetime.now(UTC),
        )
        queries = generate_queries("improve F1 score", scan, ResearchSettings())
        joined = " ".join(queries)
        assert "transformers" in joined

    def test_deterministic(self) -> None:
        args = ("improve retrieval quality under latency limits", None, ResearchSettings())
        assert generate_queries(*args) == generate_queries(*args)
