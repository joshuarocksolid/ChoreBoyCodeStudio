from pathlib import Path

import pytest

from app.bootstrap import paths
from app.core import constants

pytestmark = pytest.mark.unit


def _isolate_state_resolution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir(parents=True)
    install_root = tmp_path / "share" / "Chore_Boy" / "CBCS" / "choreboy_code_studio_vX"
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


def test_install_on_share_does_not_select_share_state_without_pointer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_state_resolution(monkeypatch, tmp_path)
    root = paths.resolve_global_state_root()
    assert root == Path("/home/default/FreeCAD/choreboy_code_studio_state")
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
    monkeypatch.setattr(constants, "SHOP_STATE_ROOT_POINTER_PATH", str(shop_pointer))
    assert paths.resolve_global_state_root() == pointed


def test_pointer_filename_and_default_dirname_are_visible() -> None:
    assert not constants.CBCS_STATE_ROOT_POINTER_FILENAME.startswith(".")
    assert not constants.GLOBAL_STATE_DIRNAME.startswith(".")
    assert not constants.GLOBAL_STATE_FREECAD_PARENT_DIRNAME.startswith(".")
