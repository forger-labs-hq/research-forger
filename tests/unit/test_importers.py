import json
import shutil
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from researchforge.cli import app
from researchforge.storage.db import open_project_db

ARTIFACTS = Path(__file__).parent.parent / "fixtures" / "artifacts"


@pytest.fixture
def project_with_papers(
    cli_runner: CliRunner,
    initialized_project: Path,
    patched_arxiv: None,
) -> Path:
    result = cli_runner.invoke(app, ["research", "search", "-q", "all:routing"])
    assert result.exit_code == 0, result.output
    return initialized_project


def _copy_fixture(name: str, dest_dir: Path) -> Path:
    target = dest_dir / name
    shutil.copy(ARTIFACTS / name, target)
    return target


class TestLandscapeImport:
    def test_valid_landscape_imports(
        self, cli_runner: CliRunner, project_with_papers: Path
    ) -> None:
        artifact = _copy_fixture("landscape_valid.yaml", project_with_papers)

        result = cli_runner.invoke(app, ["research", "landscape", "--import", str(artifact)])

        assert result.exit_code == 0, result.output
        assert "2 direction(s)" in result.output

        shown = cli_runner.invoke(app, ["research", "landscape", "--json"])
        payload = json.loads(shown.output)
        assert len(payload["directions"]) == 2
        assert len(payload["evidence"]) == 3

    def test_annotations_merge_onto_papers(
        self, cli_runner: CliRunner, project_with_papers: Path
    ) -> None:
        artifact = _copy_fixture("landscape_valid.yaml", project_with_papers)
        cli_runner.invoke(app, ["research", "landscape", "--import", str(artifact)])

        shown = cli_runner.invoke(app, ["papers", "show", "arxiv:2401.12345", "--json"])
        paper = json.loads(shown.output)
        assert paper["evidence_strength"] == "medium"
        assert paper["method_summary"].startswith("Entropy-threshold")

    def test_unknown_paper_ref_rejected_without_partial_writes(
        self, cli_runner: CliRunner, project_with_papers: Path
    ) -> None:
        artifact = _copy_fixture("landscape_bad_paper_ref.yaml", project_with_papers)

        result = cli_runner.invoke(app, ["research", "landscape", "--import", str(artifact)])

        assert result.exit_code == 1
        assert "arxiv:9999.99999" in result.output
        with closing(open_project_db()) as conn:
            assert conn.execute("SELECT COUNT(*) AS n FROM landscape").fetchone()["n"] == 0
            assert conn.execute("SELECT COUNT(*) AS n FROM evidence_claims").fetchone()["n"] == 0

    def test_json_error_payload(self, cli_runner: CliRunner, project_with_papers: Path) -> None:
        artifact = _copy_fixture("landscape_bad_paper_ref.yaml", project_with_papers)

        result = cli_runner.invoke(
            app, ["research", "landscape", "--import", str(artifact), "--json"]
        )

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["status"] == "invalid"
        assert payload["errors"]

    def test_missing_file(self, cli_runner: CliRunner, project_with_papers: Path) -> None:
        result = cli_runner.invoke(app, ["research", "landscape", "--import", "nope.yaml"])
        assert result.exit_code == 1

    def test_reimport_is_idempotent(self, cli_runner: CliRunner, project_with_papers: Path) -> None:
        artifact = _copy_fixture("landscape_valid.yaml", project_with_papers)
        cli_runner.invoke(app, ["research", "landscape", "--import", str(artifact)])
        cli_runner.invoke(app, ["research", "landscape", "--import", str(artifact)])

        with closing(open_project_db()) as conn:
            assert conn.execute("SELECT COUNT(*) AS n FROM landscape").fetchone()["n"] == 1
            assert conn.execute("SELECT COUNT(*) AS n FROM evidence_claims").fetchone()["n"] == 3


