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
