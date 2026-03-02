"""Deterministic path helpers for application bootstrap."""

from pathlib import Path
import tempfile
from typing import Optional, Union

from app.core import constants

PathInput = Union[str, Path]


def resolve_app_root() -> Path:
    """Return the repository root based on this module location."""
    return Path(__file__).resolve().parents[2]


def resolve_global_state_root(state_root: Optional[PathInput] = None) -> Path:
    """Return the global app state root path."""
    if state_root is not None:
        return _normalize_absolute_path(state_root, "state_root")
    return Path.home().expanduser().resolve() / constants.GLOBAL_STATE_DIRNAME


def global_settings_path(state_root: Optional[PathInput] = None) -> Path:
    """Return the global settings file path."""
    return _global_state_child(constants.GLOBAL_SETTINGS_FILENAME, state_root)


def global_recent_projects_path(state_root: Optional[PathInput] = None) -> Path:
    """Return the global recent-projects file path."""
    return _global_state_child(constants.GLOBAL_RECENT_PROJECTS_FILENAME, state_root)


def global_logs_dir(state_root: Optional[PathInput] = None) -> Path:
    """Return the global logs directory path."""
    return _global_state_child(constants.GLOBAL_LOGS_DIRNAME, state_root)


def global_cache_dir(state_root: Optional[PathInput] = None) -> Path:
    """Return the global cache directory path."""
    return _global_state_child(constants.GLOBAL_CACHE_DIRNAME, state_root)


def global_crash_reports_dir(state_root: Optional[PathInput] = None) -> Path:
    """Return the global crash reports directory path."""
    return _global_state_child(constants.GLOBAL_CRASH_REPORTS_DIRNAME, state_root)


def global_state_db_path(state_root: Optional[PathInput] = None) -> Path:
    """Return the optional global SQLite state path."""
    return _global_state_child(constants.GLOBAL_STATE_DB_FILENAME, state_root)


def global_app_log_path(state_root: Optional[PathInput] = None) -> Path:
    """Return the editor app log path."""
    return global_logs_dir(state_root) / constants.APP_LOG_FILENAME


def resolve_temp_root(temp_root: Optional[PathInput] = None) -> Path:
    """Return namespaced temp root for app-owned temporary files."""
    if temp_root is not None:
        return _normalize_absolute_path(temp_root, "temp_root")
    return Path(tempfile.gettempdir()).resolve() / constants.TEMP_NAMESPACE_DIRNAME


def ensure_directory(path: PathInput) -> Path:
    """Create a directory if missing and return the path."""
    directory = _normalize_absolute_path(path, "path")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def project_cbcs_dir(project_root: PathInput) -> Path:
    """Return the .cbcs metadata directory inside a project root."""
    return _normalize_project_root(project_root) / constants.PROJECT_META_DIRNAME


def project_manifest_path(project_root: PathInput) -> Path:
    """Return the canonical project manifest path."""
    return project_cbcs_dir(project_root) / constants.PROJECT_MANIFEST_FILENAME


def project_runs_dir(project_root: PathInput) -> Path:
    """Return the per-project runs metadata directory path."""
    return project_cbcs_dir(project_root) / constants.PROJECT_RUNS_DIRNAME


def project_cache_dir(project_root: PathInput) -> Path:
    """Return the per-project cache directory path."""
    return project_cbcs_dir(project_root) / constants.PROJECT_CACHE_DIRNAME


def resolve_project_path(project_root: PathInput, relative_path: PathInput) -> Path:
    """Resolve a path relative to project root without using CWD."""
    root = _normalize_project_root(project_root)
    candidate = Path(relative_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (root / candidate).resolve()


def _normalize_project_root(project_root: PathInput) -> Path:
    return _normalize_absolute_path(project_root, "project_root")


def _global_state_child(name: str, state_root: Optional[PathInput]) -> Path:
    return resolve_global_state_root(state_root) / name


def _normalize_absolute_path(path: PathInput, field_name: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{field_name} must be an absolute path")
    return candidate.resolve()
