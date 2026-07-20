"""HTML pages for the monitoring server — same look as the static dashboard."""

from __future__ import annotations

from html import escape

from researchforge import __version__
from researchforge.domain.experiment import BenchmarkStage, ExperimentExecution
from researchforge.domain.paper import Paper
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
details.session { background: var(--card); border-radius: 8px; margin: 10px 0;
  padding: 0 14px; }
details.session > summary { cursor: pointer; padding: 12px 0; font-weight: 600;
  list-style-position: outside; }
details.session > summary .sub { font-weight: 400; }
details.session[open] { padding-bottom: 12px; }
details.session table { background: var(--bg); border-radius: 6px; }
"""
)


def _badge(status: str) -> str:
    return f"<span class='badge' style='background:{status_color(status)}'>{escape(status)}</span>"


def _stage_reached(executions: list[ExperimentExecution], experiment_id: str) -> str:
    order = [BenchmarkStage.SCREENING, BenchmarkStage.FULL, BenchmarkStage.VALIDATION]
    reached = [e.benchmark_stage for e in executions if e.experiment_id == experiment_id]
    if not reached:
        return "never ran"
    return str(max(reached, key=order.index).value)


def refresh_seconds(state: ProjectState) -> int:
    return 3 if state.run_in_progress else 30


# Keeps the reader's place across auto-refreshes: which <details> are open
# (by their stable ids) and the scroll position, per page, in sessionStorage.
# Inline and self-contained — the *live monitor* only; the static
# dashboard.html file stays script-free.
STATE_KEEPER_SCRIPT = """
<script>
(function () {
  var key = 'rf-open:' + location.pathname;
  var scrollKey = 'rf-scroll:' + location.pathname;
  var restoring = true;  // events fired by a restore must not save
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  function restore() {
    restoring = true;
    try {
      var saved = JSON.parse(sessionStorage.getItem(key) || 'null');
      if (saved) {
        document.querySelectorAll('details.session[id]').forEach(function (d) {
          d.open = saved.indexOf(d.id) !== -1;
        });
      }
      var y = sessionStorage.getItem(scrollKey);
      if (y !== null) window.scrollTo(0, parseInt(y, 10));
    } catch (e) {}
    setTimeout(function () { restoring = false; }, 50);
  }
  function save() {
    if (restoring) return;
    try {
      var open = [];
      document.querySelectorAll('details.session[id][open]').forEach(function (d) {
        open.push(d.id);
      });
      sessionStorage.setItem(key, JSON.stringify(open));
      sessionStorage.setItem(scrollKey, String(window.scrollY));
    } catch (e) {}
  }
  restore();
  // The browser applies its own details/scroll restoration after load —
  // re-apply ours afterwards so the recorded state wins.
  addEventListener('pageshow', function () { setTimeout(restore, 0); });
  document.addEventListener('toggle', save, true);
  addEventListener('scroll', save, { passive: true });
  addEventListener('beforeunload', save);
})();
</script>
"""


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
        f"{__version__} — read-only monitor</span></nav>{body}{STATE_KEEPER_SCRIPT}"
        "</body></html>"
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
        _card("research sessions", str(len(state.search_runs))),
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
    body.append(locations_section(state))
    return page_shell(f"ResearchForge — {project.name}", "/", "".join(body), refresh_seconds(state))


def _papers_table(papers: list[Paper]) -> str:
    rows = "".join(
        f"<tr><td>{paper.relevance_score:.3f}</td><td>{escape(paper.paper_id)}</td>"
        f"<td>{escape(paper.title)}</td></tr>"
        for paper in papers
    )
    return (
        "<table><thead><tr><th>score</th><th>id</th><th>title</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _search_session_details(state: ProjectState) -> list[str]:
    papers_by_id = {paper.paper_id: paper for paper in state.papers}
    sections = []
    for index, run in enumerate(reversed(state.search_runs)):
        run_id = str(run["run_id"])
        number = len(state.search_runs) - index
        queries = run.get("queries") or []
        assert isinstance(queries, list)
        created = str(run.get("created_at", ""))[:16].replace("T", " ")
        opened = " open" if index == 0 else ""
        summary = (
            f"Search session #{number} <span class='sub'>· {escape(created)} · "
            f"{len(queries)} quer{'y' if len(queries) == 1 else 'ies'} · "
            f"{run.get('selected_count', 0)} selected</span>"
        )
        inner = [
            "<p class='sub'>"
            + escape(
                f"fetched {run.get('fetched_count', 0)} → deduplicated "
                f"{run.get('deduped_count', 0)} → selected {run.get('selected_count', 0)}"
            )
            + "</p>",
            "<ul>" + "".join(f"<li><code>{escape(str(q))}</code></li>" for q in queries) + "</ul>",
        ]
        linked = [
            papers_by_id[pid]
            for pid in state.search_run_papers.get(run_id, [])
            if pid in papers_by_id
        ]
        if linked:
            inner.append(_papers_table(sorted(linked, key=lambda p: -p.relevance_score)))
        else:
            inner.append(
                "<p class='empty'>Papers for this session are not attributed — it was "
                "recorded by an earlier ResearchForge version.</p>"
            )
        inner.append(f"<p class='sub'><a href='/sessions/{escape(run_id)}'>open session →</a></p>")
        sections.append(
            f"<details class='session' id='session-{escape(run_id)}'{opened}>"
            f"<summary>{summary}</summary>{''.join(inner)}</details>"
        )
    return sections


def research_page(state: ProjectState) -> str:
    body = ["<h1>Research</h1>"]
    if not state.search_runs and not state.papers:
        body.append(
            guidance_card(
                state,
                "No research sessions yet — `researchforge research search` starts the "
                "literature pipeline.",
            )
        )
    if state.search_runs:
        body.append(f"<h2>Research sessions ({len(state.search_runs)})</h2>")
        body.extend(_search_session_details(state))
    if state.papers:
        body.append(
            f"<details class='session' id='all-papers'><summary>All stored papers "
            f"({len(state.papers)})</summary>{_papers_table(state.papers)}</details>"
        )
    if state.landscape is not None:
        body.append(_landscape_details(state))
    else:
        body.append("<p class='empty'>No research landscape imported yet.</p>")
    if state.hypotheses:
        body.append(
            f"<details class='session' open id='hypotheses'>"
            f"<summary>Hypotheses ({len(state.hypotheses)})"
            f"</summary>{''.join(_hypothesis_details(h) for h in state.hypotheses)}</details>"
        )
    else:
        body.append("<p class='empty'>No hypotheses imported yet.</p>")
    return page_shell(
        "ResearchForge — research", "/research", "".join(body), refresh_seconds(state)
    )


def _bullets(heading: str, items: list[str]) -> str:
    """A titled bullet list, or nothing when the artifact recorded none."""
    if not items:
        return ""
    rendered = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f"<p class='sub' style='margin:8px 0 2px'>{escape(heading)}</p><ul>{rendered}</ul>"


def _direction_details(direction: object, landscape: object) -> str:
    from researchforge.domain.landscape import ResearchDirection, ResearchLandscape

    assert isinstance(direction, ResearchDirection) and isinstance(landscape, ResearchLandscape)
    direction_papers = set(direction.paper_ids)
    claims = [c for c in landscape.evidence if c.paper_id in direction_papers]
    claim_items = [
        f"{c.claim} ({c.evidence_type.value}, {c.extraction_confidence.value} confidence)"
        for c in claims
    ]
    return (
        f"<details class='session' id='{escape(direction.direction_id)}'>"
        f"<summary>[{escape(direction.direction_id)}] "
        f"{escape(direction.name)} <span class='sub'>· {len(direction.paper_ids)} paper(s) "
        f"· {len(claims)} claim(s)</span></summary>"
        f"<p>{escape(direction.description)}</p>"
        + _bullets("Established findings", direction.established_findings)
        + _bullets("Contradictions", direction.contradictions)
        + _bullets("Limitations", direction.limitations)
        + _bullets("Underexplored aspects", direction.underexplored_aspects)
        + _bullets("Evidence claims", claim_items)
        + _bullets("Papers", direction.paper_ids)
        + "</details>"
    )


def _landscape_details(state: ProjectState) -> str:
    assert state.landscape is not None
    landscape = state.landscape
    sections = [f"<p>{escape(landscape.summary)}</p>"]
    for direction in landscape.directions:
        sections.append(_direction_details(direction, landscape))
    if landscape.paper_annotations:
        annotations = []
        for note in landscape.paper_annotations:
            annotations.append(
                f"<details class='session' id='ann-{escape(note.paper_id)}'>"
                f"<summary>{escape(note.paper_id)} "
                f"<span class='sub'>· evidence: {escape(note.evidence_strength.value)}"
                f"</span></summary><p>{escape(note.method_summary)}</p>"
                + _bullets("Reported findings", note.reported_findings)
                + _bullets("Limitations", note.limitations)
                + (
                    f"<p class='sub'>Repository relevance: {escape(note.repository_relevance)}</p>"
                    if note.repository_relevance
                    else ""
                )
                + "</details>"
            )
        sections.append(
            f"<details class='session' id='annotations'><summary>Deep paper synthesis "
            f"({len(landscape.paper_annotations)})</summary>{''.join(annotations)}</details>"
        )
    return (
        f"<details class='session' open id='landscape'><summary>Landscape "
        f"<span class='sub'>· {len(landscape.directions)} direction(s)</span></summary>"
        f"{''.join(sections)}</details>"
    )


def _hypothesis_details(hypothesis: object) -> str:
    from researchforge.domain.hypothesis import Hypothesis

    assert isinstance(hypothesis, Hypothesis)
    impact = hypothesis.expected_impact
    impact_text = (
        f"{impact.metric} ({impact.direction})" if impact.metric else str(impact.direction)
    )
    facts = (
        f"evidence: {hypothesis.evidence_status} · feasibility: "
        f"{hypothesis.feasibility.value} · effort: {hypothesis.estimated_effort.value} · "
        f"novelty confidence: {hypothesis.novelty_confidence.value} · expected impact: "
        f"{impact_text}"
        + (
            f" · ~{hypothesis.estimated_experiment_count} experiment(s)"
            if hypothesis.estimated_experiment_count
            else ""
        )
    )
    return (
        f"<details class='session' id='{escape(hypothesis.hypothesis_id)}'>"
        f"<summary>{escape(hypothesis.hypothesis_id)} "
        f"{escape(hypothesis.title)} <span class='sub'>· {escape(hypothesis.status.value)}"
        f"</span></summary>"
        f"<p><strong>Claim:</strong> {escape(hypothesis.claim)}</p>"
        f"<p><strong>Rationale:</strong> {escape(hypothesis.rationale)}</p>"
        f"<p><strong>Proposed experiment:</strong> {escape(hypothesis.proposed_experiment)}</p>"
        f"<p class='sub'>{escape(facts)}</p>"
        + _bullets("Supporting papers", hypothesis.supporting_paper_ids)
        + _bullets("Contradicting papers", hypothesis.contradicting_paper_ids)
        + _bullets("Repository observations", hypothesis.repository_observations)
        + _bullets("Limitations", hypothesis.limitations)
        + "</details>"
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
    for index, run in enumerate(reversed(state.runs)):
        live = run.status.value == "in_progress"
        marker = "<span class='live'>● live</span> " if live else ""
        opened = " open" if index == 0 or live else ""
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
        summary = (
            f"{marker}{escape(run.run_id)} <span class='sub'>· {escape(run.status.value)} · "
            f"{escape(run.execution_mode.value)} mode · {len(plan_experiments)} experiment(s) · "
            f"<a href='/runs/{escape(run.run_id)}'>full history</a></span>"
        )
        table = (
            "<table><thead><tr><th>id</th><th>title</th><th>status</th><th>stages run</th>"
            "<th>latest value vs baseline</th><th>decision</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
        body.append(
            f"<details class='session' id='{escape(run.run_id)}'{opened}>"
            f"<summary>{summary}</summary>{table}</details>"
        )
    return page_shell(
        "ResearchForge — experiments", "/experiments", "".join(body), refresh_seconds(state)
    )


def session_page(state: ProjectState, run_id: str) -> str:
    """One research session and everything honestly connected to it.

    The landscape/hypotheses are synthesized from all stored papers, so the
    sections below are labeled by the computable relationship: directions
    and hypotheses *citing* this session's papers, and the experiments that
    tested those hypotheses.
    """
    run = next((r for r in state.search_runs if str(r["run_id"]) == run_id), None)
    assert run is not None  # the route 404s before calling us
    number = next(
        index + 1 for index, r in enumerate(state.search_runs) if str(r["run_id"]) == run_id
    )
    queries = run.get("queries") or []
    assert isinstance(queries, list)
    created = str(run.get("created_at", ""))[:16].replace("T", " ")
    papers_by_id = {paper.paper_id: paper for paper in state.papers}
    session_paper_ids = set(state.search_run_papers.get(run_id, []))
    session_papers = [papers_by_id[pid] for pid in session_paper_ids if pid in papers_by_id]

    body = [
        f"<h1>Search session #{number}</h1>",
        f"<p class='sub'>{escape(created)} · "
        + escape(
            f"fetched {run.get('fetched_count', 0)} → deduplicated "
            f"{run.get('deduped_count', 0)} → selected {run.get('selected_count', 0)}"
        )
        + " · <a href='/research'>all research</a></p>",
        "<ul>" + "".join(f"<li><code>{escape(str(q))}</code></li>" for q in queries) + "</ul>",
        f"<h2>Papers this session selected ({len(session_papers)})</h2>",
    ]
    if session_papers:
        body.append(_papers_table(sorted(session_papers, key=lambda p: -p.relevance_score)))
    else:
        body.append(
            "<p class='empty'>Papers for this session are not attributed — it was "
            "recorded by an earlier ResearchForge version.</p>"
        )

    if state.landscape is not None and session_paper_ids:
        citing = [d for d in state.landscape.directions if set(d.paper_ids) & session_paper_ids]
        if citing:
            body.append(f"<h2>Directions citing this session's papers ({len(citing)})</h2>")
            body.extend(_direction_details(d, state.landscape) for d in citing)

    citing_hypotheses = [
        h
        for h in state.hypotheses
        if (set(h.supporting_paper_ids) | set(h.contradicting_paper_ids)) & session_paper_ids
    ]
    if citing_hypotheses:
        body.append(f"<h2>Hypotheses citing this session's papers ({len(citing_hypotheses)})</h2>")
        body.extend(_hypothesis_details(h) for h in citing_hypotheses)

    hypothesis_ids = {h.hypothesis_id for h in citing_hypotheses}
    followed = [e for e in state.experiments if e.hypothesis_id in hypothesis_ids]
    if followed:
        run_by_plan = {r.plan_id: r.run_id for r in state.runs}
        rows = []
        for experiment in followed:
            exp_run = run_by_plan.get(experiment.plan_id)
            links = (
                f"<a href='/runs/{escape(exp_run)}'>history</a> · "
                f"<a href='/dashboard?run={escape(exp_run)}'>charts</a>"
                if exp_run
                else "—"
            )
            rows.append(
                f"<tr><td>{escape(experiment.experiment_id)}</td>"
                f"<td>{escape(experiment.title)}</td>"
                f"<td>{_badge(experiment.status.value)}</td>"
                f"<td>{_stage_reached(state.executions, experiment.experiment_id)}</td>"
                f"<td>{links}</td></tr>"
            )
        body.append(
            f"<h2>Experiments that followed ({len(followed)})</h2>"
            "<table><thead><tr><th>id</th><th>title</th><th>status</th>"
            "<th>stage reached</th><th>links</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )

    return page_shell(
        f"ResearchForge — session #{number}", "/research", "".join(body), refresh_seconds(state)
    )


def experiment_page(state: ProjectState, experiment_id: str) -> str:
    """Everything recorded about one experiment: the click-through from the
    tree, run pages, and results tables."""
    experiment = next(e for e in state.experiments if e.experiment_id == experiment_id)
    executions = sorted(
        (e for e in state.executions if e.experiment_id == experiment_id),
        key=lambda e: e.started_at,
    )
    hypothesis = next(
        (h for h in state.hypotheses if h.hypothesis_id == experiment.hypothesis_id), None
    )
    children = [e for e in state.experiments if e.parent_experiment_id == experiment_id]
    parent = next(
        (e for e in state.experiments if e.experiment_id == experiment.parent_experiment_id),
        None,
    )
    baseline_value = (
        state.baseline.metrics.primary_metric.value
        if state.baseline is not None and state.baseline.metrics is not None
        else None
    )

    def latest_value(eid: str) -> float | None:
        return next(
            (
                e.metrics.primary_metric.value
                for e in reversed(state.executions)
                if e.experiment_id == eid
                and e.metrics is not None
                and e.benchmark_stage is not BenchmarkStage.SCREENING
            ),
            None,
        )

    value = latest_value(experiment_id)
    cards = [_card("status", _badge(experiment.status.value))]
    if value is not None:
        cards.append(_card("score", f"{value:g}"))
        if baseline_value:
            cards.append(
                _card(
                    "vs baseline",
                    f"{(value - baseline_value) / abs(baseline_value):+.1%}",
                    f"baseline {baseline_value:g}",
                )
            )
        parent_value = latest_value(parent.experiment_id) if parent else None
        if parent is not None and parent_value is not None:
            cards.append(
                _card(
                    "vs parent",
                    f"{(value - parent_value) / abs(parent_value):+.1%}",
                    f"{parent.experiment_id} at {parent_value:g}",
                )
            )
    run_id = next((e.run_id for e in executions), None)

    body = [
        f"<h1>{escape(experiment_id)} — {escape(experiment.title)}</h1>",
        f"<p class='sub'>{escape(experiment.change_summary)}"
        + (
            f" · <a href='/runs/{escape(run_id)}'>run history</a> · "
            f"<a href='/dashboard?run={escape(run_id)}'>charts</a>"
            if run_id
            else ""
        )
        + "</p>",
        f"<div class='cards'>{''.join(cards)}</div>",
    ]
    if hypothesis is not None:
        body.append(
            f"<h2>Hypothesis</h2><p><strong>{escape(hypothesis.hypothesis_id)}</strong> — "
            f"{escape(hypothesis.claim)}</p>"
        )
    lineage = []
    if parent is not None:
        lineage.append(
            f"<li>parent: <a href='/experiments/{escape(parent.experiment_id)}'>"
            f"{escape(parent.experiment_id)}</a> ({escape(parent.title)}, "
            f"{escape(parent.status.value)})</li>"
        )
    for child in children:
        child_value = latest_value(child.experiment_id)
        value_text = f" at {child_value:g}" if child_value is not None else ""
        lineage.append(
            f"<li>child: <a href='/experiments/{escape(child.experiment_id)}'>"
            f"{escape(child.experiment_id)}</a> ({escape(child.title)}, "
            f"{escape(child.status.value)}{value_text})</li>"
        )
    if lineage:
        body.append(f"<h2>Lineage</h2><ul>{''.join(lineage)}</ul>")
    if experiment.decision is not None:
        body.append(
            f"<h2>Decision</h2><p>{escape(experiment.decision.outcome.value)} — "
            f"{escape(experiment.decision.reason)}</p>"
        )
    body.append(
        "<h2>Change</h2><ul>"
        + "".join(f"<li><code>{escape(f)}</code></li>" for f in experiment.changed_files)
        + "</ul>"
    )
    if executions:
        rows = []
        for execution in executions:
            metric = (
                f"{execution.metrics.primary_metric.value:g}"
                if execution.metrics is not None
                else "—"
            )
            constraints = "—"
            if execution.constraints:
                failed = [c.name for c in execution.constraints if c.passed is False]
                constraints = f"violated: {', '.join(failed)}" if failed else "all passed"
            rows.append(
                f"<tr><td>{escape(execution.benchmark_stage.value)}</td>"
                f"<td>{execution.attempt}</td>"
                f"<td>{_badge(execution.status.value)}</td>"
                f"<td>{metric}</td><td>{escape(constraints)}</td>"
                f"<td>{_duration(execution.started_at, execution.completed_at)}</td>"
                f"<td>{escape(execution.failure_reason or '')}</td></tr>"
            )
        body.append(
            "<h2>Executions</h2><table><thead><tr><th>stage</th><th>#</th><th>status</th>"
            "<th>value</th><th>constraints</th><th>duration</th><th>failure</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
        artifact_dirs = sorted({e.artifacts.diff_path.rsplit("/", 1)[0] for e in executions})
        body.append(
            "<h2>Artifacts on disk</h2><ul>"
            + "".join(f"<li><code>{escape(d)}</code></li>" for d in artifact_dirs)
            + "</ul>"
        )
    return page_shell(
        f"ResearchForge — {experiment_id}", "/experiments", "".join(body), refresh_seconds(state)
    )


def locations_section(state: ProjectState) -> str:
    """Where everything lives on disk (Overview page)."""
    from researchforge.config.paths import (
        artifacts_dir,
        experiments_dir,
        reports_dir,
        researchforge_dir,
        synthesis_dir,
        worktrees_dir,
    )
    from researchforge.config.settings import load_settings

    repo = state.project.repository.path or "."
    entries = [
        ("repository", repo),
        ("state", str(researchforge_dir())),
        ("worktrees", str(worktrees_dir())),
        ("artifacts", str(artifacts_dir())),
        ("reports", str(reports_dir())),
        ("synthesis staging", str(synthesis_dir())),
        ("experiments staging", str(experiments_dir())),
        ("research output", load_settings().research_output_dir),
    ]
    items = "".join(
        f"<li>{escape(label)}: <code>{escape(value)}</code></li>" for label, value in entries
    )
    return (
        "<details class='session' id='locations'><summary>Locations "
        "<span class='sub'>· where everything lives on disk</span></summary>"
        f"<ul>{items}</ul>"
        "<p class='sub'>`researchforge paths --json` prints the same map.</p></details>"
    )
