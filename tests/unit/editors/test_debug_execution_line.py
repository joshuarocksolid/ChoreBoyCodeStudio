"""Unit tests for CodeEditorWidget debug execution line indicator."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QTextFormat  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(request: pytest.FixtureRequest):  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def editor() -> CodeEditorWidget:
    widget = CodeEditorWidget()
    widget.setPlainText("line 1\nline 2\nline 3\nline 4\nline 5\n")
    return widget


def _selection_background_hex(selection) -> str:  # type: ignore[no-untyped-def]
    return selection.format.background().color().name().lower()


class TestSetDebugExecutionLine:
    def test_stores_line_number(self, editor: CodeEditorWidget) -> None:
        editor.set_debug_execution_line(3)
        assert editor._debug_execution_line == 3

    def test_stores_none(self, editor: CodeEditorWidget) -> None:
        editor.set_debug_execution_line(3)
        editor.set_debug_execution_line(None)
        assert editor._debug_execution_line is None

    def test_clear_resets_to_none(self, editor: CodeEditorWidget) -> None:
        editor.set_debug_execution_line(2)
        editor.clear_debug_execution_line()
        assert editor._debug_execution_line is None

    def test_no_op_when_unchanged(self, editor: CodeEditorWidget) -> None:
        editor.set_debug_execution_line(4)
        with patch.object(editor._line_number_area, "update") as mock_update:
            editor.set_debug_execution_line(4)
            mock_update.assert_not_called()

    def test_triggers_gutter_update_on_change(self, editor: CodeEditorWidget) -> None:
        with patch.object(editor._line_number_area, "update") as mock_update:
            editor.set_debug_execution_line(2)
            assert mock_update.call_count >= 1


class TestDebugExecutionLineHighlight:
    def test_extra_selections_include_debug_highlight(self, editor: CodeEditorWidget) -> None:
        editor.set_debug_execution_line(2)
        selections = editor.extraSelections()
        assert len(selections) >= 2
        debug_matches = [
            selection
            for selection in selections
            if _selection_background_hex(selection) == editor._debug_execution_line_bg.name().lower()
            and selection.cursor.block().blockNumber() == 1
        ]
        assert debug_matches

    def test_extra_selections_no_debug_highlight_when_none(self, editor: CodeEditorWidget) -> None:
        editor.set_debug_execution_line(None)
        selections = editor.extraSelections()
        assert all(
            _selection_background_hex(selection) != editor._debug_execution_line_bg.name().lower()
            for selection in selections
        )

    def test_debug_highlight_removed_after_clear(self, editor: CodeEditorWidget) -> None:
        editor.set_debug_execution_line(3)
        count_with = len(editor.extraSelections())
        editor.clear_debug_execution_line()
        count_without = len(editor.extraSelections())
        assert count_without < count_with

    def test_debug_highlight_paints_after_current_line_when_sharing_line(self, editor: CodeEditorWidget) -> None:
        editor.go_to_line(2)
        editor.set_debug_execution_line(2)
        selections = editor.extraSelections()

        current_line_index = next(
            index
            for index, selection in enumerate(selections)
            if _selection_background_hex(selection) == editor._line_highlight.name().lower()
            and bool(selection.format.property(QTextFormat.FullWidthSelection))
        )
        debug_line_index = next(
            index
            for index, selection in enumerate(selections)
            if _selection_background_hex(selection) == editor._debug_execution_line_bg.name().lower()
            and bool(selection.format.property(QTextFormat.FullWidthSelection))
        )

        assert debug_line_index > current_line_index


class TestGutterPainting:
    def test_gutter_width_includes_icon_zone(self, editor: CodeEditorWidget) -> None:
        width = editor.line_number_area_width()
        assert width >= editor._ICON_ZONE_WIDTH + 8

    def test_paint_does_not_crash_with_execution_line(self, editor: CodeEditorWidget) -> None:
        editor.set_debug_execution_line(2)
        editor.show()
        editor.repaint()

    def test_paint_does_not_crash_without_execution_line(self, editor: CodeEditorWidget) -> None:
        editor.set_debug_execution_line(None)
        editor.show()
        editor.repaint()

    def test_paint_does_not_crash_with_breakpoint_and_execution_on_same_line(
        self, editor: CodeEditorWidget
    ) -> None:
        editor.set_debug_execution_line(3)
        editor._breakpoints.add(3)
        editor.show()
        editor.repaint()
