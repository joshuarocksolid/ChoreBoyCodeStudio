# pyright: reportAttributeAccessIssue=false
"""Lookup section: one undo per control, Show focused after insert, the long-list sentence."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.schema import Column, Reference, Schema, Table, set_schema_reader
from app.features.form_builder.engine.data.source import Lookup, RecordSource, read_lookup, write_data, write_lookup
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.inspector.data_page import DataPage
from app.qt.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QWidget
from tests.form_builder.qtside.test_m8_2_data_tab import _FORM, _column_row, _connect, _prop
from xml.sax.saxutils import escape

pytestmark = pytest.mark.unit

_SCHEMA = Schema(
    "office",
    "sqlite",
    "SQLite",
    "2026-11-02T12:00:00",
    "sqlite3",
    (
        Table(
            "invoices",
            (
                Column("id", "integer", False, unique=True),
                Column("customer_id", "integer", True, references=Reference("customers", "id")),
            ),
            key="id",
        ),
        Table(
            "customers",
            (
                Column("id", "integer", False),
                Column("name", "text", True),
                Column("email", "text", True),
            ),
            key="id",
            rows=12480,
        ),
    ),
)


@pytest.fixture
def office(tmp_path):
    set_schema_reader(lambda _doc, _name: _SCHEMA)
    save_connections(
        str(tmp_path),
        ConnectionSet((Connection("office", "Office", "sqlite", file="shop.db"),)),
    )
    try:
        yield tmp_path
    finally:
        set_schema_reader(None)


def test_changing_show_is_one_undo_and_names_the_row_count(qapp, office) -> None:
    session, host = _open(_combo_form(), office)
    try:
        combo_id = session.document.by_name("customerCombo")[0]
        session.selection.set((combo_id,), source=SelectionSource.PROGRAM)
        host.show()
        page = DataPage(host)
        page.resize(420, 560)
        page.show()
        qapp.processEvents()
        page.paint("QComboBox")
        qapp.processEvents()
        show = page.findChild(QComboBox, "formBuilder.inspectorData.lookupShow")
        rows = page.findChild(QLabel, "formBuilder.inspectorData.lookupRows")
        typed = page.findChild(QCheckBox, "formBuilder.inspectorData.lookupType")
        assert show is not None and rows is not None and typed is not None
        assert show.currentData() == "name"
        assert "12,480" in rows.text()
        assert page.findChild(QWidget, "formBuilder.inspectorData.lookup").accessibleName() == "Lookup, fill from customers, show name"
        before = len(session.log.entries())
        show.setCurrentIndex(show.findData("email"))
        assert len(session.log.entries()) == before + 1
        assert session.log.undo_label() == "Show email"
        found, error = read_lookup(_prop(session.document.node(combo_id), "cbcsLookup"))
        assert error is None and found is not None and found.show == "email"
        typed.setChecked(True)
        assert session.log.undo_label() == "Let people type to search"
        assert session.log.undo()
        assert session.log.undo()
        found, _error = read_lookup(_prop(session.document.node(combo_id), "cbcsLookup"))
        assert found is not None and found.show == "name"
    finally:
        session.dispose()


def test_insert_focuses_show(qapp, office) -> None:
    session, host = _open(_FORM, office)
    try:
        _connect(session)
        panel_host = host
        from app.features.form_builder.qtside.data_panel.panel import DataPanel
        from app.qt.QtCore import QEvent, Qt
        from app.qt.QtGui import QKeyEvent

        panel = DataPanel(panel_host)
        row = _column_row(panel, "customer_id")
        row.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
        combo_id = session.document.by_name("customer_id")[0]
        from app.features.form_builder.qtside.data_panel.lookup_columns import pending_show_focus

        assert pending_show_focus(session.document) == combo_id
        host.show()
        page = DataPage(host)
        page.resize(420, 560)
        page.show()
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            QApplication.setActiveWindow(page)
        qapp.processEvents()
        page.paint("QComboBox")
        for _cycle in range(4):
            qapp.processEvents()
        show = page.findChild(QComboBox, "formBuilder.inspectorData.lookupShow")
        assert show is not None
        assert QApplication.focusWidget() is show or show.hasFocus()
    finally:
        session.dispose()


def _combo_form() -> str:
    source = write_data(RecordSource("office", "invoices", "id"))
    lookup = write_lookup(Lookup("customers", "id", "name", order="name", blank="(choose a customer)"))
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="cbcsData" stdset="0"><string notr="true">%s</string></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QComboBox" name="customerCombo">
     <property name="cbcsBind" stdset="0"><string notr="true">customer_id</string></property>
     <property name="cbcsLookup" stdset="0"><string notr="true">%s</string></property>
    </widget>
   </item>
  </layout>
 </widget>
</ui>
""" % (escape(source), escape(lookup))


def _open(text: str, folder):
    scope = FormScope(kind="external", ui_path=str(folder / "form.ui"), project_root=str(folder))
    session = FormSession.open(text, path=str(folder / "form.ui"), scope=scope)
    host = QWidget()
    host.session = session
    host.project_root = str(folder)
    return session, host
