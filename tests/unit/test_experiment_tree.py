"""Branching experiments: parent chains through import, execution, shipping."""

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from researchforge.cli import app

PARENT_PATCH = """\
diff --git a/src/algo.py b/src/algo.py
new file mode 100644
--- /dev/null
+++ b/src/algo.py
@@ -0,0 +1,2 @@
+IMPROVEMENT = 5
+LATENCY = 150.0
"""

# Written against the PARENT's state (src/algo.py exists with IMPROVEMENT=5):
# only applies when the chain was applied first.
CHILD_PATCH = """\
diff --git a/src/algo.py b/src/algo.py
--- a/src/algo.py
+++ b/src/algo.py
@@ -1,2 +1,2 @@
-IMPROVEMENT = 5
+IMPROVEMENT = 7
 LATENCY = 150.0
"""


def _stage_tree_plan(base: Path, child_parent: str = "root") -> Path:
    staging = base / ".researchforge" / "experiments"
    patches = staging / "patches"
    patches.mkdir(parents=True, exist_ok=True)
    (patches / "root.patch").write_text(PARENT_PATCH, encoding="utf-8")
    (patches / "child.patch").write_text(CHILD_PATCH, encoding="utf-8")
    plan = staging / "plan.yaml"
    plan.write_text(
        "hypothesis_id: hyp-001\n"
        "approach_summary: Branching knobs.\n"
        "experiments:\n"
        "  - key: root\n"
        "    title: Root improvement\n"
        "    change_summary: Set knobs.\n"
        "    patch_file: patches/root.patch\n"
        "  - key: child\n"
        "    title: Child refinement\n"
        "    change_summary: Bump improvement on top of root.\n"
        "    patch_file: patches/child.patch\n"
        f"    parent: {child_parent}\n",
        encoding="utf-8",
    )
    return plan


