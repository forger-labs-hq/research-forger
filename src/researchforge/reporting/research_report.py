"""Research-only Markdown report builder.

All headings and structure are CLI-authored; artifact free text is rendered
as content only. The report mechanically separates the four epistemic
levels: published claims, interpretations, hypotheses, and speculation.
"""

from __future__ import annotations

from datetime import UTC, datetime

from researchforge import __version__
from researchforge.domain.evidence import EvidenceClaim, EvidenceType
from researchforge.domain.hypothesis import Hypothesis
from researchforge.domain.landscape import ResearchLandscape
from researchforge.domain.paper import Paper
from researchforge.domain.project import Project, ProjectMode
from researchforge.domain.repo_scan import RepoScan

EPISTEMIC_LEGEND = """\
| Label | Meaning |
|---|---|
| Published claim | Stated in the cited paper's abstract. |
| Interpretation | A ResearchForge reading of the source, not stated verbatim. |
| Hypothesis (speculative) | Proposed and untested; requires experiments. |
| Speculation | Not grounded in the retrieved text. |

**No novelty guarantee.** "Underexplored" means *not found in the retrieved
literature*, not absent from all literature. Novelty has not been established.
"""

RANKING_DISCLAIMER = (
    "Relevance scores are advisory: they estimate topical relevance to the "
    "objective from titles and abstracts only, and are not evidence strength."
)


def _paper_line(paper: Paper) -> str:
    year = paper.published_at.year
    return (
        f"| {paper.paper_id} | {paper.title} | {year} | "
        f"{paper.relevance_score:.3f} | {paper.evidence_strength.value} |"
    )


def hypothesis_section(hypothesis: Hypothesis) -> list[str]:
    """Public alias used by the engineering report and research package."""
    return _hypothesis_section(hypothesis)


def landscape_sections(
    landscape: ResearchLandscape | None, papers_by_id: dict[str, Paper]
) -> list[str]:
    """Landscape rendering shared by the research and engineering reports."""
    evidence: list[EvidenceClaim] = landscape.evidence if landscape else []
    lines: list[str] = ["## Research landscape", ""]
    if landscape is None:
        lines += ["No landscape has been imported yet.", ""]
        return lines
    lines += [landscape.summary, ""]
    for direction in landscape.directions:
        lines += [
            f"### {direction.direction_id}: {direction.name}",
            "",
            direction.description,
            "",
            "| Paper | Title | Year | Relevance | Evidence strength |",
            "|---|---|---|---|---|",
        ]
        for paper_id in direction.paper_ids:
            paper = papers_by_id.get(paper_id)
            if paper is not None:
                lines.append(_paper_line(paper))
        lines.append("")

        published = [
            e
            for e in evidence
            if e.paper_id in direction.paper_ids and e.evidence_type is EvidenceType.PUBLISHED_CLAIM
        ]
        interpretations = [
            e
            for e in evidence
            if e.paper_id in direction.paper_ids and e.evidence_type is EvidenceType.INTERPRETATION
        ]
        if published:
            lines.append("**Published claims:**")
            lines.extend(
                f"- {e.claim} [{e.paper_id}] (confidence: {e.extraction_confidence.value})"
                for e in published
            )
            lines.append("")
        if interpretations:
            lines.append("**Interpretations (ResearchForge reading):**")
            lines.extend(f"- {e.claim} [{e.paper_id}]" for e in interpretations)
            lines.append("")
        if direction.contradictions:
            lines.append("**Contradictions:**")
            lines.extend(f"- {c}" for c in direction.contradictions)
            lines.append("")
        if direction.limitations:
            lines.append("**Limitations in prior work:**")
            lines.extend(f"- {limitation}" for limitation in direction.limitations)
            lines.append("")
        if direction.underexplored_aspects:
            lines.append("**Underexplored in the reviewed sources:**")
            lines.extend(f"- {aspect}" for aspect in direction.underexplored_aspects)
            lines.append("")
    return lines


def references_section(
    landscape: ResearchLandscape | None,
    hypotheses: list[Hypothesis],
    papers_by_id: dict[str, Paper],
) -> list[str]:
    """References list for every cited paper (shared with the package)."""
    evidence: list[EvidenceClaim] = landscape.evidence if landscape else []
    cited_ids: set[str] = set()
    if landscape is not None:
        for direction in landscape.directions:
            cited_ids.update(direction.paper_ids)
        cited_ids.update(a.paper_id for a in landscape.paper_annotations)
        cited_ids.update(e.paper_id for e in evidence)
    for hypothesis in hypotheses:
        cited_ids.update(hypothesis.supporting_paper_ids)
        cited_ids.update(hypothesis.contradicting_paper_ids)

    lines = ["## References", ""]
    for paper_id in sorted(cited_ids):
        paper = papers_by_id.get(paper_id)
        if paper is None:
            continue
        authors = ", ".join(paper.authors)
        link = paper.pdf_url or paper.source_url
        lines.append(
            f"- **{paper_id}** — {authors}. *{paper.title}* "
            f"({paper.published_at.year}). {', '.join(paper.categories)}. <{link}>"
        )
    if not cited_ids:
        lines.append("No papers cited yet.")
    lines.append("")
    return lines


