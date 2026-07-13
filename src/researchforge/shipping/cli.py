"""`researchforge ship` sub-app."""

from __future__ import annotations

from contextlib import closing
from typing import Annotated

import typer

from researchforge.shipping.branch import ShipBlockedError, prepare_ship, ship_branch
from researchforge.storage.db import open_project_db
from researchforge.utils.output import JsonOption, echo_model

ship_app = typer.Typer(name="ship", no_args_is_help=True, help="Ship validated findings.")


@ship_app.command("branch")
def branch_command(
    experiment_id: Annotated[
        str | None,
        typer.Argument(help="Experiment to ship (defaults to the unique validated one)."),
    ] = None,
    branch: Annotated[
        str | None, typer.Option("--branch", help="Override the derived branch name.")
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation prompt.")] = False,
    json_output: JsonOption = False,
) -> None:
    """Reconstruct the validated change as a clean local branch (never pushed)."""
    with closing(open_project_db()) as conn:
        if not yes:
            try:
                ship = prepare_ship(conn, experiment_id)
            except ShipBlockedError as exc:
                typer.echo(str(exc))
                raise typer.Exit(code=1) from None
            minutes = ship.prep.contract.spec.execution.timeout_minutes
            typer.echo(
                f"Shipping {ship.experiment.experiment_id} ({ship.experiment.title}) — "
                f"a pre-ship confirmation will re-run the full benchmark (~{minutes} min "
                "worst case), then a clean local branch is created. Nothing is pushed."
            )
            confirmation = typer.prompt("Type 'ship' to proceed")
            if confirmation.strip().lower() != "ship":
                typer.echo("Not shipped.")
                raise typer.Exit(code=1)

        try:
            result = ship_branch(conn, experiment_id, branch=branch)
        except ShipBlockedError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from None

    if json_output:
        echo_model(result)
        return
    typer.echo(f"Branch:    {result.branch}")
    typer.echo(f"Commit:    {result.commit_sha[:12]} (parent {result.baseline_commit[:12]})")
    typer.echo(f"Pre-ship:  primary metric {result.preship_primary_value}")
    typer.echo(f"Changed:   {', '.join(result.changed_files)}")
    typer.echo(
        "Branch created locally. Nothing was pushed. Push with `researchforge ship pr` "
        "(draft, opt-in) or `git push` yourself."
    )
    typer.echo(f"Next: {result.next_action}")
