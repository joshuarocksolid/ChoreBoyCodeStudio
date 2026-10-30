# pyright: reportAttributeAccessIssue=false
"""Regressions from the M6.2b gate probes that need a window."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtGui import QTextCursor  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(120)]


def test_go_to_code_does_not_pad_the_document(qapp: QApplication) -> None:
    from app.editors.code_editor_widget import CodeEditorWidget
    from app.features.form_builder.integration.code_bridge import _scroll_into_top_third

    widget = CodeEditorWidget()
    widget.resize(800, 600)
    widget.show()
    original = "class A:\n    def f(self):\n        pass\n"
    widget.setPlainText(original)
    widget.document().setModified(False)
    qapp.processEvents()
    cursor = widget.textCursor()
    cursor.setPosition(len("class A:\n    def f(self):\n        "))
    widget.setTextCursor(cursor)
    steps = widget.document().availableUndoSteps()
    _scroll_into_top_third(widget)
    qapp.processEvents()
    assert widget.toPlainText() == original
    assert widget.document().toPlainText() == original
    assert widget.document().availableUndoSteps() == steps
    assert not hasattr(widget, "_cbcs_scroll_pad")
    cursor = widget.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    widget.setTextCursor(cursor)
    widget.textCursor().insertText("def helper():\n    return 1\n")
    typed = widget.toPlainText()
    assert "\n" * 20 not in typed
    assert typed.endswith("def helper():\n    return 1\n")
    many = "x = 1" + "\n" * 120
    widget.setPlainText(many)
    assert widget.toPlainText() == many
    widget.deleteLater()
    qapp.processEvents()


def test_quick_open_accepts_once(qapp: QApplication) -> None:
    from app.editors.quick_open_dialog import QuickOpenCandidate
    from tests.unit.editors.test_quick_open_dialog import _dialog, _wait_for_debounce

    dialog = _dialog()
    dialog.set_candidates([QuickOpenCandidate(relative_path="src/main.py", absolute_path="/proj/src/main.py")])
    got = []
    dialog.file_selected.connect(got.append)
    dialog.show()
    qapp.processEvents()
    dialog._search_input.setFocus()
    QTest.keyClicks(dialog._search_input, "main")
    _wait_for_debounce()
    QTest.keyClick(dialog._search_input, Qt.Key.Key_Return)
    qapp.processEvents()
    assert len(got) == 1
    dialog.deleteLater()
    qapp.processEvents()


def test_your_methods_refreshes_when_the_window_file_is_saved(tmp_path: Path, qapp: QApplication) -> None:
    from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
    from app.features.form_builder.engine.logic.events_codec import call_step
    from app.features.form_builder.qtside.inspector import TabId
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close
    from tests.form_builder.qtside.test_m6_2b_k26 import _session

    window, kb, guard, path = _session(tmp_path, qapp)
    try:
        surface = kb.surface
        surface.session.log.execute(
            SetEventSteps("printButton", "clicked", (call_step("print_receipt"),), caption="Call print_receipt()")
        )
        surface.session.selection.set((surface.session.document.root.id,), source="canvas")
        inspector = surface.workbench.inspector
        inspector.focus_tab(TabId.BEHAVIOR)
        inspector.flush()
        for _ in range(6):
            qapp.processEvents()
        yours = inspector.findChild(QWidget, "formBuilder.yourMethods")
        assert yours is not None
        before = _texts(yours)
        assert any("print_receipt" in item and "not in" in item for item in before)
        assert not any("accept()" in item and "not in" in item for item in before)
        assert not any("reject()" in item and "not in" in item for item in before)
        window_file = path.parent / "sale_window.py"
        original = window_file.read_text(encoding="utf-8")
        added = original.replace(
            "    def show_total(self):",
            "    def print_receipt(self):\n        pass\n\n    def show_total(self):",
            1,
        )
        window._editor_tab_workflow.open_file_at_line(str(window_file), 1)
        qapp.processEvents()
        widget = window._workspace_controller.widget_for_path(str(window_file))
        assert widget is not None
        widget.setPlainText(added)
        qapp.processEvents()
        assert window._save_workflow.save_tab(str(window_file), show_style_warnings=False, apply_transforms=False)
        assert "def print_receipt" in widget.toPlainText()
        from tests.form_builder.qtside.test_m6_2b_k26 import _back_to_form

        _back_to_form(kb)
        inspector.flush()
        for _ in range(8):
            qapp.processEvents()
        inspector.flush()
        after = _texts(inspector.findChild(QWidget, "formBuilder.yourMethods"))
        assert not any("print_receipt" in item and "not in" in item for item in after), after
    finally:
        kb.done(guard)
        _close(window, qapp, guard)


def test_closing_the_form_drops_the_window_file_listener(tmp_path: Path, qapp: QApplication) -> None:
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close
    from tests.form_builder.qtside.test_m6_2b_k26 import _session

    window, kb, guard, _path = _session(tmp_path, qapp)
    try:
        bridge = kb.surface.code_bridge
        assert bridge._listeners
        kb.surface.release()
        assert bridge._listeners == []
    finally:
        kb.done(guard)
        _close(window, qapp, guard)


def _texts(widget: QWidget) -> list:
    found = [child.text() for child in widget.findChildren(QLabel) if child.text()]
    found.extend(child.accessibleName() for child in widget.findChildren(QWidget) if child.accessibleName())
    return found
