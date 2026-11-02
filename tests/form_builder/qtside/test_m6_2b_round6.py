# pyright: reportAttributeAccessIssue=false
"""Round 6: a focused row keeps its prefix, a not-checked tooltip, a refused save."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import QPointF  # noqa: E402
from app.qt.QtGui import QEnterEvent, QTextCursor  # noqa: E402
from app.qt.QtWidgets import QApplication, QPushButton, QWidget  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close  # noqa: E402
from tests.form_builder.qtside.test_m6_2b_k26 import _session  # noqa: E402
from tests.form_builder.qtside.test_m6_2b_round4 import _keeps_prefix  # noqa: E402
from tests.form_builder.qtside.test_m6_2b_shots import _set_inspector_width  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(120)]


def _pump(qapp: QApplication, times: int = 6) -> None:
    for _ in range(times):
        qapp.processEvents()


def _hover(row: QWidget) -> None:
    where = QPointF(2, 2)
    row.enterEvent(QEnterEvent(where, where, where))


def _prefixes(row: QWidget) -> None:
    label = row._label  # noqa: SLF001
    place = row.findChild(QPushButton, "formBuilder.events.place")
    assert place is not None
    full_call = str(label.toolTip() or "")
    full_place = str(place.property("cbcsFull") or "")
    assert _keeps_prefix(label.text(), full_call), (label.text(), full_call)
    assert _keeps_prefix(place.text(), full_place), (place.text(), full_place)
    if label.text() == full_call and label.wordWrap():
        assert label.height() + 2 >= label.heightForWidth(max(1, label.width()))
    else:
        assert label.fontMetrics().horizontalAdvance(label.text()) <= label.width() + 2
    assert place.fontMetrics().horizontalAdvance(place.text()) <= place.width() + 2


def test_a_focused_and_hovered_row_at_236_keeps_prefixes(tmp_path: Path, qapp: QApplication) -> None:
    from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
    from app.features.form_builder.engine.logic.events_codec import call_step
    from app.features.form_builder.qtside.inspector import TabId

    window, kb, guard, _path = _session(tmp_path, qapp)
    try:
        surface = kb.surface
        surface.session.log.execute(
            SetEventSteps("printButton", "clicked", (call_step("missing_method"),), caption="Call missing_method()")
        )
        inspector = surface.workbench.inspector
        inspector.focus_tab(TabId.BEHAVIOR)
        button = surface.session.document.by_name("printButton")[0]
        surface.session.selection.set((button,), source="canvas")
        inspector.flush()
        _set_inspector_width(window, 236, qapp)
        inspector.flush()
        _pump(qapp)
        events = inspector.findChild(QWidget, "formBuilder.events")
        assert events is not None
        rows = [row for row in events.findChildren(QWidget) if getattr(row, "step_index", -1) >= 0]
        assert rows
        row = rows[0]
        row.setFocus()
        _pump(qapp)
        _prefixes(row)
        _hover(row)
        _pump(qapp)
        _prefixes(row)
        assert row._menu is not None and row._menu.text() == "\u22ef"  # noqa: SLF001
    finally:
        kb.done(guard)
        _close(window, qapp, guard)


def test_a_not_checked_place_tooltip_is_the_reason_and_the_full_text_when_elided(
    tmp_path: Path, qapp: QApplication
) -> None:
    from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
    from app.features.form_builder.engine.logic.events_codec import call_step
    from app.features.form_builder.qtside.inspector import TabId

    window, kb, guard, path = _session(tmp_path, qapp)
    try:
        surface = kb.surface
        window_file = path.parent / "sale_window.py"
        window_file.write_text("class Broken(:\n", encoding="utf-8")
        surface.session.log.execute(
            SetEventSteps("printButton", "clicked", (call_step("x_method"),), caption="Call x_method()")
        )
        surface.code_bridge.notify_saved(str(window_file))
        inspector = surface.workbench.inspector
        inspector.focus_tab(TabId.BEHAVIOR)
        button = surface.session.document.by_name("printButton")[0]
        surface.session.selection.set((button,), source="canvas")
        inspector.flush()
        _pump(qapp)
        events = inspector.findChild(QWidget, "formBuilder.events")
        assert events is not None
        places = events.findChildren(QPushButton, "formBuilder.events.place")
        assert places
        place = places[0]
        reason = str(place.property("cbcsReason") or "")
        assert place.text() == "not checked"
        assert reason
        assert place.toolTip() == reason
        row = place.parentWidget()
        assert row is not None
        elided = False
        for width in range(48, 240, 8):
            row.setFixedWidth(width)
            row._fit_texts()  # noqa: SLF001
            if place.text() and place.text() != "not checked":
                elided = True
                break
        assert elided, place.text()
        assert _keeps_prefix(place.text(), "not checked")
        assert place.toolTip() == "not checked\n" + reason
    finally:
        kb.done(guard)
        _close(window, qapp, guard)


def test_a_refused_save_keeps_the_earlier_undo_and_the_caret(tmp_path: Path, qapp: QApplication) -> None:
    import app.shell.save_workflow as save_workflow
    from app.features.form_builder.integration.handlers_code import SERVICE
    from tests.form_builder.test_m6_2b_gesture import _request

    import app.shell.external_file_change_workflow as external

    warning = save_workflow.QMessageBox.warning
    question = external.QMessageBox.question
    save_workflow.QMessageBox.warning = staticmethod(lambda *_args, **_kwargs: 0)  # type: ignore[method-assign]
    # The file is touched on disk below. A due poll would open a modal and never return.
    external.QMessageBox.question = staticmethod(lambda *_args, **_kwargs: external.QMessageBox.No)  # type: ignore[method-assign]
    window, kb, guard, path = _session(tmp_path, qapp)
    window_file = path.parent / "sale_window.py"
    try:
        window._editor_tab_workflow.open_file_at_line(str(window_file), 1)
        _pump(qapp)
        editor = window._workspace_controller.widget_for_path(str(window_file))
        assert editor is not None
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        editor.textCursor().insertText("# mine\n")
        assert window._save_workflow.save_tab(str(window_file))
        _pump(qapp)
        cursor = editor.textCursor()
        cursor.setPosition(40)
        editor.setTextCursor(cursor)
        editor.verticalScrollBar().setValue(editor.verticalScrollBar().value())
        caret = editor.textCursor().position()
        scroll = editor.verticalScrollBar().value()
        assert editor.document().isUndoAvailable()
        window_file.write_bytes(window_file.read_bytes() + b"# elsewhere\n")
        os.utime(str(window_file), None)
        outcome = SERVICE.make_method(kb.surface, _request())
        _pump(qapp, 8)
        assert outcome.ok is False
        text = editor.toPlainText()
        assert "# mine" in text
        assert "def print_receipt" not in text
        assert editor.document().isUndoAvailable()
        assert not editor.document().isRedoAvailable()
        assert editor.textCursor().position() == caret
        assert editor.verticalScrollBar().value() == scroll
    finally:
        os.chmod(str(window_file), stat.S_IRUSR | stat.S_IWUSR)
        save_workflow.QMessageBox.warning = warning  # type: ignore[method-assign]
        external.QMessageBox.question = question  # type: ignore[method-assign]
        kb.done(guard)
        _close(window, qapp, guard)
