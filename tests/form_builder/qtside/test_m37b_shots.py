# pyright: reportAttributeAccessIssue=false
"""Screenshots for the M3.7b inspector sentences. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Tuple, cast

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.engine.session import FormSession  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.features.form_builder.integration.chrome import chrome_for  # noqa: E402
from app.features.form_builder.qtside.inspector import InspectorPane  # noqa: E402
from app.features.form_builder.qtside.inspector.api import GROUP_ORDER, GroupId  # noqa: E402
from app.features.form_builder.qtside.realize.api import Realizer  # noqa: E402
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.shell.main_window import MainWindow  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from tests.form_builder.qtside.support import form, opened  # noqa: E402

pytestmark = pytest.mark.unit

_LABELS = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>160</height></rect></property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="shortLabel"><property name="text"><string>No</string></property></widget>
   </item>
   <item row="0" column="1"><widget class="QLineEdit" name="short"/></item>
   <item row="1" column="0">
    <widget class="QLabel" name="longLabel"><property name="text"><string>Street address line</string></property></widget>
   </item>
   <item row="1" column="1"><widget class="QLineEdit" name="long"/></item>
  </layout>
""",
)

_FREE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>320</width><height>200</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QGroupBox" name="box">
     <property name="title"><string>Box</string></property>
     <widget class="QPushButton" name="free">
      <property name="geometry"><rect><x>8</x><y>24</y><width>80</width><height>24</height></rect></property>
      <property name="text"><string>Free</string></property>
     </widget>
    </widget>
   </item>
  </layout>
""",
)

_LINE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>320</width><height>120</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLineEdit" name="email"/></item>
  </layout>
""",
)

_ROOT = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>280</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="one"><property name="text"><string>One</string></property></widget></item>
  </layout>
""",
)

_SHARE = (
    '<property name="sizePolicy"><sizepolicy hsizetype="Expanding" vsizetype="Preferred">'
    "<horstretch>%d</horstretch><verstretch>0</verstretch></sizepolicy></property>"
)


def _splitter() -> str:
    return form(
        'class="QSplitter" name="Form"',
        """
  <property name="orientation"><enum>Qt::Horizontal</enum></property>
  <property name="geometry"><rect><x>0</x><y>0</y><width>640</width><height>240</height></rect></property>
  <widget class="QTextEdit" name="left">%s</widget>
  <widget class="QTextEdit" name="right">%s</widget>
"""
        % (_SHARE % 1, _SHARE % 3),
    )


def _events() -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()


def _select(session: FormSession, pane: InspectorPane, name: str) -> None:
    found = session.document.by_name(name)
    assert found, name
    session.selection.set((found[0],), source=SelectionSource.PROGRAM)
    pane.flush()
    _events()


def _host(session: FormSession, realizer: Realizer) -> Tuple[QWidget, InspectorPane]:
    window = QWidget()
    row = QHBoxLayout(window)
    row.setContentsMargins(0, 0, 0, 0)
    root = realizer.root_widget
    assert root is not None
    root.setParent(window)
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    pane.setFixedWidth(236)
    row.addWidget(root, 1)
    row.addWidget(pane)
    window.resize(1400, 900)
    window.show()
    _events()
    pane.flush()
    _events()
    return window, pane


def _show_why(pane: InspectorPane) -> None:
    why = pane.findChild(QLabel, "formBuilder.sizeWhy")
    area = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
    if isinstance(area, QScrollArea) and isinstance(why, QLabel):
        area.ensureWidgetVisible(why, 0, 12)
        _events()


def _save(qapp: QApplication, window: QWidget, pane: InspectorPane, folder: Path, stem: str) -> None:
    for mode in ("light", "dark"):
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        pane.apply_chrome(chrome_for(tokens))
        _events()
        window.resize(1400, 900)
        _events()
        window.grab().save(str(folder / ("%s-%s-1400x900.png" % (stem, mode))))
        pane.grab().save(str(folder / ("%s-%s-236.png" % (stem, mode))))


def _shot(qapp: QApplication, folder: Path, stem: str, text: str, name: str, group: GroupId) -> None:
    with opened(text) as (session, realizer):
        window, pane = _host(session, realizer)
        try:
            pane.set_group_expanded(group, True)
            _select(session, pane, name)
            if group is GroupId.SIZE:
                _show_why(pane)
            _save(qapp, window, pane, folder, stem)
        finally:
            pane.dispose()
            window.close()
            window.deleteLater()
            _events()


_MAIN = form(
    'class="QMainWindow" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>320</height></rect></property>
  <widget class="QWidget" name="centralwidget">
   <layout class="QVBoxLayout" name="verticalLayout">
    <item><widget class="QLineEdit" name="email"/></item>
   </layout>
  </widget>
  <widget class="QStatusBar" name="statusbar"/>
""",
)


