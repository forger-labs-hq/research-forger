"""ResearchForge CLI shell."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import typer

from researchforge.config.paths import is_initialized, researchforge_dir
from researchforge.contract.cli import contract_app
from researchforge.domain.project import Project, ProjectMode, ProjectStatus
from researchforge.hypotheses.cli import hypotheses_app
from researchforge.project.cli import project_app
from researchforge.reporting.cli import report_app
from researchforge.repository.cli import repo_app
from researchforge.research.cli import papers_app, research_app
from researchforge.storage.db import open_project_db
from researchforge.storage.project_repository import get_project, insert_project
from researchforge.utils.output import JsonOption, echo_model
from researchforge.utils.system_checks import run_all_checks

app = typer.Typer(
    name="researchforge",
    no_args_is_help=True,
    add_completion=False,
    help="From papers to proof.",
)

app.add_typer(project_app, name="project")
app.add_typer(repo_app, name="repo")
app.add_typer(research_app, name="research")
app.add_typer(papers_app, name="papers")
app.add_typer(hypotheses_app, name="hypotheses")
app.add_typer(report_app, name="report")
app.add_typer(contract_app, name="contract")


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
    with closing(open_project_db()) as conn:
        insert_project(conn, project)

    if json_output:
        echo_model(project)
    else:
        typer.echo(f"Initialized ResearchForge project '{project.name}' in {researchforge_dir()}")


_COUNT_QUERIES = {
    "papers": "SELECT COUNT(*) AS n FROM papers",
    "hypotheses": "SELECT COUNT(*) AS n FROM hypotheses",
    "landscape": "SELECT COUNT(*) AS n FROM landscape",
}


def _count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(_COUNT_QUERIES[table]).fetchone()
    return int(row["n"])


def _next_action(
    project: Project,
    papers: int,
    hypotheses: int,
    landscape: int,
    *,
    contract_version: int | None,
    contract_drifted: bool,
) -> str:
    if project.mode is None or project.objective is None:
        return "researchforge project create"
    if project.mode is ProjectMode.IMPROVE_REPOSITORY and project.repository.path is None:
        return "researchforge repo scan"
    if papers == 0:
        return "researchforge research search"
    if landscape == 0 or hypotheses == 0:
        return (
            "researchforge research context — then ask Claude to write the synthesis "
            "artifacts and import them"
        )
    if project.status not in (
        ProjectStatus.REPORTED,
        ProjectStatus.CONTRACTED,
        ProjectStatus.BASELINED,
    ):
        return "researchforge report build"
    if project.mode is ProjectMode.IMPROVE_REPOSITORY:
        if contract_version is None:
            return "researchforge contract generate"
        if contract_drifted:
            return "researchforge contract approve  # researchforge.yaml changed since approval"
        if project.status is not ProjectStatus.BASELINED:
            return "researchforge baseline run"
        return "Phase 1B complete — experiment engine arrives in Phase 1C."
    return "Research complete — report generated. Attach a repository to run experiments."


@app.command()
def status(json_output: JsonOption = False) -> None:
    """Show the status of the current ResearchForge project."""
    from researchforge.config.paths import contract_path
    from researchforge.contract.service import check_contract_drift
    from researchforge.storage.contract_repository import get_active_contract

    if not is_initialized():
        typer.echo("Not an initialized ResearchForge project. Run `researchforge init`.")
        raise typer.Exit(code=1)

    with closing(open_project_db()) as conn:
        project = get_project(conn)
        if project is None:
            typer.echo("Project database exists but no project record was found.")
            raise typer.Exit(code=1)
        papers = _count(conn, "papers")
        hypotheses = _count(conn, "hypotheses")
        landscape = _count(conn, "landscape")
        contract = get_active_contract(conn)
        repo_root = Path(project.repository.path) if project.repository.path else Path.cwd()
        drifted = check_contract_drift(conn, contract_path(repo_root))

    next_action = _next_action(
        project,
        papers,
        hypotheses,
        landscape,
        contract_version=contract.contract_version if contract else None,
        contract_drifted=drifted,
    )

    if json_output:
        payload = project.model_dump(mode="json")
        payload["counts"] = {"papers": papers, "hypotheses": hypotheses, "landscape": landscape}
        payload["contract_version"] = contract.contract_version if contract else None
        payload["contract_drifted"] = drifted
        payload["next_action"] = next_action
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(f"Name:       {project.name}")
        typer.echo(f"Mode:       {project.mode.value if project.mode else 'unset'}")
        typer.echo(f"Objective:  {project.objective or 'unset'}")
        typer.echo(f"Status:     {project.status.value}")
        typer.echo(f"Papers:     {papers}")
        typer.echo(f"Hypotheses: {hypotheses}")
        if contract is not None:
            drift_note = " (drifted — re-approve)" if drifted else ""
            typer.echo(f"Contract:   v{contract.contract_version}{drift_note}")
        typer.echo(f"Created:    {project.created_at.isoformat()}")
        typer.echo(f"Updated:    {project.updated_at.isoformat()}")
        typer.echo(f"Next:       {next_action}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
