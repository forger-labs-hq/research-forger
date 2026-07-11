"""ResearchForge CLI shell: `doctor`, `init`, `status`."""

from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from researchforge.config.paths import db_path, is_initialized, researchforge_dir
from researchforge.domain.project import Project, ProjectStatus
from researchforge.storage.db import get_connection, initialize_schema
from researchforge.storage.project_repository import get_project, insert_project
from researchforge.utils.system_checks import run_all_checks

app = typer.Typer(
    name="researchforge",
    no_args_is_help=True,
    add_completion=False,
    help="From papers to proof.",
)

JsonOption = Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON output.")]


@app.command()
def doctor(json_output: JsonOption = False) -> None:
    """Check that required and optional dependencies are available."""
    results = run_all_checks()

    if json_output:
        typer.echo(json.dumps([r.model_dump() for r in results], indent=2))
    else:
        for result in results:
            marker = "✓" if result.ok else ("✗" if result.required else "-")
            typer.echo(f"{marker} {result.name}: {result.detail}")
            if not result.ok and result.hint:
                typer.echo(f"    hint: {result.hint}")

    if any(not result.ok and result.required for result in results):
        raise typer.Exit(code=1)


@app.command()
def init(json_output: JsonOption = False) -> None:
    """Initialize a ResearchForge project in the current directory."""
    if is_initialized():
        if json_output:
            typer.echo(json.dumps({"status": "already_initialized"}))
        else:
            typer.echo("Already initialized.")
        return

    researchforge_dir().mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    project = Project(
        id=uuid4().hex,
        name=Path.cwd().name,
        status=ProjectStatus.INITIALIZED,
        created_at=now,
        updated_at=now,
    )
    with closing(get_connection(db_path())) as conn:
        initialize_schema(conn)
        insert_project(conn, project)

    if json_output:
        typer.echo(project.model_dump_json(indent=2))
    else:
        typer.echo(f"Initialized ResearchForge project '{project.name}' in {researchforge_dir()}")


@app.command()
def status(json_output: JsonOption = False) -> None:
    """Show the status of the current ResearchForge project."""
    if not is_initialized():
        typer.echo("Not an initialized ResearchForge project. Run `researchforge init`.")
        raise typer.Exit(code=1)

    with closing(get_connection(db_path())) as conn:
        project = get_project(conn)
    if project is None:
        typer.echo("Project database exists but no project record was found.")
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(project.model_dump_json(indent=2))
    else:
        typer.echo(f"Name:      {project.name}")
        typer.echo(f"Mode:      {project.mode.value if project.mode else 'unset'}")
        typer.echo(f"Objective: {project.objective or 'unset'}")
        typer.echo(f"Status:    {project.status.value}")
        typer.echo(f"Created:   {project.created_at.isoformat()}")
        typer.echo(f"Updated:   {project.updated_at.isoformat()}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
