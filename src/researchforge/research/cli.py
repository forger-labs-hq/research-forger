"""`researchforge research` and `researchforge papers` sub-apps."""

from __future__ import annotations

import json
from contextlib import closing
from typing import Annotated

import typer

from researchforge.config.settings import load_settings
from researchforge.domain.paper import Paper
from researchforge.research.arxiv_client import ArxivClient, ArxivError
from researchforge.research.search_service import CitedPapersError, run_search
from researchforge.storage.db import open_project_db
from researchforge.storage.paper_repository import get_paper, list_papers
from researchforge.storage.project_repository import get_project
from researchforge.storage.scan_repository import get_latest_scan
from researchforge.utils.output import JsonOption, echo_model

research_app = typer.Typer(name="research", no_args_is_help=True, help="Paper discovery.")
papers_app = typer.Typer(name="papers", no_args_is_help=True, help="Stored paper records.")


@research_app.command()
def search(
    query: Annotated[
        list[str] | None,
        typer.Option("--query", "-q", help="Search query (repeatable). Omit to auto-generate."),
    ] = None,
    max_candidates: Annotated[int | None, typer.Option("--max-candidates", min=10)] = None,
    select: Annotated[int | None, typer.Option("--select", min=1)] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Replace papers already cited by hypotheses.")
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Discover, deduplicate, rank, and store relevant arXiv papers."""
    with closing(open_project_db()) as conn:
        project = get_project(conn)
        if project is None or project.objective is None:
            typer.echo("Define the project first: `researchforge project create`.")
            raise typer.Exit(code=1)
        scan = get_latest_scan(conn)
        settings = load_settings()
        if max_candidates is not None:
            settings = settings.model_copy(update={"max_candidates": max_candidates})

        try:
            outcome = run_search(
                conn,
                project,
                scan,
                queries=query,
                settings=settings,
                client=ArxivClient(),
                select=select,
                force=force,
            )
        except CitedPapersError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from None
        except ArxivError as exc:
            typer.echo(f"arXiv retrieval failed: {exc}")
            raise typer.Exit(code=1) from None

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "run_id": outcome.run_id,
                    "queries": outcome.queries,
                    "fetched_count": outcome.fetched_count,
                    "deduped_count": outcome.deduped_count,
                    "selected_count": len(outcome.selected),
                    "papers": [p.model_dump(mode="json") for p in outcome.selected],
                },
                indent=2,
            )
        )
    else:
        typer.echo(f"Queries ({len(outcome.queries)}):")
        for q in outcome.queries:
            typer.echo(f"  - {q}")
        typer.echo(
            f"Fetched {outcome.fetched_count}, deduplicated to {outcome.deduped_count}, "
            f"selected {len(outcome.selected)}."
        )
        for paper in outcome.selected[:10]:
            typer.echo(f"  {paper.relevance_score:.3f}  {paper.paper_id}  {paper.title[:70]}")
        if len(outcome.selected) > 10:
            typer.echo(f"  ... and {len(outcome.selected) - 10} more (`researchforge papers list`)")
        typer.echo("Next: researchforge research context")


def _print_paper(paper: Paper) -> None:
    typer.echo(f"{paper.paper_id}  (relevance {paper.relevance_score:.3f})")
    typer.echo(f"Title:      {paper.title}")
    typer.echo(f"Authors:    {', '.join(paper.authors)}")
    typer.echo(f"Published:  {paper.published_at.date().isoformat()}")
    typer.echo(f"Categories: {', '.join(paper.categories)}")
    typer.echo(f"Link:       {paper.source_url}")
    if paper.method_summary:
        typer.echo(f"Method:     {paper.method_summary}")
    if paper.evidence_strength.value != "unknown":
        typer.echo(f"Evidence:   {paper.evidence_strength.value}")
    for finding in paper.reported_findings:
        typer.echo(f"  finding:    {finding}")
    for limitation in paper.limitations:
        typer.echo(f"  limitation: {limitation}")
    if paper.repository_relevance:
        typer.echo(f"Repo relevance: {paper.repository_relevance}")
    if paper.supports_hypotheses:
        typer.echo(f"Supports:   {', '.join(paper.supports_hypotheses)}")
    if paper.contradicts_hypotheses:
        typer.echo(f"Contradicts: {', '.join(paper.contradicts_hypotheses)}")
    typer.echo(f"Abstract:   {paper.abstract[:400]}{'…' if len(paper.abstract) > 400 else ''}")


@papers_app.command("list")
def list_command(
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    json_output: JsonOption = False,
) -> None:
    """List stored papers ordered by relevance."""
    with closing(open_project_db()) as conn:
        papers = list_papers(conn, limit=limit)
    if json_output:
        typer.echo(json.dumps([p.model_dump(mode="json") for p in papers], indent=2))
        return
    if not papers:
        typer.echo("No papers stored. Run `researchforge research search` first.")
        return
    for paper in papers:
        typer.echo(f"{paper.relevance_score:.3f}  {paper.paper_id}  {paper.title[:80]}")


@papers_app.command("show")
def show_command(
    paper_id: Annotated[str, typer.Argument(help="e.g. arxiv:2401.12345")],
    json_output: JsonOption = False,
) -> None:
    """Show one stored paper in full."""
    with closing(open_project_db()) as conn:
        paper = get_paper(conn, paper_id)
    if paper is None:
        typer.echo(f"Unknown paper id: {paper_id}. See `researchforge papers list`.")
        raise typer.Exit(code=1)
    if json_output:
        echo_model(paper)
    else:
        _print_paper(paper)
