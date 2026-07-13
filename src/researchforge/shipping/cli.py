"""`researchforge ship` sub-app."""

from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from researchforge.shipping.branch import ShipBlockedError, prepare_ship, ship_branch
from researchforge.shipping.gh import GhClient, GhError
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


@ship_app.command("pr")
def pr_command(
    experiment_id: Annotated[
        str | None,
        typer.Argument(help="Shipped experiment (defaults to the latest shipped branch)."),
    ] = None,
    base: Annotated[str | None, typer.Option("--base", help="PR base branch.")] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the push confirmation.")] = False,
    json_output: JsonOption = False,
) -> None:
    """Push the shipped branch and open a DRAFT pull request (opt-in twice)."""
    from researchforge.domain.deliverable import Deliverable, DeliverableKind
    from researchforge.domain.experiment import BenchmarkStage
    from researchforge.execution.validation import summarize_validation
    from researchforge.shipping.pr_body import build_pr_body, build_pr_title
    from researchforge.storage.baseline_repository import get_latest_successful_baseline
    from researchforge.storage.contract_repository import get_active_contract
    from researchforge.storage.deliverable_repository import (
        get_branch_deliverable,
        insert_deliverable,
        list_deliverables,
    )
    from researchforge.storage.experiment_repository import (
        get_experiment,
        list_executions,
        list_experiments,
        list_runs,
    )
    from researchforge.storage.hypothesis_repository import get_hypothesis
    from researchforge.storage.paper_repository import list_papers
    from researchforge.storage.project_repository import get_project

    gh = GhClient()
    with closing(open_project_db()) as conn:
        project = get_project(conn)
        if project is None:
            typer.echo("No project found.")
            raise typer.Exit(code=1)
        repo_root = Path(project.repository.path) if project.repository.path else Path.cwd()

        deliverable = get_branch_deliverable(conn, experiment_id)
        if deliverable is None or deliverable.experiment_id is None:
            typer.echo("No shipped branch found — run `researchforge ship branch` first.")
            raise typer.Exit(code=1)
        branch = deliverable.location
        winner = get_experiment(conn, deliverable.experiment_id)
        assert winner is not None

        contract = get_active_contract(conn)
        if contract is None:
            typer.echo("No approved contract.")
            raise typer.Exit(code=1)
        if not contract.spec.shipping.allow_draft_pr:
            typer.echo(
                "Draft PRs are opt-in — set shipping.allow_draft_pr: true in "
                "researchforge.yaml and re-approve the contract."
            )
            raise typer.Exit(code=1)
        if not gh.available():
            typer.echo("The GitHub CLI (gh) is not installed: https://cli.github.com/")
            raise typer.Exit(code=1)
        if not gh.auth_ok(repo_root):
            typer.echo("gh is not authenticated — run `gh auth login` first.")
            raise typer.Exit(code=1)
        if not gh.default_remote_exists(repo_root):
            typer.echo("No 'origin' remote configured — add one before opening a PR.")
            raise typer.Exit(code=1)

        if not yes:
            typer.echo(
                f"About to push branch {branch!r} (commit "
                f"{(deliverable.commit_sha or '')[:12]}) to 'origin' and open a DRAFT "
                "pull request. Only this one branch is pushed."
            )
            confirmation = typer.prompt("Type 'push' to proceed")
            if confirmation.strip().lower() != "push":
                typer.echo("Not pushed.")
                raise typer.Exit(code=1)

        hypothesis = get_hypothesis(conn, winner.hypothesis_id)
        assert hypothesis is not None
        baseline = get_latest_successful_baseline(conn)
        assert baseline is not None
        experiments = list_experiments(conn, winner.plan_id)
        runs = [r for r in list_runs(conn) if r.plan_id == winner.plan_id]
        executions = list_executions(conn, run_id=runs[-1].run_id) if runs else []
        validation_attempts = [
            e
            for e in executions
            if e.experiment_id == winner.experiment_id
            and e.benchmark_stage is BenchmarkStage.VALIDATION
        ]
        validation = (
            summarize_validation(
                winner,
                validation_attempts,
                baseline,
                contract.spec.objective.primary_metric.direction,
            )
            if validation_attempts
            else None
        )
        preship = validation_attempts[-1] if validation_attempts else None
        reports = list_deliverables(conn, kind=DeliverableKind.ENGINEERING_REPORT)
        report_path = reports[-1].location if reports else None

        body = build_pr_body(
            contract=contract,
            hypothesis=hypothesis,
            papers=list_papers(conn),
            experiments=experiments,
            executions=executions,
            winner=winner,
            baseline=baseline,
            validation=validation,
            preship=preship,
            report_path=report_path,
        )
        title = build_pr_title(hypothesis, winner, contract)
        body_dir = repo_root / ".researchforge" / "artifacts" / "ship" / winner.experiment_id
        body_dir.mkdir(parents=True, exist_ok=True)
        body_file = body_dir / "pr_body.md"
        body_file.write_text(body, encoding="utf-8")

        try:
            gh.push_branch(repo_root, branch)
            url = gh.create_draft_pr(
                repo_root, branch=branch, title=title, body_file=body_file, base=base
            )
        except GhError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from None

        insert_deliverable(
            conn,
            project.id,
            Deliverable(
                deliverable_id=uuid4().hex,
                kind=DeliverableKind.DRAFT_PR,
                experiment_id=winner.experiment_id,
                location=url,
                commit_sha=deliverable.commit_sha,
                details={"branch": branch},
                created_at=datetime.now(UTC),
            ),
        )

    if json_output:
        typer.echo(json.dumps({"url": url, "branch": branch, "draft": True}, indent=2))
    else:
        typer.echo(f"Draft PR opened: {url}")
