"""Unit tests for deterministic bootstrap/path helpers."""

from pathlib import Path
import os
import tempfile

import pytest

from app.bootstrap import paths
from app.core import constants

pytestmark = pytest.mark.unit

_PRODUCT_DEFAULT_STATE_ROOT = Path("/home/default/FreeCAD/choreboy_code_studio_state")


def _isolate_state_resolution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir(parents=True)
    install_root = tmp_path / "install" / "choreboy_code_studio_vX"
    install_root.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("CBCS_STATE_ROOT", raising=False)
    monkeypatch.setattr(paths, "resolve_app_root", lambda: install_root)
    monkeypatch.setattr(
        constants,
        "SHOP_STATE_ROOT_POINTER_PATH",
        str(tmp_path / "missing_shop_pointer"),
    )
    return fake_home


def test_resolve_app_root_is_absolute_and_cwd_independent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """App root must come from module location, not current working directory."""
    monkeypatch.chdir(tmp_path)
    expected = Path(paths.__file__).resolve().parents[2]
    assert paths.resolve_app_root() == expected


def test_global_state_root_defaults_to_freecad_adjacent_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_state_resolution(monkeypatch, tmp_path)
    assert paths.resolve_global_state_root() == _PRODUCT_DEFAULT_STATE_ROOT


def test_legacy_home_state_dir_wins_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_state_resolution(monkeypatch, tmp_path)
    legacy = fake_home / constants.GLOBAL_STATE_DIRNAME
    legacy.mkdir()
    assert paths.resolve_global_state_root() == legacy


def test_cbcs_state_root_env_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_home = _isolate_state_resolution(monkeypatch, tmp_path)
    (fake_home / constants.GLOBAL_STATE_DIRNAME).mkdir()
    env_root = tmp_path / "from_env"
    monkeypatch.setenv("CBCS_STATE_ROOT", str(env_root))
    assert paths.resolve_global_state_root() == env_root


def test_install_parent_pointer_wins_when_env_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_state_resolution(monkeypatch, tmp_path)
    (fake_home / constants.GLOBAL_STATE_DIRNAME).mkdir()
    pointed = tmp_path / "from_install_pointer"
    pointer = tmp_path / "install" / "cbcs_state_root"
    pointer.write_text(f"# shop pointer\n\n{pointed}\n", encoding="utf-8")
    assert paths.resolve_global_state_root() == pointed


def test_explicit_state_root_wins_over_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolate_state_resolution(monkeypatch, tmp_path)
    monkeypatch.setenv("CBCS_STATE_ROOT", str(tmp_path / "from_env"))
    explicit = tmp_path / "explicit"
    assert paths.resolve_global_state_root(explicit) == explicit


def test_state_root_symlink_keeps_logical_path(tmp_path: Path) -> None:
    target = tmp_path / "real_state"
    target.mkdir()
    link = tmp_path / "link_state"
    link.symlink_to(target)
    got = paths.resolve_global_state_root(link)
    assert got == Path(os.path.abspath(str(link)))
    assert got != target.resolve()
    assert got.name == link.name


def test_default_state_root_has_no_hidden_components(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_state_resolution(monkeypatch, tmp_path)
    root = paths.resolve_global_state_root()
    assert not any(part.startswith(".") for part in root.parts if part not in {"/", ""})


def test_empty_or_relative_env_does_not_select_state_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_state_resolution(monkeypatch, tmp_path)
    monkeypatch.setenv("CBCS_STATE_ROOT", "   ")
    assert paths.resolve_global_state_root() == _PRODUCT_DEFAULT_STATE_ROOT
    monkeypatch.setenv("CBCS_STATE_ROOT", "relative/state")
    assert paths.resolve_global_state_root() == _PRODUCT_DEFAULT_STATE_ROOT


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
