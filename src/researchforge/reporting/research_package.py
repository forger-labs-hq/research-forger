"""Research package builder (spec: research contribution outcome).

Every file is rendered from stored records only. Sections without recorded
data say so instead of inventing content; the no-novelty conventions from
the research report apply throughout.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path

from pydantic import BaseModel

from researchforge.domain.baseline import BaselineRun
from researchforge.domain.contract import ExperimentContract
from researchforge.domain.experiment import (
    Experiment,
    ExperimentExecution,
    ExperimentPlan,
    ExperimentStatus,
)
from researchforge.domain.hypothesis import Hypothesis
from researchforge.domain.landscape import ResearchLandscape
from researchforge.domain.paper import Paper
from researchforge.domain.project import Project
from researchforge.reporting.engineering_report import reproduction_steps
from researchforge.reporting.research_report import (
    EPISTEMIC_LEGEND,
    build_research_report,
    hypothesis_section,
)


class PackageResult(BaseModel):
    output_dir: str
    files: list[str]


def _bib_escape(text: str) -> str:
    return text.replace("{", "\\{").replace("}", "\\}")


def render_bibtex(papers: list[Paper], cited_ids: set[str]) -> str:
    """Hand-rendered BibTeX @misc entries for the cited arXiv papers."""
    entries = []
    for paper in sorted(papers, key=lambda p: p.paper_id):
        if paper.paper_id not in cited_ids:
            continue
        eprint = paper.paper_id.removeprefix("arxiv:")
        key = f"arxiv_{eprint.replace('.', '_')}"
        authors = " and ".join(paper.authors) or "Unknown"
        primary_class = paper.categories[0] if paper.categories else "cs.LG"
        entries.append(
            "\n".join(
                [
                    f"@misc{{{key},",
                    f"  title         = {{{_bib_escape(paper.title)}}},",
                    f"  author        = {{{_bib_escape(authors)}}},",
                    f"  year          = {{{paper.published_at.year}}},",
                    f"  eprint        = {{{eprint}}},",
                    "  archivePrefix = {arXiv},",
                    f"  primaryClass  = {{{primary_class}}},",
                    f"  url           = {{{paper.pdf_url or paper.source_url}}}",
                    "}",
                ]
            )
        )
    return "\n\n".join(entries) + ("\n" if entries else "% No cited papers recorded.\n")


def render_related_work(landscape: ResearchLandscape | None, papers: list[Paper]) -> str:
    papers_by_id = {p.paper_id: p for p in papers}
    lines = ["# Related work", ""]
    if landscape is None:
        lines += ["No research landscape has been imported.", ""]
        return "\n".join(lines)
    for direction in landscape.directions:
        lines += [f"## {direction.name}", "", direction.description, ""]
        for paper_id in direction.paper_ids:
            paper = papers_by_id.get(paper_id)
            if paper is None:
                continue
            lines.append(f"### {paper.title} ({paper_id})")
            lines.append("")
            if paper.method_summary:
                lines.append(f"**Method.** {paper.method_summary}")
            for finding in paper.reported_findings:
                lines.append(f"- Reported: {finding}")
            for limitation in paper.limitations:
                lines.append(f"- Limitation: {limitation}")
            lines.append("")
    return "\n".join(lines)


def render_evidence_matrix(
    landscape: ResearchLandscape | None, papers: list[Paper]
) -> list[list[str]]:
    papers_by_id = {p.paper_id: p for p in papers}
    rows: list[list[str]] = [
        ["paper_id", "title", "year", "claim", "evidence_type", "extraction_confidence"]
    ]
    if landscape is None:
        return rows
    for claim in landscape.evidence:
        paper = papers_by_id.get(claim.paper_id)
        rows.append(
            [
                claim.paper_id,
                paper.title if paper else "",
                str(paper.published_at.year) if paper else "",
                claim.claim,
                claim.evidence_type.value,
                claim.extraction_confidence.value,
            ]
        )
    return rows


def render_methodology(contract: ExperimentContract, baseline: BaselineRun) -> str:
    spec = contract.spec
    lines = [
        "# Methodology",
        "",
        "All measurements follow the approved experiment contract "
        f"(`{contract.contract_id}` v{contract.contract_version}).",
        "",
        f"- Primary metric: {spec.objective.primary_metric.name} "
        f"({spec.objective.primary_metric.direction.value})",
    ]
    for constraint in spec.objective.hard_constraints:
        lines.append(
            f"- Hard constraint: {constraint.name} {constraint.operator.value} {constraint.value}"
        )
    lines += [
        f"- Evaluation command: `{spec.execution.full_command}`",
        f"- Result file: `{spec.execution.result_file}` (schema v1)",
    ]
    if spec.execution.screening_command:
        lines.append(f"- Screening subset: `{spec.execution.screening_command}`")
    lines += [
        f"- Validation policy: {spec.validation.repeat_finalists} repeated finalist run(s), "
        "fresh environment per attempt",
        f"- Baseline commit: `{contract.baseline_commit}`",
        f"- Environment: {baseline.execution_mode.value}, {baseline.fingerprint.platform}",
        "",
    ]
    return "\n".join(lines)


def render_limitations(
    hypotheses: list[Hypothesis],
    landscape: ResearchLandscape | None,
    baseline: BaselineRun,
    repeat_finalists: int,
) -> str:
    lines = ["# Limitations", ""]
    for hypothesis in hypotheses:
        for limitation in hypothesis.limitations:
            lines.append(f"- {limitation}")
    if landscape is not None:
        for direction in landscape.directions:
            for limitation in direction.limitations:
                lines.append(f"- Prior work: {limitation}")
    lines += [
        f"- All results come from a single machine in {baseline.execution_mode.value} mode "
        f"with n={repeat_finalists} validation repeats; statistical power is limited.",
        "- Screening-stage numbers use a reduced subset and are not comparable to "
        "full-benchmark numbers.",
        "- No novelty guarantee: 'underexplored' means not found in the retrieved "
        "literature, not absent from all literature.",
        "",
    ]
    return "\n".join(lines)


def render_paper_outline(
    project: Project,
    landscape: ResearchLandscape | None,
    hypotheses: list[Hypothesis],
    contract: ExperimentContract,
    experiments: list[Experiment],
    executions: list[ExperimentExecution],
) -> str:
    """The spec's 13-section outline, populated from recorded data only."""
    spec = contract.spec
    primary = spec.objective.primary_metric.name
    todo = "*(No recorded data — to be completed by the author.)*"
    validated = [
        e
        for e in experiments
        if e.status in (ExperimentStatus.VALIDATED, ExperimentStatus.IMPLEMENTATION_READY)
    ]

    lines = ["# Paper outline", ""]
    lines += ["## 1. Proposed title options", ""]
    for hypothesis in hypotheses[:3]:
        lines.append(f"- {hypothesis.title} *(placeholder — author to revise)*")
    if not hypotheses:
        lines.append(todo)
    lines += ["", "## 2. Problem statement", "", spec.objective.description.strip(), ""]
    lines += ["## 3. Research question", ""]
    lines += [project.objective or todo, ""]
    lines += ["## 4. Related work", "", "See `related_work.md`.", ""]
    lines += ["## 5. Identified gap", ""]
    gaps = [
        aspect
        for direction in (landscape.directions if landscape else [])
        for aspect in direction.underexplored_aspects
    ]
    lines += [*(f"- {gap}" for gap in gaps)] if gaps else [todo]
    lines += ["", "## 6. Proposed method", ""]
    lines += (
        [f"- {e.experiment_id}: {e.change_summary}" for e in validated] if validated else [todo]
    )
    lines += ["", "## 7. Experimental setup", "", "See `methodology.md`.", ""]
    lines += ["## 8. Results", ""]
    fulls = [e for e in executions if e.benchmark_stage.value in ("full", "validation")]
    if fulls:
        lines.append("Recorded measurements only (see `experiments/results.csv`):")
        for execution in fulls:
            if execution.metrics is not None:
                lines.append(
                    f"- {execution.experiment_id} [{execution.benchmark_stage.value} "
                    f"a{execution.attempt}]: {primary}={execution.metrics.primary_metric.value}"
                )
    else:
        lines.append(todo)
    lines += ["", "## 9. Ablations", "", "Not run in Phase 1 — see `results.csv` for raw data.", ""]
    lines += ["## 10. Discussion", "", todo, ""]
    lines += ["## 11. Limitations", "", "See `limitations.md`.", ""]
    lines += ["## 12. Future work", ""]
    validated_hypothesis_ids = {e.hypothesis_id for e in validated}
    unvalidated = [h for h in hypotheses if h.hypothesis_id not in validated_hypothesis_ids]
    lines += [f"- {h.hypothesis_id}: {h.title}" for h in unvalidated] or [todo]
    lines += ["", "## 13. Citation mapping", ""]
    lines += ["See `citations.bib` and `evidence_matrix.csv`.", ""]
    return "\n".join(lines)


