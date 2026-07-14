"""Opt-in local analytics: default-off, allowed keys only, local metrics."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from researchforge.analytics.service import (
    analytics_path,
    compute_metrics,
    is_enabled,
    load_events,
    record_event,
    set_enabled,
)
from researchforge.cli import app


class TestOptIn:
    def test_disabled_by_default_records_nothing(
        self, cli_runner: CliRunner, isolated_project_dir: Path
    ) -> None:
        assert cli_runner.invoke(app, ["init"]).exit_code == 0
        create = cli_runner.invoke(
            app,
            ["project", "create", "--mode", "explore_research_idea", "--objective", "Test"],
        )
        assert create.exit_code == 0

        assert not is_enabled()
        assert not analytics_path().exists()

    def test_enable_records_coarse_events_only(
        self, cli_runner: CliRunner, isolated_project_dir: Path
    ) -> None:
        assert cli_runner.invoke(app, ["init"]).exit_code == 0
        result = cli_runner.invoke(app, ["analytics", "enable"])
        assert result.exit_code == 0
        assert "LOCAL-ONLY" in result.output
        assert "Never collected" in result.output

        create = cli_runner.invoke(
            app,
            ["project", "create", "--mode", "explore_research_idea", "--objective", "Secret"],
        )
        assert create.exit_code == 0

        events = load_events()
        assert [e["event"] for e in events] == ["project_created"]
        assert set(events[0]) <= {"event", "ts", "ok", "category"}
        assert "Secret" not in analytics_path().read_text(encoding="utf-8")

    def test_disable_stops_recording_and_keeps_log(
        self, cli_runner: CliRunner, isolated_project_dir: Path
    ) -> None:
        assert cli_runner.invoke(app, ["init"]).exit_code == 0
        cli_runner.invoke(app, ["analytics", "enable"])
        record_event("doctor_passed")
        cli_runner.invoke(app, ["analytics", "disable"])
        record_event("doctor_passed")

        assert len(load_events()) == 1

        status = cli_runner.invoke(app, ["analytics", "status", "--json"])
        payload = json.loads(status.output)
        assert payload == {"analytics_enabled": False, "events_recorded": 1}

    def test_enable_preserves_other_settings(self, isolated_project_dir: Path) -> None:
        from researchforge.config.paths import config_path
        from researchforge.config.settings import load_settings

        config_path().parent.mkdir(parents=True)
        config_path().write_text(json.dumps({"selected_papers": 10}), encoding="utf-8")

        set_enabled(True)

        settings = load_settings()
        assert settings.analytics_enabled is True
        assert settings.selected_papers == 10

    def test_unknown_event_name_is_a_bug(self, isolated_project_dir: Path) -> None:
        with pytest.raises(AssertionError):
            record_event("made_up_event")


class TestMetrics:
    def _write_log(self, base: Path, events: list[dict[str, object]]) -> None:
        set_enabled(True, base)
        path = analytics_path(base)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(e) + "\n" for e in events),
            encoding="utf-8",
        )

    def test_beta_metrics_from_synthetic_log(
        self, cli_runner: CliRunner, isolated_project_dir: Path
    ) -> None:
        self._write_log(
            isolated_project_dir,
            [
                {"event": "project_created", "ts": "2026-07-14T10:00:00+00:00", "ok": True},
                {"event": "landscape_imported", "ts": "2026-07-14T10:10:00+00:00", "ok": True},
                {
                    "event": "baseline_completed",
                    "ts": "2026-07-14T10:20:00+00:00",
                    "ok": False,
                    "category": "failed_setup",
                },
                {"event": "baseline_completed", "ts": "2026-07-14T10:30:00+00:00", "ok": True},
                {"event": "experiment_started", "ts": "2026-07-14T11:00:00+00:00", "ok": True},
                {"event": "experiment_started", "ts": "2026-07-14T11:00:00+00:00", "ok": True},
                {
                    "event": "experiment_completed",
                    "ts": "2026-07-14T11:05:00+00:00",
                    "ok": True,
                    "category": "promising",
                },
                {
                    "event": "experiment_completed",
                    "ts": "2026-07-14T11:06:00+00:00",
                    "ok": False,
                    "category": "rejected",
                },
                {"event": "validated_finding", "ts": "2026-07-14T11:30:00+00:00", "ok": True},
                {"event": "branch_created", "ts": "2026-07-14T11:40:00+00:00", "ok": True},
                {"event": "report_generated", "ts": "2026-07-14T11:41:00+00:00", "ok": True},
            ],
        )

        metrics = compute_metrics()

        assert metrics.events_recorded == 11
        assert metrics.time_to_first_landscape_s == 600
        assert metrics.time_to_baseline_s == 1800  # first *successful* baseline
        assert metrics.baseline_success_rate == 0.5
        assert metrics.experiment_completion_rate == 0.5
        assert metrics.valid_metrics_rate == 0.5
        assert metrics.validated_findings == 1
        assert metrics.branches_created == 1
        assert metrics.reports_generated == 1
        assert metrics.failure_categories == {"failed_setup": 1, "rejected": 1}

        shown = cli_runner.invoke(app, ["analytics", "show", "--json"])
        assert shown.exit_code == 0
        assert json.loads(shown.output)["failure_categories"] == {
            "failed_setup": 1,
            "rejected": 1,
        }

    def test_empty_log_yields_nulls(self, isolated_project_dir: Path) -> None:
        metrics = compute_metrics()
        assert metrics.events_recorded == 0
        assert metrics.time_to_baseline_s is None
        assert metrics.baseline_success_rate is None
