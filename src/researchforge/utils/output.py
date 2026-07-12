"""Shared CLI output conventions."""

from __future__ import annotations

import json
from typing import Annotated, Any

import typer
from pydantic import BaseModel

JsonOption = Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON output.")]


def echo_model(model: BaseModel) -> None:
    """Print a pydantic model as indented JSON."""
    typer.echo(model.model_dump_json(indent=2))


def echo_json(payload: Any) -> None:
    """Print an arbitrary JSON-serializable payload."""
    typer.echo(json.dumps(payload, indent=2, default=str))


def echo_import_result(
    errors: list[str], warnings: list[str], success_message: str, json_output: bool
) -> None:
    """Standard rendering for artifact import outcomes (both human and --json).

    With --json, invalid artifacts produce {"status": "invalid", "errors": [...]}
    so a synthesis author (Claude) can self-correct and retry.
    """
    if json_output:
        payload = {
            "status": "ok" if not errors else "invalid",
            "errors": errors,
            "warnings": warnings,
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        for warning in warnings:
            typer.echo(f"warning: {warning}")
        for error in errors:
            typer.echo(f"error: {error}")
        if not errors:
            typer.echo(success_message)
    if errors:
        raise typer.Exit(code=1)
