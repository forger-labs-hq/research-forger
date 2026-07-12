"""`researchforge hypotheses` sub-app."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Annotated

import typer

from researchforge.config.settings import load_settings
from researchforge.domain.hypothesis import Hypothesis
from researchforge.research.importers import import_hypotheses
from researchforge.storage.db import open_project_db
from researchforge.storage.hypothesis_repository import get_hypothesis, list_hypotheses
from researchforge.storage.project_repository import get_project
from researchforge.utils.output import JsonOption, echo_import_result, echo_model

hypotheses_app = typer.Typer(
    name="hypotheses", no_args_is_help=True, help="Evidence-backed hypotheses."
)


def _print_hypothesis(hypothesis: Hypothesis) -> None:
    label = hypothesis.evidence_status.upper()
    typer.echo(f"[{hypothesis.hypothesis_id}] {hypothesis.title}  ({label})")
    typer.echo(f"Status:      {hypothesis.status.value}")
    typer.echo(f"Claim:       {hypothesis.claim}")
    typer.echo(f"Rationale:   {hypothesis.rationale}")
    if hypothesis.supporting_paper_ids:
        typer.echo(f"Supported by:    {', '.join(hypothesis.supporting_paper_ids)}")
    if hypothesis.contradicting_paper_ids:
        typer.echo(f"Contradicted by: {', '.join(hypothesis.contradicting_paper_ids)}")
    for observation in hypothesis.repository_observations:
        typer.echo(f"  repo observation: {observation}")
    impact = hypothesis.expected_impact
    typer.echo(f"Impact:      {impact.metric or 'unspecified metric'} ({impact.direction.value})")
    typer.echo(f"Feasibility: {hypothesis.feasibility.value}")
    typer.echo(f"Effort:      {hypothesis.estimated_effort.value}")
    if hypothesis.estimated_experiment_count is not None:
        typer.echo(f"Experiments: ~{hypothesis.estimated_experiment_count}")
    typer.echo(f"Novelty:     {hypothesis.novelty_confidence.value} (not established)")
    typer.echo(f"Experiment:  {hypothesis.proposed_experiment}")
    for limitation in hypothesis.limitations:
        typer.echo(f"  limitation: {limitation}")


@hypotheses_app.command("import")
def import_command(
    file: Annotated[Path, typer.Argument(help="Hypotheses artifact (YAML or JSON).")],
    json_output: JsonOption = False,
) -> None:
    """Validate and import a hypotheses artifact."""
    with closing(open_project_db()) as conn:
        project = get_project(conn)
        if project is None:
            typer.echo("No project found. Run `researchforge project create` first.")
            raise typer.Exit(code=1)
        result = import_hypotheses(conn, file, project.id, load_settings())
        count = len(list_hypotheses(conn)) if result.ok else 0
    echo_import_result(
        result.errors,
        result.warnings,
        f"{count} hypothesis(es) imported. Next: researchforge report build",
        json_output,
    )


@hypotheses_app.command("list")
def list_command(json_output: JsonOption = False) -> None:
    """List stored hypotheses."""
    with closing(open_project_db()) as conn:
        hypotheses = list_hypotheses(conn)
    if json_output:
        typer.echo(json.dumps([h.model_dump(mode="json") for h in hypotheses], indent=2))
        return
    if not hypotheses:
        typer.echo("No hypotheses imported yet. See `researchforge research context`.")
        return
    for hypothesis in hypotheses:
        label = hypothesis.evidence_status.upper()
        citations = len(hypothesis.supporting_paper_ids)
        typer.echo(
            f"{hypothesis.hypothesis_id}  [{label}, {citations} citation(s), "
            f"{hypothesis.feasibility.value} feasibility]  {hypothesis.title}"
        )


@hypotheses_app.command("show")
def show_command(
    hypothesis_id: Annotated[str, typer.Argument(help="e.g. hyp-001")],
    json_output: JsonOption = False,
) -> None:
    """Show one hypothesis in full."""
    with closing(open_project_db()) as conn:
        hypothesis = get_hypothesis(conn, hypothesis_id)
    if hypothesis is None:
        typer.echo(f"Unknown hypothesis id: {hypothesis_id}. See `researchforge hypotheses list`.")
        raise typer.Exit(code=1)
    if json_output:
        echo_model(hypothesis)
    else:
        _print_hypothesis(hypothesis)
