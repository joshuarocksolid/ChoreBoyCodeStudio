"""Behavior tests for first-launch leftover state copy."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.bootstrap import paths, state_migration
from app.core import constants

pytestmark = pytest.mark.unit


def _patch_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    state_root: Path,
    shop_pointer_path: Path | None = None,
) -> paths.ProductStateLayout:
    layout = paths.ProductStateLayout(
        install_base=state_root.parent,
        state_root=state_root,
        shop_pointer_path=shop_pointer_path or (tmp_path / "missing_shop_pointer"),
        occupancy_filename=constants.GLOBAL_SETTINGS_FILENAME,
        migrating_suffix=constants.STATE_MIGRATING_SUFFIX,
        legacy_leaf=constants.GLOBAL_STATE_DIRNAME,
    )
    monkeypatch.setattr(paths, "DEFAULT_PRODUCT_STATE_LAYOUT", layout)
    monkeypatch.setattr(state_migration, "DEFAULT_PRODUCT_STATE_LAYOUT", layout)
    return layout


def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("CBCS_STATE_ROOT", raising=False)
    return fake_home


def _write_legacy_tree(root: Path, settings_body: str = '{"theme":"legacy"}') -> None:
    root.mkdir(parents=True)
    (root / constants.GLOBAL_SETTINGS_FILENAME).write_text(settings_body, encoding="utf-8")
    (root / constants.GLOBAL_RECENT_PROJECTS_FILENAME).write_text("[]", encoding="utf-8")
    plugins = root / constants.PLUGINS_STATE_DIRNAME
    plugins.mkdir()
    (plugins / "registry.json").write_text("{}", encoding="utf-8")
    history = root / constants.GLOBAL_HISTORY_DIRNAME
    history.mkdir()
    (history / "index.sqlite3").write_text("blob", encoding="utf-8")


def test_empty_dest_copies_home_leftover_and_leaves_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    dest = tmp_path / "FreeCAD" / "CBCS" / "state"
    _patch_layout(monkeypatch, tmp_path, state_root=dest)
    source = fake_home / constants.GLOBAL_STATE_DIRNAME
    _write_legacy_tree(source)

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.CopiedLegacyState)
    assert outcome.dest == dest
    assert outcome.dest.name == "state"
    assert outcome.source == source
    assert (dest / constants.GLOBAL_SETTINGS_FILENAME).read_text(encoding="utf-8") == '{"theme":"legacy"}'
    assert (dest / constants.GLOBAL_RECENT_PROJECTS_FILENAME).is_file()
    assert (dest / constants.PLUGINS_STATE_DIRNAME / "registry.json").is_file()
    assert (dest / constants.GLOBAL_HISTORY_DIRNAME / "index.sqlite3").is_file()
    assert (source / constants.GLOBAL_SETTINGS_FILENAME).is_file()
    assert not dest.with_name(dest.name + constants.STATE_MIGRATING_SUFFIX).exists()


def test_occupied_dest_is_unchanged_when_legacy_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    dest = tmp_path / "FreeCAD" / "CBCS" / "state"
    dest.mkdir(parents=True)
    (dest / constants.GLOBAL_SETTINGS_FILENAME).write_text('{"theme":"live"}', encoding="utf-8")
    _patch_layout(monkeypatch, tmp_path, state_root=dest)
    _write_legacy_tree(fake_home / constants.GLOBAL_STATE_DIRNAME, '{"theme":"legacy"}')

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.OccupiedStateRoot)
    assert outcome.dest == dest
    assert outcome.settings_path == dest / constants.GLOBAL_SETTINGS_FILENAME
    assert (dest / constants.GLOBAL_SETTINGS_FILENAME).read_text(encoding="utf-8") == '{"theme":"live"}'


def test_env_dest_with_settings_is_not_overwritten_by_home_tree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    env_dest = tmp_path / "env_state"
    env_dest.mkdir()
    (env_dest / constants.GLOBAL_SETTINGS_FILENAME).write_text('{"theme":"env"}', encoding="utf-8")
    monkeypatch.setenv("CBCS_STATE_ROOT", str(env_dest))
    _patch_layout(monkeypatch, tmp_path, state_root=tmp_path / "FreeCAD" / "CBCS" / "state")
    _write_legacy_tree(fake_home / constants.GLOBAL_STATE_DIRNAME, '{"theme":"legacy"}')

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.OccupiedStateRoot)
    assert outcome.dest == env_dest
    assert (env_dest / constants.GLOBAL_SETTINGS_FILENAME).read_text(encoding="utf-8") == '{"theme":"env"}'


def test_shop_pointer_empty_dest_receives_the_copy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    pointed = tmp_path / "shop_state"
    shop_pointer = tmp_path / "shop_cbcs_state_root"
    shop_pointer.write_text(f"{pointed}\n", encoding="utf-8")
    _patch_layout(
        monkeypatch,
        tmp_path,
        state_root=tmp_path / "FreeCAD" / "CBCS" / "state",
        shop_pointer_path=shop_pointer,
    )
    _write_legacy_tree(fake_home / constants.GLOBAL_STATE_DIRNAME)

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.CopiedLegacyState)
    assert outcome.dest == pointed
    assert (pointed / constants.GLOBAL_SETTINGS_FILENAME).is_file()


def test_second_migrate_is_occupied(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    dest = tmp_path / "FreeCAD" / "CBCS" / "state"
    _patch_layout(monkeypatch, tmp_path, state_root=dest)
    _write_legacy_tree(fake_home / constants.GLOBAL_STATE_DIRNAME)

    first = state_migration.migrate_legacy_global_state()
    second = state_migration.migrate_legacy_global_state()

    assert isinstance(first, state_migration.CopiedLegacyState)
    assert isinstance(second, state_migration.OccupiedStateRoot)
    assert second.dest == dest


def test_crash_leftover_staging_promotes_when_dest_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_home(monkeypatch, tmp_path)
    dest = tmp_path / "FreeCAD" / "CBCS" / "state"
    _patch_layout(monkeypatch, tmp_path, state_root=dest)
    staging = dest.with_name(dest.name + constants.STATE_MIGRATING_SUFFIX)
    staging.mkdir(parents=True)
    (staging / constants.GLOBAL_SETTINGS_FILENAME).write_text('{"theme":"staged"}', encoding="utf-8")

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.PromotedStaging)
    assert outcome.dest == dest
    assert (dest / constants.GLOBAL_SETTINGS_FILENAME).read_text(encoding="utf-8") == '{"theme":"staged"}'
    assert not staging.exists()


def test_source_equal_to_dest_is_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    dest = fake_home / constants.GLOBAL_STATE_DIRNAME
    dest.mkdir()
    monkeypatch.setenv("CBCS_STATE_ROOT", str(dest))
    _patch_layout(monkeypatch, tmp_path, state_root=tmp_path / "FreeCAD" / "CBCS" / "state")

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.NoLegacyStateFound)
    assert outcome.dest == dest
    assert not hasattr(outcome, "considered")


def test_identity_skip_continues_to_later_leftover(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    dest = fake_home / constants.GLOBAL_STATE_DIRNAME
    dest.mkdir()
    monkeypatch.setenv("CBCS_STATE_ROOT", str(dest))
    _patch_layout(monkeypatch, tmp_path, state_root=tmp_path / "FreeCAD" / "CBCS" / "state")
    xdg = fake_home / ".local" / "share" / "FreeCAD" / constants.GLOBAL_STATE_DIRNAME
    _write_legacy_tree(xdg, '{"theme":"xdg"}')

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.CopiedLegacyState)
    assert outcome.source == xdg
    assert (dest / constants.GLOBAL_SETTINGS_FILENAME).read_text(encoding="utf-8") == '{"theme":"xdg"}'


def test_xdg_leftover_is_used_when_home_leaf_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    dest = tmp_path / "FreeCAD" / "CBCS" / "state"
    _patch_layout(monkeypatch, tmp_path, state_root=dest)
    xdg = fake_home / ".local" / "share" / "FreeCAD" / constants.GLOBAL_STATE_DIRNAME
    _write_legacy_tree(xdg, '{"theme":"xdg"}')

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.CopiedLegacyState)
    assert outcome.source == xdg
    assert (dest / constants.GLOBAL_SETTINGS_FILENAME).read_text(encoding="utf-8") == '{"theme":"xdg"}'


def test_symlink_dest_keeps_inode_and_does_not_overwrite_existing_children(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    share = tmp_path / "share_state"
    share.mkdir()
    logs = share / constants.GLOBAL_LOGS_DIRNAME
    logs.mkdir()
    (logs / "app.log").write_text("keep-me", encoding="utf-8")
    dest = tmp_path / "FreeCAD" / "CBCS" / "state"
    dest.parent.mkdir(parents=True)
    dest.symlink_to(share)
    _patch_layout(monkeypatch, tmp_path, state_root=dest)
    source = fake_home / constants.GLOBAL_STATE_DIRNAME
    _write_legacy_tree(source, '{"theme":"legacy"}')
    source_logs = source / constants.GLOBAL_LOGS_DIRNAME
    source_logs.mkdir()
    (source_logs / "app.log").write_text("overwrite-me", encoding="utf-8")
    (source_logs / "old.log").write_text("new-log", encoding="utf-8")

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.CopiedLegacyState)
    assert dest.is_symlink()
    assert dest.resolve() == share.resolve()
    assert (share / constants.GLOBAL_SETTINGS_FILENAME).read_text(encoding="utf-8") == '{"theme":"legacy"}'
    assert (logs / "app.log").read_text(encoding="utf-8") == "keep-me"
    assert (logs / "old.log").read_text(encoding="utf-8") == "new-log"
    assert (source / constants.GLOBAL_SETTINGS_FILENAME).is_file()


def test_logs_only_dest_receives_missing_children_without_replacing_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    dest = tmp_path / "FreeCAD" / "CBCS" / "state"
    logs = dest / constants.GLOBAL_LOGS_DIRNAME
    logs.mkdir(parents=True)
    (logs / "app.log").write_text("already-here", encoding="utf-8")
    _patch_layout(monkeypatch, tmp_path, state_root=dest)
    source = fake_home / constants.GLOBAL_STATE_DIRNAME
    _write_legacy_tree(source)
    source_logs = source / constants.GLOBAL_LOGS_DIRNAME
    source_logs.mkdir()
    (source_logs / "app.log").write_text("from-legacy", encoding="utf-8")
    (source_logs / "old.log").write_text("copied", encoding="utf-8")

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.CopiedLegacyState)
    assert dest.is_dir()
    assert not dest.is_symlink()
    assert (dest / constants.GLOBAL_SETTINGS_FILENAME).is_file()
    assert (logs / "app.log").read_text(encoding="utf-8") == "already-here"
    assert (logs / "old.log").read_text(encoding="utf-8") == "copied"
    assert (source / constants.GLOBAL_SETTINGS_FILENAME).is_file()


def test_copy_failure_returns_migration_failed_and_leaves_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_home(monkeypatch, tmp_path)
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    dest = blocked / "state"
    monkeypatch.setenv("CBCS_STATE_ROOT", str(dest))
    _patch_layout(monkeypatch, tmp_path, state_root=tmp_path / "FreeCAD" / "CBCS" / "state")
    source = fake_home / constants.GLOBAL_STATE_DIRNAME
    _write_legacy_tree(source)

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.MigrationFailed)
    assert outcome.dest == dest
    assert outcome.source == source
    assert (source / constants.GLOBAL_SETTINGS_FILENAME).is_file()
    assert outcome.error
