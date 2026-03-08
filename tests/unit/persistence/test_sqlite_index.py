"""Unit tests for SQLite symbol index cache."""

from __future__ import annotations

from pathlib import Path
import sqlite3

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


def test_sqlite_symbol_index_lists_indexed_python_files(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "index.sqlite3"
    index = SQLiteSymbolIndex(str(db_path))
    project_root = str((tmp_path / "project").resolve())
    file_a = "/tmp/project/a.py"
    file_b = "/tmp/project/b.py"
    readme = "/tmp/project/README.md"

    index.upsert_file_fingerprints(project_root, {file_a: (10, 100), file_b: (20, 200), readme: (30, 300)})

    assert index.list_indexed_python_files(project_root) == [file_a, file_b]


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


def test_sqlite_symbol_index_round_trips_extended_metadata_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "index.sqlite3"
    index = SQLiteSymbolIndex(str(db_path))
    project_root = str((tmp_path / "project").resolve())
    symbol = IndexedSymbol(
        name="build_report",
        file_path="/tmp/project/main.py",
        line_number=3,
        symbol_kind="function",
        container_name="",
        signature_text="build_report(name, compact=False)",
        doc_excerpt="Build report summary.",
        column_number=4,
        fingerprint_version=2,
    )
    index.replace_symbols_for_project(project_root, [symbol])

    loaded = index.lookup(project_root, "build_report")

    assert len(loaded) == 1
    assert loaded[0].symbol_kind == "function"
    assert loaded[0].signature_text == "build_report(name, compact=False)"
    assert loaded[0].doc_excerpt == "Build report summary."
    assert loaded[0].column_number == 4
    assert loaded[0].fingerprint_version == 2


def test_sqlite_symbol_index_migrates_legacy_symbols_table_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "legacy.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE symbols(
                project_root TEXT NOT NULL,
                name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                line_number INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE indexed_files(
                project_root TEXT NOT NULL,
                file_path TEXT NOT NULL,
                mtime_ns INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL,
                PRIMARY KEY(project_root, file_path)
            )
            """
        )
        connection.commit()

    index = SQLiteSymbolIndex(str(db_path))
    project_root = str((tmp_path / "project").resolve())
    index.upsert_symbols_for_files(
        project_root,
        {
            "/tmp/project/a.py": [
                IndexedSymbol(
                    name="task",
                    file_path="/tmp/project/a.py",
                    line_number=1,
                    symbol_kind="function",
                    signature_text="task()",
                )
            ]
        },
    )

    loaded = index.lookup(project_root, "task")
    assert len(loaded) == 1
    assert loaded[0].signature_text == "task()"
