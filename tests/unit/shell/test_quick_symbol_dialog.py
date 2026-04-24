"""Unit tests for the QuickSymbolDialog."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.intelligence.outline_service import OutlineSymbol  # noqa: E402
from app.shell.quick_symbol_dialog import QuickSymbolDialog  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def _ensure_qapp(qapp):  # type: ignore[no-untyped-def]
    yield qapp


def _sample_symbols() -> list[OutlineSymbol]:
    return [
        OutlineSymbol(name="Alpha", qualified_name="Alpha", kind="class", line_number=1, end_line_number=20),
        OutlineSymbol(name="foo", qualified_name="Alpha.foo", kind="method", line_number=4, end_line_number=6),
        OutlineSymbol(name="bar", qualified_name="Alpha.bar", kind="method", line_number=8, end_line_number=10),
        OutlineSymbol(name="standalone", qualified_name="standalone", kind="function", line_number=22, end_line_number=24),
        OutlineSymbol(name="CONST", qualified_name="CONST", kind="constant", line_number=26, end_line_number=26),
    ]


def test_filter_narrows_list(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    dialog = QuickSymbolDialog(_sample_symbols())
    assert dialog.symbol_count() == 5
    assert dialog.visible_count() == 5

    dialog.line_edit().setText("fo")

    assert dialog.visible_count() == 1
    current = dialog.list_widget().currentItem()
    assert current is not None
    assert "foo" in current.text()


def test_filter_matches_qualified_name(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    dialog = QuickSymbolDialog(_sample_symbols())
    dialog.line_edit().setText("alpha.bar")
    assert dialog.visible_count() == 1
    current = dialog.list_widget().currentItem()
    assert current is not None
    assert "bar" in current.text()


def test_filter_no_matches_clears_selection(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    dialog = QuickSymbolDialog(_sample_symbols())
    dialog.line_edit().setText("zzzzz_no_match")
    assert dialog.visible_count() == 0
    assert dialog.list_widget().currentRow() == -1


def test_commit_current_emits_chosen_signal(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    dialog = QuickSymbolDialog(_sample_symbols())
    dialog.line_edit().setText("standalone")

    received: list[int] = []
    dialog.symbol_chosen.connect(received.append)
    dialog.commit_current()

    assert received == [22]


def test_preview_signal_fires_on_selection_change(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    dialog = QuickSymbolDialog(_sample_symbols())
    received: list[int] = []
    dialog.symbol_preview.connect(received.append)

    dialog.list_widget().setCurrentRow(2)

    assert received[-1] == 8


def test_dialog_rejected_does_not_emit_chosen(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    dialog = QuickSymbolDialog(_sample_symbols())
    received: list[int] = []
    dialog.symbol_chosen.connect(received.append)

    dialog.reject()

    assert received == []


def test_empty_symbols_initializes_without_error(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    dialog = QuickSymbolDialog(())
    assert dialog.symbol_count() == 0
    assert dialog.list_widget().currentRow() == -1


def test_commit_current_on_hidden_item_is_noop(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    dialog = QuickSymbolDialog(_sample_symbols())
    dialog.line_edit().setText("zzzzz_no_match")

    received: list[int] = []
    dialog.symbol_chosen.connect(received.append)
    dialog.commit_current()

    assert received == []
