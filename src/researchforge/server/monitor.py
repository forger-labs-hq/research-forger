"""Background-monitor bookkeeping: ports, pid file, spawn/stop.

The background monitor is a detached `researchforge serve` process recorded
in `.researchforge/monitor.json` so other commands (and later sessions) can
find, reuse, or stop it. Everything is stale-pid tolerant: a recorded
monitor whose process is gone is treated as not running.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from researchforge.config.paths import researchforge_dir

MONITOR_FILENAME = "monitor.json"
MONITOR_LOG_FILENAME = "monitor.log"
DEFAULT_PORT = 9000


class MonitorRecord(BaseModel):
    pid: int
    url: str
    host: str
    port: int
    started_at: str


def monitor_path(base: Path | None = None) -> Path:
    return researchforge_dir(base) / MONITOR_FILENAME


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


def read_monitor(base: Path | None = None) -> MonitorRecord | None:
    """The recorded monitor, or None when absent or its process is gone."""
    path = monitor_path(base)
    if not path.is_file():
        return None
    try:
        record = MonitorRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if not _pid_alive(record.pid):
        return None
    return record


def pick_port(host: str, preferred: int) -> int:
    """The preferred port if free, else the next free port the OS hands out."""
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, candidate))
            except OSError:
                continue
            return int(probe.getsockname()[1])
    raise OSError(f"no free port on {host}")


def spawn_background_monitor(host: str, port: int, base: Path | None = None) -> MonitorRecord:
    """Start a detached foreground `serve` and record it; caller checked deps."""
    root = base if base is not None else Path.cwd()
    log_path = researchforge_dir(base) / MONITOR_LOG_FILENAME
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        process = subprocess.Popen(  # noqa: S603 — our own CLI, fixed argv
            [sys.executable, "-m", "researchforge", "serve", "--port", str(port), "--foreground"],
            cwd=root,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    record = MonitorRecord(
        pid=process.pid,
        url=f"http://{host}:{port}/",
        host=host,
        port=port,
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    monitor_path(base).write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return record


def stop_monitor(base: Path | None = None) -> MonitorRecord | None:
    """Terminate the recorded monitor; returns what was stopped (or None)."""
    record = read_monitor(base)
    monitor_path(base).unlink(missing_ok=True)
    if record is None:
        return None
    try:
        os.kill(record.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return None
    return record


def ensure_background_monitor(base: Path | None = None) -> MonitorRecord | None:
    """Reuse the live monitor or spawn one; None when the extra is missing."""
    existing = read_monitor(base)
    if existing is not None:
        return existing
    try:
        import uvicorn  # noqa: F401

        import researchforge.server.app  # noqa: F401
    except ImportError:
        return None
    host = "127.0.0.1"
    return spawn_background_monitor(host, pick_port(host, DEFAULT_PORT), base)
