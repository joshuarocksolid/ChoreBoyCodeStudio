# pyright: reportAttributeAccessIssue=false
"""State rows: which ones show, empty text, and now:."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Tuple

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.inspector import TabId
from app.features.form_builder.qtside.inspector.pane import InspectorPane
from app.qt.QtWidgets import QApplication, QComboBox, QLabel, QVBoxLayout, QWidget
from tests.form_builder.qtside.support import form, opened

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]

_LINE = (
    "cbcsKind",
    "cbcsEnabledWhen",
    "cbcsVisibleWhen",
    "cbcsReadOnlyWhen",
    "cbcsValue",
    "cbcsFormat",
    "cbcsDefault",
)

FORM = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>280</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QCheckBox" name="discountCheck">
     <property name="text"><string>Discount</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="rateLabel">
     <property name="text"><string>Discount rate</string></property>
     <property name="buddy"><cstring>discountEdit</cstring></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="discountEdit"/>
   </item>
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
  </layout>
""",
)

FILLED = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>280</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QCheckBox" name="discountCheck">
     <property name="text"><string>Discount</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="rateLabel">
     <property name="text"><string>Discount rate</string></property>
     <property name="buddy"><cstring>discountEdit</cstring></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="discountEdit">
     <property name="cbcsEnabledWhen"><string>discountCheck</string></property>
    </widget>
   </item>
  </layout>
""",
)


def pump() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(4):
        app.processEvents()


def _id(session: FormSession, name: str) -> object:
    found = session.document.by_name(name)
    assert found, name
    return found[0]


@contextmanager
def desk() -> Iterator[Tuple[FormSession, InspectorPane]]:
    with opened(FORM) as (session, realizer):
        window = QWidget()
        pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
        layout = QVBoxLayout(window)
        layout.addWidget(pane)
        window.resize(480, 720)
        window.show()
        pump()
        try:
            yield session, pane
        finally:
            pane.dispose()
            window.close()
            window.deleteLater()
            pump()


def _select(session: FormSession, pane: InspectorPane, name: str) -> None:
    session.selection.set((_id(session, name),), source=SelectionSource.PROGRAM)  # type: ignore[arg-type]
    pane.focus_tab(TabId.BEHAVIOR)
    pane.flush()
    pump()


def _row(pane: QWidget, key: str) -> QWidget:
    found = pane.findChild(QWidget, "formBuilder.state.row.%s" % key)
    assert found is not None, key
    return found


def _showing(pane: QWidget) -> Tuple[str, ...]:
    found = []
    for key in _LINE:
        row = pane.findChild(QWidget, "formBuilder.state.row.%s" % key)
        if row is not None and row.isVisible():
            found.append(key)
    return tuple(found)


def _stored(session: FormSession, name: str, key: str) -> str:
    node = session.document.node(_id(session, name))  # type: ignore[arg-type]
    assert isinstance(node, WidgetNode)
    value = node.value(key)
    if isinstance(value, StringValue):
        return value.text
    return ""


def test_a_line_edit_lists_kind_through_format_and_a_button_lists_two() -> None:
    with desk() as (session, pane):
        state = pane.findChild(QWidget, "formBuilder.state")
        assert state is not None and state.objectName() == "formBuilder.state"
        _select(session, pane, "discountEdit")
        assert _showing(pane) == _LINE
        enabled = _row(pane, "cbcsEnabledWhen")
        value = enabled.findChild(QLabel, "formBuilder.state.value.cbcsEnabledWhen")
        assert value is not None
        assert value.text() == "always"
        assert pane._services.chrome.muted in value.styleSheet()  # type: ignore[attr-defined]
        assert enabled.accessibleName() == "Enabled when  always"
        kind = _row(pane, "cbcsKind")
        form_row = _row(pane, "cbcsFormat")
        value_row = _row(pane, "cbcsValue")
        assert kind.y() < enabled.y()
        assert value_row.y() < form_row.y()
        assert _stored(session, "discountEdit", "cbcsKind") == ""
        combo = pane.findChild(QComboBox, "formBuilder.state.kind")
        assert combo is not None and combo.currentText() == "Text"
        _select(session, pane, "okButton")
        assert _showing(pane) == ("cbcsEnabledWhen", "cbcsVisibleWhen")


def test_a_filled_enabled_when_row_shows_the_formula_and_now_no(qapp: QApplication) -> None:
    del qapp
    with opened(FILLED) as (session, realizer):
        window = QWidget()
        pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
        layout = QVBoxLayout(window)
        layout.addWidget(pane)
        window.resize(480, 720)
        window.show()
        pump()
        try:
            _select(session, pane, "discountEdit")
            row = _row(pane, "cbcsEnabledWhen")
            formula = row.findChild(QLabel, "formBuilder.state.value.cbcsEnabledWhen")
            now = row.findChild(QLabel, "formBuilder.state.now.cbcsEnabledWhen")
            assert formula is not None and formula.text() == "discountCheck"
            assert now is not None and now.text() == "now: no" and now.isVisible()
            assert row.accessibleName() == "Enabled when  discountCheck   now: no"
        finally:
            pane.dispose()
            window.close()
