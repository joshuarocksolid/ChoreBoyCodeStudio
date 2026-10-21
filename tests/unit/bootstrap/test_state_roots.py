"""Shared settings root versus the local state root."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.bootstrap import paths, state_roots
from app.bootstrap.startup_problems import SHARED_SETTINGS_PROBLEM_ID, assemble_startup_problems
from app.core import constants

pytestmark = pytest.mark.unit


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("CBCS_STATE_ROOT", raising=False)
    local = tmp_path / "FreeCAD" / "CBCS" / "state"
    monkeypatch.setattr(
        paths,
        "DEFAULT_PRODUCT_STATE_LAYOUT",
        paths.ProductStateLayout(
            install_base=local.parent,
            state_root=local,
            shop_pointer_path=tmp_path / "missing_shop_pointer",
            occupancy_filename=constants.GLOBAL_SETTINGS_FILENAME,
            migrating_suffix=constants.STATE_MIGRATING_SUFFIX,
            legacy_leaf=constants.GLOBAL_STATE_DIRNAME,
        ),
    )
    return fake_home


def _write_pointer(path: Path, target: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# shop\n{target}\n", encoding="utf-8")


def test_server_pointer_and_share_child_pointer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_home = _isolate(monkeypatch, tmp_path)
    local = paths.DEFAULT_PRODUCT_STATE_LAYOUT.state_root
    server_target = tmp_path / "server_settings"
    client_target = tmp_path / "client_settings"
    server_pointer = paths.DEFAULT_PRODUCT_STATE_LAYOUT.shop_pointer_path
    _write_pointer(server_pointer, server_target)

    choice = state_roots.resolve_settings_root()

    assert choice.source == "pointer"
    assert choice.path == Path(os.path.abspath(str(server_target)))
    assert paths.resolve_global_state_root() == Path(os.path.abspath(str(local)))
    assert paths.global_state_db_path().parent == paths.resolve_global_state_root()
    assert not any(server_target.rglob("*.sqlite3"))

    server_pointer.unlink()
    client_pointer = fake_home / "share" / "net1" / "Chore_Boy" / "CBCS" / constants.CBCS_STATE_ROOT_POINTER_FILENAME
    _write_pointer(client_pointer, client_target)
    choice = state_roots.resolve_settings_root()
    assert choice.path == Path(os.path.abspath(str(client_target)))
    assert paths.global_logs_dir().parent == paths.resolve_global_state_root()
    assert not any(client_target.rglob("*.sqlite3"))


def test_unreachable_shared_root_falls_back_and_records_problem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    blocked = tmp_path / "not_a_directory"
    blocked.write_text("file", encoding="utf-8")
    monkeypatch.setenv("CBCS_STATE_ROOT", str(blocked / "settings"))
    local = Path(os.path.abspath(str(paths.DEFAULT_PRODUCT_STATE_LAYOUT.state_root)))

    choice = state_roots.resolve_settings_root()

    assert choice.fell_back_to_local
    assert choice.path == local
    problems = assemble_startup_problems(
        degraded_issues=[],
        history_folder="",
        symbol_folder="",
        settings_choice=choice,
        migration=None,
    )
    assert len(problems) == 1
    assert problems[0].problem_id == SHARED_SETTINGS_PROBLEM_ID
    assert problems[0].title == "Shared settings are not available"
    assert str(blocked / "settings") in problems[0].folder


def test_pointer_under_an_unmounted_share_falls_back_without_creating_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    unmounted = tmp_path / "net1"
    _write_pointer(paths.DEFAULT_PRODUCT_STATE_LAYOUT.shop_pointer_path, unmounted / "cbcs_settings")

    choice = state_roots.resolve_settings_root()

    assert choice.fell_back_to_local
    assert not unmounted.exists()


def test_legacy_home_symlink_into_share_is_the_settings_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate(monkeypatch, tmp_path)
    target = fake_home / "share" / "team_settings"
    target.mkdir(parents=True)
    link = fake_home / constants.GLOBAL_STATE_DIRNAME
    link.symlink_to(target, target_is_directory=True)
    local = Path(os.path.abspath(str(paths.DEFAULT_PRODUCT_STATE_LAYOUT.state_root)))

    choice = state_roots.resolve_settings_root()

    assert choice.source == "legacy-symlink"
    assert choice.path == Path(os.path.abspath(str(link)))
    assert choice.path != target.resolve()
    assert paths.resolve_global_state_root() == local
    assert paths.global_settings_path() == choice.path / constants.GLOBAL_SETTINGS_FILENAME
    assert paths.global_history_dir() == local / constants.GLOBAL_HISTORY_DIRNAME


def test_legacy_symlink_outside_share_stays_a_leftover(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_home = _isolate(monkeypatch, tmp_path)
    target = tmp_path / "private_settings"
    target.mkdir()
    link = fake_home / constants.GLOBAL_STATE_DIRNAME
    link.symlink_to(target, target_is_directory=True)
    local = Path(os.path.abspath(str(paths.DEFAULT_PRODUCT_STATE_LAYOUT.state_root)))

    choice = state_roots.resolve_settings_root()

    assert choice.source == "local"
    assert choice.path == local