def _only(pane: InspectorPane, groups: Tuple[GroupId, ...]) -> None:
    wanted = set(groups)
    for group in GROUP_ORDER:
        pane.set_group_expanded(group, group in wanted)
    _events()
    pane.flush()
    _events()


def test_m37b_inspector_shots(qapp: QApplication, tmp_path: Path) -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    _shot(qapp, folder, "s5-form-label", _LABELS, "shortLabel", GroupId.SIZE)
    _shot(qapp, folder, "s11-free-widget", _FREE, "free", GroupId.SIZE)
    with opened(_FREE) as (session, realizer):
        window, pane = _host(session, realizer)
        try:
            _only(pane, (GroupId.SIZE, GroupId.PLACEMENT))
            _select(session, pane, "free")
            _save(qapp, window, pane, folder, "s11-size-and-placement")
        finally:
            pane.dispose()
            window.close()
            window.deleteLater()
            _events()
    with opened(_splitter()) as (session, realizer):
        window, pane = _host(session, realizer)
        try:
            root = realizer.root_widget
            assert isinstance(root, QSplitter)
            splitter = cast(QSplitter, root)
            sizes = [int(size) for size in splitter.sizes()]
            splitter.setSizes([sizes[0] + 40, sizes[1] - 40])
            _events()
            _only(pane, (GroupId.SIZE,))
            _select(session, pane, "right")
            _show_why(pane)
            _save(qapp, window, pane, folder, "l2-after-grip")
        finally:
            pane.dispose()
            window.close()
            window.deleteLater()
            _events()
    _shot(qapp, folder, "s11-centralwidget", _MAIN, "centralwidget", GroupId.SIZE)
    _shot(qapp, folder, "l2-splitter-pane", _splitter(), "right", GroupId.SIZE)
    _shot(qapp, folder, "s9-root-layout", _ROOT, "verticalLayout", GroupId.LAYOUT)
    with opened(_LINE) as (session, realizer):
        window, pane = _host(session, realizer)
        try:
            pane.set_group_expanded(GroupId.SIZE, True)
            _select(session, pane, "email")
            fill = pane.findChild(QToolButton, "formBuilder.size.width.Fill")
            assert isinstance(fill, QToolButton)
            QTest.mouseClick(fill, Qt.LeftButton)
            _events()
            pane.flush()
            _events()
            _save(qapp, window, pane, folder, "s7-fill-noop")
        finally:
            pane.dispose()
            window.close()
            window.deleteLater()
            _events()
    if not form_builder_enabled():
        return
    path = tmp_path / "invoice.ui"
    path.write_text(_LINE, encoding="utf-8")
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(True)
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        assert window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
        stack = window._center_stack  # noqa: SLF001
        assert stack is not None
        stack.setCurrentIndex(1)
        window.resize(1400, 900)
        window.show()
        window.activateWindow()
        _events()
        key = getattr(getattr(Qt, "Key", Qt), "Key_O")
        modifier = getattr(getattr(Qt, "KeyboardModifier", Qt), "AltModifier")
        QTest.keyClick(window, key, modifier)
        _events()
        popup = QApplication.activePopupWidget()
        assert popup is not None and popup.objectName() == "formBuilder.menu"
        popup.grab().save(str(folder / "form-menu-alt-o.png"))
        window.grab().save(str(folder / "form-menu-alt-o-window-1400x900.png"))
    finally:
        popup = QApplication.activePopupWidget()
        if popup is not None:
            popup.close()
        shutdown_main_window_for_test(window, qapp)
