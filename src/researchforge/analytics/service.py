"""Local-only beta analytics (spec §20).

Disabled by default. When enabled, coarse events append to
`.researchforge/analytics.jsonl` — event name, timestamp, ok flag, and an
optional short category. Never code, paper text, secrets, metric values, or
logs; nothing is ever transmitted anywhere. The file exists so beta users
can *choose* to share it, and so `researchforge analytics show` can compute
the beta metrics locally. Recording must never break a command: failures to
write are swallowed.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from researchforge.config.paths import config_path, researchforge_dir
from researchforge.config.settings import load_settings

ANALYTICS_FILENAME = "analytics.jsonl"

# The spec §20 event vocabulary; record_event refuses anything else so the
# log can never accumulate ad-hoc payloads.
EVENTS = frozenset(
    {
        "initialized",
        "doctor_passed",
        "project_created",
        "repo_scanned",
        "papers_retrieved",
        "landscape_imported",
        "hypotheses_imported",
        "contract_approved",
        "baseline_completed",
        "experiment_started",
        "experiment_completed",
        "validated_finding",
        "branch_created",
        "draft_pr_created",
        "report_generated",
        "package_generated",
    }
)


def analytics_path(base: Path | None = None) -> Path:
    return researchforge_dir(base) / ANALYTICS_FILENAME


def is_enabled(base: Path | None = None) -> bool:
    try:
        return load_settings(base).analytics_enabled
    except (OSError, ValueError):
        return False


def set_enabled(enabled: bool, base: Path | None = None) -> None:
    """Flip the opt-in flag in `.researchforge/config.json`, preserving other keys."""
    path = config_path(base)
    raw: dict[str, object] = {}
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
    raw["analytics_enabled"] = enabled
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")


def record_event(
    name: str, ok: bool = True, category: str | None = None, base: Path | None = None
) -> None:
    """Append one coarse event if analytics are enabled; never raise."""
    assert name in EVENTS, f"unknown analytics event: {name}"
    try:
        if not is_enabled(base):
            return
        entry: dict[str, object] = {
            "event": name,
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "ok": ok,
        }
        if category is not None:
            entry["category"] = category
        with analytics_path(base).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        return


def load_events(base: Path | None = None) -> list[dict[str, object]]:
    path = analytics_path(base)
    if not path.is_file():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


class BetaMetrics(BaseModel):
    """Spec §20 key beta metrics, computed locally from the event log."""

    events_recorded: int
    time_to_first_landscape_s: float | None = None
    time_to_baseline_s: float | None = None
    baseline_success_rate: float | None = None
    experiment_completion_rate: float | None = None
    valid_metrics_rate: float | None = None
    validated_findings: int = 0
    branches_created: int = 0
    reports_generated: int = 0
    packages_generated: int = 0
    failure_categories: dict[str, int] = {}


def _first_ts(events: list[dict[str, object]], name: str, ok_only: bool = False) -> datetime | None:
    for event in events:
        if event.get("event") == name and (not ok_only or event.get("ok")):
            return datetime.fromisoformat(str(event["ts"]))
    return None


def _rate(events: list[dict[str, object]], name: str) -> float | None:
    matching = [e for e in events if e.get("event") == name]
    if not matching:
        return None
    return sum(1 for e in matching if e.get("ok")) / len(matching)


def compute_metrics(base: Path | None = None) -> BetaMetrics:
    events = load_events(base)
    created = _first_ts(events, "project_created")
    landscape = _first_ts(events, "landscape_imported", ok_only=True)
    baseline = _first_ts(events, "baseline_completed", ok_only=True)

    started = sum(1 for e in events if e.get("event") == "experiment_started")
    completed = [e for e in events if e.get("event") == "experiment_completed"]

    failure_categories = Counter(
        str(e.get("category", "uncategorized"))
        for e in events
        if not e.get("ok") and e.get("event") in ("baseline_completed", "experiment_completed")
    )

    return BetaMetrics(
        events_recorded=len(events),
        time_to_first_landscape_s=(
            (landscape - created).total_seconds() if created and landscape else None
        ),
        time_to_baseline_s=((baseline - created).total_seconds() if created and baseline else None),
        baseline_success_rate=_rate(events, "baseline_completed"),
        experiment_completion_rate=(
            sum(1 for e in completed if e.get("ok")) / started if started else None
        ),
        valid_metrics_rate=_rate(events, "experiment_completed"),
        validated_findings=sum(
            1 for e in events if e.get("event") == "validated_finding" and e.get("ok")
        ),
        branches_created=sum(1 for e in events if e.get("event") == "branch_created"),
        reports_generated=sum(1 for e in events if e.get("event") == "report_generated"),
        packages_generated=sum(1 for e in events if e.get("event") == "package_generated"),
        failure_categories=dict(failure_categories),
    )
