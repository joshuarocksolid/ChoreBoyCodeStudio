"""Unit tests for editor completion service and providers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.completion_providers import extract_completion_prefix
from app.intelligence.completion_providers import provide_project_module_items
from app.intelligence.completion_service import CompletionRequest, CompletionService
from app.persistence.sqlite_index import IndexedSymbol, SQLiteSymbolIndex

pytestmark = pytest.mark.unit


def test_extract_completion_prefix_reads_identifier_before_cursor() -> None:
    source = "value = alpha_beta\nalpha_be"
    cursor_position = len(source)

    prefix = extract_completion_prefix(source, cursor_position)

    assert prefix == "alpha_be"


def test_completion_service_prefers_current_file_symbols(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    current_file = project_root / "main.py"
    current_source = "def alpha_local():\n    return 1\n\nalp"
    current_file.write_text(current_source, encoding="utf-8")
    cache_path = tmp_path / "state" / "symbols.sqlite3"

    cache = SQLiteSymbolIndex(str(cache_path))
    cache.upsert_symbols_for_files(
        str(project_root),
        {
            str((project_root / "other.py").resolve()): [
                IndexedSymbol(name="alpha_local", file_path=str((project_root / "other.py").resolve()), line_number=3),
                IndexedSymbol(name="alpha_other", file_path=str((project_root / "other.py").resolve()), line_number=6),
            ]
        },
    )

    service = CompletionService(cache_db_path=str(cache_path))
    request = CompletionRequest(
        source_text=current_source,
        cursor_position=len(current_source),
        current_file_path=str(current_file.resolve()),
        project_root=str(project_root.resolve()),
        trigger_is_manual=False,
        min_prefix_chars=2,
    )

    completions = service.complete(request)

    assert completions
    assert completions[0].insert_text == "alpha_local"
    assert completions[0].detail == "current file"


def test_completion_service_manual_trigger_allows_short_prefix(tmp_path: Path) -> None:
    cache_path = tmp_path / "state" / "symbols.sqlite3"
    service = CompletionService(cache_db_path=str(cache_path))
    source = "im"

    automatic_request = CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str((tmp_path / "main.py").resolve()),
        project_root=None,
        trigger_is_manual=False,
        min_prefix_chars=3,
    )
    manual_request = CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str((tmp_path / "main.py").resolve()),
        project_root=None,
        trigger_is_manual=True,
        min_prefix_chars=3,
    )

    assert service.complete(automatic_request) == []
    manual = service.complete(manual_request)
    assert any(item.insert_text == "import" for item in manual)


def test_completion_service_dedupes_project_symbol_rows_by_insert_text(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    cache_path = tmp_path / "state" / "symbols.sqlite3"
    cache = SQLiteSymbolIndex(str(cache_path))
    cache.upsert_symbols_for_files(
        str(project_root),
        {
            str((project_root / "a.py").resolve()): [IndexedSymbol(name="helper", file_path=str((project_root / "a.py").resolve()), line_number=1)],
            str((project_root / "b.py").resolve()): [IndexedSymbol(name="helper", file_path=str((project_root / "b.py").resolve()), line_number=9)],
        },
    )

    service = CompletionService(cache_db_path=str(cache_path))
    request = CompletionRequest(
        source_text="hel",
        cursor_position=3,
        current_file_path=str((project_root / "main.py").resolve()),
        project_root=str(project_root.resolve()),
        trigger_is_manual=True,
        min_prefix_chars=2,
    )

    completions = [item for item in service.complete(request) if item.insert_text == "helper"]

    assert len(completions) == 1


def test_completion_service_boosts_recently_accepted_items(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    cache_path = tmp_path / "state" / "symbols.sqlite3"
    cache = SQLiteSymbolIndex(str(cache_path))
    other_path = str((project_root / "other.py").resolve())
    cache.upsert_symbols_for_files(
        str(project_root),
        {
            other_path: [
                IndexedSymbol(name="alpha_one", file_path=other_path, line_number=1),
                IndexedSymbol(name="alpha_two", file_path=other_path, line_number=2),
            ]
        },
    )

    service = CompletionService(cache_db_path=str(cache_path))
    request = CompletionRequest(
        source_text="alp",
        cursor_position=3,
        current_file_path=str((project_root / "main.py").resolve()),
        project_root=str(project_root.resolve()),
        trigger_is_manual=True,
        min_prefix_chars=2,
    )

    initial = service.complete(request)
    assert initial[0].insert_text == "alpha_one"
    preferred = next(item for item in initial if item.insert_text == "alpha_two")
    service.record_acceptance(preferred)

    boosted = service.complete(request)
    assert boosted[0].insert_text == "alpha_two"


def test_completion_service_suggests_members_for_direct_import(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text(
        "def entrypoint():\n"
        "    return 1\n\n"
        "class Runner:\n"
        "    pass\n",
        encoding="utf-8",
    )
    cache_path = tmp_path / "state" / "symbols.sqlite3"
    service = CompletionService(cache_db_path=str(cache_path))
    source = "import main\nmain."
    request = CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str((project_root / "consumer.py").resolve()),
        project_root=str(project_root.resolve()),
        trigger_is_manual=True,
        min_prefix_chars=2,
    )

    completions = service.complete(request)
    inserts = {item.insert_text for item in completions}

    assert "entrypoint" in inserts
    assert "Runner" in inserts


def test_completion_service_suggests_members_for_import_alias(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text(
        "def run_task():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    cache_path = tmp_path / "state" / "symbols.sqlite3"
    service = CompletionService(cache_db_path=str(cache_path))
    source = "import main as m\nm."
    request = CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str((project_root / "consumer.py").resolve()),
        project_root=str(project_root.resolve()),
        trigger_is_manual=True,
        min_prefix_chars=2,
    )

    completions = service.complete(request)

    assert any(item.insert_text == "run_task" for item in completions)


def test_completion_service_suggests_members_for_from_imported_module(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pkg").mkdir()
    (project_root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "pkg" / "mod.py").write_text(
        "def helper():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    cache_path = tmp_path / "state" / "symbols.sqlite3"
    service = CompletionService(cache_db_path=str(cache_path))
    source = "from pkg import mod\nmod."
    request = CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str((project_root / "consumer.py").resolve()),
        project_root=str(project_root.resolve()),
        trigger_is_manual=True,
        min_prefix_chars=2,
    )

    completions = service.complete(request)

    assert any(item.insert_text == "helper" for item in completions)


def test_completion_service_module_member_completion_returns_empty_for_unresolved_import(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    cache_path = tmp_path / "state" / "symbols.sqlite3"
    service = CompletionService(cache_db_path=str(cache_path))
    source = "import missing_module\nmissing_module."
    request = CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str((project_root / "consumer.py").resolve()),
        project_root=str(project_root.resolve()),
        trigger_is_manual=True,
        min_prefix_chars=2,
    )

    completions = service.complete(request)

    assert completions == []


def test_completion_service_module_member_completion_uses_parse_recovery(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text(
        "def recovered():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    cache_path = tmp_path / "state" / "symbols.sqlite3"
    service = CompletionService(cache_db_path=str(cache_path))
    source = "import main\nif True:\n    broken =\nmain."
    request = CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str((project_root / "consumer.py").resolve()),
        project_root=str(project_root.resolve()),
        trigger_is_manual=True,
        min_prefix_chars=2,
    )

    completions = service.complete(request)

    assert any(item.insert_text == "recovered" for item in completions)


def test_project_module_items_uses_indexed_file_cache_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    cache_path = tmp_path / "state" / "symbols.sqlite3"
    cache = SQLiteSymbolIndex(str(cache_path))
    module_file = project_root / "pkg" / "mod.py"
    cache.upsert_file_fingerprints(
        str(project_root.resolve()),
        {str(module_file.resolve()): (10, 100)},
    )

    monkeypatch.setattr(
        Path,
        "rglob",
        lambda self, pattern: (_ for _ in () if False),  # pragma: no cover - must not be used
    )

    results = provide_project_module_items(
        project_root=str(project_root),
        prefix="pkg",
        limit=10,
        cache_db_path=str(cache_path),
    )

    assert [item.insert_text for item in results] == ["pkg.mod"]