def render_reproducibility(
    contract: ExperimentContract,
    baseline: BaselineRun,
    plans: list[ExperimentPlan],
    experiments: list[Experiment],
) -> str:
    lines = [
        "# Reproducibility",
        "",
        "## Commands",
        "",
        "```bash",
        *reproduction_steps(contract, plans),
        "```",
        "",
        "## Fixed points",
        "",
        f"- Baseline commit: `{contract.baseline_commit}`",
        f"- Contract: `{contract.contract_id}` v{contract.contract_version} "
        f"(sha256 `{contract.source_sha256[:16]}…`)",
        f"- Environment fingerprint: {baseline.fingerprint.model_dump_json()}",
        "",
        "## Experiment patches (sha256)",
        "",
    ]
    for experiment in experiments:
        lines.append(f"- {experiment.experiment_id}: `{experiment.patch_sha256}`")
    lines += [
        "",
        "Patches: `.researchforge/artifacts/experiments/<plan>/<exp>/change.patch`.",
        "",
    ]
    return "\n".join(lines)


def render_results_csv(
    executions: list[ExperimentExecution], contract: ExperimentContract
) -> list[list[str]]:
    secondary_names = sorted(
        {
            name
            for execution in executions
            if execution.metrics is not None
            for name in execution.metrics.secondary_metrics
        }
    )
    header = [
        "experiment_id",
        "stage",
        "attempt",
        "status",
        contract.spec.objective.primary_metric.name,
        *secondary_names,
        "constraints_ok",
        "duration_seconds",
    ]
    rows = [header]
    for execution in executions:
        primary_value = (
            str(execution.metrics.primary_metric.value) if execution.metrics is not None else ""
        )
        secondary_values = [
            str(execution.metrics.secondary_metrics.get(name, ""))
            if execution.metrics is not None
            else ""
            for name in secondary_names
        ]
        constraints_ok = (
            str(all(c.passed is not False for c in execution.constraints))
            if execution.constraints
            else ""
        )
        rows.append(
            [
                execution.experiment_id,
                execution.benchmark_stage.value,
                str(execution.attempt),
                execution.status.value,
                primary_value,
                *secondary_values,
                constraints_ok,
                f"{execution.duration_seconds:.2f}",
            ]
        )
    return rows


