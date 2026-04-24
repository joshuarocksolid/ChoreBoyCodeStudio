"""Recent-project persistence helpers for project-first workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.bootstrap.paths import PathInput, global_recent_projects_path
from app.core.errors import ProjectStructureValidationError
from app.persistence.settings_store import load_json_object, save_json_object
from app.project.project_service import validate_openable_project_root

RECENT_PROJECTS_SCHEMA_VERSION = 1
OPEN_RECENT_MENU_LIMIT = 10
_RECENT_PROJECTS_PAYLOAD_DEFAULT: dict[str, object] = {
    "schema_version": RECENT_PROJECTS_SCHEMA_VERSION,
    "projects": [],
}


def load_recent_projects(
    state_root: PathInput | None = None,
    *,
    max_entries: Optional[int] = None,
) -> list[str]:
    """Load, normalize, prune, and persist the recent-project list.

    When *max_entries* is ``None`` (the default) the full history is returned.
    """
    if max_entries is not None:
        _validate_max_entries(max_entries)
    recents_path = global_recent_projects_path(state_root)
    payload = load_json_object(recents_path, default=_RECENT_PROJECTS_PAYLOAD_DEFAULT)
    projects = _extract_project_list(payload.get("projects"))
    normalized = _normalize_and_dedupe_paths(projects)
    pruned = _prune_invalid_projects(normalized)
    limited = pruned[:max_entries] if max_entries is not None else pruned
    _save_recent_projects_payload(recents_path, limited)
    return limited


def remember_recent_project(
    project_root: PathInput,
    state_root: PathInput | None = None,
    *,
    max_entries: Optional[int] = None,
) -> list[str]:
    """Add a valid project root to recents and return the updated list."""
    if max_entries is not None:
        _validate_max_entries(max_entries)
    resolved_project_root = validate_openable_project_root(project_root)
    recents = load_recent_projects(state_root=state_root, max_entries=max_entries)
    remembered = [str(resolved_project_root)] + [entry for entry in recents if entry != str(resolved_project_root)]
    limited = remembered[:max_entries] if max_entries is not None else remembered
    _save_recent_projects_payload(global_recent_projects_path(state_root), limited)
    return limited


def _extract_project_list(raw_projects: object) -> list[str]:
    if not isinstance(raw_projects, list):
        return []
    return [entry for entry in raw_projects if isinstance(entry, str)]


def _normalize_and_dedupe_paths(project_paths: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for raw_path in project_paths:
        normalized = str(Path(raw_path).expanduser().resolve())
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _prune_invalid_projects(project_paths: list[str]) -> list[str]:
    valid_projects: list[str] = []
    for project_path in project_paths:
        if _is_valid_project_root(project_path):
            valid_projects.append(project_path)
    return valid_projects


def _is_valid_project_root(project_path: str) -> bool:
    try:
        validate_openable_project_root(project_path)
    except (ProjectStructureValidationError, ValueError):
        return False
    return True


def _save_recent_projects_payload(recents_path: Path, projects: list[str]) -> None:
    save_json_object(
        recents_path,
        {
            "schema_version": RECENT_PROJECTS_SCHEMA_VERSION,
            "projects": projects,
        },
    )


def _validate_max_entries(max_entries: int) -> None:
    if max_entries < 1:
        raise ValueError("max_entries must be >= 1.")
