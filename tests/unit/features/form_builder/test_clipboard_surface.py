"""Form clipboard keys on a real form surface, pressed through Qt's shortcut map.

A form shortcut that re-sent its own key would recurse here until the
process crashed. A paste onto a dialog without a layout must keep each
widget's size and must not stack the pasted widgets on each other.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QLineEdit, QPushButton, QWidget  # noqa: E402

from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.engine.ui4.values import RectValue  # noqa: E402
from tests.unit.features.form_builder.test_workbench import _open  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="rootLayout">
   <item><widget class="QPushButton" name="ok"><property name="text"><string>Save</string></property></widget></item>
   <item><widget class="QLabel" name="note"><property name="text"><string>Note</string></property></widget></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_KEY = getattr(Qt, "Key", Qt)
_MOD = getattr(Qt, "KeyboardModifier", Qt)
_CTRL = getattr(_MOD, "ControlModifier")
_NONE = getattr(_MOD, "NoModifier")


def _flush(qapp) -> None:  # type: ignore[no-untyped-def]
    for _ in range(6):
        qapp.processEvents()


def _press(qapp, widget: QWidget, key: str, modifier: object = _CTRL) -> None:  # type: ignore[no-untyped-def]
    QTest.keyClick(widget, getattr(_KEY, key), modifier)
    _flush(qapp)


def _inline_editor(qapp, surface) -> QLineEdit:  # type: ignore[no-untyped-def]
    session = surface.session
    ok = session.document.by_name("ok")[0]
    session.selection.set((ok,), current=ok, source=SelectionSource.COMMAND)
    canvas = surface.findChild(QWidget, "formBuilder.canvas")
    assert canvas is not None
    canvas.setFocus()
    _flush(qapp)
    _press(qapp, canvas, "Key_Return", _NONE)
    edits = [edit for edit in canvas.findChildren(QLineEdit) if edit.isVisible()]
    assert len(edits) == 1
    edits[0].setFocus()
    _flush(qapp)
    assert QApplication.focusWidget() is edits[0]
    return edits[0]


def test_form_keys_inside_the_inline_editor_edit_its_text(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    parent = QWidget()
    parent.resize(1200, 800)
    surface = _open(parent, _FORM, tmp_path / "keys.ui")
    surface.resize(1200, 800)
    parent.show()
    _flush(qapp)
    try:
        doc = surface.session.document
        edit = _inline_editor(qapp, surface)
        names = doc.names()
        revision = doc.revision

        _press(qapp, edit, "Key_D")
        assert edit.text() == "Save"
        assert doc.names() == names and doc.revision == revision

        _press(qapp, edit, "Key_A")
        assert edit.selectedText() == "Save"
        _press(qapp, edit, "Key_C")
        assert QApplication.clipboard().text() == "Save"
        _press(qapp, edit, "Key_X")
        assert edit.text() == ""
        _press(qapp, edit, "Key_V")
        assert edit.text() == "Save"
        _press(qapp, edit, "Key_Backspace", _NONE)
        assert edit.text() == "Sav"
        edit.setCursorPosition(0)
        _press(qapp, edit, "Key_Delete", _NONE)
        assert edit.text() == "av"

        assert doc.names() == names and doc.revision == revision
        assert QApplication.focusWidget() is edit
    finally:
        QApplication.clipboard().clear()
        surface.release()
        parent.deleteLater()
        _flush(qapp)



_BARE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Dialog</class>
 <widget class="QDialog" name="Dialog">
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <widget class="QLineEdit" name="nameEdit">
   <property name="geometry"><rect><x>20</x><y>20</y><width>200</width><height>24</height></rect></property>
  </widget>
  <widget class="QPushButton" name="okButton">
   <property name="geometry"><rect><x>290</x><y>250</y><width>90</width><height>30</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
  <widget class="QTabWidget" name="tabs">
   <property name="geometry"><rect><x>20</x><y>60</y><width>300</width><height>150</height></rect></property>
   <widget class="QWidget" name="page1"><attribute name="title"><string>One</string></attribute></widget>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _rect(doc, name: str) -> RectValue:  # type: ignore[no-untyped-def]
    value = doc.node(doc.by_name(name)[0]).value("geometry")
    assert isinstance(value, RectValue)
    return value


def _meet(first: RectValue, second: RectValue) -> bool:
    return (
        first.x < second.x + second.width
        and second.x < first.x + first.width
        and first.y < second.y + second.height
        and second.y < first.y + first.height
    )


def _shown_surface(qapp, parent: QWidget, text: str, path: Path):  # type: ignore[no-untyped-def]
    surface = _open(parent, text, path)
    surface.resize(1200, 800)
    parent.show()
    _flush(qapp)
    return surface


def _keys_on_form(qapp, surface, *letters: str) -> None:  # type: ignore[no-untyped-def]
    session = surface.session
    root = session.document.root.id
    session.selection.set((root,), current=root, source=SelectionSource.COMMAND)
    canvas = surface.findChild(QWidget, "formBuilder.canvas")
    assert canvas is not None
    canvas.window().activateWindow()
    canvas.setFocus()
    _flush(qapp)
    for letter in letters:
        _press(qapp, canvas, "Key_" + letter)


def test_select_all_copy_paste_on_a_bare_dialog_keeps_sizes(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    parent = QWidget()
    parent.resize(1200, 800)
    surface = _shown_surface(qapp, parent, _BARE, tmp_path / "bare.ui")
    try:
        doc = surface.session.document
        sources = ("nameEdit", "okButton", "tabs")
        before = {name: _rect(doc, name) for name in sources}
        _keys_on_form(qapp, surface, "A", "C")
        _keys_on_form(qapp, surface, "V")

        pasted = {name: _rect(doc, name + "_2") for name in sources}
        for name in sources:
            assert (pasted[name].width, pasted[name].height) == (before[name].width, before[name].height)
            assert _rect(doc, name) == before[name]
        boxes = list(pasted.values())
        for index, first in enumerate(boxes):
            assert not any(_meet(first, second) for second in boxes[index + 1 :])
            assert first.x >= 0 and first.y >= 0
            assert first.x + first.width <= 400 and first.y + first.height <= 300
        # One group: the pieces keep where they sat relative to each other.
        shift = {(pasted[name].x - before[name].x, pasted[name].y - before[name].y) for name in sources}
        assert len(shift) == 1
    finally:
        QApplication.clipboard().clear()
        surface.release()
        parent.deleteLater()
        _flush(qapp)


def test_widgets_from_a_layout_paste_at_their_natural_size(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    parent = QWidget()
    parent.resize(1200, 800)
    laid = _shown_surface(qapp, parent, _FORM, tmp_path / "laid.ui")
    other = QWidget()
    other.resize(1200, 800)
    bare = _shown_surface(qapp, other, _BARE, tmp_path / "bare.ui")
    try:
        _keys_on_form(qapp, laid, "A", "C")
        _keys_on_form(qapp, bare, "V")
        doc = bare.session.document
        save = _rect(doc, "ok")
        note = _rect(doc, "note")
        probe = QPushButton("Save")
        hint = probe.sizeHint()
        probe.deleteLater()
        assert (save.width, save.height) == (hint.width(), hint.height())
        assert not _meet(save, note)
        for name in ("nameEdit", "okButton", "tabs"):
            assert not _meet(save, _rect(doc, name))
            assert not _meet(note, _rect(doc, name))
    finally:
        QApplication.clipboard().clear()
        laid.release()
        bare.release()
        parent.deleteLater()
        other.deleteLater()
        _flush(qapp)
