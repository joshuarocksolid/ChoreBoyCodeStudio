"""Path/layout helpers shared across packaging workflows."""

from __future__ import annotations

import re
from pathlib import Path

from app.packaging.models import PACKAGE_PROFILE_INSTALLABLE, PACKAGE_PROFILE_PORTABLE

_EXCLUDED_RELATIVE_PREFIXES = (
    "cbcs/runs",
    "cbcs/logs",
    "cbcs/cache",
)
_EXCLUDED_DIR_NAMES = {
    "__pycache__",
}
_EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
}


def sanitize_project_name(name: str) -> str:
    """Convert a human name into a filesystem-safe slug."""
    cleaned = name.strip().lower()
    cleaned = re.sub(r"[^a-z0-9_\-]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip("_")
    return cleaned or "project"


def build_launcher_filename(display_name: str) -> str:
    """Return the stable launcher filename for one package."""
    return f"{sanitize_project_name(display_name)}.desktop"


def build_default_install_dirname(display_name: str, version: str) -> str:
    """Return the versioned default install directory name."""
    safe_name = sanitize_project_name(display_name)
    safe_version = version.strip() or "dev"
    return f"{safe_name}_v{safe_version}"


def build_artifact_root_name(display_name: str, version: str, profile: str) -> str:
    """Return the export folder name for one profile."""
    safe_name = sanitize_project_name(display_name)
    safe_version = version.strip() or "dev"
    if profile == PACKAGE_PROFILE_PORTABLE:
        return f"{safe_name}_portable_v{safe_version}"
    return f"{safe_name}_installer_v{safe_version}"


def build_installer_launcher_filename(display_name: str) -> str:
    """Return the launcher used to start the installer package itself."""
    return f"install_{sanitize_project_name(display_name)}.desktop"


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


def should_exclude_relative_path(rel_path: Path) -> bool:
    """Return True if *rel_path* should be excluded from a package export."""
    parts = rel_path.parts
    if any(part in _EXCLUDED_DIR_NAMES for part in parts):
        return True
    if any(part.startswith(".") for part in parts if part not in {".", ".."}):
        return True
    posix_path = rel_path.as_posix()
    for excluded in _EXCLUDED_RELATIVE_PREFIXES:
        if posix_path == excluded or posix_path.startswith(excluded + "/"):
            return True
    if rel_path.suffix in _EXCLUDED_SUFFIXES:
        return True
    return False