def _hypothesis_section(hypothesis: Hypothesis) -> list[str]:
    lines = [
        f"### {hypothesis.hypothesis_id}: {hypothesis.title}",
        "",
        f"**Status:** {hypothesis.status.value} · "
        f"**Evidence:** {hypothesis.evidence_status.upper()} · "
        f"**Feasibility:** {hypothesis.feasibility.value} · "
        f"**Effort:** {hypothesis.estimated_effort.value} · "
        f"**Novelty confidence:** {hypothesis.novelty_confidence.value} (not established)",
        "",
        f"**Claim.** {hypothesis.claim}",
        "",
        f"**Rationale.** {hypothesis.rationale}",
        "",
    ]
    if hypothesis.supporting_paper_ids:
        lines.append(f"**Supporting evidence:** {', '.join(hypothesis.supporting_paper_ids)}")
    else:
        lines.append("**Supporting evidence:** none — this hypothesis is UNSUPPORTED.")
    if hypothesis.contradicting_paper_ids:
        lines.append(f"**Contradicting evidence:** {', '.join(hypothesis.contradicting_paper_ids)}")
    lines.append("")
    impact = hypothesis.expected_impact
    lines.append(
        f"**Expected impact:** {impact.metric or 'unspecified metric'} ({impact.direction.value})"
    )
    if hypothesis.repository_observations:
        lines.append("")
        lines.append("**Repository observations:**")
        lines.extend(f"- {obs}" for obs in hypothesis.repository_observations)
    lines.append("")
    lines.append(f"**Proposed experiment.** {hypothesis.proposed_experiment}")
    if hypothesis.limitations:
        lines.append("")
        lines.append("**Limitations:**")
        lines.extend(f"- {limitation}" for limitation in hypothesis.limitations)
    lines.append("")
    return lines


def build_research_report(
    project: Project,
    scan: RepoScan | None,
    landscape: ResearchLandscape | None,
    papers: list[Paper],
    hypotheses: list[Hypothesis],
    search_runs: list[dict[str, object]],
) -> str:
    papers_by_id = {p.paper_id: p for p in papers}
    evidence: list[EvidenceClaim] = landscape.evidence if landscape else []
    lines: list[str] = []

    # 1. Header
    lines += [
        f"# Research Report: {project.name}",
        "",
        f"- **Mode:** {project.mode.value if project.mode else 'unset'}",
        f"- **Objective:** {project.objective or 'unset'}",
        f"- **Generated:** {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"- **ResearchForge version:** {__version__}",
        "",
    ]

    # 2. Methodology & provenance
    lines += ["## Methodology and provenance", ""]
    if search_runs:
        for run in search_runs:
            queries = run["queries"]
            assert isinstance(queries, list)
            lines.append(
                f"- Search run `{run['run_id']}`: {len(queries)} query(ies), "
                f"{run['fetched_count']} fetched, {run['deduped_count']} after "
                f"deduplication, {run['selected_count']} selected."
            )
            lines.extend(f"  - `{q}`" for q in queries)
    else:
        lines.append("- No search runs recorded.")
    lines += ["", RANKING_DISCLAIMER, "", "### How to read this report", "", EPISTEMIC_LEGEND, ""]

    # 3. Repository compatibility (improve mode only)
    if project.mode is ProjectMode.IMPROVE_REPOSITORY and scan is not None:
        lines += [
            "## Repository compatibility",
            "",
            f"- **Repository:** `{scan.repo_path}`",
            f"- **Status:** {scan.compatibility.value}",
        ]
        if scan.git.commit:
            lines.append(f"- **Commit:** `{scan.git.commit}`")
        lines.extend(f"- {reason}" for reason in scan.compatibility_reasons)
        if scan.suggested_editable_paths:
            lines.append(
                f"- **Suggested editable paths:** {', '.join(scan.suggested_editable_paths)}"
            )
        if scan.suggested_protected_paths:
            lines.append(
                f"- **Suggested protected paths:** {', '.join(scan.suggested_protected_paths)}"
            )
        lines.append("")

    # 4. Research landscape
    lines += landscape_sections(landscape, papers_by_id)

    # 5. Hypotheses
    lines += ["## Hypotheses (all speculative until tested)", ""]
    if not hypotheses:
        lines += ["No hypotheses have been imported yet.", ""]
    else:
        for hypothesis in hypotheses:
            lines.extend(_hypothesis_section(hypothesis))

    # 6. Speculation register
    speculations = [e for e in evidence if e.evidence_type is EvidenceType.SPECULATION]
    if speculations:
        lines += ["## Speculation register", ""]
        lines.append(
            "The following claims are speculation: they are not grounded in the "
            "retrieved text and must not be treated as evidence."
        )
        lines.append("")
        lines.extend(f"- {e.claim} [{e.paper_id}]" for e in speculations)
        lines.append("")

    # 7. References
    lines += references_section(landscape, hypotheses, papers_by_id)

    return "\n".join(lines)
