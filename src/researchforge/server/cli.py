"""`researchforge serve` — local, read-only live monitor."""

from __future__ import annotations

import webbrowser
from typing import Annotated

import typer

from researchforge.config.paths import is_initialized

INSTALL_HINT = (
    "The monitoring server needs the optional dependencies — install with:\n"
    '  pip install "researchforge[serve]"'
)


def serve_command(
    host: Annotated[
        str, typer.Option("--host", help="Bind address (loopback by default; change with care).")
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8500,
    open_browser: Annotated[
        bool, typer.Option("--open", help="Open the monitor in the default browser.")
    ] = False,
) -> None:
    """Run the live monitoring server (read-only view of this project)."""
    if not is_initialized():
        typer.echo("Not an initialized ResearchForge project. Run `researchforge init`.")
        raise typer.Exit(code=1)
    try:
        import uvicorn

        from researchforge.server.app import create_app
    except ImportError:
        typer.echo(INSTALL_HINT)
        raise typer.Exit(code=1) from None

    if host not in ("127.0.0.1", "localhost", "::1"):
        typer.echo(
            f"WARNING: binding to {host} exposes this project's research notes and results "
            "beyond this machine. The server is read-only, but anyone who can reach it can "
            "read everything."
        )

    url = f"http://{host}:{port}/"
    typer.echo(f"Monitoring at {url} (read-only; Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
