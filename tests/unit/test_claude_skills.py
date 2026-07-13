"""Packaged Claude skills: content lint, spec §19 behaviors, and the installer."""

import json
import re
from pathlib import Path

import typer
from typer.testing import CliRunner

from researchforge.claude.installer import (
    SkillAction,
    install_skills,
    list_packaged_skills,
    load_manifest,
    manifest_path,
    skills_status,
    uninstall_skills,
)
from researchforge.cli import app

EXPECTED_SKILLS = {
    "researchforge-start",
    "researchforge-doctor",
    "researchforge-papers",
    "researchforge-landscape",
    "researchforge-hypotheses",
    "researchforge-baseline",
    "researchforge-plan",
    "researchforge-run",
    "researchforge-results",
    "researchforge-validate",
    "researchforge-ship",
    "researchforge-paper",
}

RULES_PHRASES = [
    "the Python engine is the boundary",
    "never pass `--yes`",
    "never invent metrics",
]


def _frontmatter(content: str) -> dict[str, str]:
    assert content.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
    block = content.split("---", 2)[1]
    fields = {}
    for line in block.strip().splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _cli_command_tree() -> tuple[set[str], dict[str, set[str]]]:
    """Top-level command names and group -> subcommand names, from the Typer app."""
    top = {c.name or (c.callback.__name__ if c.callback else "") for c in app.registered_commands}
    groups: dict[str, set[str]] = {}
    for group in app.registered_groups:
        sub: typer.Typer = group.typer_instance
        assert group.name is not None
        groups[group.name] = {
            c.name or (c.callback.__name__ if c.callback else "") for c in sub.registered_commands
        }
    return top, groups


class TestSkillContent:
    def test_exact_skill_set_packaged(self) -> None:
        assert set(list_packaged_skills()) == EXPECTED_SKILLS

    def test_frontmatter_valid(self) -> None:
        for name, content in list_packaged_skills().items():
            fields = _frontmatter(content)
            assert fields.get("name") == name, name
            assert len(fields.get("description", "")) > 40, name

    def test_every_referenced_command_exists(self) -> None:
        """Skills may only reference commands that resolve in the CLI tree."""
        top, groups = _cli_command_tree()
        pattern = re.compile(r"\bresearchforge ([a-z][a-z-]*)(?: ([a-z][a-z-]*))?")
        for name, content in list_packaged_skills().items():
            for match in pattern.finditer(content):
                first, second = match.group(1), match.group(2)
                if first in top:
                    continue
                assert first in groups, f"{name}: unknown command 'researchforge {first}'"
                assert second in groups[first], (
                    f"{name}: unknown command 'researchforge {first} {second}'"
                )

    def test_rules_block_in_every_skill(self) -> None:
        for name, content in list_packaged_skills().items():
            for phrase in RULES_PHRASES:
                assert phrase.lower() in content.lower(), f"{name}: missing rule '{phrase}'"

    def test_spec_behaviors(self) -> None:
        """Spec §19 skill-test behaviors are instructed by the relevant skills."""
        # Normalize hard-wrapped prose so phrases can be matched across line breaks.
        skills = {
            name: " ".join(content.split()) for name, content in list_packaged_skills().items()
        }
        # start + resume
        assert "status --json" in skills["researchforge-start"]
        assert "next_action" in skills["researchforge-start"]
        # malformed synthesis output -> self-correct from the --json payload
        for handshake in ("researchforge-landscape", "researchforge-hypotheses"):
            assert "error payload" in skills[handshake]
            assert "re-import" in skills[handshake]
        # unapproved run refused
        assert "refuses unapproved runs" in skills["researchforge-run"]
        # protected benchmark edits rejected
        assert "protected path" in skills["researchforge-plan"]
        assert "rejected" in skills["researchforge-plan"]
        # summaries grounded in saved artifacts
        assert "only" in skills["researchforge-results"]
        assert "recorded" in skills["researchforge-results"]
        # screening honesty and validation honesty
        assert "Screening numbers are screening numbers" in skills["researchforge-run"]
        assert "one-off" in skills["researchforge-validate"].lower()


