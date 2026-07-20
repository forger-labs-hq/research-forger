"""Configurable research-pipeline knobs (spec: "decisions that should remain configurable").

Precedence: code defaults < `.researchforge/config.json` < CLI flags.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from researchforge.config.paths import config_path


class ResearchSettings(BaseModel):
    min_queries: int = Field(default=3, ge=1)
    max_queries: int = Field(default=8, ge=1)
    max_candidates: int = Field(default=200, ge=10, le=1000)
    selected_papers: int = Field(default=30, ge=5, le=100)
    deep_synthesis_count: int = Field(default=12, ge=1)
    hypothesis_min: int = Field(default=3, ge=1)
    hypothesis_max: int = Field(default=7, ge=1)
    report_dir: str = "reports"
    screening_reject_margin_pct: float = Field(default=10.0, ge=0.0)
    tradeoff_material_pct: float = Field(default=5.0, ge=0.0)
    analytics_enabled: bool = False  # opt-in, local-only (spec §20)
    research_output_dir: str = ".researchforge/research-output"  # `paper package` target


def load_settings(base: Path | None = None) -> ResearchSettings:
    """Load settings, applying overrides from `.researchforge/config.json` if present."""
    path = config_path(base)
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
        return ResearchSettings.model_validate(raw)
    return ResearchSettings()
