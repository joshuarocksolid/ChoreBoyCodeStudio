# pyright: reportAttributeAccessIssue=false
"""UX-PED-002: an editor that asks for the stacked row gets its label above it, at full width."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.qtside.inspector._properties import _Row
from app.features.form_builder.qtside.inspector._services import Services
from app.features.form_builder.qtside.inspector.api import EditorKey, OpenRow, Unset, ValueSpec
from app.features.form_builder.qtside.inspector.catalog import Registrations
from app.features.form_builder.qtside.inspector.model import PropertyWrite
from app.qt.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget
from tests.form_builder.qtside.support import open_session

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form"><widget class="QLineEdit" name="field"/></widget>
 <resources/>
 <connections/>
</ui>
"""

_KEY = EditorKey("fbtestwide")


class _Editor:
    """A test editor that stacks below 300 px, as the size editors do."""

    def __init__(self, parent: QWidget, *, stacks: bool) -> None:
        self._stacks = stacks
        self._widget = QWidget(parent)
        layout = QVBoxLayout(self._widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLineEdit("1234567890", self._widget))

    @property
    def widget(self) -> QWidget:
        return self._widget

    def show(self, value: object) -> None:
        del value

    def wants_stacked(self, width: int) -> bool:
        return self._stacks and width < 300


def _catalog(stacks: bool):  # type: ignore[no-untyped-def]
    found = Registrations()
    found.scope("tests.stacked").editor(_KEY, lambda spec, host, parent: _Editor(parent, stacks=stacks))
    return found.freeze()


def _row(qapp: QApplication, width: int, stacks: bool):  # type: ignore[no-untyped-def]
    session = open_session(_FORM, "/tmp/cbcs-stacked.ui")
    node: NodeId = session.document.by_name("field")[0]
    services = Services(session, _catalog(stacks), None)
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    row = _Row(services, container)
    layout.addWidget(row)
    view = OpenRow(
        key="fbtest.row",
        label="Test field",
        qt_name="",
        help="",
        value=Unset(),
        spec=ValueSpec(element="fbtest"),
        editor=_KEY,
        write=PropertyWrite((node,), "text"),
    )
    row.paint(view, "", False)
    container.resize(width, 120)
    container.show()
    for _ in range(4):
        qapp.processEvents()
    return session, container, row


def _lowest_label_edge(row: _Row) -> int:
    return row._label_col.mapTo(row, row._label_col.rect().bottomLeft()).y()


def test_a_stacking_editor_puts_its_label_above_it_at_236_px(qapp: QApplication) -> None:
    session, container, row = _row(qapp, 236, stacks=True)
    try:
        editor = row._editor.widget  # type: ignore[union-attr]
        assert row._stacked is True
        assert _lowest_label_edge(row) <= editor.mapTo(row, editor.rect().topLeft()).y()
        assert editor.width() >= row.width() - 4
        assert row.minimumSizeHint().width() <= 236
    finally:
        container.close()
        session.dispose()


def test_a_stacking_editor_sits_beside_its_label_at_320_px(qapp: QApplication) -> None:
    session, container, row = _row(qapp, 320, stacks=True)
    try:
        editor = row._editor.widget  # type: ignore[union-attr]
        assert row._stacked is False
        assert row._label_col.geometry().right() < editor.mapTo(row, editor.rect().topLeft()).x()
    finally:
        container.close()
        session.dispose()


def test_an_editor_that_never_stacks_keeps_the_side_by_side_row(qapp: QApplication) -> None:
    session, container, row = _row(qapp, 236, stacks=False)
    try:
        editor = row._editor.widget  # type: ignore[union-attr]
        assert row._stacked is False
        assert row._label_col.geometry().right() < editor.mapTo(row, editor.rect().topLeft()).x()
        assert row._label_col.width() == row._label_px
    finally:
        container.close()
        session.dispose()


def test_the_row_restacks_when_it_is_widened(qapp: QApplication) -> None:
    session, container, row = _row(qapp, 236, stacks=True)
    try:
        container.resize(320, 120)
        for _ in range(4):
            qapp.processEvents()
        assert row._stacked is False
        container.resize(236, 120)
        for _ in range(4):
            qapp.processEvents()
        assert row._stacked is True
    finally:
        container.close()
        session.dispose()
