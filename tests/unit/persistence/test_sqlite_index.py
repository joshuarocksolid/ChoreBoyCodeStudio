"""Unit tests for SQLite symbol index cache."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.persistence.sqlite_index import IndexedSymbol, SQLiteSymbolIndex

pytestmark = pytest.mark.unit


def test_sqlite_symbol_index_replace_and_lookup(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "index.sqlite3"
    index = SQLiteSymbolIndex(str(db_path))
    project_root = str((tmp_path / "project").resolve())
    symbols = [
        IndexedSymbol(name="run", file_path="/tmp/project/run.py", line_number=1),
        IndexedSymbol(name="run", file_path="/tmp/project/utils.py", line_number=4),
    ]
    index.replace_symbols_for_project(project_root, symbols)

    loaded = index.lookup(project_root, "run")

    assert len(loaded) == 2
    assert loaded[0].file_path.endswith("run.py")
