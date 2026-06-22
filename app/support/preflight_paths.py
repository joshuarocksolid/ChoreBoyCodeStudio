"""Path helpers for run/package preflight checks (no packaging-layer imports)."""

from __future__ import annotations

import re
from pathlib import Path

_PREFLIGHT_EXCLUDED_CBCS_SUBTREES = ("runs", "logs", "cache")


def sanitize_project_name(name: str) -> str:
    """Convert a human name into a filesystem-safe slug."""
    cleaned = name.strip().lower()
    cleaned = re.sub(r"[^a-z0-9_\-]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip("_")
    return cleaned or "project"


def paths_overlap(a: Path, b: Path) -> bool:
    """Return True if resolved *a* and *b* are identical or nested."""
    resolved_a = a.resolve()
    resolved_b = b.resolve()
    if resolved_a == resolved_b:
        return True
    try:
        resolved_a.relative_to(resolved_b)
        return True
    except ValueError:
        pass
    try:
        resolved_b.relative_to(resolved_a)
        return True
    except ValueError:
        pass
    return False


def resolve_entry_path(*, root: Path, entry_file: str) -> tuple[Path | None, str | None]:
    """Resolve an entry file path relative to *root* with clear validation errors."""
    if not entry_file.strip():
        return None, "Entry file must be a non-empty path."
    candidate = Path(entry_file).expanduser()
    resolved_entry = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        resolved_entry.relative_to(root)
    except ValueError:
        return None, f"Entry file must be inside project root: {entry_file}"
    if not resolved_entry.exists() or not resolved_entry.is_file():
        return None, f"Entry file not found in project: {entry_file}"
    return resolved_entry, None


def is_preflight_packaging_excluded_path(rel_path: Path) -> bool:
    """Return True when *rel_path* would be excluded from a package export."""
    parts = rel_path.parts
    if any(part.startswith(".") and part not in {".", ".."} for part in parts):
        return True
    if "__pycache__" in parts:
        return True
    if rel_path.name.endswith((".pyc", ".pyo")):
        return True
    posix_path = rel_path.as_posix()
    for subtree in _PREFLIGHT_EXCLUDED_CBCS_SUBTREES:
        excluded_prefix = f"cbcs/{subtree}"
        if posix_path == excluded_prefix or posix_path.startswith(excluded_prefix + "/"):
            return True
    return False
