import os
from pathlib import Path

import pytest

from app.bootstrap import paths, state_migration
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
            occupancy_filename=constants.GLOBAL_SETTINGS_FILENAME,
            migrating_suffix=constants.STATE_MIGRATING_SUFFIX,
            legacy_leaf=constants.GLOBAL_STATE_DIRNAME,
        ),
    )
    return fake_home


def test_install_on_share_does_not_select_share_state_without_pointer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_state_resolution(monkeypatch, tmp_path)
    install_root = tmp_path / "share" / "Chore_Boy" / "CBCS" / "choreboy_code_studio_vX"
    install_root.mkdir(parents=True)
    monkeypatch.setattr(paths, "resolve_app_root", lambda: install_root)
    root = paths.resolve_global_state_root()
    assert root == Path("/home/default/FreeCAD/CBCS/state")
    assert "share" not in root.parts


def test_pointer_filename_and_state_leaves_are_visible() -> None:
    assert not constants.CBCS_STATE_ROOT_POINTER_FILENAME.startswith(".")
    assert not constants.GLOBAL_STATE_DIRNAME.startswith(".")
    assert not constants.PRODUCT_STATE_LEAF.startswith(".")
    assert not constants.PRODUCT_NEST_DIRNAME.startswith(".")


def test_empty_product_dest_copies_home_leftover(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_state_resolution(monkeypatch, tmp_path)
    dest = tmp_path / "FreeCAD" / "CBCS" / "state"
    layout = paths.ProductStateLayout(
        install_base=dest.parent,
        state_root=dest,
        occupancy_filename=constants.GLOBAL_SETTINGS_FILENAME,
        migrating_suffix=constants.STATE_MIGRATING_SUFFIX,
        legacy_leaf=constants.GLOBAL_STATE_DIRNAME,
    )
    monkeypatch.setattr(paths, "DEFAULT_PRODUCT_STATE_LAYOUT", layout)
    leftover = fake_home / constants.GLOBAL_STATE_DIRNAME
    leftover.mkdir()
    (leftover / constants.GLOBAL_SETTINGS_FILENAME).write_text("{}", encoding="utf-8")

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.SettingsImported)
    assert outcome.dest.name == "state"
    assert (outcome.dest / constants.GLOBAL_SETTINGS_FILENAME).is_file()
    assert (leftover / constants.GLOBAL_SETTINGS_FILENAME).is_file()


def test_second_migrate_is_noop_occupied(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = _isolate_state_resolution(monkeypatch, tmp_path)
    dest = tmp_path / "FreeCAD" / "CBCS" / "state"
    layout = paths.ProductStateLayout(
        install_base=dest.parent,
        state_root=dest,
        occupancy_filename=constants.GLOBAL_SETTINGS_FILENAME,
        migrating_suffix=constants.STATE_MIGRATING_SUFFIX,
        legacy_leaf=constants.GLOBAL_STATE_DIRNAME,
    )
    monkeypatch.setattr(paths, "DEFAULT_PRODUCT_STATE_LAYOUT", layout)
    leftover = fake_home / constants.GLOBAL_STATE_DIRNAME
    leftover.mkdir()
    (leftover / constants.GLOBAL_SETTINGS_FILENAME).write_text("{}", encoding="utf-8")

    state_migration.migrate_legacy_global_state()
    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.SettingsAlreadyPresent)
