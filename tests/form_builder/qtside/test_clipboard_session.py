# pyright: reportAttributeAccessIssue=false
"""Clipboard size and paste status inside a real main window."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.engine.ui4.nodes import WidgetNode  # noqa: E402
from app.features.form_builder.engine.ui4.values import RectValue  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QPushButton, QWidget  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit

_FORM_A = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>FormA</class>
 <widget class="QWidget" name="FormA">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>320</width><height>200</height></rect>
  </property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_FORM_B = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>FormB</class>
 <widget class="QWidget" name="FormB">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>640</width><height>480</height></rect>
  </property>
  <widget class="QPushButton" name="okButton">
   <property name="geometry">
    <rect><x>20</x><y>340</y><width>300</width><height>150</height></rect>
   </property>
   <property name="sizePolicy">
    <sizepolicy hsizetype="Fixed" vsizetype="Fixed">
     <horstretch>0</horstretch>
     <verstretch>0</verstretch>
    </sizepolicy>
   </property>
   <property name="minimumSize">
    <size><width>300</width><height>150</height></size>
   </property>
   <property name="maximumSize">
    <size><width>300</width><height>150</height></size>
   </property>
   <property name="text"><string>OK</string></property>
  </widget>
  <widget class="QWidget" name="tray">
   <property name="geometry">
    <rect><x>16</x><y>16</y><width>420</width><height>280</height></rect>
   </property>
   <widget class="QLabel" name="mark">
    <property name="geometry">
     <rect><x>8</x><y>8</y><width>48</width><height>20</height></rect>
    </property>
    <property name="text"><string>Mark</string></property>
   </widget>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_TABS = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>420</width><height>280</height></rect>
  </property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QTabWidget" name="pages">
     <widget class="QWidget" name="one">
      <attribute name="title"><string>One</string></attribute>
     </widget>
     <widget class="QWidget" name="two">
      <attribute name="title"><string>Two</string></attribute>
     </widget>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _require() -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")


def _key(name: str) -> Qt.Key:
    return getattr(getattr(Qt, "Key", Qt), name)


def _mod(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _open(window: MainWindow, qapp: QApplication, path: Path, text: str) -> object:
    path.write_text(text, encoding="utf-8")
    assert window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
    stack = window._center_stack  # noqa: SLF001
    assert stack is not None
    stack.setCurrentIndex(1)
    window.resize(1400, 900)
    window.show()
    qapp.processEvents()
    surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
    assert surface is not None
    return surface


def _flush(qapp: QApplication) -> None:
    for _ in range(4):
        qapp.processEvents()


def _focus_canvas(surface: object, qapp: QApplication) -> QWidget:
    canvas = surface.findChild(QWidget, "formBuilder.canvas")  # type: ignore[attr-defined]
    assert isinstance(canvas, QWidget)
    canvas.setFocus()
    _flush(qapp)
    return canvas


def _select(surface: object, name: str) -> None:
    document = surface.session.document  # type: ignore[attr-defined]
    found = document.by_name(name)
    assert len(found) == 1
    surface.session.selection.set(found, current=found[0], source=SelectionSource.COMMAND)  # type: ignore[attr-defined]


def test_paste_into_another_form_keeps_the_copied_buttons_natural_size(
    tmp_path: Path, qapp: QApplication
) -> None:
    _require()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        surface_a = _open(window, qapp, tmp_path / "form_a.ui", _FORM_A)
        surface_b = _open(window, qapp, tmp_path / "form_b.ui", _FORM_B)
        tabs = window._editor_tabs_widget  # noqa: SLF001
        assert tabs is not None
        tabs.setCurrentIndex(0)
        _flush(qapp)
        _select(surface_a, "okButton")
        _focus_canvas(surface_a, qapp)
        surface_a.dispatch("form.action.copy")  # type: ignore[attr-defined]
        tabs.setCurrentIndex(1)
        _flush(qapp)
        _select(surface_b, "tray")
        _focus_canvas(surface_b, qapp)
        surface_b.dispatch("form.action.paste")  # type: ignore[attr-defined]
        _flush(qapp)

        document = surface_b.session.document  # type: ignore[attr-defined]
        pasted_ids = document.by_name("okButton_2")
        assert len(pasted_ids) == 1
        pasted = document.node(pasted_ids[0])
        assert isinstance(pasted, WidgetNode)
        parent = document.parent(pasted.id)
        assert isinstance(parent, WidgetNode) and parent.object_name == "tray"
        rect = pasted.value("geometry")
        assert isinstance(rect, RectValue)
        probe = QPushButton("OK")
        hint = probe.sizeHint()
        probe.deleteLater()
        assert (rect.width, rect.height) == (hint.width(), hint.height())
        assert (rect.width, rect.height) != (300, 150)
    finally:
        QApplication.clipboard().clear()
        shutdown_main_window_for_test(window)


def test_pasting_a_tab_widget_with_two_pages_says_one_widget(
    tmp_path: Path, qapp: QApplication
) -> None:
    _require()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        surface = _open(window, qapp, tmp_path / "invoice.ui", _TABS)
        _select(surface, "pages")
        canvas = _focus_canvas(surface, qapp)
        QTest.keyClick(canvas, _key("Key_C"), _mod("ControlModifier"))
        _flush(qapp)
        QTest.keyClick(canvas, _key("Key_V"), _mod("ControlModifier"))
        _flush(qapp)
        shown = window._status_controller.editor_status_text()  # noqa: SLF001
        assert shown == "Pasted 1 widget after pages"
        assert "3" not in shown
    finally:
        QApplication.clipboard().clear()
        shutdown_main_window_for_test(window)
