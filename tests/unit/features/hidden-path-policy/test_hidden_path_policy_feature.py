"""Behavior tests for the per-parent hidden-path probe used by Desktop icon sidecars."""

from pathlib import Path
from typing import Iterator

import pytest

from app.bootstrap import hidden_path_policy

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_probe_cache() -> Iterator[None]:
    hidden_path_policy.clear_hidden_path_probe_cache()
    yield
    hidden_path_policy.clear_hidden_path_probe_cache()


def _probe_leftovers(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if "cbcs_probe" in path.name)


def test_probe_leaves_no_canaries_on_writable_parent(tmp_path: Path) -> None:
    result = hidden_path_policy.probe_hidden_path_support(tmp_path)

    assert result.hidden_file_ok is True
    assert result.hidden_dir_ok is True
    assert result.visible_dir_ok is True
    assert _probe_leftovers(tmp_path) == []


def test_probe_canaries_stay_hidden_for_hidden_kinds(tmp_path: Path) -> None:
    result = hidden_path_policy.probe_hidden_path_support(tmp_path)

    assert result.errors == ()
    assert _probe_leftovers(tmp_path) == []
    assert not any(path.name.startswith(".") and "capability_probe_" in path.name for path in tmp_path.rglob("*"))
