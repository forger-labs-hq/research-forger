import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from researchforge.config.settings import ResearchSettings, load_settings


def test_defaults() -> None:
    settings = ResearchSettings()

    assert settings.min_queries == 3
    assert settings.max_queries == 8
    assert settings.max_candidates == 200
    assert settings.selected_papers == 30
    assert settings.hypothesis_min == 3
    assert settings.hypothesis_max == 7


def test_load_settings_without_config_file(tmp_path: Path) -> None:
    settings = load_settings(tmp_path)

    assert settings == ResearchSettings()


def test_load_settings_with_overrides(tmp_path: Path) -> None:
    config_dir = tmp_path / ".researchforge"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({"max_candidates": 100, "selected_papers": 20}), encoding="utf-8"
    )

    settings = load_settings(tmp_path)

    assert settings.max_candidates == 100
    assert settings.selected_papers == 20
    assert settings.min_queries == 3  # default retained


def test_invalid_override_rejected(tmp_path: Path) -> None:
    config_dir = tmp_path / ".researchforge"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(json.dumps({"max_candidates": 99999}), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_settings(tmp_path)
