"""HTML pages for the monitoring server — same look as the static dashboard."""

from __future__ import annotations

from html import escape

from researchforge import __version__
from researchforge.domain.experiment import BenchmarkStage
from researchforge.reporting.dashboard import DASHBOARD_CSS
from researchforge.reporting.svg_charts import status_color
from researchforge.server.data import ProjectState

_NAV = (
    ("/", "Overview"),
    ("/research", "Research"),
    ("/experiments", "Experiments"),
    ("/dashboard", "Dashboard"),
)

_PAGE_CSS = (
    DASHBOARD_CSS
    + """
nav { display: flex; gap: 16px; margin-bottom: 20px; padding-bottom: 10px;
  border-bottom: 1px solid var(--grid); }
nav a { color: var(--fg-muted); text-decoration: none; font-weight: 600; }
nav a.active { color: var(--fg); }
.live { color: var(--chart-good); font-weight: 600; }
.next { background: var(--card); border-left: 3px solid var(--chart-info);
  padding: 10px 14px; border-radius: 0 6px 6px 0; font-family: ui-monospace, monospace;
  font-size: 0.9rem; overflow-wrap: anywhere; }
"""
)


def _badge(status: str) -> str:
    return f"<span class='badge' style='background:{status_color(status)}'>{escape(status)}</span>"


def refresh_seconds(state: ProjectState) -> int:
    return 3 if state.run_in_progress else 10


def page_shell(title: str, active: str, body: str, refresh: int | None) -> str:
    nav = "".join(
        f"<a href='{href}'{' class=active' if href == active else ''}>{label}</a>"
        for href, label in _NAV
    )
    meta_refresh = f"<meta http-equiv='refresh' content='{refresh}'>" if refresh else ""
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{escape(title)}</title>{meta_refresh}<style>{_PAGE_CSS}</style></head>"
        f"<body><nav>{nav}<span style='margin-left:auto' class='sub'>ResearchForge "
        f"{__version__} — read-only monitor</span></nav>{body}</body></html>"
    )


def _card(key: str, value: str, detail: str = "") -> str:
    return (
        f"<div class='card'><div class='k'>{escape(key)}</div>"
        f"<div class='v'>{value}</div><div class='d'>{detail}</div></div>"
    )


def overview_page(state: ProjectState) -> str:
    project = state.project
    status_counts: dict[str, int] = {}
    for experiment in state.experiments:
        status_counts[experiment.status.value] = status_counts.get(experiment.status.value, 0) + 1
    cards = [
        _card("project", escape(project.name), escape(project.mode.value if project.mode else "")),
        _card("status", escape(project.status.value)),
        _card("papers", str(len(state.papers))),
        _card(
            "directions",
            str(len(state.landscape.directions) if state.landscape else 0),
        ),
        _card("hypotheses", str(len(state.hypotheses))),
        _card(
            "experiments",
            str(len(state.experiments)),
            " ".join(f"{count} {status}" for status, count in sorted(status_counts.items())),
        ),
    ]
    if state.baseline is not None and state.baseline.metrics is not None:
        cards.append(
            _card(
                f"baseline {escape(state.baseline.metrics.primary_metric.name)}",
                f"{state.baseline.metrics.primary_metric.value:g}",
                escape(state.baseline.execution_mode.value),
            )
        )
    body = [
        f"<h1>{escape(project.name)}</h1>",
        "<p class='sub'>Live view — refreshes automatically; everything is read from "
        "recorded data.</p>",
        f"<div class='cards'>{''.join(cards)}</div>",
        f"<h2>Next action</h2><div class='next'>{escape(state.next_action)}</div>",
    ]
    if state.run_in_progress:
        running = [run for run in state.runs if run.status.value == "in_progress"]
        body.append(
            f"<h2>Now running</h2><p class='live'>● {escape(running[-1].run_id)} in progress "
            f"({escape(running[-1].execution_mode.value)} mode) — this page refreshes every "
            "3 seconds.</p>"
        )
    if state.deliverables:
        items = "".join(
            f"<li>{escape(d.kind.value)}: <code>{escape(d.location)}</code></li>"
            for d in state.deliverables
        )
        body.append(f"<h2>Deliverables</h2><ul>{items}</ul>")
    return page_shell(f"ResearchForge — {project.name}", "/", "".join(body), refresh_seconds(state))


