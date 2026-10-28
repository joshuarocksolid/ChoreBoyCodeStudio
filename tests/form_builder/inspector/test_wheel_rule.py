# pyright: reportAttributeAccessIssue=false
"""UX-PED-005: a wheel over a field without keyboard focus scrolls the inspector and changes nothing."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.inspector.api import GroupId
from app.features.form_builder.qtside.realize import Realizer
from app.qt.QtCore import QPoint, QPointF, Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtGui import QWheelEvent  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtWidgets import QAbstractSpinBox, QApplication, QScrollArea, QVBoxLayout, QWidget
from tests.form_builder.qtside.support import realize

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QVBoxLayout" name="mainLayout">
   <item><widget class="QSpinBox" name="count"/></item>
   <item><widget class="QLineEdit" name="email"/></item>
   <item><widget class="QPushButton" name="okButton"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _enum(group: str, name: str):  # type: ignore[no-untyped-def]
    return getattr(getattr(Qt, group, Qt), name)


def _settle(qapp: QApplication) -> None:
    for _ in range(3):
        qapp.processEvents()


def _wheel(widget: QWidget, delta: int) -> QWheelEvent:
    """Send a wheel event to ``widget`` the way the platform does, and return it for its accepted flag."""
    local = QPointF(widget.rect().center())
    globe = QPointF(widget.mapToGlobal(widget.rect().center()))
    event = QWheelEvent(
        local,
        globe,
        QPoint(0, 0),
        QPoint(0, delta),
        _enum("MouseButton", "NoButton"),
        _enum("KeyboardModifier", "NoModifier"),
        _enum("ScrollPhase", "NoScrollPhase"),
        False,
    )
    QApplication.sendEvent(widget, event)
    return event


def test_wheel_over_an_unfocused_spin_box_scrolls_the_inspector_and_changes_nothing(qapp: QApplication) -> None:
    session, realizer = realize(_FORM)
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    QVBoxLayout(window).addWidget(pane)
    window.resize(360, 240)
    window.show()
    qapp.setActiveWindow(window)
    try:
        count = session.document.by_name("count")[0]
        session.selection.set((count,), source=SelectionSource.PROGRAM)
        pane.set_group_expanded(GroupId.ALL, True)
        pane.flush()
        _settle(qapp)
        spin = next(
            widget for widget in pane.findChildren(QAbstractSpinBox) if widget.isVisible()
        )
        scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
        assert scroll is not None
        bar = scroll.verticalScrollBar()
        assert bar.maximum() > 0, "the inspector must have something to scroll"
        bar.setValue(0)
        search = pane.findChild(QWidget, "formBuilder.inspectorSearch")
        assert search is not None
        search.setFocus()
        _settle(qapp)
        assert not spin.hasFocus() and not spin.isAncestorOf(QApplication.focusWidget())
        before_xml = write_ui(session.document).text
        before_value = spin.value()
        event = _wheel(spin, -120)
        _settle(qapp)
        assert write_ui(session.document).text == before_xml
        assert spin.value() == before_value
        # The field ignored the wheel, so Qt passes it to the parents. Offscreen,
        # sendEvent does not carry it on to the scroll area (a label does not
        # scroll it either), so deliver it to the viewport as propagation would.
        assert not event.isAccepted()
        QApplication.sendEvent(scroll.viewport(), event)
        _settle(qapp)
        assert bar.value() > 0
    finally:
        pane.dispose()
        realizer.dispose()
        session.dispose()
        window.close()
