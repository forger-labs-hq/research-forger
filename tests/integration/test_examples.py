"""The examples/simple-python demo repo must survive the real funnel.

Pins the launch-demo behaviors: the normalize variant wins, the n-gram
variant is rejected on the latency constraint, and the broken variant fails
and is preserved — all through the actual CLI with the venv runner.
"""

import json
import shutil
import subprocess
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from researchforge.cli import app

EXAMPLE = Path(__file__).parent.parent.parent / "examples" / "simple-python"

CONFIG_PATCH = '''\
diff --git a/src/config.py b/src/config.py
--- a/src/config.py
+++ b/src/config.py
@@ -1,4 +1,4 @@
 """Tunable classifier settings — experiments patch this file."""

-NORMALIZE = False
+NORMALIZE = True
 NGRAM_EXPANSION = False
'''

NGRAM_PATCH = '''\
diff --git a/src/config.py b/src/config.py
--- a/src/config.py
+++ b/src/config.py
@@ -1,4 +1,4 @@
 """Tunable classifier settings — experiments patch this file."""

 NORMALIZE = False
-NGRAM_EXPANSION = False
+NGRAM_EXPANSION = True
'''

BROKEN_PATCH = '''\
diff --git a/src/config.py b/src/config.py
--- a/src/config.py
+++ b/src/config.py
@@ -1,4 +1,4 @@
 """Tunable classifier settings — experiments patch this file."""

-NORMALIZE = False
+import missing_dependency_for_demo
 NGRAM_EXPANSION = False
'''


def _stage_plan(base: Path, entries: list[tuple[str, str]]) -> Path:
    staging = base / ".researchforge" / "experiments"
    patches = staging / "patches"
    patches.mkdir(parents=True, exist_ok=True)
    lines = ["hypothesis_id: hyp-001", "approach_summary: Demo variants.", "experiments:"]
    for key, patch_text in entries:
        (patches / f"{key}.patch").write_text(patch_text, encoding="utf-8")
        lines += [
            f"  - key: {key}",
            f"    title: Variant {key}",
            f"    change_summary: Demo variant {key}.",
            f"    patch_file: patches/{key}.patch",
        ]
    plan = staging / "plan.yaml"
    plan.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return plan


@pytest.fixture
def example_project(cli_runner: CliRunner, isolated_project_dir: Path) -> Path:
    """examples/simple-python copied into a fresh git repo, contracted and baselined."""
    from researchforge.domain.hypothesis import Hypothesis, Level, NoveltyConfidence
    from researchforge.storage.db import open_project_db
    from researchforge.storage.hypothesis_repository import replace_hypotheses
    from researchforge.storage.project_repository import get_project

    repo = isolated_project_dir / "demo"
    shutil.copytree(EXAMPLE, repo, ignore=shutil.ignore_patterns("__pycache__", "artifacts"))
    subprocess.run(["git", "init", "-qb", "main"], cwd=repo, check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Demo"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "baseline"], check=True)

    create = cli_runner.invoke(
        app,
        [
            "project",
            "create",
            "--mode",
            "improve_repository",
            "--objective",
            "Improve sentiment classification F1 without exceeding the latency budget",
        ],
    )
    assert create.exit_code == 0, create.output
    assert cli_runner.invoke(app, ["repo", "scan", str(repo)]).exit_code == 0

    shutil.copy(repo / "researchforge.example.yaml", repo / "researchforge.yaml")
    approve = cli_runner.invoke(app, ["contract", "approve", "--yes"])
    assert approve.exit_code == 0, approve.output

    hypothesis = Hypothesis(
        hypothesis_id="hyp-001",
        title="Token normalization improves F1",
        claim="Normalizing case and punctuation recovers missed keywords.",
        rationale="The classifier only matches exact lowercase tokens.",
        feasibility=Level.HIGH,
        estimated_effort=Level.LOW,
        novelty_confidence=NoveltyConfidence.UNKNOWN,
        proposed_experiment="Toggle normalization and n-gram settings; benchmark.",
    )
    with closing(open_project_db()) as conn:
        project = get_project(conn)
        assert project is not None
        replace_hypotheses(conn, project.id, [hypothesis])

    baseline = cli_runner.invoke(app, ["baseline", "run", "--json"])
    assert baseline.exit_code == 0, baseline.output
    return repo


def test_demo_repo_through_the_funnel(
    cli_runner: CliRunner, example_project: Path, isolated_project_dir: Path
) -> None:
    plan = _stage_plan(
        isolated_project_dir,
        [
            ("normalize", CONFIG_PATCH),
            ("ngram", NGRAM_PATCH),
            ("broken", BROKEN_PATCH),
        ],
    )
    assert cli_runner.invoke(app, ["experiment", "import", str(plan)]).exit_code == 0
    assert cli_runner.invoke(app, ["experiment", "approve", "plan-001", "--yes"]).exit_code == 0
    run = cli_runner.invoke(app, ["experiment", "run", "plan-001"])
    assert run.exit_code == 0, run.output

    results = cli_runner.invoke(app, ["results", "show", "run-001", "--json"])
    assert results.exit_code == 0, results.output
    report = json.loads(results.output)

    candidates = {row["title"]: row for row in report["candidates"]}
    rejected = {row["title"]: row for row in report["rejected"]}

    winner = candidates["Variant normalize"]
    assert winner["primary_value"] == 0.9
    assert winner["primary_delta"] is not None and winner["primary_delta"] > 0

    ngram = rejected["Variant ngram"]
    assert ngram["status"] == "rejected"
    assert "p95_latency_ms" in (ngram["decision"] or {}).get("reason", "")

    broken = rejected["Variant broken"]
    assert broken["status"] in ("failed_execution", "failed_setup")

    validate = cli_runner.invoke(app, ["validate", "run-001", "--yes"])
    assert validate.exit_code == 0, validate.output

    ship = cli_runner.invoke(app, ["ship", "branch", "--yes", "--json"])
    assert ship.exit_code == 0, ship.output
    branch = json.loads(ship.output)["branch"]

    log = subprocess.run(
        ["git", "-C", str(example_project), "log", "--format=%s", branch],
        capture_output=True,
        text=True,
        check=True,
    )
    assert len(log.stdout.strip().splitlines()) == 2  # winning commit + baseline

    report_result = cli_runner.invoke(app, ["report", "build", "--json"])
    assert report_result.exit_code == 0, report_result.output
    text = Path(json.loads(report_result.output)["path"]).read_text(encoding="utf-8")
    assert "0.9" in text  # the winner's recorded f1
    assert "Variant ngram" in text  # the rejected variant is preserved
