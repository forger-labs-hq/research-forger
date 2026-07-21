"""`researchforge paths` — where everything lives on disk."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from researchforge.config.paths import (
    artifacts_dir,
    contract_path,
    db_path,
    experiments_dir,
    is_initialized,
    reports_dir,
    researchforge_dir,
    synthesis_dir,
    worktrees_dir,
)
from researchforge.utils.output import JsonOption


def paths_command(json_output: JsonOption = False) -> None:
    """Show every location ResearchForge uses in this project."""
    from researchforge.config.settings import load_settings

    if not is_initialized():
        typer.echo("Not an initialized ResearchForge project. Run `researchforge init`.")
        raise typer.Exit(code=1)

    settings = load_settings()
    locations: dict[str, str] = {
        "repo_root": str(Path.cwd().resolve()),
        "state_dir": str(researchforge_dir().resolve()),
        "database": str(db_path().resolve()),
        "contract": str(contract_path().resolve()),
        "worktrees": str(worktrees_dir().resolve()),
        "artifacts": str(artifacts_dir().resolve()),
        "reports": str(reports_dir().resolve()),
        "synthesis_staging": str(synthesis_dir().resolve()),
        "experiments_staging": str(experiments_dir().resolve()),
        "research_output": str(Path(settings.research_output_dir).resolve()),
        "monitor_log": str((researchforge_dir() / "monitor.log").resolve()),
    }
    if json_output:
        typer.echo(json.dumps(locations, indent=2))
        return
    width = max(len(k) for k in locations)
    for key, value in locations.items():
        exists = "" if Path(value).exists() else "  (not created yet)"
        typer.echo(f"{key.ljust(width)}  {value}{exists}")
