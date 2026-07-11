"""Path conventions for ResearchForge's local `.researchforge/` project state.

Phase 0 only needs the directory itself and the sqlite database inside it.
Subdirectories such as `worktrees/`, `artifacts/`, `papers/`, and `reports/`
(see the phased spec's workspace-isolation section) are the responsibility of
later-phase execution code to create lazily on first use — they are
intentionally not created here.
"""

from __future__ import annotations

from pathlib import Path

RESEARCHFORGE_DIR_NAME = ".researchforge"
DB_FILENAME = "researchforge.db"


def researchforge_dir(base: Path | None = None) -> Path:
    """The `.researchforge/` directory for the given base path (default: cwd)."""
    root = base if base is not None else Path.cwd()
    return root / RESEARCHFORGE_DIR_NAME


def db_path(base: Path | None = None) -> Path:
    """Path to the sqlite database file inside `.researchforge/`."""
    return researchforge_dir(base) / DB_FILENAME


def is_initialized(base: Path | None = None) -> bool:
    """Whether `.researchforge/` and its database both exist at `base`."""
    root = researchforge_dir(base)
    return root.is_dir() and db_path(base).is_file()
