"""`researchforge paper` sub-app."""

from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from researchforge.config.paths import researchforge_dir
from researchforge.reporting.research_package import build_research_package
from researchforge.storage.db import open_project_db
from researchforge.utils.output import JsonOption

paper_app = typer.Typer(name="paper", no_args_is_help=True, help="Research packages.")

PACKAGE_DIR_NAME = "research-output"


@paper_app.command("package")
def package_command(
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            help="Package directory (default: .researchforge/research-output; "
            "pass a path to write elsewhere, e.g. ./research-output).",
        ),
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Generate the research package: report, related work, BibTeX, outline, data."""
    from researchforge.domain.deliverable import Deliverable, DeliverableKind
    from researchforge.storage.deliverable_repository import record_deliverable_once
    from researchforge.storage.paper_repository import list_papers
    from researchforge.storage.project_repository import get_project

    with closing(open_project_db()) as conn:
        project = get_project(conn)
        if project is None or project.objective is None:
            typer.echo("Define the project first: `researchforge project create`.")
            raise typer.Exit(code=1)
        if not list_papers(conn):
            typer.echo("No papers stored — run `researchforge research search` first.")
            raise typer.Exit(code=1)

        target = output or (researchforge_dir() / PACKAGE_DIR_NAME)
        result = build_research_package(conn, target)
        from researchforge.analytics.service import record_event

        record_event("package_generated")
        record_deliverable_once(
            conn,
            project.id,
            Deliverable(
                deliverable_id=uuid4().hex,
                kind=DeliverableKind.RESEARCH_PACKAGE,
                location=str(target),
                created_at=datetime.now(UTC),
            ),
        )

    if json_output:
        typer.echo(json.dumps(result.model_dump(), indent=2))
    else:
        typer.echo(f"Research package written to {result.output_dir}")
        for name in result.files:
            typer.echo(f"  - {name}")
