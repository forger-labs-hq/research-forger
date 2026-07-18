"""Monitoring server: pages, API, read-only guarantee, and the serve CLI."""

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from researchforge.cli import app as cli_app
from researchforge.domain.experiment import ExperimentExecution
from researchforge.server.data import read_state


@pytest.fixture
def client(validated_project: Path, isolated_project_dir: Path):  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    from researchforge.server.app import create_app

    return TestClient(create_app())


class TestPages:
    def test_overview(self, client) -> None:  # type: ignore[no-untyped-def]
        response = client.get("/")
        assert response.status_code == 200
        assert "Next action" in response.text
        assert "ship branch" in response.text  # validated fixture's next step
        assert "read-only monitor" in response.text
        assert "content='10'" in response.text  # no run in progress -> slow refresh

    def test_research_empty_state_is_honest(self, client) -> None:  # type: ignore[no-untyped-def]
        response = client.get("/research")
        assert response.status_code == 200
        assert "No papers stored yet" in response.text
        assert "No hypotheses imported yet" not in response.text  # fixture has hyp-001

    def test_experiments_live_table(self, client) -> None:  # type: ignore[no-untyped-def]
        response = client.get("/experiments")
        assert response.status_code == 200
        assert "run-001" in response.text
        assert "validated" in response.text
        assert "rejected" in response.text
        assert "p95_latency_ms" in response.text  # rejection reason shown

    def test_dashboard_page_has_charts_and_nav(self, client) -> None:  # type: ignore[no-untyped-def]
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "Progress —" in response.text and "Funnel" in response.text
        assert "<nav>" in response.text
        assert "http-equiv='refresh'" in response.text


class TestApi:
    def test_state_snapshot(self, client) -> None:  # type: ignore[no-untyped-def]
        payload = client.get("/api/state").json()
        assert payload["project"]["status"]
        assert len(payload["experiments"]) == 2
        assert payload["next_action"]

    def test_run_manifest(self, client) -> None:  # type: ignore[no-untyped-def]
        payload = client.get("/api/runs/run-001").json()
        parsed = [ExperimentExecution.model_validate(item) for item in payload]
        assert parsed and all(e.run_id == "run-001" for e in parsed)
        assert client.get("/api/runs/run-999").status_code == 404

    def test_read_only_and_get_only(self, client, isolated_project_dir: Path) -> None:  # type: ignore[no-untyped-def]
        db_file = isolated_project_dir / ".researchforge" / "researchforge.db"
        before = hashlib.sha256(db_file.read_bytes()).hexdigest()

        for route in ("/", "/research", "/experiments", "/dashboard", "/api/state"):
            assert client.get(route).status_code == 200

        assert hashlib.sha256(db_file.read_bytes()).hexdigest() == before

        from fastapi.routing import APIRoute

        from researchforge.server.app import create_app

        methods = {m for r in create_app().routes if isinstance(r, APIRoute) for m in r.methods}
        assert methods <= {"GET", "HEAD"}


class TestRefreshAndState:
    def test_fast_refresh_while_run_in_progress(self, client, isolated_project_dir: Path) -> None:  # type: ignore[no-untyped-def]
        import sqlite3

        db_file = isolated_project_dir / ".researchforge" / "researchforge.db"
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        record = json.loads(conn.execute("SELECT record FROM experiment_runs").fetchone()["record"])
        record["status"] = "in_progress"
        conn.execute(
            "UPDATE experiment_runs SET record = ?, status = 'in_progress'",
            (json.dumps(record),),
        )
        conn.commit()
        conn.close()

        response = client.get("/")
        assert "content='3'" in response.text
        assert "in progress" in response.text

    def test_read_state_on_baseline_only_project(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        state = read_state()
        assert state.baseline is not None
        assert state.runs == []
        assert "experiment plan" in state.next_action


class TestServeCli:
    def test_uninitialized_directory_refused(
        self, cli_runner: CliRunner, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(cli_app, ["serve"])
        assert result.exit_code == 1
        assert "Not an initialized" in result.output

    def test_missing_extra_prints_install_hint(
        self,
        cli_runner: CliRunner,
        validated_project: Path,
        isolated_project_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def no_uvicorn(name: str, *args: object, **kwargs: object) -> object:
            if name == "uvicorn":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", no_uvicorn)
        result = cli_runner.invoke(cli_app, ["serve"])
        assert result.exit_code == 1
        assert "researchforge[serve]" in result.output

    def test_serve_runs_uvicorn_and_warns_on_public_host(
        self,
        cli_runner: CliRunner,
        validated_project: Path,
        isolated_project_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import uvicorn

        calls: list[dict[str, object]] = []
        monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))

        result = cli_runner.invoke(cli_app, ["serve"])
        assert result.exit_code == 0, result.output
        assert calls[-1]["host"] == "127.0.0.1"
        assert "WARNING" not in result.output

        result = cli_runner.invoke(cli_app, ["serve", "--host", "0.0.0.0"])
        assert result.exit_code == 0
        assert "WARNING" in result.output
