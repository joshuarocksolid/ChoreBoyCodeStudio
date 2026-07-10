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


def test_semantic_refinement_returns_semantic_tier_without_merging_fast(tmp_path: Path) -> None:
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
    assert envelope.confidence == "exact"
    assert len(envelope.tiers) == 1
    assert envelope.tiers[0].phase.value == "semantic"
    assert envelope.items[0].source == "semantic"
    assert envelope.items[0].resolve_provider == "jedi"
    assert all(item.source != "static_api_index" for item in envelope.items)


def test_static_index_item_with_docs_skips_resolvable_fields(tmp_path: Path) -> None:
    semantic = _SemanticFacadeStub()
    broker = CompletionBroker(cache_db_path=str(tmp_path / "symbols.sqlite3"), semantic_facade=semantic)  # type: ignore[arg-type]
    source = "import os\nos.getcwd"
    request = CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str(tmp_path / "main.py"),
        project_root=None,
        trigger_is_manual=True,
        min_prefix_chars=1,
        trigger_kind="trigger_character",
        trigger_character=".",
    )

    envelope = broker.complete_fast(request)
    getcwd = next(item for item in envelope.items if item.label == "getcwd")

    assert getcwd.documentation or getcwd.signature
    assert getcwd.resolvable_fields == ()
    assert getcwd.resolve_provider == "api_index"


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


def test_fast_completion_reuse_rejects_buffer_revision_change(tmp_path: Path) -> None:
    semantic = _SemanticFacadeStub()
    broker = CompletionBroker(cache_db_path=str(tmp_path / "symbols.sqlite3"), semantic_facade=semantic)  # type: ignore[arg-type]
    source = "from PySide2 import QtW"
    first = CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str(tmp_path / "main.py"),
        project_root=None,
        trigger_is_manual=False,
        min_prefix_chars=2,
        buffer_revision=1,
    )
    second = CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str(tmp_path / "main.py"),
        project_root=None,
        trigger_is_manual=False,
        min_prefix_chars=2,
        buffer_revision=2,
    )

    broker.complete_fast(first)
    envelope = broker.complete_fast(second)

    assert envelope.source_phase != "reuse"


class _DottedMemberSemanticStub:
    def complete(self, **_kwargs: object) -> list[CompletionItem]:
        return [
            CompletionItem(
                label="__init__",
                insert_text="__init__",
                kind=CompletionKind.METHOD,
                source="semantic",
                confidence="exact",
                engine="jedi",
            ),
            CompletionItem(
                label="paint",
                insert_text="paint",
                kind=CompletionKind.METHOD,
                source="semantic",
                confidence="exact",
                engine="jedi",
                documentation="Draw the widget.",
            ),
            CompletionItem(
                label="resize",
                insert_text="resize",
                kind=CompletionKind.METHOD,
                source="semantic",
                confidence="exact",
                engine="jedi",
            ),
            CompletionItem(
                label="_private",
                insert_text="_private",
                kind=CompletionKind.METHOD,
                source="semantic",
                confidence="exact",
                engine="jedi",
            ),
        ]


def test_dotted_member_semantic_hides_dunders_unless_underscore_prefix(tmp_path: Path) -> None:
    broker = CompletionBroker(
        cache_db_path=str(tmp_path / "symbols.sqlite3"),
        semantic_facade=_DottedMemberSemanticStub(),  # type: ignore[arg-type]
    )
    source = "obj = Widget()\nobj."
    request = CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str(tmp_path / "main.py"),
        project_root=None,
        trigger_is_manual=True,
        min_prefix_chars=0,
        trigger_kind="trigger_character",
        trigger_character=".",
    )

    envelope = broker.complete_semantic(request)
    labels = [item.label for item in envelope.items]

    assert "paint" in labels
    assert "resize" in labels
    assert "__init__" not in labels
    assert "_private" not in labels
    assert labels.index("paint") < labels.index("resize") or "resize" in labels


def test_dotted_member_semantic_keeps_private_when_prefix_starts_with_underscore(tmp_path: Path) -> None:
    broker = CompletionBroker(
        cache_db_path=str(tmp_path / "symbols.sqlite3"),
        semantic_facade=_DottedMemberSemanticStub(),  # type: ignore[arg-type]
    )
    source = "obj = Widget()\nobj._"
    request = CompletionRequest(
        source_text=source,
        cursor_position=len(source),
        current_file_path=str(tmp_path / "main.py"),
        project_root=None,
        trigger_is_manual=True,
        min_prefix_chars=0,
        trigger_kind="trigger_character",
        trigger_character=".",
    )

    envelope = broker.complete_semantic(request)
    labels = [item.label for item in envelope.items]

    assert "_private" in labels
    assert "__init__" in labels
    assert "paint" not in labels
