"""Settings-only leftover import."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.bootstrap import paths, state_migration
from app.core import constants

pytestmark = pytest.mark.unit


def _patch_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, state_root: Path) -> None:
    layout = paths.ProductStateLayout(
        install_base=state_root.parent,
        state_root=state_root,
        shop_pointer_path=tmp_path / "missing_shop_pointer",
        occupancy_filename=constants.GLOBAL_SETTINGS_FILENAME,
        migrating_suffix=constants.STATE_MIGRATING_SUFFIX,
        legacy_leaf=constants.GLOBAL_STATE_DIRNAME,
    )
    monkeypatch.setattr(paths, "DEFAULT_PRODUCT_STATE_LAYOUT", layout)


def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("CBCS_STATE_ROOT", raising=False)
    return fake_home


def _write_leftover(root: Path, settings_body: str = '{"theme":"legacy"}') -> None:
    root.mkdir(parents=True)
    (root / constants.GLOBAL_SETTINGS_FILENAME).write_text(settings_body, encoding="utf-8")
    (root / constants.GLOBAL_RECENT_PROJECTS_FILENAME).write_text('{"projects":[]}', encoding="utf-8")
    (root / constants.GLOBAL_PYTHON_CONSOLE_HISTORY_FILENAME).write_text('{"entries":["1"]}', encoding="utf-8")
    (root / "state.sqlite3").write_bytes(b"sqlite")
    (root / "state.sqlite3-wal").write_bytes(b"wal")
    (root / "state.sqlite3-shm").write_bytes(b"shm")
    history = root / constants.GLOBAL_HISTORY_DIRNAME
    history.mkdir()
    (history / "index.sqlite3").write_bytes(b"history")
    cache = root / constants.GLOBAL_CACHE_DIRNAME
    cache.mkdir()
    (cache / "symbols.sqlite3").write_bytes(b"symbols")
    logs = root / constants.GLOBAL_LOGS_DIRNAME
    logs.mkdir()
    (logs / "app.log").write_text("log", encoding="utf-8")


def test_migration_copies_three_json_files_and_leaves_sqlite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    dest = tmp_path / "FreeCAD" / "CBCS" / "state"
    _patch_layout(monkeypatch, tmp_path, state_root=dest)
    source = fake_home / constants.GLOBAL_STATE_DIRNAME
    _write_leftover(source)
    source_snapshot = {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.SettingsImported)
    assert outcome.message == f"Settings imported from {outcome.source}."
    assert (dest / constants.GLOBAL_SETTINGS_FILENAME).read_text(encoding="utf-8") == '{"theme":"legacy"}'
    assert (dest / constants.GLOBAL_RECENT_PROJECTS_FILENAME).is_file()
    assert (dest / constants.GLOBAL_PYTHON_CONSOLE_HISTORY_FILENAME).is_file()
    copied_names = {path.name for path in dest.rglob("*") if path.is_file()}
    assert copied_names == {
        constants.GLOBAL_SETTINGS_FILENAME,
        constants.GLOBAL_RECENT_PROJECTS_FILENAME,
        constants.GLOBAL_PYTHON_CONSOLE_HISTORY_FILENAME,
    }
    assert not (dest / "state.sqlite3").exists()
    assert not (dest / constants.GLOBAL_HISTORY_DIRNAME).exists()
    assert not (dest / constants.GLOBAL_LOGS_DIRNAME).exists()
    after = {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }
    assert after == source_snapshot


def test_several_leftovers_name_the_source_that_was_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    dest = tmp_path / "FreeCAD" / "CBCS" / "state"
    _patch_layout(monkeypatch, tmp_path, state_root=dest)
    first = fake_home / constants.GLOBAL_STATE_DIRNAME
    second = fake_home / "FreeCAD" / constants.GLOBAL_STATE_DIRNAME
    _write_leftover(first, '{"from":"home"}')
    _write_leftover(second, '{"from":"freecad"}')

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.SettingsImported)
    assert outcome.leftover_count > 1
    assert "Several leftover folders were found and settings came from" in outcome.message
    assert str(first) in outcome.message
    assert (dest / constants.GLOBAL_SETTINGS_FILENAME).read_text(encoding="utf-8") == '{"from":"home"}'
    assert (second / "state.sqlite3").read_bytes() == b"sqlite"


def test_second_run_does_not_copy_again(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    dest = tmp_path / "FreeCAD" / "CBCS" / "state"
    _patch_layout(monkeypatch, tmp_path, state_root=dest)
    source = fake_home / constants.GLOBAL_STATE_DIRNAME
    _write_leftover(source)

    state_migration.migrate_legacy_global_state()
    (source / constants.GLOBAL_SETTINGS_FILENAME).write_text('{"theme":"changed"}', encoding="utf-8")
    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.SettingsAlreadyPresent)
    assert (dest / constants.GLOBAL_SETTINGS_FILENAME).read_text(encoding="utf-8") == '{"theme":"legacy"}'


def test_shared_settings_root_receives_json_and_not_sqlite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    local = tmp_path / "FreeCAD" / "CBCS" / "state"
    shared = tmp_path / "share_settings"
    _patch_layout(monkeypatch, tmp_path, state_root=local)
    monkeypatch.setenv("CBCS_STATE_ROOT", str(shared))
    source = fake_home / constants.GLOBAL_STATE_DIRNAME
    _write_leftover(source)

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.SettingsImported)
    assert outcome.dest == Path(os.path.abspath(str(shared)))
    assert (shared / constants.GLOBAL_SETTINGS_FILENAME).is_file()
    assert list(shared.rglob("*.sqlite3")) == []
    assert not local.exists() or not any(local.rglob("*.sqlite3"))
