# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""The style sheet drawer in a real form tab: live apply, the check, match chips, outlines, one undo step."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple, cast
import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.qtside.style import gateway
from app.features.form_builder.qtside.style.drawer import StyleDrawer, chip_text, styles_sentence
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="okButton"><property name="text"><string>OK</string></property></widget></item>
   <item><widget class="QPushButton" name="cancelButton"><property name="text"><string>Cancel</string></property></widget></item>
   <item><widget class="QLabel" name="nameLabel"><property name="text"><string>Name</string></property></widget></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _surface(qapp, tmp_path: Path):  # type: ignore[no-untyped-def]
    host = QWidget()
    surface = _open(host, _FORM, tmp_path / "invoice.ui")
    host.show()
    surface.show()
    host.resize(1200, 800)
    surface.resize(1200, 800)
    qapp.processEvents()
    return host, surface


def _drawer(surface) -> StyleDrawer:  # type: ignore[no-untyped-def]
    bench = surface.workbench
    assert bench.under_canvas_key() == "style"
    return bench._under_widget


def _type(drawer: StyleDrawer, text: str) -> None:
    drawer.editor.setFocus()
    QTest.keyClicks(drawer.editor, text)
    QTest.qWait(380)
    QApplication.processEvents()


def test_typing_a_rule_restyles_the_canvas_after_300_ms_and_the_status_and_chip_follow(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    host, surface = _surface(qapp, tmp_path)
    try:
        session = surface.session
        ok = session.document.by_name("okButton")[0]
        before = session.text()
        assert gateway.open_drawer(session, ok)
        drawer = _drawer(surface)
        assert drawer.isVisibleTo(surface) and drawer.target == ok
        drawer.editor.insertPlainText("QPushButton#okButton { background: #1A7F37; }")
        QTest.qWait(150)
        # Not yet: 300 ms after the last key.
        assert session.document.node(ok).prop("styleSheet") is None
        QTest.qWait(300)
        QApplication.processEvents()
        assert session.document.node(ok).prop("styleSheet").value.text == "QPushButton#okButton { background: #1A7F37; }"
        assert drawer.status_text().endswith("Looks right")
        assert [(chip[1], chip[2]) for chip in drawer.chips()] == [("1 widget", False)]
        # Backspace over the last } : the status says where, and the canvas keeps what it had.
        cursor = drawer.editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        drawer.editor.setTextCursor(cursor)
        drawer.editor.setFocus()
        QTest.keyClick(drawer.editor, Qt.Key.Key_Backspace)
        QTest.qWait(380)
        assert drawer.status_text().endswith("Line 1: a } is missing.")
        assert session.document.node(ok).prop("styleSheet").value.text.endswith("}")
        QTest.keyClicks(drawer.editor, "}")
        QTest.qWait(380)
        assert drawer.status_text().endswith("Looks right")
        # Esc closes, keeps the text, and the whole visit is one undo step.
        QTest.keyClick(drawer.editor, Qt.Key.Key_Escape)
        qapp.processEvents()
        assert surface.workbench.under_canvas_key() == ""
        assert session.log.undo_label() == "Change style sheet of okButton"
        assert session.log.undo()
        assert session.text() == before
    finally:
        surface.release()
        host.close()


def test_the_canvas_widget_really_takes_the_sheet_and_an_unreadable_text_changes_nothing(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    host, surface = _surface(qapp, tmp_path)
    try:
        session = surface.session
        ok = session.document.by_name("okButton")[0]
        gateway.open_drawer(session, ok)
        drawer = _drawer(surface)
        drawer.editor.setPlainText("QPushButton { background: #1A7F37; }")
        drawer.close_drawer()
        live = surface.realized_object(ok)
        assert live is not None and live.styleSheet() == "QPushButton { background: #1A7F37; }"
        gateway.open_drawer(session, ok)
        drawer = _drawer(surface)
        drawer.editor.setPlainText("QPushButton { background: ")
        drawer.close_drawer()
        assert live.styleSheet() == "QPushButton { background: #1A7F37; }"
        assert session.document.node(ok).prop("styleSheet").value.text == "QPushButton { background: #1A7F37; }"
    finally:
        surface.release()
        host.close()


def test_a_rule_with_no_match_says_so_and_the_caret_in_a_rule_outlines_its_widgets(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    host, surface = _surface(qapp, tmp_path)
    try:
        session = surface.session
        form = session.document.root.id
        gateway.open_drawer(session, form)
        drawer = _drawer(surface)
        drawer.editor.setPlainText("QPushButton { color: red; }\nQProgressBar { color: red; }\n")
        drawer.editor.moveCursor(drawer.editor.textCursor().MoveOperation.Start)
        QTest.qWait(380)
        assert [(chip[1], chip[2]) for chip in drawer.chips()] == [("2 widgets", False), ("No match", True)]
        canvas = surface.workbench.canvas
        names = sorted(session.document.node(i).object_name for i in cast(Tuple[int, ...], canvas.layer_state("style_matches")))
        assert names == ["cancelButton", "okButton"]
        cursor = drawer.editor.textCursor()
        cursor.setPosition(len("QPushButton { color: red; }\nQProg"))
        drawer.editor.setTextCursor(cursor)
        QApplication.processEvents()
        assert canvas.layer_state("style_matches") is None
        drawer.close_drawer()
        assert canvas.layer_state("style_matches") is None
    finally:
        surface.release()
        host.close()


def test_the_drawer_follows_the_selection_commits_the_step_and_shows_the_other_sheet(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    host, surface = _surface(qapp, tmp_path)
    try:
        session = surface.session
        ok = session.document.by_name("okButton")[0]
        label = session.document.by_name("nameLabel")[0]
        gateway.open_drawer(session, ok)
        drawer = _drawer(surface)
        _type(drawer, "color: red;")
        session.selection.set((label,), source=SelectionSource.CANVAS)
        QTest.qWait(50)
        qapp.processEvents()
        assert drawer.target == label and drawer.editor.toPlainText() == ""
        assert session.document.node(ok).prop("styleSheet").value.text == "color: red;"
        drawer.close_drawer()
    finally:
        surface.release()
        host.close()


def test_an_undo_elsewhere_reloads_the_text_and_chips_and_sentences_read_plainly() -> None:
    assert styles_sentence(["saveButton", "cancelButton", "a", "b"]) == "This rule styles saveButton, cancelButton and 2 more."
    assert styles_sentence(["a", "b"]) == "This rule styles a and b."
    assert styles_sentence(["a"]) == "This rule styles a."
    from app.features.form_builder.engine.style.selectors import RuleMatch

    assert chip_text(RuleMatch(0, "x", ())) == ("No match", True)
    assert chip_text(RuleMatch(0, "x", (1, 2, 3), ("hovered",))) == ("3 widgets · when hovered", False)


@pytest.mark.parity("R3-176")
@pytest.mark.pain("P-8")
def test_p8_the_rule_colours_the_button_a_no_match_rule_saves_and_reopening_keeps_the_colour(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.session import FormSession
    from app.features.form_builder.engine.project.forms import FormScope
    from app.features.form_builder.qtside.realize import Realizer

    host, surface = _surface(qapp, tmp_path)
    try:
        session = surface.session
        ok = session.document.by_name("okButton")[0]
        gateway.open_drawer(session, session.document.root.id)
        drawer = _drawer(surface)
        drawer.editor.setPlainText("QPushButton#okButton { background-color: #1A7F37; border: none; }\nQProgressBar { color: red; }")
        drawer.close_drawer()
        text = session.text()
        assert "QProgressBar" in text
    finally:
        surface.release()
        host.close()
    path = str(tmp_path / "again.ui")
    reopened = FormSession.open(text, path=path, scope=FormScope(kind="external", ui_path=path))
    realizer = Realizer(reopened)
    realizer.build()
    try:
        realizer.root_widget.resize(300, 200)
        QApplication.processEvents()
        again = reopened.document.by_name("okButton")[0]
        color = realizer.widget_for(again).grab().toImage().pixelColor(5, 5)
        other = realizer.widget_for(reopened.document.by_name("cancelButton")[0]).grab().toImage().pixelColor(5, 5)
        assert (color.red(), color.green(), color.blue()) == (0x1A, 0x7F, 0x37)
        assert other.green() != 0x7F or other.red() != 0x1A
        del ok
    finally:
        realizer.dispose()
        reopened.dispose()