def render_rejected(experiments: list[Experiment]) -> str:
    lines = [
        "# Rejected experiments",
        "",
        "Negative results, preserved so they are not repeated (spec §4.5).",
        "",
    ]
    rejected = [
        e
        for e in experiments
        if e.status
        in (
            ExperimentStatus.REJECTED,
            ExperimentStatus.FAILED_SETUP,
            ExperimentStatus.FAILED_EXECUTION,
            ExperimentStatus.CANCELLED,
        )
    ]
    if not rejected:
        lines.append("None recorded.")
    for experiment in rejected:
        reason = experiment.decision.reason if experiment.decision else experiment.status.value
        lines += [
            f"## {experiment.experiment_id} — {experiment.title}",
            "",
            f"- Change: {experiment.change_summary}",
            f"- Files: {', '.join(experiment.changed_files) or '(none)'}",
            f"- Outcome: {experiment.status.value}",
            f"- Reason: {reason}",
            "",
        ]
    return "\n".join(lines)


def render_hypotheses(hypotheses: list[Hypothesis]) -> str:
    lines = ["# Hypotheses", "", EPISTEMIC_LEGEND, ""]
    if not hypotheses:
        lines.append("None recorded.")
    for hypothesis in hypotheses:
        lines.extend(hypothesis_section(hypothesis))
    return "\n".join(lines)


