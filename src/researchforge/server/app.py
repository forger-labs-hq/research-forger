"""FastAPI app factory for `researchforge serve` (import requires the extra)."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from researchforge.server.data import ProjectState, open_readonly, read_state
from researchforge.server.pages import (
    experiments_page,
    guidance_card,
    overview_page,
    page_shell,
    refresh_seconds,
    research_page,
    run_page,
    session_page,
)


def create_app(base: Path | None = None) -> FastAPI:
    app = FastAPI(title="ResearchForge monitor", docs_url=None, redoc_url=None)

    def state_or_404() -> ProjectState:
        try:
            return read_state(base)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail="No initialized ResearchForge project here — run `researchforge init`.",
            ) from exc

    @app.get("/", response_class=HTMLResponse)
    def overview() -> str:
        return overview_page(state_or_404())

    @app.get("/research", response_class=HTMLResponse)
    def research() -> str:
        return research_page(state_or_404())

    @app.get("/experiments", response_class=HTMLResponse)
    def experiments() -> str:
        return experiments_page(state_or_404())

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_detail(run_id: str) -> str:
        state = state_or_404()
        if not any(run.run_id == run_id for run in state.runs):
            raise HTTPException(status_code=404, detail=f"Unknown run: {run_id}")
        return run_page(state, run_id)

    @app.get("/sessions/{search_run_id}", response_class=HTMLResponse)
    def session_detail(search_run_id: str) -> str:
        state = state_or_404()
        if not any(str(run["run_id"]) == search_run_id for run in state.search_runs):
            raise HTTPException(status_code=404, detail=f"Unknown session: {search_run_id}")
        return session_page(state, search_run_id)

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(run: str | None = None) -> str:
        from researchforge.reporting.dashboard import build_dashboard
        from researchforge.storage.baseline_repository import get_latest_successful_baseline
        from researchforge.storage.contract_repository import get_active_contract
        from researchforge.storage.experiment_repository import list_runs

        state = state_or_404()
        with closing(open_readonly(base)) as conn:
            if get_active_contract(conn) is None or get_latest_successful_baseline(conn) is None:
                body = "<h1>Dashboard</h1>" + guidance_card(
                    state,
                    "The dashboard needs an approved contract and a successful baseline "
                    "before there is anything honest to chart.",
                )
                return page_shell(
                    "ResearchForge — dashboard", "/dashboard", body, refresh_seconds(state)
                )
            runs = list_runs(conn)
            if run is not None:
                selected = next((r for r in runs if r.run_id == run), None)
                if selected is None:
                    raise HTTPException(status_code=404, detail=f"Unknown run: {run}")
            else:
                selected = runs[-1] if runs else None
            html = build_dashboard(conn, selected)
        # Inject the nav + auto-refresh into the standalone dashboard page.
        from researchforge.server.pages import _NAV

        nav = "".join(
            f"<a href='{href}'{' class=active' if href == '/dashboard' else ''}>{label}</a>"
            for href, label in _NAV
        )
        nav_css = (
            "<style>nav{display:flex;gap:16px;margin-bottom:20px;padding-bottom:10px;"
            "border-bottom:1px solid var(--grid)}nav a{color:var(--fg-muted);"
            "text-decoration:none;font-weight:600}nav a.active{color:var(--fg)}</style>"
        )
        picker = ""
        if len(runs) > 1 and selected is not None:
            links = " · ".join(
                (
                    f"<strong>{r.run_id}</strong>"
                    if r.run_id == selected.run_id
                    else f"<a href='/dashboard?run={r.run_id}'>{r.run_id}</a>"
                )
                for r in reversed(runs)
            )
            picker = (
                f"<p style='color:var(--fg-muted);font-size:0.85rem'>Charts for run: {links}</p>"
            )
        refresh = f"<meta http-equiv='refresh' content='{refresh_seconds(state)}'>"
        return html.replace("</head>", f"{nav_css}{refresh}</head>").replace(
            "<body>", f"<body><nav>{nav}</nav>{picker}", 1
        )

    @app.get("/api/state")
    def api_state() -> JSONResponse:
        return JSONResponse(state_or_404().model_dump(mode="json"))

    @app.get("/api/runs/{run_id}")
    def api_run(run_id: str) -> JSONResponse:
        state = state_or_404()
        if not any(run.run_id == run_id for run in state.runs):
            raise HTTPException(status_code=404, detail=f"Unknown run: {run_id}")
        executions = [e.model_dump(mode="json") for e in state.executions if e.run_id == run_id]
        return JSONResponse(executions)

    return app
