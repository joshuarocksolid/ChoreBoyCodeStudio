# pyright: reportAttributeAccessIssue=false
"""M8.2 Data tab: connect, bind, Show SQL, and the record toolbar are one undo step each."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.data import sql
from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.schema import Column, Reference, Schema, Table, set_schema_reader
from app.features.form_builder.engine.data.source import RecordSource, has_data_source, read_data
from app.features.form_builder.engine.logic.codec import parse_steps
from app.features.form_builder.engine.logic.storage import signal_property
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.data_panel.panel import DataPanel
from app.features.form_builder.qtside.data_panel.sheets import BindSheet, ConnectSheet, SqlDialog
from app.qt.QtCore import QEvent, Qt
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import QWidget

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="invoiceDateLabel"><property name="text"><string>Invoice date</string></property></widget>
   </item>
   <item row="0" column="1">
    <widget class="QLineEdit" name="invoiceDateEdit"/>
   </item>
   <item row="1" column="0">
    <widget class="QLabel" name="notesLabel"><property name="text"><string>Notes</string></property></widget>
   </item>
   <item row="1" column="1">
    <widget class="QLineEdit" name="notesEdit"/>
   </item>
  </layout>
 </widget>
</ui>
"""

_VBOX = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLineEdit" name="titleEdit"/>
   </item>
  </layout>
 </widget>
