"""Behavior tests for the probed product state default, through the public picker and probe."""

from pathlib import Path
from typing import Iterator, Optional

import pytest

from app.bootstrap import hidden_path_policy, paths
from app.core import constants

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_probe_cache() -> Iterator[None]:
    hidden_path_policy.clear_hidden_path_probe_cache()
    yield
    hidden_path_policy.clear_hidden_path_probe_cache()


def _isolate_to_probed_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    install_root = tmp_path / "install" / "choreboy_code_studio_vX"
    install_root.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("CBCS_STATE_ROOT", raising=False)
    monkeypatch.setattr(paths, "resolve_app_root", lambda: install_root)
    monkeypatch.setattr(constants, "SHOP_STATE_ROOT_POINTER_PATH", str(tmp_path / "missing_shop_pointer"))
    monkeypatch.setattr(paths, "PRODUCT_STATE_XDG_PARENT", tmp_path / "missing_xdg" / "FreeCAD")
    monkeypatch.setattr(paths, "PRODUCT_STATE_CACHE_PARENT", tmp_path / ".cache" / "FreeCAD")
    monkeypatch.setattr(paths, "PRODUCT_STATE_VISIBLE_PARENT", tmp_path / "FreeCAD")


def _probe_leftovers(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if "cbcs_probe" in path.name)


@pytest.mark.parametrize(
    ("existing_cache_dir", "expected_parent_name"),
    (
        (".cache/FreeCAD", "PRODUCT_STATE_CACHE_PARENT"),
        (".cache", "PRODUCT_STATE_CACHE_PARENT"),
        (None, "PRODUCT_STATE_VISIBLE_PARENT"),
    ),
    ids=("cache_freecad_exists", "only_dot_cache_exists", "dot_cache_missing_is_never_created"),
)
def test_cache_candidate_needs_an_existing_dot_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    existing_cache_dir: Optional[str],
    expected_parent_name: str,
) -> None:
    _isolate_to_probed_default(monkeypatch, tmp_path)
    if existing_cache_dir is not None:
        (tmp_path / existing_cache_dir).mkdir(parents=True)

    root = paths.resolve_global_state_root()

    assert root == getattr(paths, expected_parent_name) / constants.GLOBAL_STATE_DIRNAME
    assert (tmp_path / ".cache").exists() == (existing_cache_dir is not None)


def test_chosen_default_accepts_the_state_tree_and_leaves_no_canaries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_to_probed_default(monkeypatch, tmp_path)
    (tmp_path / ".cache" / "FreeCAD").mkdir(parents=True)

    root = paths.resolve_global_state_root()
    created = paths.ensure_directory(root)
    (created / constants.GLOBAL_SETTINGS_FILENAME).write_text("{}", encoding="utf-8")

    assert created == root
    assert root.name == constants.GLOBAL_STATE_DIRNAME
    assert (root / constants.GLOBAL_SETTINGS_FILENAME).read_text(encoding="utf-8") == "{}"
    assert _probe_leftovers(tmp_path) == []
