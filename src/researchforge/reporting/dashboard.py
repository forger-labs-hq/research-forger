"""Self-contained HTML dashboard: experiments vs the frozen baseline.

One static file from recorded data only — inline CSS and inline SVG, no
scripts, no network. The honesty rules of the reports apply: screening
numbers are labeled screening, one-off results carry the caveat, and
rejected/failed experiments are shown, not hidden.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from html import escape

from researchforge import __version__
from researchforge.config.settings import load_settings
from researchforge.domain.baseline import BaselineRun
from researchforge.domain.contract import ContractSpec, ExperimentContract, MetricDirection
from researchforge.domain.experiment import (
    BenchmarkStage,
    Experiment,
    ExperimentExecution,
    ExperimentRunGroup,
    ExperimentStatus,
)
from researchforge.execution.ranking import (
    ONE_OFF_CAVEAT,
    RankingReport,
    build_ranking_report,
    signed_improvement,
)
from researchforge.execution.validation import summarize_validation
from researchforge.reporting.svg_charts import (
    Bar,
    Point,
    ProgressPoint,
    SpreadRow,
    bar_chart,
    funnel_chart,
    progress_chart,
    scatter_chart,
    spread_chart,
    status_color,
)

DASHBOARD_CSS = """
:root {
  --bg: #ffffff; --card: #f6f8fa; --fg: #1f2328; --fg-muted: #59636e;
  --grid: #d1d9e0; --chart-good: #1a7f37; --chart-info: #0969da;
  --chart-bad: #cf222e; --chart-muted: #8c959f; --chart-baseline: #6639ba;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117; --card: #161b22; --fg: #e6edf3; --fg-muted: #8d96a0;
    --grid: #30363d; --chart-good: #3fb950; --chart-info: #58a6ff;
    --chart-bad: #f85149; --chart-muted: #6e7681; --chart-baseline: #bc8cff;
  }
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); margin: 0 auto; max-width: 860px;
  padding: 24px 16px 60px; font-family: ui-sans-serif, system-ui, sans-serif; }
h1 { font-size: 1.5rem; margin: 0 0 4px; }
h2 { font-size: 1.1rem; margin: 32px 0 10px; }
.sub { color: var(--fg-muted); margin: 0 0 20px; }
.cards { display: flex; gap: 12px; flex-wrap: wrap; }
.card { background: var(--card); border-radius: 8px; padding: 12px 16px; flex: 1 1 160px; }
.card .k { color: var(--fg-muted); font-size: 0.75rem; text-transform: uppercase; }
.card .v { font-size: 1.25rem; font-weight: 600; margin-top: 2px; overflow-wrap: anywhere; }
.card .d { color: var(--fg-muted); font-size: 0.8rem; margin-top: 2px; }
svg { width: 100%; height: auto; background: var(--card); border-radius: 8px; padding: 8px; }
table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--grid);
  vertical-align: top; }
th { color: var(--fg-muted); font-weight: 600; }
.badge { display: inline-block; padding: 1px 8px; border-radius: 10px; color: #fff;
  font-size: 0.75rem; white-space: nowrap; }
.caveat { background: var(--card); border-left: 3px solid var(--chart-baseline);
  padding: 8px 12px; border-radius: 0 6px 6px 0; color: var(--fg-muted); font-size: 0.85rem;
  margin: 8px 0; }
