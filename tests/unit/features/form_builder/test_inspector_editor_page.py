from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.features.form_builder.integration.surface import FormSurface  # noqa: E402
from app.features.form_builder.qtside.inspector.api import GroupId  # noqa: E402
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QScrollArea,
    QSpinBox,
    QWidget,
)
from app.qt.qt_compat import enum_value  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QLineEdit" name="email">
     <property name="text"><string>Pay</string></property>
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


def _open(tmp_path: Path, qapp: QApplication) -> tuple[MainWindow, FormSurface]:
    path = tmp_path / "invoice.ui"
    path.write_text(_FORM, encoding="utf-8")
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    assert window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
    window._center_stack.setCurrentIndex(1)  # noqa: SLF001
    window.resize(1400, 900)
    window.show()
    qapp.processEvents()
    surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
    assert isinstance(surface, FormSurface)
    return window, surface


def test_editor_page_inspector_does_not_scroll_sideways(tmp_path: Path, qapp: QApplication) -> None:
    _require()
    window, surface = _open(tmp_path, qapp)
    try:
        scroll = surface.findChild(QScrollArea, "formBuilder.inspectorScroll")
        assert scroll is not None
        off = getattr(getattr(Qt, "ScrollBarPolicy", Qt), "ScrollBarAlwaysOff")
        assert enum_value(scroll.horizontalScrollBarPolicy()) == enum_value(off)
        assert scroll.horizontalScrollBar().isVisible() is False
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_editor_page_shows_live_defaults_and_the_form_size(tmp_path: Path, qapp: QApplication) -> None:
    _require()
    window, surface = _open(tmp_path, qapp)
    try:
        session = surface._session  # noqa: SLF001
        pane = surface._workbench.inspector  # noqa: SLF001
        session.selection.clear(source=SelectionSource.PROGRAM)
        pane.flush()
        qapp.processEvents()
        size = surface.findChild(QLabel, "formBuilder.formDesignSize")
        caption = surface.findChild(QLabel, "formBuilder.formCaption.window")
        assert size is not None and size.text().endswith(" px")
        assert caption is not None and caption.text() == "Window"
        email = session.document.by_name("email")[0]
        session.selection.set((email,), source=SelectionSource.PROGRAM)
        pane.set_group_expanded(GroupId.ALL, True)
        pane.flush()
        qapp.processEvents()
        widget = surface._realizer.widget_for(email)  # noqa: SLF001
        length = surface.findChild(QWidget, "formBuilder.row.maxLength")
        assert widget is not None and length is not None
        spin = length.findChild(QSpinBox)
        assert spin is not None
        assert spin.value() == int(widget.property("maxLength"))
        assert spin.value() != 0
        echo = surface.findChild(QWidget, "formBuilder.row.echoMode")
        assert echo is not None
        combo = echo.findChild(QComboBox)
        assert combo is not None and combo.currentText()
        enabled = surface.findChild(QWidget, "formBuilder.row.enabled")
        assert enabled is not None
        box = enabled.findChild(QCheckBox)
        assert box is not None and box.isChecked() == bool(widget.isEnabled())
    finally:
        shutdown_main_window_for_test(window, qapp)