class TestImportValidation:
    def test_unknown_parent(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        plan = _stage_tree_plan(isolated_project_dir, child_parent="exp-999")
        result = cli_runner.invoke(app, ["experiment", "import", str(plan)])
        assert result.exit_code == 1
        assert "unknown parent experiment" in result.output

    def test_same_plan_cycle(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        staging = isolated_project_dir / ".researchforge" / "experiments"
        patches = staging / "patches"
        patches.mkdir(parents=True, exist_ok=True)
        (patches / "a.patch").write_text(PARENT_PATCH, encoding="utf-8")
        (patches / "b.patch").write_text(CHILD_PATCH, encoding="utf-8")
        plan = staging / "plan.yaml"
        plan.write_text(
            "hypothesis_id: hyp-001\napproach_summary: Cycle.\nexperiments:\n"
            "  - {key: a, title: A, change_summary: a, patch_file: patches/a.patch, parent: b}\n"
            "  - {key: b, title: B, change_summary: b, patch_file: patches/b.patch, parent: a}\n",
            encoding="utf-8",
        )
        result = cli_runner.invoke(app, ["experiment", "import", str(plan)])
        assert result.exit_code == 1
        assert "cycle" in result.output

    def test_child_patch_must_apply_on_chain(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        """A child written against the wrong parent state is an import error."""
        staging = isolated_project_dir / ".researchforge" / "experiments"
        patches = staging / "patches"
        patches.mkdir(parents=True, exist_ok=True)
        (patches / "root.patch").write_text(PARENT_PATCH, encoding="utf-8")
        # Child expects IMPROVEMENT = 6, but the parent sets 5 -> won't apply.
        (patches / "child.patch").write_text(
            CHILD_PATCH.replace("-IMPROVEMENT = 5", "-IMPROVEMENT = 6"), encoding="utf-8"
        )
        plan = staging / "plan.yaml"
        plan.write_text(
            "hypothesis_id: hyp-001\napproach_summary: Bad chain.\nexperiments:\n"
            "  - {key: root, title: R, change_summary: r, patch_file: patches/root.patch}\n"
            "  - {key: child, title: C, change_summary: c, patch_file: patches/child.patch, "
            "parent: root}\n",
            encoding="utf-8",
        )
        result = cli_runner.invoke(app, ["experiment", "import", str(plan)])
        assert result.exit_code == 1
        assert "does not apply on top of its parent chain" in result.output

    def test_unmeasured_db_parent_refused(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        # First import creates exp-001/exp-002 in `planned` state (never run).
        plan = _stage_tree_plan(isolated_project_dir)
        assert cli_runner.invoke(app, ["experiment", "import", str(plan)]).exit_code == 0
        # Second plan branching on the unmeasured exp-001 must be refused.
        second = _stage_tree_plan(isolated_project_dir, child_parent="exp-001")
        result = cli_runner.invoke(app, ["experiment", "import", str(second)])
        assert result.exit_code == 1
        assert "only measured experiments" in result.output


class TestTreeExecution:
    def test_chain_applied_and_measured(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        plan = _stage_tree_plan(isolated_project_dir)
        result = cli_runner.invoke(app, ["experiment", "start", str(plan), "--yes"])
        assert result.exit_code == 0, result.output

        listed = cli_runner.invoke(app, ["experiment", "list", "--json"])
        rows = {row["experiment_id"]: row for row in json.loads(listed.output)["experiments"]}
        child_id = next(eid for eid, row in rows.items() if row["parent_experiment_id"] is not None)
        parent_id = rows[child_id]["parent_experiment_id"]
        assert rows[parent_id]["parent_experiment_id"] is None

        results = cli_runner.invoke(app, ["results", "show", "run-001", "--json"])
        report = json.loads(results.output)
        values = {row["experiment_id"]: row["primary_value"] for row in report["candidates"]}
        # Parent measured alone (0.85); child measured with BOTH patches (0.87)
        # — 0.87 is only reachable if the ancestor chain was applied.
        assert values[parent_id] == 0.85
        assert values[child_id] == 0.87

        show = cli_runner.invoke(app, ["experiment", "show", child_id])
        assert f"Parent:     {parent_id}" in show.output

        text_results = cli_runner.invoke(app, ["results", "show", "run-001"])
        assert f"parent: {parent_id}" in text_results.output

    def test_ship_branched_winner_composes_chain(
        self, cli_runner: CliRunner, funnel_project: Path, isolated_project_dir: Path
    ) -> None:
        plan = _stage_tree_plan(isolated_project_dir)
        assert cli_runner.invoke(app, ["experiment", "start", str(plan), "--yes"]).exit_code == 0
        listed = cli_runner.invoke(app, ["experiment", "list", "--json"])
        child_id = next(
            row["experiment_id"]
            for row in json.loads(listed.output)["experiments"]
            if row["parent_experiment_id"] is not None
        )
        assert (
            cli_runner.invoke(app, ["validate", "run-001", "-e", child_id, "--yes"]).exit_code == 0
        )

        ship = cli_runner.invoke(app, ["ship", "branch", child_id, "--yes", "--json"])
        assert ship.exit_code == 0, ship.output
        payload = json.loads(ship.output)

        # Single commit on the baseline whose content composes the chain.
        log = subprocess.run(
            ["git", "-C", str(funnel_project), "log", "--format=%H", payload["branch"]],
            capture_output=True,
            text=True,
            check=True,
        )
        assert len(log.stdout.split()) == 2  # winning commit + fixture baseline commit
        content = subprocess.run(
            ["git", "-C", str(funnel_project), "show", f"{payload['branch']}:src/algo.py"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "IMPROVEMENT = 7" in content.stdout  # child's edit on parent's file


class TestContextExport:
    def test_prior_experiments_in_context(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        result = cli_runner.invoke(app, ["experiment", "plan", "hyp-001", "--json"])
        assert result.exit_code == 0, result.output
        context = json.loads(result.output)
        priors = {p["experiment_id"]: p for p in context["prior_experiments"]}
        assert "exp-001" in priors and "exp-002" in priors
        assert priors["exp-001"]["primary_value"] is not None
        assert any("parent" in i for i in context["instructions"])

    def test_branching_on_rejected_parent_allowed(
        self, cli_runner: CliRunner, validated_project: Path, isolated_project_dir: Path
    ) -> None:
        # exp-002 in the fixture is rejected (latency violator) — branching on
        # it is allowed; its patch creates src/algo.py, so the child edits it.
        staging = isolated_project_dir / ".researchforge" / "experiments"
        patches = staging / "patches"
        patches.mkdir(parents=True, exist_ok=True)
        (patches / "retry.patch").write_text(
            CHILD_PATCH.replace("-IMPROVEMENT = 5", "-IMPROVEMENT = 6").replace(
                "LATENCY = 150.0", "LATENCY = 250.0"
            ),
            encoding="utf-8",
        )
        plan = staging / "plan.yaml"
        plan.write_text(
            "hypothesis_id: hyp-001\napproach_summary: Explore around the rejection.\n"
            "experiments:\n"
            "  - {key: retry, title: Retry around rejection, change_summary: r, "
            "patch_file: patches/retry.patch, parent: exp-002}\n",
            encoding="utf-8",
        )
        result = cli_runner.invoke(app, ["experiment", "import", str(plan)])
        assert result.exit_code == 0, result.output
