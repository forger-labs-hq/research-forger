"""Code-enforced path protection.

The reusable primitive behind the spec guarantee that an experiment patch
cannot change protected paths. Phase 1C wires `check_changed_paths` into
diff enforcement; contract validation uses `find_overlaps` at approval time.
Prompt instructions can never bypass this — it runs on every changed path
regardless of what proposed the change.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable
from enum import StrEnum

from pydantic import BaseModel

from researchforge.domain.contract import PermissionsSection

IMPLICIT_PROTECTED: tuple[str, ...] = (".researchforge/", ".git/", "researchforge.yaml")

_VALID_PATH = re.compile(r"^[^\0]+$")


class PathGuardError(Exception):
    """A path could not be safely normalized."""


class PathRule(StrEnum):
    PROTECTED = "protected"
    NOT_EDITABLE = "not_editable"
    INVALID = "invalid"


class PathViolation(BaseModel):
    path: str
    rule: PathRule
    matched: str | None = None


class PathCheckResult(BaseModel):
    allowed: bool
    violations: list[PathViolation]


def normalize_change_path(path: str) -> str:
    """Normalize a repo-relative changed path; reject anything escaping the repo."""
    if not path or not _VALID_PATH.match(path):
        raise PathGuardError(f"Empty or invalid path: {path!r}")
    if "\\" in path:
        raise PathGuardError(f"Backslash paths are not allowed: {path!r}")
    if path.startswith("/") or path.startswith("~"):
        raise PathGuardError(f"Absolute paths are not allowed: {path!r}")
    normalized = posixpath.normpath(path)
    if normalized == ".." or normalized.startswith("../") or normalized == ".":
        raise PathGuardError(f"Path escapes the repository: {path!r}")
    return normalized


def _normalize_entry(entry: str) -> str:
    is_dir = entry.endswith("/")
    normalized = normalize_change_path(entry)
    return f"{normalized}/" if is_dir else normalized


def matches_entry(path: str, entry: str) -> bool:
    """Whether normalized `path` matches a permissions entry.

    Entries ending in "/" match the directory and everything under it
    (segment-aware: `src/` matches `src/a.py`, not `src2/a.py`).
    Other entries match that exact file only.
    """
    if entry.endswith("/"):
        prefix = entry.rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return path == entry


def check_changed_paths(changed: Iterable[str], permissions: PermissionsSection) -> PathCheckResult:
    """Check changed paths against the contract's permissions.

    A path violates when it (a) fails normalization, (b) matches any
    protected entry (contract's plus the always-on implicit set), or
    (c) editable_paths is non-empty and it matches none of them.
    """
    protected = [_normalize_entry(e) for e in permissions.protected_paths] + list(
        IMPLICIT_PROTECTED
    )
    editable = [_normalize_entry(e) for e in permissions.editable_paths]

    violations: list[PathViolation] = []
    for raw in changed:
        try:
            path = normalize_change_path(raw)
        except PathGuardError as exc:
            violations.append(PathViolation(path=raw, rule=PathRule.INVALID, matched=str(exc)))
            continue

        protected_hit = next((e for e in protected if matches_entry(path, e)), None)
        if protected_hit is not None:
            violations.append(
                PathViolation(path=raw, rule=PathRule.PROTECTED, matched=protected_hit)
            )
            continue

        if editable and not any(matches_entry(path, e) for e in editable):
            violations.append(PathViolation(path=raw, rule=PathRule.NOT_EDITABLE))

    return PathCheckResult(allowed=not violations, violations=violations)


def find_overlaps(editable: list[str], protected: list[str]) -> list[tuple[str, str]]:
    """Pairs of (editable, protected) entries where one contains the other."""
    overlaps: list[tuple[str, str]] = []
    for e in editable:
        for p in protected:
            e_norm, p_norm = _normalize_entry(e), _normalize_entry(p)
            e_path, p_path = e_norm.rstrip("/"), p_norm.rstrip("/")
            if matches_entry(e_path, p_norm) or matches_entry(p_path, e_norm) or e_path == p_path:
                overlaps.append((e, p))
    return overlaps
