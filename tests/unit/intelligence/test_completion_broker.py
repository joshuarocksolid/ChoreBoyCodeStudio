"""Unit tests for tiered completion broker behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.completion_broker import CompletionBroker
from app.intelligence.completion_models import CompletionItem, CompletionKind
from app.intelligence.completion_service import CompletionRequest

pytestmark = pytest.mark.unit


class _SemanticFacadeStub:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, **_kwargs: object) -> list[CompletionItem]:
        self.calls += 1
        return [
            CompletionItem(
                label="QtWidgets",
                insert_text="QtWidgets",
                kind=CompletionKind.MODULE,
                detail="module semantic",
                engine="jedi",
                source="semantic",
                confidence="exact",
            )
        ]


def test_fast_completion_serves_pyside_import_context_without_semantic_call(tmp_path: Path) -> None:
    semantic = _SemanticFacadeStub()
    broker = CompletionBroker(cache_db_path=str(tmp_path / "symbols.sqlite3"), semantic_facade=semantic)  # type: ignore[arg-type]
    source = "from PySide2 import QtWi"
    request = CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str(tmp_path / "main.py"),
        project_root=None,
        trigger_is_manual=False,
        min_prefix_chars=2,
    )

    envelope = broker.complete_fast(request)

    assert semantic.calls == 0
    assert envelope.source_phase == "fast"
    assert any(item.label == "QtWidgets" and item.source == "static_api_index" for item in envelope.items)


def test_semantic_refinement_merges_exact_items_after_fast_candidates(tmp_path: Path) -> None:
    semantic = _SemanticFacadeStub()
    broker = CompletionBroker(cache_db_path=str(tmp_path / "symbols.sqlite3"), semantic_facade=semantic)  # type: ignore[arg-type]
    source = "from PySide2 import QtWi"
    request = CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str(tmp_path / "main.py"),
        project_root=None,
        trigger_is_manual=False,
        min_prefix_chars=2,
    )

    envelope = broker.complete_semantic(request)

    assert semantic.calls == 1
    assert envelope.source_phase == "semantic"
    assert envelope.items[0].source == "semantic"
    assert envelope.items[0].resolve_provider == "jedi"


def test_fast_completion_reuses_previous_valid_result_for_longer_prefix(tmp_path: Path) -> None:
    semantic = _SemanticFacadeStub()
    broker = CompletionBroker(cache_db_path=str(tmp_path / "symbols.sqlite3"), semantic_facade=semantic)  # type: ignore[arg-type]
    first_source = "from PySide2 import QtW"
    second_source = "from PySide2 import QtWi"
    first = CompletionRequest(
        source_text=first_source,
        cursor_position=len(first_source),
        current_file_path=str(tmp_path / "main.py"),
        project_root=None,
        trigger_is_manual=False,
        min_prefix_chars=2,
    )
    second = CompletionRequest(
        source_text=second_source,
        cursor_position=len(second_source),
        current_file_path=str(tmp_path / "main.py"),
        project_root=None,
        trigger_is_manual=False,
        min_prefix_chars=2,
    )

    broker.complete_fast(first)
    envelope = broker.complete_fast(second)

    assert envelope.source_phase == "reuse"
    assert [item.label for item in envelope.items] == ["QtWidgets"]
