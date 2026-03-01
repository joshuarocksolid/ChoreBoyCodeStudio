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


def test_sqlite_symbol_index_upsert_symbols_for_files_and_count(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "index.sqlite3"
    index = SQLiteSymbolIndex(str(db_path))
    project_root = str((tmp_path / "project").resolve())
    file_a = "/tmp/project/a.py"
    file_b = "/tmp/project/b.py"

    index.upsert_symbols_for_files(
        project_root,
        {
            file_a: [IndexedSymbol(name="run", file_path=file_a, line_number=1)],
            file_b: [IndexedSymbol(name="util", file_path=file_b, line_number=3)],
        },
    )
    assert index.count_symbols(project_root) == 2

    index.upsert_symbols_for_files(
        project_root,
        {
            file_a: [IndexedSymbol(name="run", file_path=file_a, line_number=2)],
            file_b: [],
        },
    )
    assert index.count_symbols(project_root) == 1
    lookup = index.lookup(project_root, "run")
    assert lookup[0].line_number == 2


def test_sqlite_symbol_index_file_fingerprints_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "index.sqlite3"
    index = SQLiteSymbolIndex(str(db_path))
    project_root = str((tmp_path / "project").resolve())
    file_a = "/tmp/project/a.py"
    file_b = "/tmp/project/b.py"

    index.upsert_file_fingerprints(project_root, {file_a: (10, 100), file_b: (20, 200)})
    fingerprints = index.lookup_file_fingerprints(project_root)
    assert fingerprints[file_a] == (10, 100)
    assert fingerprints[file_b] == (20, 200)

    index.remove_file_fingerprints(project_root, [file_a])
    assert file_a not in index.lookup_file_fingerprints(project_root)


def test_sqlite_symbol_index_search_by_prefix_is_case_insensitive(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "index.sqlite3"
    index = SQLiteSymbolIndex(str(db_path))
    project_root = str((tmp_path / "project").resolve())
    symbols = [
        IndexedSymbol(name="Alpha", file_path="/tmp/project/a.py", line_number=1),
        IndexedSymbol(name="alphabet", file_path="/tmp/project/b.py", line_number=2),
        IndexedSymbol(name="beta", file_path="/tmp/project/c.py", line_number=3),
    ]
    index.replace_symbols_for_project(project_root, symbols)

    results = index.search_by_prefix(project_root, "alp", limit=10)

    assert [symbol.name for symbol in results] == ["Alpha", "alphabet"]
