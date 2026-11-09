# pyright: reportAttributeAccessIssue=false
"""Screenshots for the M4.3a scalar editors. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Tuple

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.engine.session import FormSession  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.features.form_builder.integration.chrome import chrome_for  # noqa: E402
from app.features.form_builder.qtside.inspector.api import GroupId  # noqa: E402
from app.features.form_builder.qtside.inspector.pane import InspectorPane  # noqa: E402
from app.features.form_builder.qtside.realize.api import Realizer  # noqa: E402
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402
from tests.form_builder.qtside.support import form, opened  # noqa: E402

pytestmark = pytest.mark.unit

_MODES = (
    "light",
    "dark",
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)

_FORM = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>320</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLineEdit" name="email">
    <property name="echoMode"><enum>QLineEdit::Normal</enum></property>
   </widget></item>
   <item><widget class="QLabel" name="caption"><property name="text"><string>Name</string></property></widget></item>
   <item><widget class="QDoubleSpinBox" name="amount"/></item>
   <item><widget class="QDateEdit" name="when"/></item>
   <item><widget class="QKeySequenceEdit" name="keys"/></item>
  </layout>
""",
)

_ACTIONS = form(
    'class="QMainWindow" name="MainWindow"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>240</height></rect></property>
  <widget class="QWidget" name="centralwidget">
   <layout class="QVBoxLayout" name="verticalLayout">
    <item><widget class="QKeySequenceEdit" name="keys"/></item>
   </layout>
  </widget>
  <action name="actionPrint">
   <property name="text"><string>Print</string></property>
   <property name="shortcut"><string>Ctrl+Alt+P</string></property>
  </action>
  <action name="actionCopy">
   <property name="text"><string>Save a copy</string></property>
   <property name="shortcut"><string>Ctrl+Alt+C</string></property>
  </action>
""",
)

Prepare = Callable[[FormSession, InspectorPane], None]


def _events() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(4):
        app.processEvents()


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _mods(*names: str) -> object:
    enum = getattr(Qt, "KeyboardModifier", Qt)
    value = getattr(enum, "NoModifier")
    for name in names:
        value = value | getattr(enum, name + "Modifier")
    return value


def _select(session: FormSession, pane: InspectorPane, name: str) -> None:
    found = session.document.by_name(name)
    assert found, name
    session.selection.set((found[0],), source=SelectionSource.PROGRAM)
    pane.flush()
    _events()


def _row(pane: QWidget, key: str) -> QWidget:
    for group in GroupId:
        button = pane.findChild(QWidget, "formBuilder.group.%s" % group.value)
        if isinstance(button, QWidget) and hasattr(button, "isChecked") and not button.isChecked():
            button.click()
    for _ in range(6):
        _events()
    pane.flush()
    _events()
    found = pane.findChild(QWidget, "formBuilder.row.%s" % key)
    assert isinstance(found, QWidget), key
    area = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
    if isinstance(area, QScrollArea):
        area.ensureWidgetVisible(found, 0, 40)
        _events()
    return found


def _summary(row: QWidget) -> QPushButton:
    button = row.findChild(QPushButton, "formBuilder.summary")
    assert isinstance(button, QPushButton), row.objectName()
    return button


def _open_button(row: QWidget) -> QPushButton:
    for button in row.findChildren(QPushButton):
        if button.objectName() != "formBuilder.summary" and button.isVisible():
            return button
    raise AssertionError("open button")


def _popover() -> QWidget:
    app = QApplication.instance()
    assert app is not None
    for widget in app.allWidgets():
        if widget.objectName() == "formBuilder.rowPopover" and widget.isVisible():
            return widget
    raise AssertionError("popover")


def _dismiss() -> None:
    app = QApplication.instance()
    assert app is not None
    for widget in list(app.allWidgets()):
        if widget.objectName() != "formBuilder.rowPopover" or not widget.isVisible():
            continue
        done = widget.findChild(QPushButton, "formBuilder.popoverDone")
        if isinstance(done, QPushButton):
            done.click()
        else:
            widget.hide()
    _events()


def _host(session: FormSession, realizer: Realizer, width: int) -> Tuple[QWidget, InspectorPane]:
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(pane)
    pane.setFixedWidth(width)
    window.resize(width, 920)
    window.show()
    _events()
    pane.flush()
    _events()
    return window, pane


def _no_sideways_scroll(pane: InspectorPane, stem: str) -> None:
    area = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
    assert isinstance(area, QScrollArea), stem
    assert area.horizontalScrollBar().maximum() == 0, "%s scrolls sideways" % stem


def _capture(
    qapp: QApplication,
    folder: Path,
    stem: str,
    text: str,
    prepare: Prepare,
    *,
    popover: bool,
) -> None:
    base = qapp.font()
    point = base.pointSize() if base.pointSize() > 0 else 9
    try:
        for scale, factor in ((100, 1), (200, 2)):
            font = qapp.font()
            font.setPointSize(point * factor)
            qapp.setFont(font)
            for width in (236, 300):
                with opened(text) as (session, realizer):
                    window, pane = _host(session, realizer, width)
                    try:
                        for mode in _MODES:
                            tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
                            pane.apply_chrome(chrome_for(tokens))
                            _events()
                            prepare(session, pane)
                            _events()
                            if scale == 100:
                                _no_sideways_scroll(pane, stem)
                            target = _popover() if popover else pane
                            name = "%s__%s__%s__%s.png" % (stem, mode, scale, width)
                            assert target.grab().save(str(folder / name)), name
                            _dismiss()
                    finally:
                        pane.dispose()
                        window.close()
                        window.deleteLater()
                        _events()
    finally:
        qapp.setFont(base)


def _expand(pane: InspectorPane) -> None:
    for group in GroupId:
        button = pane.findChild(QWidget, "formBuilder.group.%s" % group.value)
        if isinstance(button, QWidget) and hasattr(button, "isChecked") and not button.isChecked():
            button.click()
    for _ in range(6):
        _events()
    pane.flush()
    _events()
    area = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
    if isinstance(area, QScrollArea):
        area.verticalScrollBar().setValue(0)
        _events()


def _select_only(name: str) -> Prepare:
    def prepare(session: FormSession, pane: InspectorPane) -> None:
        _select(session, pane, name)
        _expand(pane)

    return prepare


def _flags(session: FormSession, pane: InspectorPane) -> None:
    _select(session, pane, "caption")
    _summary(_row(pane, "textInteractionFlags")).click()
    _events()


def _size_policy(session: FormSession, pane: InspectorPane) -> None:
    _select(session, pane, "email")
    _summary(_row(pane, "sizePolicy")).click()
    _events()


def _date(session: FormSession, pane: InspectorPane) -> None:
    _select(session, pane, "when")
    _open_button(_row(pane, "date")).click()
    _events()


def _locale(session: FormSession, pane: InspectorPane) -> None:
    _select(session, pane, "email")
    _summary(_row(pane, "locale")).click()
    _events()


def _record_button(row: QWidget) -> QPushButton:
    for candidate in row.findChildren(QPushButton):
        if candidate.text() == "Record":
            return candidate
    raise AssertionError("Record")


def _recording(session: FormSession, pane: InspectorPane) -> None:
    _select(session, pane, "keys")
    _record_button(_row(pane, "keySequence")).click()
    _events()


def _clash(session: FormSession, pane: InspectorPane) -> None:
    _select(session, pane, "keys")
    row = _row(pane, "keySequence")
    _record_button(row).click()
    _events()
    edit = row.findChild(QLineEdit)
    assert isinstance(edit, QLineEdit)
    edit.setFocus()
    QTest.keyClick(edit, _key("Key_P"), _mods("Control", "Alt"))
    QTest.qWait(1100)
    _events()
    pane.flush()
    _events()
    row = _row(pane, "keySequence")
    warning = row.findChild(QLabel, "formBuilder.rowWarning")
    area = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
    if isinstance(area, QScrollArea) and isinstance(warning, QLabel):
        area.ensureWidgetVisible(warning, 0, 24)
        _events()


def _refusal(session: FormSession, pane: InspectorPane) -> None:
    _select(session, pane, "email")
    row = _row(pane, "maxLength")
    spin = row.findChild(QSpinBox)
    assert isinstance(spin, QSpinBox)
    edit = spin.lineEdit()
    assert edit is not None
    edit.setFocus()
    edit.selectAll()
    QTest.keyClicks(edit, "99999")
    QTest.keyClick(edit, _key("Key_Return"))
    _events()
    pane.flush()
    _row(pane, "maxLength")


def _unknown(session: FormSession, pane: InspectorPane) -> None:
    _select(session, pane, "email")
    _row(pane, "echoMode")


def test_m43a_scalar_shots(qapp: QApplication) -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    unknown = _FORM.replace("QLineEdit::Normal", "QLineEdit::SomeFutureMode")
    _capture(qapp, folder, "inspector-min-width-all-line", _FORM, _select_only("email"), popover=False)
    _capture(qapp, folder, "inspector-min-width-all-label", _FORM, _select_only("caption"), popover=False)
    _capture(qapp, folder, "inspector-min-width-all-spin", _FORM, _select_only("amount"), popover=False)
    _capture(qapp, folder, "inspector-min-width-all-date", _FORM, _select_only("when"), popover=False)
    _capture(qapp, folder, "popover-flags", _FORM, _flags, popover=True)
    _capture(qapp, folder, "popover-size-policy", _FORM, _size_policy, popover=True)
    _capture(qapp, folder, "popover-date", _FORM, _date, popover=True)
    _capture(qapp, folder, "popover-locale", _FORM, _locale, popover=True)
    _capture(qapp, folder, "enum-unknown", unknown, _unknown, popover=False)
    _capture(qapp, folder, "keyseq-recording", _FORM, _recording, popover=False)
    _capture(qapp, folder, "keyseq-clash", _ACTIONS, _clash, popover=False)
    _capture(qapp, folder, "number-refusal", _FORM, _refusal, popover=False)
