"""Stress tests for completion broker cache/acceptance mutation (CC-01)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from app.intelligence.completion_broker import CompletionBroker
from app.intelligence.completion_models import CompletionItem, CompletionKind
from app.intelligence.completion_service import CompletionRequest
from app.persistence.sqlite_index import IndexedSymbol, SQLiteSymbolIndex

pytestmark = pytest.mark.unit


def _seed_project_symbols(
    cache_db_path: Path,
    project_root: Path,
    *,
    symbols: list[tuple[str, int]],
) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    main_path = project_root / "main.py"
    main_path.write_text("def placeholder():\n    return 1\n", encoding="utf-8")
    other_path = str((project_root / "other.py").resolve())
    SQLiteSymbolIndex(str(cache_db_path)).upsert_symbols_for_files(
        str(project_root.resolve()),
        {
            other_path: [
                IndexedSymbol(name=name, file_path=other_path, line_number=line_number)
                for name, line_number in symbols
            ]
        },
    )


def test_completion_broker_survives_concurrent_fast_completion_and_acceptance(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    cache_path = tmp_path / "state" / "symbols.sqlite3"
    _seed_project_symbols(
        cache_path,
        project_root,
        symbols=[("alpha_one", 1), ("alpha_two", 2)],
    )

    broker = CompletionBroker(cache_db_path=str(cache_path))
    request = CompletionRequest(
        source_text="alp",
        cursor_position=3,
        current_file_path=str((project_root / "main.py").resolve()),
        project_root=str(project_root.resolve()),
        trigger_is_manual=True,
        min_prefix_chars=2,
    )
    preferred = CompletionItem(
        label="alpha_two",
        insert_text="alpha_two",
        kind=CompletionKind.SYMBOL,
        source="cache",
        confidence="exact",
    )

    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        try:
            barrier.wait(timeout=2.0)
            for _ in range(25):
                broker.complete_fast(request)
                broker.record_acceptance(preferred)
        except BaseException as exc:  # pragma: no cover - surfaced after join
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)
        assert not thread.is_alive()

    assert errors == []

    final = broker.complete_fast(request).items
    assert final[0].insert_text == "alpha_two"
    assert any(item.insert_text == "alpha_one" for item in final)
