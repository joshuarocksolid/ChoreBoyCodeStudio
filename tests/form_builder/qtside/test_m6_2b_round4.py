# pyright: reportAttributeAccessIssue=false
"""Round-4 regressions: elision at 236 px, one save notify, no redo after a refusal."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QLabel, QPushButton, QToolButton, QWidget  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close  # noqa: E402
from tests.form_builder.qtside.test_m6_2b_k26 import _session  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(120)]


def _keeps_prefix(shown: str, full: str) -> bool:
    if shown == full:
        return True
    mark = "\u2026" if "\u2026" in shown else ("..." if "..." in shown else "")
    if not mark:
        return False
    head, tail = shown.split(mark, 1)
    if not full.startswith(head):
        return False
    return not tail or full.endswith(tail)


def _pump(qapp: QApplication, times: int = 6) -> None:
    for _ in range(times):
        qapp.processEvents()


def test_event_rows_at_236_px_do_not_clip_a_middle_fragment(tmp_path: Path, qapp: QApplication) -> None:
    from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
    from app.features.form_builder.engine.logic.events_codec import call_step
    from app.features.form_builder.qtside.inspector import TabId
    from tests.form_builder.qtside.test_m6_2b_shots import _set_inspector_width

    window, kb, guard, path = _session(tmp_path, qapp)
    try:
        surface = kb.surface
        surface.session.log.execute(
            SetEventSteps("printButton", "clicked", (call_step("missing_method"),), caption="Call missing_method()")
        )
        window_file = path.parent / "sale_window.py"
        raw = window_file.read_bytes()
        if b"on_printButton_clicked" not in raw:
            window_file.write_bytes(raw + b"\r\n    @Slot()\r\n    def on_printButton_clicked(self):\r\n        pass\r\n")
        surface.code_bridge.notify_saved(str(window_file))
        _pump(qapp)
        inspector = surface.workbench.inspector
        inspector.focus_tab(TabId.BEHAVIOR)
        root_id = surface.session.document.root.id
        surface.session.selection.set((root_id,), source="canvas")
        inspector.flush()
        _set_inspector_width(window, 236, qapp)
        inspector.flush()
        _pump(qapp)
        yours = inspector.findChild(QWidget, "formBuilder.yourMethods")
        assert yours is not None
        _assert_labels(yours)
        button = surface.session.document.by_name("printButton")[0]
        surface.session.selection.set((button,), source="canvas")
        inspector.flush()
        _pump(qapp)
        events = inspector.findChild(QWidget, "formBuilder.events")
        assert events is not None
        _assert_labels(events)
        places = events.findChildren(QPushButton, "formBuilder.events.place")
        assert places
        for place in places:
            full = str(place.accessibleName())
            assert full
            assert place.toolTip() == full
            assert _keeps_prefix(place.text(), full), (place.text(), full)
        by_name = [row for row in events.findChildren(QWidget) if getattr(row, "step_index", None) == -2]
        assert by_name
        layout = by_name[0].layout()
        assert layout is not None
        last = layout.itemAt(layout.count() - 1).widget()
        assert isinstance(last, QToolButton)
        assert last.accessibleName() == "Event menu"
    finally:
        kb.done(guard)
        _close(window, qapp, guard)


def _assert_labels(root: QWidget) -> None:
    for label in root.findChildren(QLabel):
        if label.text() in ("!", "\u22ef"):
            continue
        full = str(label.toolTip() or "")
        if not full:
            continue
        assert _keeps_prefix(label.text(), full), (label.text(), full)


def test_a_clean_tab_gesture_notifies_once_and_main_py_reruns_nothing(tmp_path: Path, qapp: QApplication) -> None:
    import app.features.form_builder.integration.handler_checks_bridge as checks
    from app.features.form_builder.integration.handlers_code import SERVICE
    from tests.form_builder.test_m6_2b_gesture import _request

    window, kb, guard, path = _session(tmp_path, qapp)
    bridge = kb.surface.code_bridge
    original_notify = bridge.notify_saved
    original_publish = checks.publish
    notes: list = []
    pubs: list = []

    def _note(saved: str) -> None:
        notes.append(saved)
        original_notify(saved)

    def _pub(surface: object) -> None:
        pubs.append(1)
        original_publish(surface)

    bridge.notify_saved = _note  # type: ignore[method-assign]
    checks.publish = _pub  # type: ignore[assignment]
    try:
        window_file = path.parent / "sale_window.py"
        window._editor_tab_workflow.open_file_at_line(str(window_file), 1)
        _pump(qapp)
        notes.clear()
        pubs.clear()
        outcome = SERVICE.make_method(kb.surface, _request())
        _pump(qapp)
        assert outcome.ok, outcome.reason
        assert len(notes) == 1
        main = path.parent.parent / "main.py"
        main.write_text("x = 1\n", encoding="utf-8")
        notes.clear()
        pubs.clear()
        window._editor_tab_workflow.open_file_at_line(str(main), 1)
        _pump(qapp)
        editor = window._workspace_controller.widget_for_path(str(main))
        assert editor is not None
        editor.textCursor().insertText("# hi\n")
        assert window._save_workflow.save_tab(str(main))
        _pump(qapp)
        assert pubs == []
    finally:
        checks.publish = original_publish
        bridge.notify_saved = original_notify  # type: ignore[method-assign]
        kb.done(guard)
        _close(window, qapp, guard)


def test_redo_after_a_refused_save_changes_nothing(tmp_path: Path, qapp: QApplication) -> None:
    from app.features.form_builder.integration.handlers_code import SERVICE
    from tests.form_builder.test_m6_2b_gesture import _request

    window, kb, guard, path = _session(tmp_path, qapp)
    try:
        window_file = path.parent / "sale_window.py"
        window._editor_tab_workflow.open_file_at_line(str(window_file), 1)
        _pump(qapp)
        editor = window._workspace_controller.widget_for_path(str(window_file))
        assert editor is not None
        before = editor.toPlainText()

        def _refuse(*_args: object, **_kwargs: object) -> bool:
            return False

        window._save_workflow.save_tab = _refuse  # type: ignore[method-assign]
        outcome = SERVICE.make_method(kb.surface, _request())
        assert outcome.ok is False
        assert outcome.reason == "Code Studio couldn't change sale_window.py: the copy on disk changed"
        assert editor.toPlainText() == before
        editor.setFocus()
        _pump(qapp)
        QTest.keyClick(
            editor,
            Qt.Key.Key_Z,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        _pump(qapp)
        assert editor.toPlainText() == before
        assert not editor.document().isRedoAvailable()
    finally:
        kb.done(guard)
        _close(window, qapp, guard)


def test_a_failed_open_clears_the_quick_open_restore_flag(tmp_path: Path, qapp: QApplication) -> None:
    from app.editors.quick_open_dialog import note_focus_restore, take_focus_restore
    from app.shell import editor_tab_factory

    window, kb, guard, _path = _session(tmp_path, qapp)
    warning = editor_tab_factory.QMessageBox.warning
    editor_tab_factory.QMessageBox.warning = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    try:
        note_focus_restore()
        bad = tmp_path / "bad.py"
        bad.write_bytes(b"\xff\xfe")
        assert window._editor_tab_factory.open_file_in_editor(str(bad)) is False
        assert take_focus_restore() is False
    finally:
        editor_tab_factory.QMessageBox.warning = warning  # type: ignore[method-assign]
        kb.done(guard)
        _close(window, qapp, guard)
