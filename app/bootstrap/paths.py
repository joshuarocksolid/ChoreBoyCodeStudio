"""Deterministic path helpers for application bootstrap."""

from pathlib import Path
import os
import tempfile
from typing import Optional, Tuple

from app.bootstrap.hidden_path_policy import (
    PathInput,
    normalize_state_root_identity,
    probe_hidden_path_support,
)
from app.core import constants

PRODUCT_STATE_XDG_PARENT = Path("/home/default/.local/share/FreeCAD")
PRODUCT_STATE_CACHE_PARENT = Path("/home/default/.cache/FreeCAD")
PRODUCT_STATE_VISIBLE_PARENT = Path("/home/default") / constants.GLOBAL_STATE_FREECAD_PARENT_DIRNAME


def resolve_app_root() -> Path:
    """Return the repository root based on this module location."""
    return Path(__file__).resolve().parents[2]


def resolve_global_state_root(state_root: Optional[PathInput] = None) -> Path:
    """Return the global app state root path."""
    if state_root is not None:
        return normalize_state_root_identity(state_root)

    env_root = _state_root_from_env()
    if env_root is not None:
        return env_root

    install_pointer = resolve_app_root().parent / constants.CBCS_STATE_ROOT_POINTER_FILENAME
    pointer_root = _state_root_from_pointer_file(install_pointer)
    if pointer_root is not None:
        return pointer_root

    shop_root = _state_root_from_pointer_file(Path(constants.SHOP_STATE_ROOT_POINTER_PATH))
    if shop_root is not None:
        return shop_root

    legacy = Path.home().expanduser() / constants.GLOBAL_STATE_DIRNAME
    if _is_existing_directory(legacy):
        return normalize_state_root_identity(legacy)

    return normalize_state_root_identity(_probed_product_state_parent() / constants.GLOBAL_STATE_DIRNAME)


def _probed_product_state_parent() -> Path:
    """Return the first product default parent whose live probe accepts the state tree.

    Order and evidence: docs/DISCOVERY.md section 4A. (a) the existing FreeCAD XDG
    tree, (b) the FreeCAD cache tree when hidden and visible directories both probe
    ok there, (c) the visible FreeCAD directory under home.
    """
    if probe_hidden_path_support(PRODUCT_STATE_XDG_PARENT).visible_dir_ok:
        return PRODUCT_STATE_XDG_PARENT
    if _hidden_cache_tree_accepts_state(PRODUCT_STATE_CACHE_PARENT):
        return PRODUCT_STATE_CACHE_PARENT
    return PRODUCT_STATE_VISIBLE_PARENT


def _hidden_cache_tree_accepts_state(cache_parent: Path) -> bool:
    """Probe the cache parent, or its parent when only that exists so ``FreeCAD/`` can be created.

    ``.cache`` itself is never created: a new hidden directory under home is BLOCKED
    (docs/DISCOVERY.md section 4A).
    """
    for existing in (cache_parent, cache_parent.parent):
        if _is_existing_directory(existing):
            result = probe_hidden_path_support(existing)
            return result.hidden_dir_ok and result.visible_dir_ok
    return False


def global_settings_path(state_root: Optional[PathInput] = None) -> Path:
    """Return the global settings file path."""
    return _global_state_child(constants.GLOBAL_SETTINGS_FILENAME, state_root)


def global_recent_projects_path(state_root: Optional[PathInput] = None) -> Path:
    """Return the global recent-projects file path."""
    return _global_state_child(constants.GLOBAL_RECENT_PROJECTS_FILENAME, state_root)


def global_python_console_history_path(state_root: Optional[PathInput] = None) -> Path:
    """Return persisted Python console history file path."""
    return _global_state_child(constants.GLOBAL_PYTHON_CONSOLE_HISTORY_FILENAME, state_root)


def global_logs_dir(state_root: Optional[PathInput] = None) -> Path:
    """Return the global logs directory path."""
    return _global_state_child(constants.GLOBAL_LOGS_DIRNAME, state_root)


def global_cache_dir(state_root: Optional[PathInput] = None) -> Path:
    """Return the global cache directory path."""
    return _global_state_child(constants.GLOBAL_CACHE_DIRNAME, state_root)


def global_history_dir(state_root: Optional[PathInput] = None) -> Path:
    """Return the global local-history directory path."""
    return _global_state_child(constants.GLOBAL_HISTORY_DIRNAME, state_root)


def global_history_index_path(state_root: Optional[PathInput] = None) -> Path:
    """Return the SQLite metadata index path for local history."""
    return global_history_dir(state_root) / constants.GLOBAL_HISTORY_INDEX_FILENAME


def global_history_blobs_dir(state_root: Optional[PathInput] = None) -> Path:
    """Return the content-addressed blob directory for local history."""
    return global_history_dir(state_root) / constants.GLOBAL_HISTORY_BLOBS_DIRNAME


def global_crash_reports_dir(state_root: Optional[PathInput] = None) -> Path:
    """Return the global crash reports directory path."""
    return _global_state_child(constants.GLOBAL_CRASH_REPORTS_DIRNAME, state_root)


def global_trash_dir(state_root: Optional[PathInput] = None) -> Path:
    """Return the global trash directory path."""
    return _global_state_child(constants.GLOBAL_TRASH_DIRNAME, state_root)


def global_trash_files_dir(state_root: Optional[PathInput] = None) -> Path:
    """Return the global trash-files directory path."""
    return global_trash_dir(state_root) / constants.GLOBAL_TRASH_FILES_DIRNAME


def global_trash_info_dir(state_root: Optional[PathInput] = None) -> Path:
    """Return the global trash-metadata directory path."""
    return global_trash_dir(state_root) / constants.GLOBAL_TRASH_INFO_DIRNAME


def global_plugins_dir(state_root: Optional[PathInput] = None) -> Path:
    """Return the global plugins state directory path."""
    return _global_state_child(constants.PLUGINS_STATE_DIRNAME, state_root)


def global_plugins_installed_dir(state_root: Optional[PathInput] = None) -> Path:
    """Return the global installed-plugins directory path."""
    return global_plugins_dir(state_root) / constants.PLUGINS_INSTALLED_DIRNAME


def global_plugins_logs_dir(state_root: Optional[PathInput] = None) -> Path:
    """Return the global plugin logs directory path."""
    return global_plugins_dir(state_root) / constants.PLUGINS_LOGS_DIRNAME


def global_plugins_registry_path(state_root: Optional[PathInput] = None) -> Path:
    """Return the global plugin registry file path."""
    return global_plugins_dir(state_root) / constants.PLUGINS_REGISTRY_FILENAME


def global_plugins_trust_path(state_root: Optional[PathInput] = None) -> Path:
    """Return the global plugin trust-state file path."""
    return global_plugins_dir(state_root) / constants.PLUGINS_TRUST_FILENAME


def bundled_plugins_root() -> Path:
    """Return the repository-bundled plugin directory path."""
    return resolve_app_root() / constants.BUNDLED_PLUGINS_DIRNAME


def plugin_install_dir(plugin_id: str, version: str, state_root: Optional[PathInput] = None) -> Path:
    """Return install directory for one plugin version."""
    return global_plugins_installed_dir(state_root) / _safe_path_component(plugin_id, "plugin_id") / _safe_path_component(version, "version")


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


def try_ensure_directory(path: PathInput) -> Tuple[Optional[Path], Optional[OSError]]:
    """Attempt to create a directory; return (path, None) on success or (None, error) on failure."""
    try:
        return ensure_directory(path), None
    except OSError as exc:
        return None, exc


def project_cbcs_dir(project_root: PathInput) -> Path:
    """Return the cbcs metadata directory inside a project root."""
    return _normalize_project_root(project_root) / constants.PROJECT_META_DIRNAME


def project_manifest_path(project_root: PathInput) -> Path:
    """Return the canonical project manifest path."""
    return project_cbcs_dir(project_root) / constants.PROJECT_MANIFEST_FILENAME


def project_package_config_path(project_root: PathInput) -> Path:
    """Return the canonical per-project packaging config path."""
    return project_cbcs_dir(project_root) / constants.PROJECT_PACKAGE_CONFIG_FILENAME


def project_plugins_path(project_root: PathInput) -> Path:
    """Return the canonical per-project plugin policy path."""
    return project_cbcs_dir(project_root) / constants.PROJECT_PLUGINS_FILENAME


def project_settings_path(project_root: PathInput) -> Path:
    """Return the canonical per-project settings path."""
    return project_cbcs_dir(project_root) / constants.PROJECT_SETTINGS_FILENAME


def project_runs_dir(project_root: PathInput) -> Path:
    """Return the per-project runs metadata directory path."""
    return project_cbcs_dir(project_root) / constants.PROJECT_RUNS_DIRNAME


def project_logs_dir(project_root: PathInput) -> Path:
    """Return the per-project run logs directory path."""
    return project_cbcs_dir(project_root) / constants.PROJECT_LOGS_DIRNAME


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


def _state_root_from_env() -> Optional[Path]:
    raw = os.environ.get(constants.CBCS_STATE_ROOT_ENV_NAME, "")
    if not raw.strip():
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        return None
    return normalize_state_root_identity(candidate)


def _state_root_from_pointer_file(pointer_path: Path) -> Optional[Path]:
    try:
        if not pointer_path.is_file():
            return None
        text = pointer_path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        candidate = Path(stripped).expanduser()
        if not candidate.is_absolute():
            continue
        return normalize_state_root_identity(candidate)
    return None


def _is_existing_directory(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _normalize_absolute_path(path: PathInput, field_name: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{field_name} must be an absolute path")
    return candidate.resolve()


def _safe_path_component(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    if normalized in {".", ".."}:
        raise ValueError(f"{field_name} cannot be '.' or '..'")
    if "/" in normalized or "\\" in normalized:
        raise ValueError(f"{field_name} cannot contain path separators")
    return normalized