def research_page(state: ProjectState) -> str:
    body = ["<h1>Research</h1>"]
    if not state.papers:
        body.append(
            "<p class='empty'>No papers stored yet — `researchforge research search` starts "
            "the literature pipeline.</p>"
        )
    else:
        rows = "".join(
            f"<tr><td>{paper.relevance_score:.3f}</td><td>{escape(paper.paper_id)}</td>"
            f"<td>{escape(paper.title)}</td></tr>"
            for paper in state.papers
        )
        body.append(
            f"<h2>Papers ({len(state.papers)})</h2><table><thead><tr><th>score</th>"
            f"<th>id</th><th>title</th></tr></thead><tbody>{rows}</tbody></table>"
        )
    if state.landscape is not None:
        body.append(f"<h2>Landscape</h2><p>{escape(state.landscape.summary)}</p>")
        for direction in state.landscape.directions:
            direction_papers = set(direction.paper_ids)
            claims = [c for c in state.landscape.evidence if c.paper_id in direction_papers]
            body.append(
                f"<h2>[{escape(direction.direction_id)}] {escape(direction.name)}</h2>"
                f"<p>{escape(direction.description)}</p>"
                f"<p class='sub'>{len(direction.paper_ids)} paper(s), "
                f"{len(claims)} evidence claim(s)</p>"
            )
    else:
        body.append("<p class='empty'>No research landscape imported yet.</p>")
    if state.hypotheses:
        cards = []
        for hypothesis in state.hypotheses:
            cards.append(
                f"<div class='card'><div class='k'>{escape(hypothesis.hypothesis_id)} "
                f"[{escape(hypothesis.status.value)}]</div>"
                f"<div class='v'>{escape(hypothesis.title)}</div>"
                f"<div class='d'>{escape(hypothesis.claim)}<br>"
                f"evidence: {escape(hypothesis.evidence_status)}; supports: "
                f"{len(hypothesis.supporting_paper_ids)} paper(s)</div></div>"
            )
        body.append(
            f"<h2>Hypotheses ({len(state.hypotheses)})</h2>"
            f"<div class='cards'>{''.join(cards)}</div>"
        )
    else:
        body.append("<p class='empty'>No hypotheses imported yet.</p>")
    return page_shell(
        "ResearchForge — research", "/research", "".join(body), refresh_seconds(state)
    )


def guidance_card(state: ProjectState, message: str) -> str:
    """Honest empty-state: what exists is nothing, and here is the next step."""
    return (
        f"<div class='card'><div class='k'>nothing here yet</div>"
        f"<div class='d'>{escape(message)}</div>"
        f"<div class='next' style='margin-top:8px'>{escape(state.next_action)}</div></div>"
    )


def _duration(started: object, completed: object) -> str:
    from datetime import datetime

    if not isinstance(started, datetime) or not isinstance(completed, datetime):
        return "—"
    return f"{(completed - started).total_seconds():.0f}s"


