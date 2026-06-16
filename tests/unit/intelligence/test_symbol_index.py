"""Unit tests for project Python symbol index."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.symbol_index import build_python_symbol_index, to_indexed_symbols, update_symbol_index_cache
from app.persistence.sqlite_index import SQLiteSymbolIndex

pytestmark = pytest.mark.unit


def test_build_python_symbol_index_collects_functions_and_classes(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "module.py").write_text(
        "class Widget:\n    pass\n\ndef helper():\n    return 1\n",
        encoding="utf-8",
    )

    index = build_python_symbol_index(str(project_root))

    assert "Widget" in index
    assert "helper" in index
    assert index["Widget"][0].line_number == 1


def test_to_indexed_symbols_flattens_deterministically(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "alpha.py").write_text("def run():\n    pass\n", encoding="utf-8")
    index = build_python_symbol_index(str(project_root))

    flattened = to_indexed_symbols(index)

    assert [entry.name for entry in flattened] == ["run"]


def test_update_symbol_index_cache_populates_sqlite(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "module.py").write_text("def task():\n    return 1\n", encoding="utf-8")
    cache_path = tmp_path / "state" / "symbols.sqlite3"

    count = update_symbol_index_cache(
        project_root=str(project_root),
        cache_db_path=str(cache_path),
    )

    assert count == 1
    cache = SQLiteSymbolIndex(str(cache_path))
    assert cache.lookup(str(project_root), "task")


def test_update_symbol_index_cache_incrementally_updates_changed_files(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    module_a = project_root / "alpha.py"
    module_b = project_root / "beta.py"
    module_a.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    module_b.write_text("def beta():\n    return 2\n", encoding="utf-8")
    cache_path = tmp_path / "state" / "symbols.sqlite3"

    update_symbol_index_cache(
        project_root=str(project_root),
        cache_db_path=str(cache_path),
    )

    cache = SQLiteSymbolIndex(str(cache_path))
    assert cache.lookup(str(project_root), "alpha")
    assert cache.lookup(str(project_root), "beta")

    module_a.write_text("def alpha_new():\n    return 3\n", encoding="utf-8")
    module_b.unlink()

    update_symbol_index_cache(
        project_root=str(project_root),
        cache_db_path=str(cache_path),
    )

    assert cache.lookup(str(project_root), "alpha") == []
    assert cache.lookup(str(project_root), "beta") == []
    assert cache.lookup(str(project_root), "alpha_new")


def test_update_symbol_index_cache_skips_commit_when_generation_is_stale(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    module = project_root / "module.py"
    module.write_text("def before():\n    return 1\n", encoding="utf-8")
    cache_path = tmp_path / "state" / "symbols.sqlite3"

    update_symbol_index_cache(
        project_root=str(project_root),
        cache_db_path=str(cache_path),
    )

    module.write_text("def after():\n    return 2\n", encoding="utf-8")
    count = update_symbol_index_cache(
        project_root=str(project_root),
        cache_db_path=str(cache_path),
        should_commit=lambda: False,
    )

    assert count == 0
    cache = SQLiteSymbolIndex(str(cache_path))
    assert cache.lookup(str(project_root), "before")
    assert cache.lookup(str(project_root), "after") == []
