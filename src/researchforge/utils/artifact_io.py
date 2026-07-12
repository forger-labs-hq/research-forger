"""Safe loading of Claude-authored JSON/YAML artifacts.

Artifacts are untrusted input: size-capped, parsed with safe loaders only,
and required to be a top-level mapping. Everything beyond parsing is
enforced by pydantic validation in the importers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

MAX_ARTIFACT_BYTES = 2_000_000


class ArtifactLoadError(Exception):
    """The file could not be parsed into a top-level mapping."""


def load_artifact(path: Path, max_bytes: int = MAX_ARTIFACT_BYTES) -> dict[str, Any]:
    if not path.is_file():
        raise ArtifactLoadError(f"File not found: {path}")
    if path.stat().st_size > max_bytes:
        raise ArtifactLoadError(f"File exceeds {max_bytes} bytes: {path}")

    text = path.read_text(encoding="utf-8")
    is_json = path.suffix.lower() == ".json"
    try:
        # YAML is a JSON superset, so non-.json files go through safe_load.
        data = json.loads(text) if is_json else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ArtifactLoadError(f"Could not parse {path.name}: {exc}") from exc

    if not isinstance(data, dict):
        raise ArtifactLoadError(
            f"{path.name} must contain a top-level mapping, got {type(data).__name__}."
        )
    return data
