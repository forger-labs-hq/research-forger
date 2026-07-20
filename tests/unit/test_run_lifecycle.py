"""Run lifecycle UX: experiment start/abandon, monitor bookkeeping, port fallback."""

import json
import socket
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from researchforge.cli import app
from researchforge.server.monitor import (
    MonitorRecord,
    monitor_path,
    pick_port,
    read_monitor,
    stop_monitor,
)

KNOB_PATCH = """\
diff --git a/src/algo.py b/src/algo.py
new file mode 100644
--- /dev/null
+++ b/src/algo.py
@@ -0,0 +1,2 @@
+IMPROVEMENT = 5
+LATENCY = 150.0
"""


def _stage_plan_file(base: Path) -> Path:
    staging = base / ".researchforge" / "experiments"
    patches = staging / "patches"
    patches.mkdir(parents=True, exist_ok=True)
    (patches / "improve.patch").write_text(KNOB_PATCH, encoding="utf-8")
    plan = staging / "plan.yaml"
    plan.write_text(
        "hypothesis_id: hyp-001\n"
        "approach_summary: Knob variants.\n"
        "experiments:\n"
        "  - key: improve\n"
        "    title: Variant improve\n"
        "    change_summary: Set knobs.\n"
        "    patch_file: patches/improve.patch\n",
        encoding="utf-8",
    )
    return plan


class TestExperimentStart:
    def test_one_command_with_yes(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        plan = _stage_plan_file(isolated_project_dir)
        result = cli_runner.invoke(app, ["experiment", "start", str(plan), "--yes"])

        assert result.exit_code == 0, result.output
        assert "Run run-001 complete" in result.output
        assert "promising: 1" in result.output

    def test_single_typed_approval(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        plan = _stage_plan_file(isolated_project_dir)
        result = cli_runner.invoke(app, ["experiment", "start", str(plan)], input="approve\n")

        assert result.exit_code == 0, result.output
        assert result.output.count("Type 'approve'") == 1
        assert "Run run-001 complete" in result.output

    def test_declined_leaves_plan_unapproved(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        plan = _stage_plan_file(isolated_project_dir)
        result = cli_runner.invoke(app, ["experiment", "start", str(plan)], input="no\n")

        assert result.exit_code == 1
        assert "Not approved" in result.output

        listed = cli_runner.invoke(app, ["experiment", "list", "--json"])
        rows = json.loads(listed.output)["experiments"]
        assert all(row["status"] == "planned" for row in rows)

    def test_invalid_plan_exits_nonzero(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        bad = isolated_project_dir / "bad.yaml"
        bad.write_text("hypothesis_id: hyp-999\nexperiments: []\n", encoding="utf-8")
        result = cli_runner.invoke(app, ["experiment", "start", str(bad), "--yes"])
        assert result.exit_code == 1


class TestAbandon:
    def _interrupt_run(self, base: Path) -> None:
        """Flip the completed fixture run back to an interrupted-looking state."""
        import sqlite3

        conn = sqlite3.connect(base / ".researchforge" / "researchforge.db")
        conn.row_factory = sqlite3.Row
        record = json.loads(conn.execute("SELECT record FROM experiment_runs").fetchone()["record"])
        record["status"] = "in_progress"
        conn.execute(
            "UPDATE experiment_runs SET record = ?, status = 'in_progress'", (json.dumps(record),)
        )
        for row in conn.execute("SELECT experiment_id, record FROM experiments").fetchall():
            experiment = json.loads(row["record"])
            if experiment["experiment_id"] == "exp-002":
                experiment["status"] = "running"
                experiment["decision"] = None
                conn.execute(
                    "UPDATE experiments SET record = ?, status = 'running' WHERE experiment_id = ?",
                    (json.dumps(experiment), "exp-002"),
                )
        conn.commit()
        conn.close()

    def test_abandon_interrupted_run(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        self._interrupt_run(isolated_project_dir)

        result = cli_runner.invoke(app, ["experiment", "abandon", "run-001"], input="abandon\n")
        assert result.exit_code == 0, result.output
        assert "abandoned" in result.output

        listed = cli_runner.invoke(app, ["experiment", "list", "--json"])
        statuses = {
            row["experiment_id"]: row["status"] for row in json.loads(listed.output)["experiments"]
        }
        assert statuses["exp-002"] == "cancelled"
        # Finished results are preserved.
        assert statuses["exp-001"] in ("validated", "implementation_ready")

    def test_completed_run_refused(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(app, ["experiment", "abandon", "run-001", "--yes"])
        assert result.exit_code == 1
        assert "completed" in result.output

    def test_unknown_run(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(app, ["experiment", "abandon", "run-404", "--yes"])
        assert result.exit_code == 1


class TestMonitorBookkeeping:
    def test_pick_port_prefers_then_falls_back(self) -> None:
        free = pick_port("127.0.0.1", 0)
        assert free > 0

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen(1)
            busy_port = blocker.getsockname()[1]
            chosen = pick_port("127.0.0.1", busy_port)
            assert chosen != busy_port

    def test_read_monitor_is_stale_pid_tolerant(self, isolated_project_dir: Path) -> None:
        monitor_path().parent.mkdir(parents=True, exist_ok=True)
        record = MonitorRecord(
            pid=99999999,
            url="http://127.0.0.1:9000/",
            host="127.0.0.1",
            port=9000,
            started_at="2026-07-18T00:00:00+00:00",
        )
        monitor_path().write_text(record.model_dump_json(), encoding="utf-8")
        assert read_monitor() is None
        assert stop_monitor() is None

    def test_serve_background_spawns_and_stop_kills(
        self,
        cli_runner: CliRunner,
        funnel_project: Path,
        isolated_project_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import researchforge.server.monitor as monitor_module

        spawned: list[list[str]] = []
        real_popen = subprocess.Popen

        def fake_popen(argv, **kwargs):  # type: ignore[no-untyped-def]
            spawned.append(list(argv))
            return real_popen(["sleep", "60"], start_new_session=True)

        monkeypatch.setattr(monitor_module.subprocess, "Popen", fake_popen)

        result = cli_runner.invoke(app, ["serve", "--background"])
        assert result.exit_code == 0, result.output
        assert "Monitoring in the background at" in result.output
        assert spawned and "--foreground" in spawned[0]
        record = read_monitor()
        assert record is not None

        again = cli_runner.invoke(app, ["serve", "--background"])
        assert "already running" in again.output

        status = cli_runner.invoke(app, ["serve", "--status"])
        assert record.url in status.output

        stopped = cli_runner.invoke(app, ["serve", "--stop"])
        assert "Stopped background monitor" in stopped.output
        assert read_monitor() is None

    def test_run_announces_existing_monitor(
        self,
        cli_runner: CliRunner,
        funnel_project: Path,
        isolated_project_dir: Path,
    ) -> None:
        record = MonitorRecord(
            pid=1,  # pid 1 is always alive
            url="http://127.0.0.1:9111/",
            host="127.0.0.1",
            port=9111,
            started_at="2026-07-18T00:00:00+00:00",
        )
        monitor_path().write_text(record.model_dump_json(), encoding="utf-8")
        plan = _stage_plan_file(isolated_project_dir)

        result = cli_runner.invoke(app, ["experiment", "start", str(plan), "--yes"])
        assert result.exit_code == 0, result.output
        assert "Live monitor: http://127.0.0.1:9111/" in result.output