def run_page(state: ProjectState, run_id: str) -> str:
    """Full history of one run: every stage attempt in chronological order."""
    run = next((r for r in state.runs if r.run_id == run_id), None)
    assert run is not None  # the route 404s before calling us
    executions = sorted(
        (e for e in state.executions if e.run_id == run_id), key=lambda e: e.started_at
    )
    titles = {e.experiment_id: e.title for e in state.experiments}
    live = run.status.value == "in_progress"
    header = "<span class='live'>● live</span> " if live else ""
    body = [
        f"<h1>{header}{escape(run_id)}</h1>",
        f"<p class='sub'>{escape(run.status.value)} · {escape(run.execution_mode.value)} mode · "
        f"started {escape(run.started_at.isoformat(timespec='seconds'))}"
        + (
            f" · finished {escape(run.completed_at.isoformat(timespec='seconds'))}"
            if run.completed_at
            else ""
        )
        + " · <a href='/experiments'>all runs</a></p>",
    ]
    for warning in run.warnings:
        body.append(f"<div class='caveat'>{escape(warning)}</div>")
    if not executions:
        body.append(guidance_card(state, "This run has no recorded stage attempts yet."))
    else:
        rows = []
        for execution in executions:
            value = (
                f"{execution.metrics.primary_metric.value:g}"
                if execution.metrics is not None
                else "—"
            )
            constraints = "—"
            if execution.constraints:
                failed = [c.name for c in execution.constraints if c.passed is False]
                constraints = f"violated: {', '.join(failed)}" if failed else "all passed"
            rows.append(
                "<tr>"
                f"<td>{escape(execution.benchmark_stage.value)}</td>"
                f"<td>{execution.attempt}</td>"
                f"<td>{escape(execution.experiment_id)}<br><span class='sub'>"
                f"{escape(titles.get(execution.experiment_id, ''))}</span></td>"
                f"<td>{_badge(execution.status.value)}</td>"
                f"<td>{value}</td>"
                f"<td>{escape(constraints)}</td>"
                f"<td>{_duration(execution.started_at, execution.completed_at)}</td>"
                f"<td>{escape(execution.failure_reason or '')}</td>"
                "</tr>"
            )
        body.append(
            "<h2>Execution timeline</h2>"
            "<table><thead><tr><th>stage</th><th>#</th><th>experiment</th><th>status</th>"
            "<th>value</th><th>constraints</th><th>duration</th><th>failure</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    body.append(
        f"<p class='sub'><a href='/dashboard?run={escape(run_id)}'>charts for this run →</a></p>"
    )
    return page_shell(
        f"ResearchForge — {run_id}", "/experiments", "".join(body), refresh_seconds(state)
    )


def experiments_page(state: ProjectState) -> str:
    body = ["<h1>Experiments</h1>"]
    if not state.runs:
        body.append(
            guidance_card(
                state,
                "No experiment runs have been recorded for this project yet — the pages "
                "below fill in as soon as the first run starts.",
            )
        )
    baseline_value = (
        state.baseline.metrics.primary_metric.value
        if state.baseline is not None and state.baseline.metrics is not None
        else None
    )
    for run in reversed(state.runs):
        live = run.status.value == "in_progress"
        marker = "<span class='live'>● live</span> " if live else ""
        body.append(
            f"<h2>{marker}<a href='/runs/{escape(run.run_id)}'>{escape(run.run_id)}</a> — "
            f"{escape(run.status.value)} ({escape(run.execution_mode.value)} mode) "
            f"<span class='sub'>· <a href='/runs/{escape(run.run_id)}'>full history</a></span></h2>"
        )
        run_executions = [e for e in state.executions if e.run_id == run.run_id]
        plan_experiments = [e for e in state.experiments if e.plan_id == run.plan_id]
        rows = []
        for experiment in plan_experiments:
            mine = [e for e in run_executions if e.experiment_id == experiment.experiment_id]
            stages = [e.benchmark_stage.value for e in mine]
            latest_value = next(
                (
                    e.metrics.primary_metric.value
                    for e in reversed(mine)
                    if e.metrics is not None and e.benchmark_stage is not BenchmarkStage.SCREENING
                ),
                None,
            )
            delta = ""
            if latest_value is not None and baseline_value:
                delta = f" ({(latest_value - baseline_value) / abs(baseline_value):+.1%})"
            value_text = f"{latest_value:g}{delta}" if latest_value is not None else "—"
            reason = experiment.decision.reason if experiment.decision else ""
            rows.append(
                f"<tr><td>{escape(experiment.experiment_id)}</td>"
                f"<td>{escape(experiment.title)}</td>"
                f"<td>{_badge(experiment.status.value)}</td>"
                f"<td>{escape(', '.join(dict.fromkeys(stages)) or 'queued')}</td>"
                f"<td>{value_text}</td><td>{escape(reason)}</td></tr>"
            )
        body.append(
            "<table><thead><tr><th>id</th><th>title</th><th>status</th><th>stages run</th>"
            "<th>latest value vs baseline</th><th>decision</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    return page_shell(
        "ResearchForge — experiments", "/experiments", "".join(body), refresh_seconds(state)
    )