def _csv_text(rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue()


def build_research_package(conn: sqlite3.Connection, output_dir: Path) -> PackageResult:
    """Assemble the research-output directory from stored records."""
    from researchforge.storage.baseline_repository import get_latest_successful_baseline
    from researchforge.storage.contract_repository import get_active_contract
    from researchforge.storage.experiment_repository import (
        list_executions,
        list_experiments,
        list_plans,
    )
    from researchforge.storage.hypothesis_repository import list_hypotheses
    from researchforge.storage.paper_repository import (
        cited_paper_ids,
        list_papers,
        list_search_runs,
    )
    from researchforge.storage.project_repository import get_project
    from researchforge.storage.scan_repository import get_latest_scan
    from researchforge.storage.synthesis_repository import get_landscape

    project = get_project(conn)
    assert project is not None
    landscape = get_landscape(conn)
    papers = list_papers(conn)
    hypotheses = list_hypotheses(conn)
    contract = get_active_contract(conn)
    baseline = get_latest_successful_baseline(conn)
    plans = list_plans(conn)
    experiments = list_experiments(conn)
    executions = list_executions(conn)

    cited = cited_paper_ids(conn)
    if landscape is not None:
        for direction in landscape.directions:
            cited.update(direction.paper_ids)
        cited.update(e.paper_id for e in landscape.evidence)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "experiments").mkdir(exist_ok=True)
    (output_dir / "figures").mkdir(exist_ok=True)

    files: dict[str, str] = {
        "research_report.md": build_research_report(
            project, get_latest_scan(conn), landscape, papers, hypotheses, list_search_runs(conn)
        ),
        "related_work.md": render_related_work(landscape, papers),
        "evidence_matrix.csv": _csv_text(render_evidence_matrix(landscape, papers)),
        "citations.bib": render_bibtex(papers, cited),
        "hypotheses.md": render_hypotheses(hypotheses),
        "figures/README.md": (
            "# Figures\n\nCharts are a Should-Have and are not generated in Phase 1. "
            "`../experiments/results.csv` contains the plottable data.\n"
        ),
    }

    if contract is not None and baseline is not None:
        repeat = contract.spec.validation.repeat_finalists
        files["methodology.md"] = render_methodology(contract, baseline)
        files["limitations.md"] = render_limitations(hypotheses, landscape, baseline, repeat)
        files["paper_outline.md"] = render_paper_outline(
            project, landscape, hypotheses, contract, experiments, executions
        )
        files["reproducibility.md"] = render_reproducibility(contract, baseline, plans, experiments)
        files["experiments/results.csv"] = _csv_text(render_results_csv(executions, contract))
        files["experiments/rejected_experiments.md"] = render_rejected(experiments)
        files["experiments/run_manifest.json"] = json.dumps(
            [e.model_dump(mode="json") for e in executions], indent=2
        )
    else:
        files["methodology.md"] = (
            "# Methodology\n\nNo approved experiment contract — this project is "
            "research-only. See `research_report.md` for the recommended methodology.\n"
        )
        files["limitations.md"] = (
            "# Limitations\n\n- No experiments were executed; every hypothesis remains "
            "speculative.\n- No novelty guarantee: 'underexplored' means not found in "
            "the retrieved literature.\n"
        )
        files["paper_outline.md"] = (
            "# Paper outline\n\nNo recorded experiments — outline generation requires "
            "an approved contract and baseline. See `research_report.md`.\n"
        )
        files["reproducibility.md"] = (
            "# Reproducibility\n\nNo experiments recorded. The research landscape can "
            "be reproduced with `researchforge research search` using the queries in "
            "`research_report.md`.\n"
        )
        files["experiments/results.csv"] = ""
        files["experiments/rejected_experiments.md"] = "# Rejected experiments\n\nNone recorded.\n"
        files["experiments/run_manifest.json"] = "[]"

    for relative, content in files.items():
        target = output_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    return PackageResult(output_dir=str(output_dir), files=sorted(files))
