"""`researchforge report` sub-app."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Annotated

import typer

from researchforge.config.paths import reports_dir
from researchforge.domain.project import ProjectStatus
from researchforge.project.service import touch_project_status
from researchforge.reporting.research_report import build_research_report
from researchforge.storage.db import open_project_db
from researchforge.storage.hypothesis_repository import list_hypotheses
from researchforge.storage.paper_repository import list_papers, list_search_runs
from researchforge.storage.project_repository import get_project
from researchforge.storage.scan_repository import get_latest_scan
from researchforge.storage.synthesis_repository import get_landscape
from researchforge.utils.output import JsonOption

report_app = typer.Typer(name="report", no_args_is_help=True, help="Reports.")

REPORT_FILENAME = "research-report.md"


@report_app.command()
def build(
    output: Annotated[
        Path | None, typer.Option("--output", help="Write the report to this path.")
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Build the research-only Markdown report from stored data."""
    with closing(open_project_db()) as conn:
        project = get_project(conn)
        if project is None or project.objective is None:
            typer.echo("Define the project first: `researchforge project create`.")
            raise typer.Exit(code=1)
        papers = list_papers(conn)
        if not papers:
            typer.echo("No papers stored. Run `researchforge research search` first.")
            raise typer.Exit(code=1)

        markdown = build_research_report(
            project,
            get_latest_scan(conn),
            get_landscape(conn),
            papers,
            list_hypotheses(conn),
            list_search_runs(conn),
        )
        touch_project_status(conn, ProjectStatus.REPORTED)

    path = output or (reports_dir() / REPORT_FILENAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")

    if json_output:
        typer.echo(
            json.dumps({"path": str(path), "bytes": len(markdown.encode("utf-8"))}, indent=2)
        )
    else:
        typer.echo(f"Report written to {path}")