class TestHypothesesImport:
    def test_valid_hypotheses_import_with_backlinks(
        self, cli_runner: CliRunner, project_with_papers: Path
    ) -> None:
        artifact = _copy_fixture("hypotheses_valid.yaml", project_with_papers)

        result = cli_runner.invoke(app, ["hypotheses", "import", str(artifact)])

        assert result.exit_code == 0, result.output
        assert "3 hypothesis(es) imported" in result.output
        # hyp-003 has no citations → warned as UNSUPPORTED
        assert "UNSUPPORTED" in result.output

        paper = json.loads(
            cli_runner.invoke(app, ["papers", "show", "arxiv:2401.12345", "--json"]).output
        )
        assert paper["supports_hypotheses"] == ["hyp-001"]

        contradicted = json.loads(
            cli_runner.invoke(app, ["papers", "show", "arxiv:2405.98765", "--json"]).output
        )
        assert contradicted["contradicts_hypotheses"] == ["hyp-001"]

    def test_status_becomes_synthesized(
        self, cli_runner: CliRunner, project_with_papers: Path
    ) -> None:
        artifact = _copy_fixture("hypotheses_valid.yaml", project_with_papers)
        cli_runner.invoke(app, ["hypotheses", "import", str(artifact)])

        status = json.loads(cli_runner.invoke(app, ["status", "--json"]).output)
        assert status["status"] == "synthesized"
        assert status["counts"]["hypotheses"] == 3

    def test_missing_claim_rejected_with_field_error(
        self, cli_runner: CliRunner, project_with_papers: Path
    ) -> None:
        artifact = _copy_fixture("hypotheses_missing_claim.yaml", project_with_papers)

        result = cli_runner.invoke(app, ["hypotheses", "import", str(artifact)])

        assert result.exit_code == 1
        assert "claim" in result.output
        with closing(open_project_db()) as conn:
            assert conn.execute("SELECT COUNT(*) AS n FROM hypotheses").fetchone()["n"] == 0

    def test_supporting_contradicting_overlap_rejected(
        self, cli_runner: CliRunner, project_with_papers: Path
    ) -> None:
        artifact = _copy_fixture("hypotheses_overlap.yaml", project_with_papers)

        result = cli_runner.invoke(app, ["hypotheses", "import", str(artifact)])

        assert result.exit_code == 1
        assert "both" in result.output

    def test_list_and_show(self, cli_runner: CliRunner, project_with_papers: Path) -> None:
        artifact = _copy_fixture("hypotheses_valid.yaml", project_with_papers)
        cli_runner.invoke(app, ["hypotheses", "import", str(artifact)])

        listed = cli_runner.invoke(app, ["hypotheses", "list"])
        assert listed.exit_code == 0
        assert "hyp-001" in listed.output
        assert "SUPPORTED" in listed.output

        shown = cli_runner.invoke(app, ["hypotheses", "show", "hyp-003", "--json"])
        payload = json.loads(shown.output)
        assert payload["evidence_status"] == "unsupported"
        assert payload["status"] == "speculative"

    def test_show_unknown_id(self, cli_runner: CliRunner, project_with_papers: Path) -> None:
        result = cli_runner.invoke(app, ["hypotheses", "show", "hyp-999"])
        assert result.exit_code == 1

    def test_reimport_recomputes_backlinks_idempotently(
        self, cli_runner: CliRunner, project_with_papers: Path
    ) -> None:
        artifact = _copy_fixture("hypotheses_valid.yaml", project_with_papers)
        cli_runner.invoke(app, ["hypotheses", "import", str(artifact)])
        cli_runner.invoke(app, ["hypotheses", "import", str(artifact)])

        paper = json.loads(
            cli_runner.invoke(app, ["papers", "show", "arxiv:2401.12345", "--json"]).output
        )
        assert paper["supports_hypotheses"] == ["hyp-001"]
        with closing(open_project_db()) as conn:
            assert conn.execute("SELECT COUNT(*) AS n FROM hypotheses").fetchone()["n"] == 3
