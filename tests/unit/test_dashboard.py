"""Dashboard: SVG renderers, HTML assembly, gates, and self-containment."""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from typer.testing import CliRunner

from researchforge.cli import app
from researchforge.reporting.svg_charts import (
    Bar,
    Point,
    SpreadRow,
    bar_chart,
    funnel_chart,
    scatter_chart,
    spread_chart,
)


def _parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)


class TestSvgCharts:
    def test_bar_chart_has_baseline_plus_experiment_bars(self) -> None:
        svg = bar_chart(
            [
                Bar(label="exp-001", value=0.85, status="validated", delta_pct=6.25),
                Bar(label="exp-002", value=0.7, status="rejected"),
                Bar(label="exp-003", value=0.81, status="promising", note="screening"),
            ],
            baseline_value=0.8,
            metric_name="f1",
        )
        root = _parse(svg)
        bars = [e for e in root.iter() if e.get("data-bar")]
        assert [b.get("data-bar") for b in bars] == ["baseline", "exp-001", "exp-002", "exp-003"]
        assert "screening" in svg  # screening values are labeled
        assert "+6.2%" in svg or "+6.3%" in svg

    def test_scatter_chart_constraint_line_position(self) -> None:
        svg = scatter_chart(
            [Point(label="exp-001", x=150.0, y=0.85, status="promising", pareto=True)],
            baseline=Point(label="baseline", x=100.0, y=0.8, status="baseline"),
            x_label="p95_latency_ms",
            y_label="f1",
            x_threshold=200.0,
            threshold_note="p95_latency_ms <= 200",
        )
        root = _parse(svg)
        line = next(e for e in root.iter() if e.get("data-role") == "constraint-line")
        region = next(e for e in root.iter() if e.get("data-role") == "violation-region")
        # The shaded violating region starts exactly at the constraint line.
        assert line.get("x1") == region.get("x")
        assert any(e.get("data-role") == "pareto-ring" for e in root.iter())
        assert "p95_latency_ms &lt;= 200" in svg or "p95_latency_ms <= 200" in svg

    def test_funnel_counts(self) -> None:
        svg = funnel_chart(
            [("imported", 3), ("screening", 3), ("full benchmark", 2), ("validated", 1)],
            ["", "exp-003 failed_execution", "exp-002 rejected", ""],
        )
        root = _parse(svg)
        counts = {
            e.get("data-funnel"): e.get("data-count") for e in root.iter() if e.get("data-funnel")
        }
        assert counts == {
            "imported": "3",
            "screening": "3",
            "full benchmark": "2",
            "validated": "1",
        }
        assert "exp-002 rejected" in svg

    def test_spread_chart_attempts_and_mean(self) -> None:
        svg = spread_chart(
            [
                SpreadRow(
                    label="exp-001",
                    values=[0.85, 0.84],
                    mean=0.845,
                    stdev=0.007,
                    outcome="validated",
                    extra_values=[0.85],
                )
            ],
            baseline_value=0.8,
            metric_name="f1",
        )
        root = _parse(svg)
        attempts = [e for e in root.iter() if e.get("data-attempt-value")]
        assert len(attempts) == 2
        assert any(e.get("data-role") == "mean-tick" for e in root.iter())
        assert any(e.get("data-role") == "full-run-value" for e in root.iter())


class TestDashboardCommand:
    def test_dashboard_on_validated_project(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(app, ["dashboard", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["run_id"] == "run-001"
        html = Path(payload["path"]).read_text(encoding="utf-8")

        assert "0.8" in html  # baseline value
        assert "0.85" in html  # winner value
        assert "exp-002" in html  # the rejected loser is shown
        assert "p95_latency_ms" in html  # constraint scatter present
        assert "validated" in html
        assert "Funnel" in html and "Validation spread" in html

        # Self-contained: no external references, no scripts.
        assert "<script" not in html
        assert not re.search(r"https?://(?!www\.w3\.org)", html)

    def test_gate_without_contract(self, cli_runner: CliRunner, initialized_project: Path) -> None:
        result = cli_runner.invoke(app, ["dashboard"])
        assert result.exit_code == 1
        assert "approved contract" in result.output

    def test_baseline_but_no_runs_renders_empty_state(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(app, ["dashboard", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["run_id"] is None
        html = Path(payload["path"]).read_text(encoding="utf-8")
        assert "No experiment runs recorded yet" in html
        assert "0.8" in html  # baseline card still rendered

    def test_unknown_run_rejected(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(app, ["dashboard", "--run", "run-999"])
        assert result.exit_code == 1
        assert "Unknown run" in result.output

    def test_rebuild_records_single_deliverable_and_open_flag(
        self,
        cli_runner: CliRunner,
        validated_project: Path,
        isolated_project_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from contextlib import closing

        import researchforge.reporting.dashboard_cli as dashboard_cli
        from researchforge.domain.deliverable import DeliverableKind
        from researchforge.storage.db import open_project_db
        from researchforge.storage.deliverable_repository import list_deliverables

        opened: list[str] = []
        monkeypatch.setattr(dashboard_cli.webbrowser, "open", lambda url: opened.append(url))

        assert cli_runner.invoke(app, ["dashboard"]).exit_code == 0
        assert cli_runner.invoke(app, ["dashboard", "--open"]).exit_code == 0

        assert len(opened) == 1 and opened[0].startswith("file://")
        with closing(open_project_db()) as conn:
            dashboards = list_deliverables(conn, kind=DeliverableKind.DASHBOARD)
        assert len(dashboards) == 1
