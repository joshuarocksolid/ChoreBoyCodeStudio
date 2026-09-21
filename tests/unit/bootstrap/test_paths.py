"""Unit tests for deterministic bootstrap/path helpers."""

from pathlib import Path
import os
import tempfile

import pytest

from app.bootstrap import hidden_path_policy, paths
from app.core import constants

pytestmark = pytest.mark.unit


def _isolate_state_resolution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("CBCS_STATE_ROOT", raising=False)
    monkeypatch.setattr(
        paths,
        "DEFAULT_PRODUCT_STATE_LAYOUT",
        paths.ProductStateLayout(
            install_base=Path(constants.PRODUCT_INSTALL_BASE),
            state_root=Path(constants.PRODUCT_STATE_ROOT),
            shop_pointer_path=tmp_path / "missing_shop_pointer",
            occupancy_filename=constants.GLOBAL_SETTINGS_FILENAME,
            migrating_suffix=constants.STATE_MIGRATING_SUFFIX,
            legacy_leaf=constants.GLOBAL_STATE_DIRNAME,
        ),
    )
    return fake_home


def test_resolve_app_root_is_absolute_and_cwd_independent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """App root must come from module location, not current working directory."""
    monkeypatch.chdir(tmp_path)
    expected = Path(paths.__file__).resolve().parents[2]
    assert paths.resolve_app_root() == expected


def test_global_state_root_defaults_to_product_state_leaf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_state_resolution(monkeypatch, tmp_path)
    root = paths.resolve_global_state_root()
    assert root == Path("/home/default/FreeCAD/CBCS/state")
    assert root.name == "state"


def test_leftover_home_state_dir_does_not_win_resolve(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_state_resolution(monkeypatch, tmp_path)
    leftover = fake_home / constants.GLOBAL_STATE_DIRNAME
    leftover.mkdir()
    (leftover / constants.GLOBAL_SETTINGS_FILENAME).write_text("{}", encoding="utf-8")
    assert paths.resolve_global_state_root() == Path("/home/default/FreeCAD/CBCS/state")


def test_cbcs_state_root_env_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_home = _isolate_state_resolution(monkeypatch, tmp_path)
    (fake_home / constants.GLOBAL_STATE_DIRNAME).mkdir()
    env_root = tmp_path / "from_env"
    monkeypatch.setenv("CBCS_STATE_ROOT", str(env_root))
    assert paths.resolve_global_state_root() == env_root


def test_install_parent_pointer_is_not_consulted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_state_resolution(monkeypatch, tmp_path)
    install_root = tmp_path / "install" / "choreboy_code_studio_vX"
    install_root.mkdir(parents=True)
    pointed = tmp_path / "from_install_pointer"
    (install_root.parent / constants.CBCS_STATE_ROOT_POINTER_FILENAME).write_text(
        f"{pointed}\n", encoding="utf-8"
    )
    monkeypatch.setattr(paths, "resolve_app_root", lambda: install_root)
    assert paths.resolve_global_state_root() == Path("/home/default/FreeCAD/CBCS/state")


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


def test_resolve_does_not_run_hidden_path_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_state_resolution(monkeypatch, tmp_path)

    def _explode(parent: Path) -> hidden_path_policy.HiddenPathProbeResult:
        raise AssertionError(f"probe invoked for {parent}")

    monkeypatch.setattr(hidden_path_policy, "probe_hidden_path_support", _explode)
    assert paths.resolve_global_state_root() == Path("/home/default/FreeCAD/CBCS/state")


def test_empty_or_relative_env_does_not_select_state_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_state_resolution(monkeypatch, tmp_path)
    monkeypatch.setenv("CBCS_STATE_ROOT", "   ")
    assert paths.resolve_global_state_root() == Path("/home/default/FreeCAD/CBCS/state")
    monkeypatch.setenv("CBCS_STATE_ROOT", "relative/state")
    assert paths.resolve_global_state_root() == Path("/home/default/FreeCAD/CBCS/state")


def test_shop_pointer_uses_first_absolute_path_ignoring_comments(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_state_resolution(monkeypatch, tmp_path)
    pointed = tmp_path / "shop_state"
    shop_pointer = tmp_path / "shop_cbcs_state_root"
    shop_pointer.write_text(
        "\n# canonical shop root\nrelative/not/used\n{0}\n{1}\n".format(
            pointed,
            tmp_path / "ignored_second",
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        paths,
        "DEFAULT_PRODUCT_STATE_LAYOUT",
        paths.ProductStateLayout(
            install_base=Path(constants.PRODUCT_INSTALL_BASE),
            state_root=Path(constants.PRODUCT_STATE_ROOT),
            shop_pointer_path=shop_pointer,
            occupancy_filename=constants.GLOBAL_SETTINGS_FILENAME,
            migrating_suffix=constants.STATE_MIGRATING_SUFFIX,
            legacy_leaf=constants.GLOBAL_STATE_DIRNAME,
        ),
    )
    assert paths.resolve_global_state_root() == pointed


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