class TestInstaller:
    def test_fresh_install_writes_skills_and_manifest(self, isolated_project_dir: Path) -> None:
        report = install_skills()

        assert {r.skill for r in report.results} == EXPECTED_SKILLS
        assert all(r.action is SkillAction.INSTALLED for r in report.results)
        for name in EXPECTED_SKILLS:
            assert (isolated_project_dir / ".claude" / "skills" / name / "SKILL.md").is_file()
        assert set(load_manifest().hashes) == EXPECTED_SKILLS

    def test_reinstall_is_unchanged(self, isolated_project_dir: Path) -> None:
        install_skills()
        report = install_skills()
        assert all(r.action is SkillAction.UNCHANGED for r in report.results)

    def test_older_version_upgraded_when_unmodified(self, isolated_project_dir: Path) -> None:
        import hashlib

        install_skills()
        target = isolated_project_dir / ".claude" / "skills" / "researchforge-start" / "SKILL.md"
        old = "---\nname: researchforge-start\n---\nold version\n"
        target.write_text(old, encoding="utf-8")
        manifest = load_manifest()
        manifest.hashes["researchforge-start"] = hashlib.sha256(old.encode()).hexdigest()
        manifest_path().write_text(manifest.model_dump_json(), encoding="utf-8")

        report = install_skills()

        by_skill = {r.skill: r.action for r in report.results}
        assert by_skill["researchforge-start"] is SkillAction.UPDATED
        assert "old version" not in target.read_text(encoding="utf-8")

    def test_user_edit_skipped_without_force(self, isolated_project_dir: Path) -> None:
        install_skills()
        target = isolated_project_dir / ".claude" / "skills" / "researchforge-start" / "SKILL.md"
        edited = target.read_text(encoding="utf-8") + "\nMy local notes.\n"
        target.write_text(edited, encoding="utf-8")

        report = install_skills()
        by_skill = {r.skill: r.action for r in report.results}
        assert by_skill["researchforge-start"] is SkillAction.SKIPPED_MODIFIED
        assert target.read_text(encoding="utf-8") == edited

        forced = install_skills(force=True)
        by_skill = {r.skill: r.action for r in forced.results}
        assert by_skill["researchforge-start"] is SkillAction.UPDATED
        assert "My local notes" not in target.read_text(encoding="utf-8")

    def test_uninstall_removes_only_ours(self, isolated_project_dir: Path) -> None:
        skills_dir = isolated_project_dir / ".claude" / "skills"
        foreign = skills_dir / "my-own-skill" / "SKILL.md"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("---\nname: my-own-skill\n---\nmine\n", encoding="utf-8")

        install_skills()
        report = uninstall_skills()

        assert all(r.action is SkillAction.REMOVED for r in report.results), [
            r.model_dump() for r in report.results
        ]
        for name in EXPECTED_SKILLS:
            assert not (skills_dir / name).exists()
        assert foreign.read_text(encoding="utf-8") == "---\nname: my-own-skill\n---\nmine\n"
        assert load_manifest().hashes == {}

    def test_uninstall_leaves_modified_unless_forced(self, isolated_project_dir: Path) -> None:
        install_skills()
        target = isolated_project_dir / ".claude" / "skills" / "researchforge-ship" / "SKILL.md"
        target.write_text("edited\n", encoding="utf-8")

        report = uninstall_skills()
        by_skill = {r.skill: r.action for r in report.results}
        assert by_skill["researchforge-ship"] is SkillAction.LEFT_MODIFIED
        assert target.is_file()

        forced = uninstall_skills(force=True)
        by_skill = {r.skill: r.action for r in forced.results}
        assert by_skill["researchforge-ship"] is SkillAction.REMOVED
        assert not target.exists()

    def test_status_reports_states(self, isolated_project_dir: Path) -> None:
        statuses = {r.skill: r.action for r in skills_status().results}
        assert all(action is SkillAction.MISSING for action in statuses.values())

        install_skills()
        target = isolated_project_dir / ".claude" / "skills" / "researchforge-run" / "SKILL.md"
        target.write_text("edited\n", encoding="utf-8")

        statuses = {r.skill: r.action for r in skills_status().results}
        assert statuses["researchforge-run"] is SkillAction.MODIFIED
        assert statuses["researchforge-start"] is SkillAction.UNCHANGED


class TestClaudeCli:
    def test_install_uninstall_status_json(
        self, cli_runner: CliRunner, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(app, ["claude", "install", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert {r["skill"] for r in payload["results"]} == EXPECTED_SKILLS

        result = cli_runner.invoke(app, ["claude", "status", "--json"])
        assert all(r["action"] == "unchanged" for r in json.loads(result.output)["results"])

        result = cli_runner.invoke(app, ["claude", "uninstall", "--json"])
        assert result.exit_code == 0
        assert all(r["action"] == "removed" for r in json.loads(result.output)["results"])

    def test_init_claude_initializes_and_installs(
        self, cli_runner: CliRunner, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(app, ["init", "--claude"])

        assert result.exit_code == 0, result.output
        assert "/researchforge-start" in result.output
        assert (isolated_project_dir / ".researchforge" / "researchforge.db").is_file()
        skills_dir = isolated_project_dir / ".claude" / "skills"
        assert {p.name for p in skills_dir.iterdir()} == EXPECTED_SKILLS

    def test_init_claude_on_existing_project(
        self, cli_runner: CliRunner, isolated_project_dir: Path
    ) -> None:
        assert cli_runner.invoke(app, ["init"]).exit_code == 0
        result = cli_runner.invoke(app, ["init", "--claude", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["status"] == "already_initialized"
        assert {r["skill"] for r in payload["skills"]["results"]} == EXPECTED_SKILLS
