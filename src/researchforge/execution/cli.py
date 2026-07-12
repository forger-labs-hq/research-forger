"""`researchforge baseline` sub-app."""

from __future__ import annotations

from contextlib import closing

import typer

from researchforge.domain.baseline import BaselineRun, BaselineStatus
from researchforge.domain.environment import EnvironmentResolution, ExecutionEngine
from researchforge.execution.baseline import (
    BaselineBlockedError,
    prepare_baseline,
    run_baseline,
)
from researchforge.execution.venv_exec import VENV_WARNING
from researchforge.storage.baseline_repository import get_latest_baseline
from researchforge.storage.db import open_project_db
from researchforge.utils.output import JsonOption, echo_model

baseline_app = typer.Typer(name="baseline", no_args_is_help=True, help="Baseline runs.")


def _print_resolution(resolution: EnvironmentResolution) -> None:
    typer.echo(f"Status:         {resolution.status.value}")
    typer.echo(f"Execution mode: {resolution.execution_mode.value}")
    for reason in resolution.reasons:
        typer.echo(f"  - {reason}")
    if resolution.required_user_actions:
        typer.echo("Required actions:")
        for action in resolution.required_user_actions:
            typer.echo(f"  * {action}")


def _print_run(run: BaselineRun) -> None:
    typer.echo(f"Baseline:  {run.baseline_id}")
    typer.echo(f"Status:    {run.status.value}")
    typer.echo(f"Mode:      {run.execution_mode.value}")
    typer.echo(f"Commit:    {run.commit_sha[:12]}")
    typer.echo(f"Contract:  v{run.contract_version}")
    typer.echo(f"Duration:  {run.duration_seconds:.1f}s")
    if run.metrics is not None:
        typer.echo(
            f"Metric:    {run.metrics.primary_metric.name} = {run.metrics.primary_metric.value}"
        )
        for name, value in run.metrics.secondary_metrics.items():
            typer.echo(f"           {name} = {value}")
    if run.failure_reason:
        typer.echo(f"Failure:   {run.failure_reason}")
    for warning in run.warnings:
        typer.echo(f"warning: {warning}")
    typer.echo(f"Artifacts: {run.stdout_path.rsplit('/', 1)[0]}")


@baseline_app.command()
def run(
    check: bool = typer.Option(  # noqa: B008
        False, "--check", help="Resolve the environment and stop (no execution)."
    ),
    json_output: JsonOption = False,
) -> None:
    """Run the baseline in an isolated worktree and store the result."""
    with closing(open_project_db()) as conn:
        try:
            prep = prepare_baseline(conn)
        except BaselineBlockedError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from None

        if check:
            if json_output:
                echo_model(prep.resolution)
            else:
                _print_resolution(prep.resolution)
            raise typer.Exit(code=0 if prep.resolution.execution_mode.value != "none" else 1)

        if prep.resolution.execution_mode is ExecutionEngine.VENV and not json_output:
            typer.echo(f"warning: {VENV_WARNING}")

        try:
            result = run_baseline(conn)
        except BaselineBlockedError as exc:
            if exc.resolution is not None:
                if json_output:
                    echo_model(exc.resolution)
                else:
                    _print_resolution(exc.resolution)
            else:
                typer.echo(str(exc))
            raise typer.Exit(code=1) from None

    if json_output:
        echo_model(result)
    else:
        _print_run(result)
        if result.status is BaselineStatus.SUCCEEDED:
            typer.echo("Baseline established. Experiments arrive in Phase 1C.")
        else:
            typer.echo("Baseline failed — experiments are blocked until it succeeds.")
    if result.status is not BaselineStatus.SUCCEEDED:
        raise typer.Exit(code=1)


@baseline_app.command()
def show(json_output: JsonOption = False) -> None:
    """Show the latest baseline run."""
    with closing(open_project_db()) as conn:
        latest = get_latest_baseline(conn)
    if latest is None:
        typer.echo("No baseline has been run. Run `researchforge baseline run`.")
        raise typer.Exit(code=1)
    if json_output:
        echo_model(latest)
    else:
        _print_run(latest)
