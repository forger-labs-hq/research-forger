"""`researchforge project` sub-app."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Annotated

import typer

from researchforge.domain.project import Project, ProjectMode
from researchforge.project.service import ProjectExistsError, define_project
from researchforge.storage.db import open_project_db
from researchforge.storage.project_repository import get_project
from researchforge.utils.output import JsonOption, echo_model

project_app = typer.Typer(name="project", no_args_is_help=True, help="Manage the project.")


def _print_project(project: Project, json_output: bool) -> None:
    if json_output:
        echo_model(project)
    else:
        typer.echo(f"Project:   {project.name} ({project.id})")
        typer.echo(f"Mode:      {project.mode.value if project.mode else 'unset'}")
        typer.echo(f"Objective: {project.objective or 'unset'}")
        typer.echo(f"Status:    {project.status.value}")


@project_app.command()
def create(
    mode: Annotated[
        ProjectMode | None,
        typer.Option("--mode", help="improve_repository or explore_research_idea"),
    ] = None,
    objective: Annotated[
        str | None, typer.Option("--objective", help="What should improve or be investigated.")
    ] = None,
    name: Annotated[str | None, typer.Option("--name")] = None,
    repo_path: Annotated[
        Path | None, typer.Option("--repo-path", exists=True, file_okay=False)
    ] = None,
    force_update: Annotated[
        bool, typer.Option("--force-update", help="Overwrite an existing definition.")
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Create (or resume) the ResearchForge project in the current directory."""
    if mode is None:
        raw_mode = typer.prompt(f"Mode ({' | '.join(m.value for m in ProjectMode)})")
        try:
            mode = ProjectMode(raw_mode.strip())
        except ValueError:
            typer.echo(
                f"Invalid mode: {raw_mode!r}. Use one of: {', '.join(m.value for m in ProjectMode)}"
            )
            raise typer.Exit(code=1) from None
    if objective is None:
        objective = typer.prompt("Objective")
    if not objective.strip():
        typer.echo("Objective must not be empty.")
        raise typer.Exit(code=1)

    with closing(open_project_db()) as conn:
        try:
            project = define_project(
                conn,
                mode=mode,
                objective=objective.strip(),
                name=name,
                repo_path=repo_path,
                force_update=force_update,
            )
        except ProjectExistsError as exc:
            _print_project(exc.project, json_output)
            if not json_output:
                typer.echo(
                    "Already defined — resuming. Use --force-update to redefine, "
                    "or run `researchforge status` for next steps."
                )
            return

    _print_project(project, json_output)
    if not json_output:
        next_step = (
            "researchforge repo scan"
            if project.mode is ProjectMode.IMPROVE_REPOSITORY
            else "researchforge research search"
        )
        typer.echo(f"Next: {next_step}")


@project_app.command()
def show(json_output: JsonOption = False) -> None:
    """Show the current project definition."""
    with closing(open_project_db()) as conn:
        project = get_project(conn)
    if project is None:
        typer.echo("No project found. Run `researchforge project create`.")
        raise typer.Exit(code=1)
    _print_project(project, json_output)
