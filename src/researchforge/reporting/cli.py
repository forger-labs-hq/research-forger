"""`researchforge report` sub-app."""

from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from researchforge.config.paths import reports_dir
from researchforge.domain.project import ProjectStatus
from researchforge.project.service import touch_project_status
from researchforge.reporting.research_report import build_research_report
from researchforge.storage.db import open_project_db
from researchforge.storage.hypothesis_repository import list_hypotheses
from researchforge.storage.paper_repository import list_papers, list_search_runs
from researchforge.storage.project_repository import get_project
from researchforge.storage.scan_repository import get_latest_scan
from researchforge.storage.synthesis_repository import get_landscape
from researchforge.utils.output import JsonOption

report_app = typer.Typer(name="report", no_args_is_help=True, help="Reports.")

REPORT_FILENAME = "research-report.md"
ENGINEERING_REPORT_FILENAME = "engineering-report.md"


@report_app.command()
def build(
    output: Annotated[
        Path | None, typer.Option("--output", help="Write the report to this path.")
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Build the report: engineering when experiment data exists, else research-only."""
    from researchforge.domain.deliverable import Deliverable, DeliverableKind
    from researchforge.storage.baseline_repository import get_latest_successful_baseline
    from researchforge.storage.contract_repository import get_active_contract
    from researchforge.storage.deliverable_repository import (
        list_deliverables,
        record_deliverable_once,
    )

    with closing(open_project_db()) as conn:
        project = get_project(conn)
        if project is None or project.objective is None:
            typer.echo("Define the project first: `researchforge project create`.")
            raise typer.Exit(code=1)

        contract = get_active_contract(conn)
        baseline = get_latest_successful_baseline(conn)
        papers = list_papers(conn)
        engineering = contract is not None and baseline is not None

        if not engineering and not papers:
            typer.echo("No papers stored. Run `researchforge research search` first.")
            raise typer.Exit(code=1)

        if engineering:
            assert contract is not None and baseline is not None
            from researchforge.config.settings import load_settings
            from researchforge.execution.ranking import build_ranking_report
            from researchforge.reporting.engineering_report import build_engineering_report
            from researchforge.storage.experiment_repository import (
                list_executions,
                list_experiments,
                list_plans,
                list_runs,
            )

            plans = list_plans(conn)
            experiments = list_experiments(conn)
            runs = list_runs(conn)
            executions = list_executions(conn, run_id=runs[-1].run_id) if runs else []
            ranking = None
            if runs and experiments:
                ranking = build_ranking_report(
                    runs[-1].run_id,
                    baseline,
                    experiments,
                    executions,
                    contract.spec,
                    tradeoff_material_pct=load_settings().tradeoff_material_pct,
                )
            markdown = build_engineering_report(
                project,
                get_latest_scan(conn),
                get_landscape(conn),
                papers,
                list_hypotheses(conn),
                contract,
                baseline,
                plans,
                experiments,
                executions,
                ranking,
                list_deliverables(conn),
            )
            filename = ENGINEERING_REPORT_FILENAME
        else:
            markdown = build_research_report(
                project,
                get_latest_scan(conn),
                get_landscape(conn),
                papers,
                list_hypotheses(conn),
                list_search_runs(conn),
            )
            filename = REPORT_FILENAME
            touch_project_status(conn, ProjectStatus.REPORTED)

        path = output or (reports_dir() / filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")

        if engineering:
            record_deliverable_once(
                conn,
                project.id,
                Deliverable(
                    deliverable_id=uuid4().hex,
                    kind=DeliverableKind.ENGINEERING_REPORT,
                    location=str(path),
                    created_at=datetime.now(UTC),
                ),
            )

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "path": str(path),
                    "kind": "engineering" if engineering else "research",
                    "bytes": len(markdown.encode("utf-8")),
                },
                indent=2,
            )
        )
    else:
        typer.echo(f"Report written to {path}")
