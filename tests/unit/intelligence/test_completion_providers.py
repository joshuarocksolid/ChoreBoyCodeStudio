"""Unit tests for completion provider degradation behavior (CC-11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.project.file_inventory import build_project_inventory_snapshot
from app.intelligence.completion_providers import provide_project_symbol_items

pytestmark = pytest.mark.unit


def test_provide_project_symbol_items_returns_approximate_when_sqlite_cache_empty(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    module_path = project_root / "module.py"
    module_path.write_text(
        "def alpha_helper():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    cache_path = tmp_path / "state" / "symbols.sqlite3"

    items = provide_project_symbol_items(
        project_root=str(project_root.resolve()),
        cache_db_path=str(cache_path),
        prefix="alp",
        limit=10,
        inventory_snapshot=build_project_inventory_snapshot(str(project_root.resolve())),
    )

    assert items
    assert all(item.source == "approximate" for item in items)
    assert all(item.confidence == "approximate" for item in items)
    assert any(item.insert_text == "alpha_helper" for item in items)
