"""`researchforge repo` sub-app."""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from researchforge.domain.repo_scan import RepoScan
from researchforge.repository.scanner import scan_repository
from researchforge.storage.db import open_project_db
from researchforge.storage.project_repository import get_project, update_project
from researchforge.storage.scan_repository import save_scan
from researchforge.utils.output import JsonOption, echo_model

repo_app = typer.Typer(name="repo", no_args_is_help=True, help="Repository intelligence.")


def _print_scan(scan: RepoScan) -> None:
    typer.echo(f"Repository:    {scan.repo_path}")
    typer.echo(f"Compatibility: {scan.compatibility.value}")
    for reason in scan.compatibility_reasons:
        typer.echo(f"  - {reason}")
    typer.echo(
        f"Git:           {'yes' if scan.git.is_repo else 'no'}"
        + (f" (commit {scan.git.commit[:12]})" if scan.git.commit else "")
    )
    typer.echo(
        f"Python:        {'yes' if scan.python.is_python_project else 'no'}"
        + (f" ({scan.python.package_name})" if scan.python.package_name else "")
    )
    typer.echo(f"Dockerfile:    {'yes' if scan.has_dockerfile else 'no'}")
    if scan.test_candidates:
        typer.echo(f"Tests:         {', '.join(scan.test_candidates)}")
    if scan.benchmark_candidates:
        typer.echo(f"Benchmarks:    {', '.join(scan.benchmark_candidates)}")
    if scan.suggested_editable_paths:
        typer.echo(f"Editable:      {', '.join(scan.suggested_editable_paths)}")
    if scan.suggested_protected_paths:
        typer.echo(f"Protected:     {', '.join(scan.suggested_protected_paths)}")


@repo_app.command()
def scan(
    path: Annotated[
        Path | None,
        typer.Argument(help="Repository to scan (defaults to the project repo path or cwd)."),
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Scan a repository and record its compatibility."""
    with closing(open_project_db()) as conn:
        project = get_project(conn)
        if project is None:
            typer.echo("No project found. Run `researchforge project create` first.")
            raise typer.Exit(code=1)

        target = path or (Path(project.repository.path) if project.repository.path else Path.cwd())
        if not target.is_dir():
            typer.echo(f"Not a directory: {target}")
            raise typer.Exit(code=1)

        result = scan_repository(target)
        save_scan(conn, project.id, result)

        repository = project.repository.model_copy(
            update={
                "path": result.repo_path,
                "remote_url": result.git.remote_url,
                "default_branch": result.git.branch,
            }
        )
        update_project(
            conn,
            project.model_copy(update={"repository": repository, "updated_at": datetime.now(UTC)}),
        )

    if json_output:
        echo_model(result)
    else:
        _print_scan(result)
