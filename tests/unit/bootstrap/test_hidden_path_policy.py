"""Unit tests for the per-parent hidden-path probe."""

from pathlib import Path
from typing import Callable, Iterator
import os
import shutil

import pytest

from app.bootstrap import hidden_path_policy

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_probe_cache() -> Iterator[None]:
    hidden_path_policy.clear_hidden_path_probe_cache()
    yield
    hidden_path_policy.clear_hidden_path_probe_cache()


def _kinds(result: hidden_path_policy.HiddenPathProbeResult) -> tuple[bool, bool, bool]:
    return (result.hidden_file_ok, result.hidden_dir_ok, result.visible_dir_ok)


def _file_parent(tmp_path: Path) -> Path:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    return blocker


def _missing_parent(tmp_path: Path) -> Path:
    return tmp_path / "missing" / ".hidden_parent"


def test_writable_parent_probes_every_kind_ok_and_leaves_no_canaries(tmp_path: Path) -> None:
    result = hidden_path_policy.probe_hidden_path_support(tmp_path)

    assert _kinds(result) == (True, True, True)
    assert result.errors == ()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "make_parent",
    (_file_parent, _missing_parent),
    ids=("parent_is_a_file", "parent_is_missing"),
)
def test_unusable_parent_probes_every_kind_false_without_creating_paths(
    tmp_path: Path,
    make_parent: Callable[[Path], Path],
) -> None:
    parent = make_parent(tmp_path)
    before = sorted(tmp_path.rglob("*"))

    result = hidden_path_policy.probe_hidden_path_support(parent)

    assert _kinds(result) == (False, False, False)
    assert result.errors
    assert sorted(tmp_path.rglob("*")) == before


def test_second_probe_is_served_from_cache_until_cleared(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    first = hidden_path_policy.probe_hidden_path_support(parent)
    shutil.rmtree(parent)

    assert hidden_path_policy.probe_hidden_path_support(parent) is first

    hidden_path_policy.clear_hidden_path_probe_cache()
    assert hidden_path_policy.probe_hidden_path_support(parent).visible_dir_ok is False


def test_symlink_parent_keeps_logical_identity(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)

    result = hidden_path_policy.probe_hidden_path_support(link)

    assert result.parent == Path(os.path.abspath(str(link)))
    assert result.parent != real.resolve()
    assert _kinds(result) == (True, True, True)
    assert list(real.iterdir()) == []
