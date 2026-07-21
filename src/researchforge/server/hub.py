"""The hub: one machine-wide, read-only server for every registered project.

The home page lists all projects from the global registry with their folder
locations; each project's full monitor UI is served under `/p/<slug>/` by
reading that project's own database read-only on demand. No per-project
server processes, no port juggling — new projects appear as soon as they
register (which `researchforge init` does automatically).
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from researchforge import __version__
from researchforge.config.registry import RegistryEntry, find_by_slug, load_registry
from researchforge.server.app import render_dashboard_page
from researchforge.server.data import ProjectState, read_state
from researchforge.server.pages import (
    _PAGE_CSS,
    experiment_page,
    experiments_page,
    overview_page,
    research_page,
    run_page,
    session_page,
)

HUB_REFRESH_SECONDS = 15


def _project_card(entry: RegistryEntry, state: ProjectState | None) -> str:
    """One project on the hub home page; honest about unreadable entries."""
    last_active = entry.last_active[:16].replace("T", " ")
    if state is None:
        reason = "folder moved or deleted" if not entry.exists else "database unreadable"
        return (
            "<div class='card'>"
            f"<div class='k'>{escape(entry.name)} <span class='badge' "
            f"style='background:var(--chart-bad)'>missing</span></div>"
            f"<div class='d'><code>{escape(entry.path)}</code></div>"
            f"<div class='d'>{escape(reason)} · last active {escape(last_active)}</div>"
            "</div>"
        )
    project = state.project
    mode = project.mode.value if project.mode else "mode unset"
    live = "<span class='live'>● live</span> " if state.run_in_progress else ""
    counts = (
        f"{len(state.papers)} papers · {len(state.hypotheses)} hypotheses · "
        f"{len(state.experiments)} experiments"
    )
    return (
        "<div class='card'>"
        f"<div class='k'>{live}<a href='/p/{escape(entry.slug)}/'>{escape(entry.name)}</a> "
        f"<span class='badge' style='background:var(--chart-info)'>"
        f"{escape(project.status.value)}</span></div>"
        f"<div class='d'>{escape(mode)} · {escape(counts)}</div>"
        f"<div class='d'><code>{escape(entry.path)}</code></div>"
        f"<div class='d'>last active {escape(last_active)}</div>"
        "</div>"
    )


def hub_home_page() -> str:
    entries = sorted(load_registry(), key=lambda e: e.last_active, reverse=True)
    cards = []
    for entry in entries:
        state: ProjectState | None = None
        try:
            state = read_state(Path(entry.path))
        except Exception:  # noqa: BLE001 — a broken project must not hide the rest
            state = None
        cards.append(_project_card(entry, state))
    if cards:
        body = f"<div class='cards' style='grid-template-columns:1fr'>{''.join(cards)}</div>"
    else:
        body = (
            "<p class='empty'>No projects registered yet. Initialize one anywhere with "
            "<code>researchforge init</code> (or <code>researchforge -C /some/folder init"
            "</code>) and it appears here.</p>"
        )
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>ResearchForge — all projects</title>"
        f"<meta http-equiv='refresh' content='{HUB_REFRESH_SECONDS}'>"
        f"<style>{_PAGE_CSS}"
        ".card .k a{color:var(--fg);text-decoration:none}"
        ".card .k a:hover{text-decoration:underline}</style></head>"
        f"<body><nav><a href='/' class='active'>All projects</a>"
        f"<span style='margin-left:auto' class='sub'>ResearchForge {__version__} "
        "— hub · read-only</span></nav>"
        f"<h1>Projects</h1><p class='sub'>Every ResearchForge project on this machine, "
        "with where it lives on disk. Newly initialized projects appear automatically."
        f"</p>{body}</body></html>"
    )


def create_hub_app() -> FastAPI:
    app = FastAPI(title="ResearchForge hub", docs_url=None, redoc_url=None)

    def project_state(slug: str) -> ProjectState:
        entry = find_by_slug(slug)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Unknown project: {slug}")
        try:
            state = read_state(Path(entry.path))
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Project '{slug}' is registered at {entry.path} but no longer "
                "readable there (moved or deleted?).",
            ) from exc
        state.link_prefix = f"/p/{slug}"
        return state

    def project_base(slug: str) -> Path:
        entry = find_by_slug(slug)
        assert entry is not None  # project_state ran first
        return Path(entry.path)

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return hub_home_page()

    @app.get("/p/{slug}/", response_class=HTMLResponse)
    @app.get("/p/{slug}", response_class=HTMLResponse)
    def overview(slug: str) -> str:
        return overview_page(project_state(slug))

    @app.get("/p/{slug}/research", response_class=HTMLResponse)
    def research(slug: str) -> str:
        return research_page(project_state(slug))

    @app.get("/p/{slug}/experiments", response_class=HTMLResponse)
    def experiments(slug: str) -> str:
        return experiments_page(project_state(slug))

    @app.get("/p/{slug}/runs/{run_id}", response_class=HTMLResponse)
    def run_detail(slug: str, run_id: str) -> str:
        state = project_state(slug)
        if not any(run.run_id == run_id for run in state.runs):
            raise HTTPException(status_code=404, detail=f"Unknown run: {run_id}")
        return run_page(state, run_id)

    @app.get("/p/{slug}/sessions/{search_run_id}", response_class=HTMLResponse)
    def session_detail(slug: str, search_run_id: str) -> str:
        state = project_state(slug)
        if not any(str(run["run_id"]) == search_run_id for run in state.search_runs):
            raise HTTPException(status_code=404, detail=f"Unknown session: {search_run_id}")
        return session_page(state, search_run_id)

    @app.get("/p/{slug}/experiments/{experiment_id}", response_class=HTMLResponse)
    def experiment_detail(slug: str, experiment_id: str) -> str:
        state = project_state(slug)
        if not any(e.experiment_id == experiment_id for e in state.experiments):
            raise HTTPException(status_code=404, detail=f"Unknown experiment: {experiment_id}")
        return experiment_page(state, experiment_id)

    @app.get("/p/{slug}/dashboard", response_class=HTMLResponse)
    def dashboard(slug: str, run: str | None = None) -> str:
        state = project_state(slug)
        return render_dashboard_page(state, project_base(slug), run)

    @app.get("/p/{slug}/api/state")
    def api_state(slug: str) -> JSONResponse:
        return JSONResponse(project_state(slug).model_dump(mode="json"))

    return app
