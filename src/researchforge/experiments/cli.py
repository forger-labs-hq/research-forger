"""`researchforge experiment` sub-app (planning surface; run/resume arrive next)."""

from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from researchforge.domain.experiment import (
    Experiment,
    ExperimentStatus,
    PlanApproval,
    PlanStatus,
    advance,
)
from researchforge.experiments.context_export import (
    ExperimentContextError,
    build_experiment_context,
    write_experiment_context,
)
from researchforge.experiments.importers import import_experiment_plan
from researchforge.storage.db import open_project_db
from researchforge.storage.experiment_repository import (
    get_experiment,
    get_plan,
    list_experiments,
    list_plans,
    update_experiment,
    update_plan_status,
)
from researchforge.utils.output import JsonOption, echo_import_result, echo_model

experiment_app = typer.Typer(
    name="experiment", no_args_is_help=True, help="Controlled experiments."
)


@experiment_app.command("plan")
def plan_command(
    hypothesis_id: Annotated[str, typer.Argument(help="e.g. hyp-001")],
    json_output: JsonOption = False,
) -> None:
    """Export the experiment-planning context for a hypothesis."""
    with closing(open_project_db()) as conn:
        try:
            context = build_experiment_context(conn, hypothesis_id)
        except ExperimentContextError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from None

    if json_output:
        echo_model(context)
        return
    path = write_experiment_context(context)
    typer.echo(f"Experiment context written to {path}")
    typer.echo("Ask Claude to read it and write:")
    typer.echo(f"  - {context.expected_artifacts.plan_path}")
    typer.echo(f"  - one unified diff per variant under {context.expected_artifacts.patches_dir}/")
    typer.echo("Then import the plan:")
    typer.echo("  researchforge experiment import .researchforge/experiments/plan.yaml")


@experiment_app.command("import")
def import_command(
    file: Annotated[Path, typer.Argument(help="Experiment plan artifact (plan.yaml).")],
    json_output: JsonOption = False,
) -> None:
    """Validate and import an experiment plan and its patches."""
    with closing(open_project_db()) as conn:
        result, plan = import_experiment_plan(conn, file)
        summary = ""
        if plan is not None:
            experiments = list_experiments(conn, plan.plan_id)
            runnable = sum(1 for e in experiments if e.status is ExperimentStatus.PLANNED)
            rejected = sum(1 for e in experiments if e.status is ExperimentStatus.REJECTED)
            summary = (
                f"Plan {plan.plan_id} imported: {len(experiments)} experiment(s) "
                f"({runnable} runnable, {rejected} rejected). "
                f"Next: researchforge experiment approve {plan.plan_id}"
            )
    echo_import_result(result.errors, result.warnings, summary, json_output)


def _print_experiment(experiment: Experiment) -> None:
    typer.echo(f"[{experiment.experiment_id}] {experiment.title}  ({experiment.status.value})")
    typer.echo(f"Plan:       {experiment.plan_id}   Hypothesis: {experiment.hypothesis_id}")
    typer.echo(f"Change:     {experiment.change_summary}")
    typer.echo(f"Files:      {', '.join(experiment.changed_files) or '(none)'}")
    if experiment.decision is not None:
        typer.echo(
            f"Decision:   {experiment.decision.outcome.value} — {experiment.decision.reason}"
        )
    if experiment.path_violations:
        for violation in experiment.path_violations:
            typer.echo(f"  violation: {violation.path} ({violation.rule.value})")


