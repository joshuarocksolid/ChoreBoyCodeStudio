from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.features.form_builder.integration.surface import FormSurface  # noqa: E402
from app.features.form_builder.qtside.inspector.api import GroupId  # noqa: E402
import re  # noqa: E402

from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtGui import QFont  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QToolButton,
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
     <property name="placeholderText"><string>name@example.com and a long tail</string></property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="okButtonWithAVeryLongObjectName"/>
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


def test_all_properties_show_the_class_value_not_the_canvas_override(tmp_path: Path, qapp: QApplication) -> None:
    """UX-INSP-008: the canvas turns focus off on every widget; the inspector must not show that."""
    _require()
    window, surface = _open(tmp_path, qapp)
    try:
        session = surface._session  # noqa: SLF001
        pane = surface._workbench.inspector  # noqa: SLF001
        email = session.document.by_name("email")[0]
        session.selection.set((email,), source=SelectionSource.PROGRAM)
        pane.set_group_expanded(GroupId.ALL, True)
        pane.flush()
        qapp.processEvents()
        widget = surface._realizer.widget_for(email)  # noqa: SLF001
        assert widget is not None
        no_focus = getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")
        assert enum_value(widget.focusPolicy()) == enum_value(no_focus)
        policy = surface.findChild(QWidget, "formBuilder.row.focusPolicy")
        tracking = surface.findChild(QWidget, "formBuilder.row.mouseTracking")
        assert policy is not None and tracking is not None
        combo = policy.findChild(QComboBox)
        box = tracking.findChild(QCheckBox)
        assert combo is not None and box is not None
        assert combo.currentText() == "StrongFocus"
        # Qt's own QLineEdit constructor turns tracking on, so the class value
        # comes from a fresh line edit rather than a constant.
        fresh = QLineEdit()
        try:
            assert box.isChecked() == fresh.hasMouseTracking()
        finally:
            fresh.deleteLater()
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_changed_labels_and_the_name_are_strong_under_the_shell_style(tmp_path: Path, qapp: QApplication) -> None:
    """UX-INSP-001 and UX-INSP-006 under the shell's chrome font-weight rule."""
    _require()
    window, surface = _open(tmp_path, qapp)
    try:
        session = surface._session  # noqa: SLF001
        pane = surface._workbench.inspector  # noqa: SLF001
        email = session.document.by_name("email")[0]
        session.selection.set((email,), source=SelectionSource.PROGRAM)
        pane.flush()
        qapp.processEvents()
        strong = enum_value(getattr(getattr(QFont, "Weight", QFont), "DemiBold"))
        changed = surface.findChild(QWidget, "formBuilder.row.text")
        plain = surface.findChild(QWidget, "formBuilder.row.maxLength")
        assert changed is not None
        label = next(item for item in changed.findChildren(QLabel) if item.text() == "Text")
        assert label.fontInfo().weight() >= strong
        if plain is not None:
            other = next(item for item in plain.findChildren(QLabel) if item.text())
            assert other.fontInfo().weight() < strong
        name = surface.findChild(QLineEdit, "formBuilder.inspectorName")
        assert name is not None and name.text() == "email"
        assert name.fontInfo().weight() >= strong
    finally:
        shutdown_main_window_for_test(window, qapp)


def _show(surface: FormSurface, qapp: QApplication, name: str, *, expand_all: bool = False) -> None:
    session = surface._session  # noqa: SLF001
    pane = surface._workbench.inspector  # noqa: SLF001
    node = session.document.by_name(name)[0]
    session.selection.set((node,), source=SelectionSource.PROGRAM)
    pane.set_group_expanded(GroupId.ALL, expand_all)
    pane.flush()
    qapp.processEvents()


def _row(surface: FormSurface, key: str) -> QWidget:
    row = surface.findChild(QWidget, "formBuilder.row.%s" % key)
    assert row is not None, key
    return row


def _label_of(row: QWidget) -> QLabel:
    labels = [item for item in row.findChildren(QLabel) if item.text()]
    assert labels
    return labels[0]


def _key_into(widget: QWidget, text: str) -> None:
    widget.setFocus()
    QTest.keyClicks(widget, text)


def test_changed_bar_paints_the_accent_and_rows_stay_aligned(tmp_path: Path, qapp: QApplication) -> None:
    """UX-INSP-006: the 2 px bar is accent coloured and does not shift its row."""
    _require()
    window, surface = _open(tmp_path, qapp)
    try:
        _show(surface, qapp, "email")
        pane = surface._workbench.inspector  # noqa: SLF001
        found = re.search(r'rowChanged\[fbChanged="true"\] \{ background: (#[0-9A-Fa-f]{6})', pane.styleSheet())
        assert found is not None
        accent = found.group(1).lower()
        changed = _row(surface, "text")
        plain = _row(surface, "maxLength")
        bar = changed.findChild(QWidget, "formBuilder.rowChanged")
        assert bar is not None and bar.isVisible() and bar.width() == 2
        image = changed.grab().toImage()
        assert image.pixelColor(bar.x(), bar.y() + bar.height() // 2).name() == accent
        changed_label = _label_of(changed)
        plain_label = _label_of(plain)
        assert changed_label.mapTo(pane, changed_label.rect().topLeft()).x() == plain_label.mapTo(
            pane, plain_label.rect().topLeft()
        ).x()
    finally:
        shutdown_main_window_for_test(window, qapp)
