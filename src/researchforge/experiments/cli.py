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
results_app = typer.Typer(name="results", no_args_is_help=True, help="Experiment results.")


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


def _emit_summary(summary: object, json_output: bool) -> None:
    from researchforge.analytics.service import record_event
    from researchforge.execution.experiments import RunSummary

    assert isinstance(summary, RunSummary)
    for status, count in summary.counts.items():
        for _ in range(count):
            record_event("experiment_started")
            record_event("experiment_completed", ok=status == "promising", category=status)
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "run_id": summary.run_id,
                    "counts": summary.counts,
                    "promising": summary.promising,
                    "next_action": summary.next_action,
                },
                indent=2,
            )
        )
        return
    typer.echo(f"Run {summary.run_id} complete:")
    for status, count in sorted(summary.counts.items()):
        typer.echo(f"  {status}: {count}")
    if summary.promising:
        typer.echo(f"Promising: {', '.join(summary.promising)}")
    typer.echo(f"Next: {summary.next_action}")


@experiment_app.command("run")
def run_command(
    plan_id: Annotated[str, typer.Argument(help="e.g. plan-001")],
    json_output: JsonOption = False,
) -> None:
    """Run the approved experiments: screening then full benchmark, one at a time."""
    from researchforge.domain.environment import ExecutionEngine
    from researchforge.execution.experiments import (
        ExperimentBlockedError,
        execute_run,
        start_run,
    )
    from researchforge.execution.venv_exec import VENV_WARNING

    with closing(open_project_db()) as conn:
        try:
            prep, run = start_run(conn, plan_id)
        except ExperimentBlockedError as exc:
            typer.echo(str(exc))
            if exc.resolution is not None:
                for reason in exc.resolution.reasons:
                    typer.echo(f"  - {reason}")
                for action in exc.resolution.required_user_actions:
                    typer.echo(f"  * {action}")
            raise typer.Exit(code=1) from None

        if prep.resolution.execution_mode is ExecutionEngine.VENV and not json_output:
            typer.echo(f"warning: {VENV_WARNING}")
        if run.warnings:  # e.g. failed screening baseline
            for warning in run.warnings:
                typer.echo(f"warning: {warning}")
            raise typer.Exit(code=1)

        summary = execute_run(conn, prep, run)
    _emit_summary(summary, json_output)


@experiment_app.command("resume")
def resume_command(
    run_id: Annotated[str, typer.Argument(help="e.g. run-001")],
    json_output: JsonOption = False,
) -> None:
    """Resume an interrupted run: stale stages are marked failed and retried."""
    from researchforge.execution.experiments import ExperimentBlockedError, resume_run

    with closing(open_project_db()) as conn:
        try:
            summary = resume_run(conn, run_id)
        except ExperimentBlockedError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from None
    _emit_summary(summary, json_output)


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


def _format_value(value: float | None) -> str:
    return f"{value:.4g}" if value is not None else "—"


