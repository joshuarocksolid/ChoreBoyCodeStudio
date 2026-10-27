"""Form clipboard keys pressed inside a text input on a real form surface.

The keys go through Qt's shortcut map, as a user's press does. A form shortcut
that re-sent its own key would recurse here until the process crashed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QLineEdit, QWidget  # noqa: E402

from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
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