.empty { color: var(--fg-muted); font-style: italic; }
footer { margin-top: 40px; color: var(--fg-muted); font-size: 0.8rem; }
"""


def _badge(status: str) -> str:
    return f"<span class='badge' style='background:{status_color(status)}'>{escape(status)}</span>"


def _latest_full_value(executions: list[ExperimentExecution], experiment_id: str) -> float | None:
    for execution in reversed(executions):
        if (
            execution.experiment_id == experiment_id
            and execution.benchmark_stage is BenchmarkStage.FULL
            and execution.metrics is not None
        ):
            return execution.metrics.primary_metric.value
    return None


def _stage_reached(executions: list[ExperimentExecution], experiment_id: str) -> str:
    order = [BenchmarkStage.SCREENING, BenchmarkStage.FULL, BenchmarkStage.VALIDATION]
    reached = [e.benchmark_stage for e in executions if e.experiment_id == experiment_id]
    if not reached:
        return "never ran"
    return max(reached, key=order.index).value


def _bars(
    experiments: list[Experiment],
    executions: list[ExperimentExecution],
    ranking: RankingReport | None,
) -> list[Bar]:
    deltas: dict[str, float | None] = {}
    if ranking is not None:
        for row in [*ranking.candidates, *ranking.rejected]:
            deltas[row.experiment_id] = row.primary_delta_pct
    bars = []
    for experiment in experiments:
        value = _latest_full_value(executions, experiment.experiment_id)
        note = None
        if value is None:  # fall back to a screening value, clearly labeled
            for execution in reversed(executions):
                if (
                    execution.experiment_id == experiment.experiment_id
                    and execution.metrics is not None
                ):
                    value, note = execution.metrics.primary_metric.value, "screening"
                    break
        if value is None:
            continue
        bars.append(
            Bar(
                label=experiment.experiment_id,
                value=value,
                status=experiment.status.value,
                delta_pct=deltas.get(experiment.experiment_id),
                note=note,
            )
        )
    return bars


_SURVIVOR_STATUSES = (
    ExperimentStatus.PROMISING,
    ExperimentStatus.VALIDATING,
    ExperimentStatus.VALIDATED,
    ExperimentStatus.IMPLEMENTATION_READY,
)


def progress_points(
    experiments: list[Experiment],
    executions: list[ExperimentExecution],
    baseline_value: float,
    direction: MetricDirection,
) -> list[ProgressPoint]:
    """Chronological full-benchmark measurements with running-best bookkeeping.

    A point is *kept* when it beat the running best AND the experiment
    survived (a constraint violator with a better primary metric stays
    discarded — the running best never advances through it).
    """
    titles = {e.experiment_id: e.title for e in experiments}
    statuses = {e.experiment_id: e.status for e in experiments}
    first_full: dict[str, ExperimentExecution] = {}
    for execution in sorted(executions, key=lambda e: e.started_at):
        if (
            execution.benchmark_stage is BenchmarkStage.FULL
            and execution.metrics is not None
            and execution.experiment_id not in first_full
        ):
            first_full[execution.experiment_id] = execution

    points: list[ProgressPoint] = []
    best = baseline_value
    for index, execution in enumerate(
        sorted(first_full.values(), key=lambda e: e.started_at), start=1
    ):
        assert execution.metrics is not None
        value = execution.metrics.primary_metric.value
        survived = statuses.get(execution.experiment_id) in _SURVIVOR_STATUSES
        kept = survived and signed_improvement(best, value, direction) > 0
        if kept:
            best = value
        points.append(
            ProgressPoint(
                index=index,
                value=value,
                kept=kept,
                label=titles.get(execution.experiment_id, execution.experiment_id),
                experiment_id=execution.experiment_id,
            )
        )
    return points


def _funnel(
    experiments: list[Experiment], executions: list[ExperimentExecution]
) -> tuple[list[tuple[str, int]], list[str]]:
    def reached(stage: BenchmarkStage) -> set[str]:
        return {e.experiment_id for e in executions if e.benchmark_stage is stage}

    screening, full, validation = (
        reached(BenchmarkStage.SCREENING),
        reached(BenchmarkStage.FULL),
        reached(BenchmarkStage.VALIDATION),
    )
    validated = {
        e.experiment_id
        for e in experiments
        if e.status in (ExperimentStatus.VALIDATED, ExperimentStatus.IMPLEMENTATION_READY)
    }
    dropped = {
        e.experiment_id: e.status.value
        for e in experiments
        if e.status
        in (
            ExperimentStatus.REJECTED,
            ExperimentStatus.FAILED_SETUP,
            ExperimentStatus.FAILED_EXECUTION,
            ExperimentStatus.CANCELLED,
        )
    }

    def drop_note(survivors: set[str]) -> str:
        lost = sorted(set(dropped) & survivors)
        return ", ".join(f"{eid} {dropped[eid]}" for eid in lost)

    stages = [
        ("imported", len(experiments)),
        ("screening", len(screening)),
        ("full benchmark", len(full)),
        ("validation", len(validation)),
        ("validated", len(validated)),
    ]
    notes = ["", drop_note(screening - full), drop_note(full - validation), "", ""]
    return stages, notes


def build_dashboard(conn: sqlite3.Connection, run: ExperimentRunGroup | None) -> str:
    """Assemble the dashboard HTML from stored records."""
    from researchforge.storage.baseline_repository import get_latest_successful_baseline
    from researchforge.storage.contract_repository import get_active_contract
    from researchforge.storage.deliverable_repository import list_deliverables
    from researchforge.storage.experiment_repository import list_executions, list_experiments
    from researchforge.storage.project_repository import get_project

    project = get_project(conn)
    contract = get_active_contract(conn)
    baseline = get_latest_successful_baseline(conn)
    assert project is not None and contract is not None and baseline is not None
    assert baseline.metrics is not None
    spec = contract.spec
    primary = spec.objective.primary_metric.name

    experiments = list_experiments(conn, run.plan_id) if run is not None else []
    executions = list_executions(conn, run_id=run.run_id) if run is not None else []
    ranking = None
    if run is not None and experiments:
        ranking = build_ranking_report(
            run.run_id,
            baseline,
            experiments,
            executions,
            spec,
            tradeoff_material_pct=load_settings().tradeoff_material_pct,
        )

    sections = [_header_section(project.name, spec, contract, baseline, run)]

    all_points = progress_points(
        list_experiments(conn),
        list_executions(conn),
        baseline.metrics.primary_metric.value,
        spec.objective.primary_metric.direction,
    )
    if all_points:
        kept = sum(1 for p in all_points if p.kept)
        chart = progress_chart(
            all_points,
            baseline.metrics.primary_metric.value,
            primary,
            lower_is_better=spec.objective.primary_metric.direction is MetricDirection.MINIMIZE,
        )
        sections.append(
            f"<h2>Progress — {len(all_points)} experiment(s), {kept} kept improvement(s)</h2>"
            f"{chart}<p class='sub'>Every full-benchmark measurement across all runs, in "
            "order. Green: improved the running best and survived; gray: discarded (worse, "
            "rejected on a constraint, or failed later).</p>"
        )

    if run is None:
        sections.append(
            "<p class='empty'>No experiment runs recorded yet — run "
            "<code>researchforge experiment run &lt;plan-id&gt;</code>, then rebuild this "
            "dashboard.</p>"
        )
    else:
        sections.append(_bar_section(experiments, executions, ranking, baseline, primary))
        sections.append(_scatter_section(spec, baseline, ranking, primary))
        sections.append(_funnel_section(experiments, executions))
        sections.append(_spread_section(spec, baseline, experiments, executions, primary))
        sections.append(_table_section(experiments, executions, primary))
        if not any(e.benchmark_stage is BenchmarkStage.VALIDATION for e in executions):
            sections.append(f"<div class='caveat'>{escape(ONE_OFF_CAVEAT)}</div>")

    deliverables = list_deliverables(conn)
    if deliverables:
        items = "".join(
            f"<li>{escape(d.kind.value)}: <code>{escape(d.location)}</code></li>"
            for d in deliverables
        )
        sections.append(f"<h2>Deliverables</h2><ul>{items}</ul>")

    sections.append(
        "<footer>Generated "
        f"{datetime.now(UTC).isoformat(timespec='seconds')} by ResearchForge {__version__} "
        f"from recorded data in <code>.researchforge/researchforge.db</code>. Results were "
        f"measured in {escape(baseline.execution_mode.value)} mode on one machine and may not "
        "generalize beyond the tested conditions.</footer>"
    )

    body = "\n".join(sections)
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>ResearchForge dashboard — {escape(project.name)}</title>"
        f"<style>{DASHBOARD_CSS}</style></head><body>{body}</body></html>"
    )


def _header_section(
    name: str,
    spec: ContractSpec,
    contract: ExperimentContract,
    baseline: BaselineRun,
    run: ExperimentRunGroup | None,
) -> str:
    assert baseline.metrics is not None
    objective = contract.spec.objective
    cards = [
        ("objective", escape(objective.description), ""),
        (
            f"baseline {escape(objective.primary_metric.name)}",
            f"{baseline.metrics.primary_metric.value:g}",
            f"commit {escape(contract.baseline_commit[:12])}",
        ),
    ]
    for metric_name, value in baseline.metrics.secondary_metrics.items():
        cards.append((f"baseline {escape(metric_name)}", f"{value:g}", ""))
    cards.append(
        (
            "contract",
            f"v{contract.contract_version}",
            f"{escape(baseline.execution_mode.value)} mode",
        )
    )
    if run is not None:
        cards.append(("run", escape(run.run_id), escape(run.status.value)))
    rendered = "".join(
        f"<div class='card'><div class='k'>{key}</div><div class='v'>{value}</div>"
        f"<div class='d'>{detail}</div></div>"
        for key, value, detail in cards
    )
    return (
        f"<h1>ResearchForge dashboard — {escape(name)}</h1>"
        "<p class='sub'>Experiments vs the frozen baseline, from recorded data only.</p>"
        f"<div class='cards'>{rendered}</div>"
    )


def _bar_section(
    experiments: list[Experiment],
    executions: list[ExperimentExecution],
    ranking: RankingReport | None,
    baseline: BaselineRun,
    primary: str,
) -> str:
    assert baseline.metrics is not None
    bars = _bars(experiments, executions, ranking)
    if not bars:
        return "<h2>Primary metric</h2><p class='empty'>No measured experiments yet.</p>"
    chart = bar_chart(bars, baseline.metrics.primary_metric.value, primary)
    return f"<h2>Primary metric — every experiment vs baseline</h2>{chart}"


def _scatter_section(
    spec: ContractSpec, baseline: BaselineRun, ranking: RankingReport | None, primary: str
) -> str:
    assert baseline.metrics is not None
    if ranking is None:
        return ""
    rows = [*ranking.candidates, *ranking.rejected]
    charts = []
    secondaries = list(baseline.metrics.secondary_metrics)
    thresholds = {c.name: c for c in spec.objective.hard_constraints}
    for secondary in secondaries:
        points = [
            Point(
                label=row.experiment_id,
                x=row.secondary_values[secondary],
                y=row.primary_value,
                status=row.status.value,
                pareto=row.experiment_id in ranking.pareto_ids,
            )
            for row in rows
            if row.primary_value is not None and secondary in row.secondary_values
        ]
        if not points:
            continue
        constraint = thresholds.get(secondary)
        chart = scatter_chart(
            points,
            baseline=Point(
                label="baseline",
                x=baseline.metrics.secondary_metrics[secondary],
                y=baseline.metrics.primary_metric.value,
                status="baseline",
            ),
            x_label=secondary,
            y_label=primary,
            x_threshold=constraint.value if constraint is not None else None,
            threshold_note=(
                f"{constraint.name} {constraint.operator.value} {constraint.value:g}"
                if constraint is not None
                else None
            ),
        )
        charts.append(f"<h2>Trade-off — {escape(primary)} vs {escape(secondary)}</h2>{chart}")
    return "".join(charts)


def _funnel_section(experiments: list[Experiment], executions: list[ExperimentExecution]) -> str:
    stages, notes = _funnel(experiments, executions)
    return f"<h2>Funnel</h2>{funnel_chart(stages, notes)}"


def _spread_section(
    spec: ContractSpec,
    baseline: BaselineRun,
    experiments: list[Experiment],
    executions: list[ExperimentExecution],
    primary: str,
) -> str:
    assert baseline.metrics is not None
    rows = []
    for experiment in experiments:
        attempts = [
            e
            for e in executions
            if e.experiment_id == experiment.experiment_id
            and e.benchmark_stage is BenchmarkStage.VALIDATION
        ]
        if not attempts:
            continue
        summary = summarize_validation(
            experiment, attempts, baseline, spec.objective.primary_metric.direction
        )
        full_value = _latest_full_value(executions, experiment.experiment_id)
        rows.append(
            SpreadRow(
                label=experiment.experiment_id,
                values=summary.values,
                mean=summary.mean,
                stdev=summary.stdev,
                outcome=summary.outcome.value,
                extra_values=[full_value] if full_value is not None else [],
            )
        )
    if not rows:
        return ""
    chart = spread_chart(rows, baseline.metrics.primary_metric.value, primary)
    return (
        "<h2>Validation spread — repeated runs, not one-offs</h2>"
        f"{chart}<p class='sub'>Filled dots: validation attempts. Hollow dot: the original "
        "full-benchmark value. Tick: mean.</p>"
    )


def _table_section(
    experiments: list[Experiment], executions: list[ExperimentExecution], primary: str
) -> str:
    rows = []
    for experiment in experiments:
        value = _latest_full_value(executions, experiment.experiment_id)
        reason = experiment.decision.reason if experiment.decision else ""
        rows.append(
            "<tr>"
            f"<td>{escape(experiment.experiment_id)}</td>"
            f"<td>{escape(experiment.title)}</td>"
            f"<td>{_badge(experiment.status.value)}</td>"
            f"<td>{escape(_stage_reached(executions, experiment.experiment_id))}</td>"
            f"<td>{value if value is not None else '—'}</td>"
            f"<td>{escape(reason)}</td>"
            "</tr>"
        )
    return (
        "<h2>All experiments</h2><table><thead><tr>"
        f"<th>id</th><th>title</th><th>status</th><th>stage reached</th><th>{escape(primary)} "
        "(full)</th><th>decision</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )
