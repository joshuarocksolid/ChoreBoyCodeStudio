"""Unit tests for deterministic bootstrap/path helpers."""

from pathlib import Path
import tempfile

import pytest

from app.bootstrap import paths
from app.core import constants

pytestmark = pytest.mark.unit


def test_resolve_app_root_is_absolute_and_cwd_independent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """App root must come from module location, not current working directory."""
    monkeypatch.chdir(tmp_path)
    expected = Path(paths.__file__).resolve().parents[2]
    assert paths.resolve_app_root() == expected


def test_global_state_root_defaults_under_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Default global state root should derive from HOME."""
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    expected = fake_home / constants.GLOBAL_STATE_DIRNAME
    assert paths.resolve_global_state_root() == expected


def test_global_helper_paths_compose_under_state_root(tmp_path: Path) -> None:
    """Settings/log/cache/crash helpers should remain under one state root."""
    state_root = tmp_path / constants.GLOBAL_STATE_DIRNAME
    assert paths.global_settings_path(state_root) == state_root / constants.GLOBAL_SETTINGS_FILENAME
    assert paths.global_recent_projects_path(state_root) == state_root / constants.GLOBAL_RECENT_PROJECTS_FILENAME
    assert paths.global_logs_dir(state_root) == state_root / constants.GLOBAL_LOGS_DIRNAME
    assert paths.global_cache_dir(state_root) == state_root / constants.GLOBAL_CACHE_DIRNAME
    assert paths.global_crash_reports_dir(state_root) == state_root / constants.GLOBAL_CRASH_REPORTS_DIRNAME
    assert paths.global_trash_dir(state_root) == state_root / constants.GLOBAL_TRASH_DIRNAME
    assert paths.global_trash_files_dir(state_root) == state_root / constants.GLOBAL_TRASH_DIRNAME / constants.GLOBAL_TRASH_FILES_DIRNAME
    assert paths.global_trash_info_dir(state_root) == state_root / constants.GLOBAL_TRASH_DIRNAME / constants.GLOBAL_TRASH_INFO_DIRNAME
    assert paths.global_state_db_path(state_root) == state_root / constants.GLOBAL_STATE_DB_FILENAME
    assert paths.global_app_log_path(state_root) == state_root / constants.GLOBAL_LOGS_DIRNAME / constants.APP_LOG_FILENAME


def test_plugin_install_dir_rejects_path_traversal_components(tmp_path: Path) -> None:
    state_root = tmp_path / constants.GLOBAL_STATE_DIRNAME
    with pytest.raises(ValueError):
        paths.plugin_install_dir("../../escape", "1.0.0", state_root)
    with pytest.raises(ValueError):
        paths.plugin_install_dir("acme.demo", "../1.0.0", state_root)


def test_resolve_temp_root_is_absolute_and_namespaced() -> None:
    """Temp root should be deterministic and app-scoped."""
    expected = Path(tempfile.gettempdir()).resolve() / constants.TEMP_NAMESPACE_DIRNAME
    assert paths.resolve_temp_root() == expected


def test_project_helpers_compose_expected_paths(tmp_path: Path) -> None:
    """Project path helpers should use explicit project root contracts."""
    project_root = tmp_path / "project_alpha"
    assert paths.project_cbcs_dir(project_root) == project_root / constants.PROJECT_META_DIRNAME
    assert paths.project_manifest_path(project_root) == project_root / constants.PROJECT_META_DIRNAME / constants.PROJECT_MANIFEST_FILENAME
    assert paths.project_settings_path(project_root) == project_root / constants.PROJECT_META_DIRNAME / constants.PROJECT_SETTINGS_FILENAME
    assert paths.project_runs_dir(project_root) == project_root / constants.PROJECT_META_DIRNAME / constants.PROJECT_RUNS_DIRNAME
    assert paths.project_cache_dir(project_root) == project_root / constants.PROJECT_META_DIRNAME / constants.PROJECT_CACHE_DIRNAME


def test_resolve_project_path_uses_project_root(tmp_path: Path) -> None:
    """Relative project paths should be resolved from explicit project root."""
    project_root = tmp_path / "project_beta"
    resolved = paths.resolve_project_path(project_root, Path("app/main.py"))
    assert resolved == project_root / "app" / "main.py"


def test_resolve_project_path_rejects_relative_project_root() -> None:
    """Reject relative roots to avoid accidental cwd coupling."""
    with pytest.raises(ValueError):
        paths.resolve_project_path("relative_project", Path("run.py"))


def test_ensure_directory_is_idempotent(tmp_path: Path) -> None:
    """Ensuring an existing directory should not fail."""
    target = tmp_path / "logs" / "nested"
    first = paths.ensure_directory(target)
    second = paths.ensure_directory(target)

    assert first == target
    assert second == target
    assert target.exists()
    assert target.is_dir()


def test_try_ensure_directory_returns_path_on_success(tmp_path: Path) -> None:
    """Successful creation should return (path, None)."""
    target = tmp_path / "new_dir" / "nested"
    result_path, error = paths.try_ensure_directory(target)

    assert result_path == target
    assert error is None
    assert target.exists()
    assert target.is_dir()


def test_try_ensure_directory_returns_error_on_failure(tmp_path: Path) -> None:
    """When parent is a file, mkdir fails; should return (None, OSError)."""
    blocker = tmp_path / "blocker"
    blocker.write_text("I am a file")
    target = blocker / "child"

    result_path, error = paths.try_ensure_directory(target)

    assert result_path is None
    assert isinstance(error, OSError)
