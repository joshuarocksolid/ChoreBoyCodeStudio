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
            shop_pointer_path=tmp_path / "missing_shop_pointer",
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
        shop_pointer_path=tmp_path / "missing_shop_pointer",
        occupancy_filename=constants.GLOBAL_SETTINGS_FILENAME,
        migrating_suffix=constants.STATE_MIGRATING_SUFFIX,
        legacy_leaf=constants.GLOBAL_STATE_DIRNAME,
    )
    monkeypatch.setattr(paths, "DEFAULT_PRODUCT_STATE_LAYOUT", layout)
    monkeypatch.setattr(state_migration, "DEFAULT_PRODUCT_STATE_LAYOUT", layout)
    leftover = fake_home / constants.GLOBAL_STATE_DIRNAME
    leftover.mkdir()
    (leftover / constants.GLOBAL_SETTINGS_FILENAME).write_text("{}", encoding="utf-8")

    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.CopiedLegacyState)
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
        shop_pointer_path=tmp_path / "missing_shop_pointer",
        occupancy_filename=constants.GLOBAL_SETTINGS_FILENAME,
        migrating_suffix=constants.STATE_MIGRATING_SUFFIX,
        legacy_leaf=constants.GLOBAL_STATE_DIRNAME,
    )
    monkeypatch.setattr(paths, "DEFAULT_PRODUCT_STATE_LAYOUT", layout)
    monkeypatch.setattr(state_migration, "DEFAULT_PRODUCT_STATE_LAYOUT", layout)
    leftover = fake_home / constants.GLOBAL_STATE_DIRNAME
    leftover.mkdir()
    (leftover / constants.GLOBAL_SETTINGS_FILENAME).write_text("{}", encoding="utf-8")

    state_migration.migrate_legacy_global_state()
    outcome = state_migration.migrate_legacy_global_state()

    assert isinstance(outcome, state_migration.OccupiedStateRoot)
