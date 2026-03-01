"""Unit tests for project Python symbol index."""

from __future__ import annotations

from pathlib import Path
import threading

import pytest

from app.intelligence.symbol_index import SymbolIndexWorker, build_python_symbol_index, to_indexed_symbols
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


def test_symbol_index_worker_populates_sqlite_cache(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "module.py").write_text("def task():\n    return 1\n", encoding="utf-8")
    cache_path = tmp_path / "state" / "symbols.sqlite3"
    done = threading.Event()
    counts: list[int] = []

    worker = SymbolIndexWorker(
        project_root=str(project_root),
        cache_db_path=str(cache_path),
        on_done=lambda count: (counts.append(count), done.set()),
    )
    worker.start()
    assert done.wait(timeout=2.0)
    assert counts == [1]

    cache = SQLiteSymbolIndex(str(cache_path))
    assert cache.lookup(str(project_root), "task")
