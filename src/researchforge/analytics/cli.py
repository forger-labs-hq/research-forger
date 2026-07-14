"""`researchforge analytics` sub-app: opt-in local beta analytics."""

from __future__ import annotations

import json

import typer

from researchforge.analytics.service import (
    analytics_path,
    compute_metrics,
    is_enabled,
    load_events,
    set_enabled,
)
from researchforge.utils.output import JsonOption

analytics_app = typer.Typer(
    name="analytics", no_args_is_help=True, help="Opt-in, local-only beta analytics."
)

COLLECTION_NOTICE = """\
Analytics are LOCAL-ONLY and nothing is ever transmitted anywhere.

When enabled, coarse events append to .researchforge/analytics.jsonl:
  - an event name (e.g. baseline_completed), a timestamp, ok/failed,
    and a short failure category.
Never collected: source code, paper text, secrets, datasets, metric
values, or logs. The file is yours — share it with a beta report only
if you choose to. Disable any time: researchforge analytics disable\
"""


@analytics_app.command("enable")
def enable_command(json_output: JsonOption = False) -> None:
    """Enable local analytics (prints exactly what is and is not collected)."""
    set_enabled(True)
    if json_output:
        typer.echo(json.dumps({"analytics_enabled": True}))
    else:
        typer.echo(COLLECTION_NOTICE)
        typer.echo("Enabled.")


@analytics_app.command("disable")
def disable_command(json_output: JsonOption = False) -> None:
    """Disable local analytics (the existing log is kept; delete it if you wish)."""
    set_enabled(False)
    if json_output:
        typer.echo(json.dumps({"analytics_enabled": False}))
    else:
        typer.echo(f"Disabled. Existing log (if any) remains at {analytics_path()}.")


@analytics_app.command("status")
def status_command(json_output: JsonOption = False) -> None:
    """Show whether analytics are enabled and how many events are recorded."""
    enabled = is_enabled()
    count = len(load_events())
    if json_output:
        typer.echo(json.dumps({"analytics_enabled": enabled, "events_recorded": count}))
    else:
        typer.echo(f"Analytics: {'enabled' if enabled else 'disabled'} ({count} event(s) recorded)")


@analytics_app.command("show")
def show_command(json_output: JsonOption = False) -> None:
    """Compute the beta metrics locally from the recorded events."""
    metrics = compute_metrics()
    if json_output:
        typer.echo(metrics.model_dump_json(indent=2))
        return
    typer.echo(f"Events recorded: {metrics.events_recorded}")
    for label, value in (
        ("Time to first landscape", metrics.time_to_first_landscape_s),
        ("Time to baseline", metrics.time_to_baseline_s),
    ):
        typer.echo(f"{label}: {f'{value:.0f}s' if value is not None else '—'}")
    for label, rate in (
        ("Baseline success rate", metrics.baseline_success_rate),
        ("Experiment completion rate", metrics.experiment_completion_rate),
        ("Valid-metrics rate", metrics.valid_metrics_rate),
    ):
        typer.echo(f"{label}: {f'{rate:.0%}' if rate is not None else '—'}")
    typer.echo(
        f"Validated findings: {metrics.validated_findings}; "
        f"branches: {metrics.branches_created}; reports: {metrics.reports_generated}; "
        f"packages: {metrics.packages_generated}"
    )
    if metrics.failure_categories:
        typer.echo("Failure categories:")
        for category, count in sorted(metrics.failure_categories.items()):
            typer.echo(f"  {category}: {count}")
