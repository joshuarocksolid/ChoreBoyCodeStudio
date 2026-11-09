"""The session resolve cache follows renames and stays bounded."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.bootstrap import paths
from app.project.file_operations import rename_path

pytestmark = pytest.mark.unit


def test_rename_through_file_operations_resolves_the_new_path(tmp_path: Path) -> None:
    paths.clear_resolved_cache()
    source = tmp_path / "old.py"
    source.write_text("x = 1\n", encoding="utf-8")
    destination = tmp_path / "new.py"
    assert paths.cached_resolve(str(source)) == str(source.resolve())

    result = rename_path(str(source), str(destination))
    other = tmp_path / "other.py"
    other.write_text("z = 3\n", encoding="utf-8")
    source.symlink_to(other)

    assert result.success
    assert paths.cached_resolve(str(destination)) == str(destination.resolve())
    assert paths.cached_resolve(str(source)) == str(other.resolve())
    paths.clear_resolved_cache()


def test_symlink_created_after_a_missing_resolve_is_followed(tmp_path: Path) -> None:
    paths.clear_resolved_cache()
    target = tmp_path / "target.py"
    target.write_text("y = 2\n", encoding="utf-8")
    missing = tmp_path / "link.py"
    first = paths.cached_resolve(str(missing))
    assert first == str(missing.resolve())
    assert paths.resolved_cache_size() == 0

    missing.symlink_to(target)

    second = paths.cached_resolve(str(missing))
    assert second == str(target.resolve())
    assert second != first
    paths.clear_resolved_cache()


def test_resolved_cache_stays_within_its_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths.clear_resolved_cache()
    monkeypatch.setattr(paths, "RESOLVED_CACHE_LIMIT", 4)
    for index in range(10):
        path = tmp_path / ("file_%d.py" % index)
        path.write_text("z = %d\n" % index, encoding="utf-8")
        paths.cached_resolve(str(path))
    assert paths.resolved_cache_size() <= 4
    paths.clear_resolved_cache()