@experiment_app.command("approve")
def approve_command(
    plan_id: Annotated[str, typer.Argument(help="e.g. plan-001")],
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    json_output: JsonOption = False,
) -> None:
    """Approve a plan's runnable experiments for execution (spec §4.6)."""
    with closing(open_project_db()) as conn:
        plan = get_plan(conn, plan_id)
        if plan is None:
            typer.echo(f"Unknown plan: {plan_id}. See `researchforge experiment list`.")
            raise typer.Exit(code=1)
        if plan.status is not PlanStatus.PLANNED:
            typer.echo(f"{plan_id} is {plan.status.value} — only planned plans can be approved.")
            raise typer.Exit(code=1)

        experiments = list_experiments(conn, plan_id)
        runnable = [e for e in experiments if e.status is ExperimentStatus.PLANNED]

        from researchforge.storage.contract_repository import get_active_contract

        contract = get_active_contract(conn)
        assert contract is not None  # import guaranteed an active contract
        stages = 2 if contract.spec.execution.screening_command else 1
        worst_case_minutes = len(runnable) * contract.spec.execution.timeout_minutes * stages

        if not yes:
            typer.echo(
                f"{plan_id} → {plan.hypothesis_id} · {len(runnable)} runnable experiment(s) "
                f"· worst case ~{worst_case_minutes} min"
            )
            for experiment in runnable:
                files = ", ".join(experiment.changed_files)
                typer.echo(f"  {experiment.experiment_id}  {experiment.title}  [{files}]")
            confirmation = typer.prompt("Type 'approve' to allow these experiments to run")
            if confirmation.strip().lower() != "approve":
                typer.echo("Not approved.")
                raise typer.Exit(code=1)

        approval = PlanApproval(
            approved_at=datetime.now(UTC),
            method="flag" if yes else "typed",
            experiment_ids=[e.experiment_id for e in runnable],
            estimated_max_minutes=worst_case_minutes,
        )
        update_plan_status(conn, plan_id, PlanStatus.APPROVED, approval)
        for experiment in runnable:
            update_experiment(
                conn,
                experiment.model_copy(
                    update={"status": advance(experiment.status, ExperimentStatus.APPROVED)}
                ),
            )

    if json_output:
        typer.echo(json.dumps({"plan_id": plan_id, "approved": approval.experiment_ids}, indent=2))
    else:
        typer.echo(f"Approved {len(approval.experiment_ids)} experiment(s).")
        typer.echo(f"Next: researchforge experiment run {plan_id}")


@experiment_app.command("list")
def list_command(json_output: JsonOption = False) -> None:
    """List plans and their experiments."""
    with closing(open_project_db()) as conn:
        plans = list_plans(conn)
        experiments = list_experiments(conn)
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "plans": [p.model_dump(mode="json") for p in plans],
                    "experiments": [e.model_dump(mode="json") for e in experiments],
                },
                indent=2,
            )
        )
        return
    if not plans:
        typer.echo("No experiment plans. Start with `researchforge experiment plan <hyp-id>`.")
        return
    for plan in plans:
        typer.echo(f"{plan.plan_id}  [{plan.status.value}]  {plan.hypothesis_id}")
        for experiment in (e for e in experiments if e.plan_id == plan.plan_id):
            typer.echo(
                f"  {experiment.experiment_id}  [{experiment.status.value}]  {experiment.title}"
            )


@experiment_app.command("show")
def show_command(
    experiment_id: Annotated[str, typer.Argument(help="e.g. exp-001")],
    json_output: JsonOption = False,
) -> None:
    """Show one experiment in full."""
    with closing(open_project_db()) as conn:
        experiment = get_experiment(conn, experiment_id)
    if experiment is None:
        typer.echo(f"Unknown experiment: {experiment_id}.")
        raise typer.Exit(code=1)
    if json_output:
        echo_model(experiment)
    else:
        _print_experiment(experiment)


@experiment_app.command("cancel")
def cancel_command(
    plan_id: Annotated[str, typer.Argument(help="e.g. plan-001")],
    yes: Annotated[bool, typer.Option("--yes")] = False,
    json_output: JsonOption = False,
) -> None:
    """Cancel a planned/approved plan (its experiments become cancelled)."""
    with closing(open_project_db()) as conn:
        plan = get_plan(conn, plan_id)
        if plan is None:
            typer.echo(f"Unknown plan: {plan_id}.")
            raise typer.Exit(code=1)
        if plan.status not in (PlanStatus.PLANNED, PlanStatus.APPROVED):
            typer.echo(f"{plan_id} is {plan.status.value} — only planned/approved plans cancel.")
            raise typer.Exit(code=1)
        if not yes:
            confirmation = typer.prompt(f"Type 'cancel' to cancel {plan_id}")
            if confirmation.strip().lower() != "cancel":
                raise typer.Exit(code=1)
        update_plan_status(conn, plan_id, PlanStatus.CANCELLED)
        for experiment in list_experiments(conn, plan_id):
            if experiment.status in (ExperimentStatus.PLANNED, ExperimentStatus.APPROVED):
                update_experiment(
                    conn,
                    experiment.model_copy(
                        update={"status": advance(experiment.status, ExperimentStatus.CANCELLED)}
                    ),
                )
    if json_output:
        typer.echo(json.dumps({"plan_id": plan_id, "status": "cancelled"}, indent=2))
    else:
        typer.echo(f"{plan_id} cancelled.")
