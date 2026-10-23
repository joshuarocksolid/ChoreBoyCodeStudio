"""Problems reveal selects by diagnostic key, scrolls, and focuses the inspector."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.diagnostics import (  # noqa: E402
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
)
from app.qt.QtCore import QPoint  # noqa: E402
from app.qt.QtWidgets import QApplication, QTabBar, QWidget  # noqa: E402
from tests.unit.features.form_builder.test_workbench import _open  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>200</width><height>900</height></rect>
  </property>
  <widget class="QPushButton" name="okButton">
   <property name="geometry">
    <rect><x>10</x><y>820</y><width>80</width><height>30</height></rect>
   </property>
   <property name="text"><string>OK</string></property>
  </widget>
  <widget class="QLineEdit" name="email">
   <property name="geometry">
    <rect><x>10</x><y>40</y><width>120</width><height>24</height></rect>
   </property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def test_reveal_uses_the_diagnostic_key_before_the_object_name(qapp: QApplication, tmp_path: Path) -> None:
    del qapp
    parent = QWidget()
    surface = _open(parent, _FORM, tmp_path / "invoice.ui")
    try:
        email = surface._session.document.by_name("email")[0]  # noqa: SLF001
        diagnostic = FormDiagnostic(
            code="FB003",
            severity=Severity.ERROR,
            message="This name is already used.",
            location=DiagnosticLocation(node_id=email, object_name="email"),
            source="reader",
        )
        surface._session.diagnostics.publish("reader", (diagnostic,))  # noqa: SLF001
        assert surface.reveal(1, {"fb_key": diagnostic.key, "fb_object": "missing"})
        assert "email" in surface.editor_status_sentence()
    finally:
        surface.release()
        parent.deleteLater()


def test_reveal_focuses_the_inspector_body(qapp: QApplication, tmp_path: Path) -> None:
    parent = QWidget()
    surface = _open(parent, _FORM, tmp_path / "invoice.ui")
    window = QWidget()
    surface.setParent(window)
    try:
        window.resize(900, 600)
        window.show()
        qapp.processEvents()
        assert surface.reveal(1, {"fb_object": "email"})
        qapp.processEvents()
        focus = qapp.focusWidget()
        assert focus is not None
        assert not isinstance(focus, QTabBar)
        body = surface.findChild(QWidget, "formBuilder.inspectorBody")
        assert body is not None
        assert focus is body or body.isAncestorOf(focus)
    finally:
        surface.release()
        window.deleteLater()
        parent.deleteLater()


def test_reveal_scrolls_the_widget_into_the_viewport(qapp: QApplication, tmp_path: Path) -> None:
    parent = QWidget()
    surface = _open(parent, _FORM, tmp_path / "invoice.ui")
    window = QWidget()
    surface.setParent(window)
    try:
        window.resize(900, 640)
        window.show()
        qapp.processEvents()
        assert surface.reveal(1, {"fb_object": "okButton"})
        qapp.processEvents()
        page = surface.page_widget()
        assert page is not None
        button = page.findChild(QWidget, "okButton")
        canvas = surface.findChild(QWidget, "formBuilder.canvas")
        assert button is not None and canvas is not None
        viewport = canvas.viewport()
        center = button.mapToGlobal(button.rect().center())
        top = viewport.mapToGlobal(QPoint(0, 0))
        bottom = viewport.mapToGlobal(viewport.rect().bottomRight())
        assert top.y() <= center.y() <= bottom.y()
        assert top.x() <= center.x() <= bottom.x()
    finally:
        surface.release()
        window.deleteLater()
        parent.deleteLater()
