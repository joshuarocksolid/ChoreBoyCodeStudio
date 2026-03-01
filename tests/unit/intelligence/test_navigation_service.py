"""Unit tests for go-to-definition lookup service."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.navigation_service import lookup_definition, lookup_definition_with_cache

pytestmark = pytest.mark.unit


def test_lookup_definition_prefers_current_file_location(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    current = project_root / "current.py"
    other = project_root / "other.py"
    current.write_text("def target():\n    return 1\n", encoding="utf-8")
    other.write_text("def target():\n    return 2\n", encoding="utf-8")

    result = lookup_definition(str(project_root), str(current.resolve()), "target")

    assert result.found is True
    assert result.locations[0].file_path == str(current.resolve())


def test_lookup_definition_with_cache_populates_and_reads_sqlite_cache(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    current = project_root / "current.py"
    current.write_text("def target():\n    return 1\n", encoding="utf-8")
    cache_db = tmp_path / "state" / "symbols.sqlite3"

    result_first = lookup_definition_with_cache(
        project_root=str(project_root),
        current_file_path=str(current.resolve()),
        symbol_name="target",
        cache_db_path=str(cache_db),
    )
    result_second = lookup_definition_with_cache(
        project_root=str(project_root),
        current_file_path=str(current.resolve()),
        symbol_name="target",
        cache_db_path=str(cache_db),
    )

    assert result_first.found is True
    assert result_second.found is True
    assert result_second.locations[0].file_path == str(current.resolve())