@results_app.command("show")
def results_show_command(
    run_id: Annotated[str, typer.Argument(help="e.g. run-001")],
    json_output: JsonOption = False,
) -> None:
    """Show the ranked results of a run, trade-offs, and rejected history."""
    from researchforge.config.settings import load_settings
    from researchforge.execution.baseline import BaselineBlockedError, baseline_gate
    from researchforge.execution.ranking import build_ranking_report
    from researchforge.storage.contract_repository import get_active_contract
    from researchforge.storage.experiment_repository import get_run, list_executions

    with closing(open_project_db()) as conn:
        run = get_run(conn, run_id)
        if run is None:
            typer.echo(f"Unknown run: {run_id}.")
            raise typer.Exit(code=1)
        contract = get_active_contract(conn)
        if contract is None:
            typer.echo("No approved contract.")
            raise typer.Exit(code=1)
        try:
            baseline = baseline_gate(conn)
        except BaselineBlockedError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from None
        experiments = list_experiments(conn, run.plan_id)
        executions = list_executions(conn, run_id=run_id)
        settings = load_settings()

    report = build_ranking_report(
        run_id,
        baseline,
        experiments,
        executions,
        contract.spec,
        tradeoff_material_pct=settings.tradeoff_material_pct,
    )

    if json_output:
        echo_model(report)
        return

    primary = contract.spec.objective.primary_metric.name
    base = report.baseline_row
    typer.echo(f"Run {run_id} — primary metric: {primary}")
    typer.echo(
        f"  baseline    {primary}={_format_value(base.primary_value)}  "
        + "  ".join(f"{k}={_format_value(v)}" for k, v in base.secondary_values.items())
    )
    for row in report.candidates:
        marker = "*" if row.experiment_id in report.pareto_ids else " "
        delta = f"{row.primary_delta_pct:+.1f}%" if row.primary_delta_pct is not None else "—"
        secondaries = "  ".join(f"{k}={_format_value(v)}" for k, v in row.secondary_values.items())
        typer.echo(
            f"{marker} {row.experiment_id}  [{row.confidence}]  "
            f"{primary}={_format_value(row.primary_value)} ({delta})  {secondaries}"
        )
    if report.single_winner:
        typer.echo(f"Winner: {report.single_winner}")
    elif len(report.pareto_ids) > 1:
        typer.echo(
            f"Pareto frontier (* above): {', '.join(report.pareto_ids)} — choose the "
            "preferred trade-off."
        )
    for note in report.trade_off_notes:
        typer.echo(f"  trade-off: {note}")
    if report.rejected:
        typer.echo("Rejected / failed:")
        for row in report.rejected:
            reason = row.decision.reason if row.decision else row.status.value
            typer.echo(f"  {row.experiment_id}  [{row.status.value}]  {reason}")
    for caveat in report.caveats:
        typer.echo(f"note: {caveat}")


def validate_command(
    run_id: Annotated[str, typer.Argument(help="e.g. run-001")],
    experiment: Annotated[
        list[str] | None,
        typer.Option("--experiment", "-e", help="Validate only these experiment ids."),
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the cost confirmation.")] = False,
    json_output: JsonOption = False,
) -> None:
    """Repeatedly re-run promising finalists to confirm or reject them (Stage 3)."""
    from researchforge.execution.experiments import ExperimentBlockedError
    from researchforge.execution.validation import validate_run
    from researchforge.storage.contract_repository import get_active_contract
    from researchforge.storage.experiment_repository import get_run as get_run_group
    from researchforge.storage.experiment_repository import list_experiments as list_exps

    with closing(open_project_db()) as conn:
        run = get_run_group(conn, run_id)
        contract = get_active_contract(conn)
        if run is not None and contract is not None and not yes:
            targets = [
                e
                for e in list_exps(conn, run.plan_id)
                if e.status is ExperimentStatus.PROMISING
                and (experiment is None or e.experiment_id in experiment)
            ]
            repeats = contract.spec.validation.repeat_finalists
            worst = len(targets) * repeats * contract.spec.execution.timeout_minutes
            typer.echo(
                f"Will re-run the full benchmark {repeats}x for "
                f"{len(targets)} experiment(s) (~{worst} min worst case)."
            )
            confirmation = typer.prompt("Type 'validate' to proceed")
            if confirmation.strip().lower() != "validate":
                typer.echo("Not started.")
                raise typer.Exit(code=1)

        try:
            outcome = validate_run(conn, run_id, experiment_ids=experiment)
        except ExperimentBlockedError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from None

    from researchforge.analytics.service import record_event

    for validated_summary in outcome.summaries:
        record_event(
            "validated_finding",
            ok=validated_summary.outcome is ExperimentStatus.VALIDATED,
            category=validated_summary.outcome.value,
        )
    if json_output:
        typer.echo(json.dumps([s.model_dump(mode="json") for s in outcome.summaries], indent=2))
        return
    for summary in outcome.summaries:
        spread = (
            f"mean {summary.mean:.4g} ± {summary.stdev:.2g}"
            if summary.mean is not None and summary.stdev is not None
            else f"mean {_format_value(summary.mean)}"
        )
        typer.echo(
            f"{summary.experiment_id}: {summary.outcome.value} "
            f"({summary.succeeded_attempts}/{summary.attempts} attempts, {spread})"
        )
    if any(s.outcome is ExperimentStatus.VALIDATED for s in outcome.summaries):
        typer.echo("Next: researchforge ship branch")
