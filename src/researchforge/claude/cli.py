"""`researchforge claude` sub-app: manage the project-level Claude skills."""

from __future__ import annotations

import json

import typer

from researchforge.claude.installer import (
    InstallReport,
    SkillAction,
    install_skills,
    skills_status,
    uninstall_skills,
)
from researchforge.utils.output import JsonOption

claude_app = typer.Typer(name="claude", no_args_is_help=True, help="Claude Code skills.")

ForceOption = typer.Option(
    False,
    "--force",
    help="Overwrite/remove skills even if they were modified after installation.",
)

_ACTION_MARKERS = {
    SkillAction.INSTALLED: "+",
    SkillAction.UPDATED: "^",
    SkillAction.UNCHANGED: "=",
    SkillAction.SKIPPED_MODIFIED: "!",
    SkillAction.REMOVED: "-",
    SkillAction.LEFT_MODIFIED: "!",
    SkillAction.MISSING: "?",
    SkillAction.MODIFIED: "!",
}


def _echo_report(report: InstallReport, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(report.model_dump(), indent=2))
        return
    for result in report.results:
        typer.echo(f"{_ACTION_MARKERS[result.action]} {result.skill}: {result.action.value}")


@claude_app.command("install")
def install_command(force: bool = ForceOption, json_output: JsonOption = False) -> None:
    """Install the ResearchForge skills into this repository's .claude/skills/."""
    report = install_skills(force=force)
    _echo_report(report, json_output)
    if not json_output:
        if report.conflicts:
            typer.echo(
                "Some skills were modified after installation and were left untouched; "
                "re-run with --force to overwrite them."
            )
        typer.echo(f"Skills directory: {report.skills_dir}")


@claude_app.command("uninstall")
def uninstall_command(force: bool = ForceOption, json_output: JsonOption = False) -> None:
    """Remove the installed ResearchForge skills (user-modified files are kept)."""
    report = uninstall_skills(force=force)
    _echo_report(report, json_output)
    if not json_output:
        left = [r for r in report.results if r.action is SkillAction.LEFT_MODIFIED]
        if left:
            typer.echo(
                "Modified skills were left in place; re-run with --force to remove them too."
            )


@claude_app.command("status")
def status_command(json_output: JsonOption = False) -> None:
    """Show whether each packaged skill is installed, modified, or missing."""
    report = skills_status()
    _echo_report(report, json_output)
