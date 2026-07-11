from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from researchforge.domain.evidence import EvidenceClaim, EvidenceType
from researchforge.domain.hypothesis import (
    Hypothesis,
    HypothesisStatus,
    Level,
    NoveltyConfidence,
)
from researchforge.domain.landscape import (
    PaperAnnotation,
    ResearchDirection,
    ResearchLandscape,
)
from researchforge.domain.paper import EvidenceStrength, Paper
from researchforge.domain.repo_scan import CompatibilityStatus, PythonInfo, RepoScan


def _make_paper(**overrides: object) -> Paper:
    defaults: dict[str, object] = {
        "paper_id": "arxiv:2401.12345",
        "title": "A Study",
        "authors": ["A. Author"],
        "published_at": datetime(2024, 1, 15, tzinfo=UTC),
        "abstract": "We study things.",
        "source_url": "https://arxiv.org/abs/2401.12345",
    }
    defaults.update(overrides)
    return Paper(**defaults)  # type: ignore[arg-type]


def _make_hypothesis(**overrides: object) -> Hypothesis:
    defaults: dict[str, object] = {
        "hypothesis_id": "hyp-001",
        "title": "Routing helps",
        "claim": "Uncertainty-aware routing reduces cost.",
        "rationale": "Papers report cost reductions.",
        "feasibility": Level.MEDIUM,
        "estimated_effort": Level.LOW,
        "novelty_confidence": NoveltyConfidence.UNKNOWN,
        "proposed_experiment": "Route by entropy threshold; measure cost and quality.",
    }
    defaults.update(overrides)
    return Hypothesis(**defaults)  # type: ignore[arg-type]


class TestPaper:
    def test_valid_paper(self) -> None:
        paper = _make_paper()
        assert paper.evidence_strength == EvidenceStrength.UNKNOWN
        assert paper.relevance_score == 0.0

    @pytest.mark.parametrize(
        "bad_id",
        ["2401.12345", "arxiv:abc.12345", "arxiv:2401.123", "arXiv:2401.12345", ""],
    )
    def test_invalid_paper_id_rejected(self, bad_id: str) -> None:
        with pytest.raises(ValidationError):
            _make_paper(paper_id=bad_id)

    def test_relevance_score_bounds(self) -> None:
        with pytest.raises(ValidationError):
            _make_paper(relevance_score=1.5)
        with pytest.raises(ValidationError):
            _make_paper(relevance_score=-0.1)


class TestHypothesis:
    def test_supported_when_citations_present(self) -> None:
        hyp = _make_hypothesis(supporting_paper_ids=["arxiv:2401.12345"])
        assert hyp.evidence_status == "supported"

    def test_unsupported_when_no_citations(self) -> None:
        hyp = _make_hypothesis()
        assert hyp.evidence_status == "unsupported"

    def test_evidence_status_is_serialized(self) -> None:
        hyp = _make_hypothesis()
        assert hyp.model_dump()["evidence_status"] == "unsupported"

    def test_default_status_is_speculative(self) -> None:
        assert _make_hypothesis().status == HypothesisStatus.SPECULATIVE

    @pytest.mark.parametrize("bad_id", ["hyp-1", "hyp-0001", "hypothesis-001", "HYP-001"])
    def test_invalid_hypothesis_id_rejected(self, bad_id: str) -> None:
        with pytest.raises(ValidationError):
            _make_hypothesis(hypothesis_id=bad_id)

    def test_novelty_confidence_cannot_be_high(self) -> None:
        with pytest.raises(ValidationError):
            _make_hypothesis(novelty_confidence="high")

    def test_empty_claim_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_hypothesis(claim="")


class TestLandscape:
    def test_valid_landscape(self) -> None:
        landscape = ResearchLandscape(
            summary="Two directions dominate.",
            directions=[
                ResearchDirection(
                    direction_id="dir-001",
                    name="Uncertainty routing",
                    description="Routing by model confidence.",
                    paper_ids=["arxiv:2401.12345"],
                )
            ],
            paper_annotations=[
                PaperAnnotation(
                    paper_id="arxiv:2401.12345",
                    evidence_strength=EvidenceStrength.MEDIUM,
                    method_summary="Entropy-threshold routing.",
                )
            ],
            evidence=[
                EvidenceClaim(
                    evidence_id="ev-001",
                    paper_id="arxiv:2401.12345",
                    claim="Reported 30% cost reduction.",
                    evidence_type=EvidenceType.PUBLISHED_CLAIM,
                    extraction_confidence=Level.HIGH,
                )
            ],
        )
        assert len(landscape.directions) == 1

    def test_extra_keys_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ResearchLandscape(
                summary="s",
                directions=[
                    ResearchDirection(
                        direction_id="dir-001",
                        name="n",
                        description="d",
                        paper_ids=["arxiv:2401.12345"],
                    )
                ],
                is_novel=True,  # type: ignore[call-arg]
            )

    def test_empty_directions_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ResearchLandscape(summary="s", directions=[])

    def test_direction_requires_papers(self) -> None:
        with pytest.raises(ValidationError):
            ResearchDirection(direction_id="dir-001", name="n", description="d", paper_ids=[])


class TestRepoScan:
    def test_python_info_detection(self) -> None:
        assert PythonInfo(has_pyproject=True).is_python_project
        assert PythonInfo(requirements_files=["requirements.txt"]).is_python_project
        assert not PythonInfo().is_python_project

    def test_minimal_scan(self) -> None:
        scan = RepoScan(
            scan_id="abc",
            repo_path="/tmp/repo",
            compatibility=CompatibilityStatus.RESEARCH_ONLY,
            scanned_at=datetime.now(UTC),
        )
        assert scan.compatibility == CompatibilityStatus.RESEARCH_ONLY