</ui>
"""

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
                Column("invoice_date", "date", True),
                Column("notes", "text", True),
                Column("customer_id", "integer", True, references=Reference("customers", "id")),
            ),
            key="id",
        ),
        Table("audit_log", (Column("message", "text", True),), key=None),
    ),
)

_SHORTCUTS = {
    "firstButton": "Ctrl+Home",
    "previousButton": "PgUp",
    "nextButton": "PgDown",
    "lastButton": "Ctrl+End",
    "newButton": "Ctrl+N",
    "saveButton": "Ctrl+S",
    "findButton": "Ctrl+F",
}


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


def test_connect_writes_one_undo_step(qapp, office) -> None:
    del qapp
    session, host = _open(_FORM, office)
    try:
        panel = DataPanel(host)
        assert panel.findChild(QWidget, "formBuilder.data.connect").isEnabled()
        add = panel.findChild(QWidget, "formBuilder.data.addConnection")
        assert add is not None and not add.isVisible()
        sheet = ConnectSheet(host, session)
        disabled = [
            sheet._form._tables.item(row).text()
            for row in range(sheet._form._tables.count())
            if sheet._form._tables.item(row) is not None
        ]
        assert any("audit_log has no single key column. Record forms need one." in text for text in disabled)
        sheet._form._select_table("invoices")
        sheet._commit()
        assert has_data_source(session.document)
        source = read_data(_text(session, "cbcsData")).value
        assert isinstance(source, RecordSource) and source.table == "invoices" and source.key == "id"
        assert len(session.log.entries()) == 1
        assert session.log.undo_label() == "Connect to invoices"
        assert session.log.undo()
        assert not has_data_source(session.document)
    finally:
        session.dispose()


def test_enter_on_a_column_inserts_a_bound_spin_box_in_one_undo(qapp, office) -> None:
    del qapp
    session, host = _open(_FORM, office)
    try:
        _connect(session)
        panel = DataPanel(host)
        row = _column_row(panel, "customer_id")
        before = len(session.log.entries())
        row.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
        assert len(session.log.entries()) == before + 1
        assert session.log.undo_label() == "Bind customer_id"
        ids = session.document.by_name("customer_id")
        assert len(ids) == 1
        node = session.document.node(ids[0])
        assert node.class_name == "QSpinBox"
        assert _prop(node, "cbcsBind") == "customer_id"
        assert session.log.undo()
        assert session.document.by_name("customer_id") == ()
        assert has_data_source(session.document)
    finally:
        session.dispose()


def test_bind_by_name_is_one_undo_step(qapp, office) -> None:
    del qapp
    session, host = _open(_FORM, office)
    try:
        _connect(session)
        sheet = BindSheet(host, session)
        preview = sheet.preview_text()
        assert "invoiceDateEdit → invoice_date" in preview
        assert "notesEdit → notes" in preview
        before = len(session.log.entries())
        sheet.accept_bind()
        assert len(session.log.entries()) == before + 1
        assert session.log.undo_label() == "Bind fields by name"
        assert _prop(_node(session, "invoiceDateEdit"), "cbcsBind") == "invoice_date"
        assert _prop(_node(session, "notesEdit"), "cbcsBind") == "notes"
        assert session.log.undo()
        assert _prop(_node(session, "invoiceDateEdit"), "cbcsBind") == ""
        assert _prop(_node(session, "notesEdit"), "cbcsBind") == ""
    finally:
        session.dispose()


def test_show_sql_text_is_the_statement_text(qapp, office) -> None:
    del qapp
    session, host = _open(_FORM, office)
    try:
        _connect(session)
        from app.features.form_builder.qtside.data_panel.edits import bind_field

        bind_field(session, session.document.by_name("notesEdit")[0], "notes")
        dialog = SqlDialog(host, session)
        shown = dialog.text()
        order = (("id", "asc"),)
        expected = (
            sql.select_keys("sqlite", "invoices", "id", order),
            sql.load_one("sqlite", "invoices", ("id", "invoice_date", "notes", "customer_id"), "id", "invoice"),
            sql.insert_row("sqlite", "invoices", ("notes",), "id"),
            sql.update_changed("sqlite", "invoices", "id", ("notes",), ("notes",), True),
            sql.delete_row("sqlite", "invoices", "id"),
        )
        for statement in expected:
            assert statement.text in shown
            assert statement.caption in shown
        assert "lookup" not in shown.lower()
    finally:
        session.dispose()


def test_record_toolbar_is_one_undo_step_and_keeps_the_shortcuts(qapp, office) -> None:
    del qapp
    session, _host = _open(_VBOX, office)
    try:
        from app.features.form_builder.qtside.data_panel.edits import insert_record_toolbar

        _connect(session)
        before = len(session.log.entries())
        insert_record_toolbar(session)
        assert len(session.log.entries()) == before + 1
        assert session.log.undo_label() == "Add record toolbar"
        for name, shortcut in _SHORTCUTS.items():
            assert _prop(_node(session, name), "shortcut") == shortcut
        for name in ("revertButton", "deleteButton", "positionLabel"):
            assert _prop(_node(session, name), "shortcut") == ""
        delete = _node(session, "deleteButton")
        steps = parse_steps(_prop(delete, signal_property("clicked"))).steps
        assert [step.verb for step in steps] == ["delete"]
        assert _prop(_node(session, "firstButton"), "cbcsEnabledWhen") == "form.position > 1"
        assert _prop(_node(session, "saveButton"), "cbcsEnabledWhen") == "form.isDirty or form.isNew"
        assert _prop(_node(session, "revertButton"), "cbcsEnabledWhen") == "form.isDirty"
        assert _prop(_node(session, "deleteButton"), "cbcsEnabledWhen") == "not form.isNew"
        assert "text(form.position)" in _prop(_node(session, "positionLabel"), "cbcsValue")
        assert session.log.undo()
        assert session.document.by_name("firstButton") == ()
        assert session.document.by_name("deleteButton") == ()
    finally:
        session.dispose()


def _open(text: str, root):
    scope = FormScope(kind="external", ui_path="/tmp/cbcs-m82.ui", project_root=str(root))
    session = FormSession.open(text, path="/tmp/cbcs-m82.ui", scope=scope)
    host = QWidget()
    host.session = session
    host.project_root = str(root)
    return session, host


def _connect(session: FormSession) -> None:
    from app.features.form_builder.engine.data.source import RecordSource
    from app.features.form_builder.qtside.data_panel.edits import connect_form

    connect_form(session, RecordSource("office", "invoices", "id"))


def _column_row(panel: QWidget, name: str) -> QWidget:
    for row in panel.findChildren(QWidget, "formBuilder.data.columnRow"):
        if row.property("column") == name:
            return row
    raise AssertionError(name)


def _node(session: FormSession, name: str):
    return session.document.node(session.document.by_name(name)[0])


def _prop(node: object, name: str) -> str:
    entry = node.prop(name)  # type: ignore[attr-defined]
    if entry is None or not isinstance(entry.value, StringValue):
        return ""
    return entry.value.text


def _text(session: FormSession, name: str) -> str:
    return _prop(session.document.root, name)
