# pyright: reportAttributeAccessIssue=false
"""M8.2 inspector Data tab: the form root, a bound column, and a problem badge."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.data.schema import Column, Schema, Table, set_schema_reader
from app.features.form_builder.engine.data.source import RecordSource
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.data_panel.edits import bind_field, connect_form
from app.features.form_builder.qtside.inspector.data_page import DataPage, selected_class
from app.qt.QtWidgets import QCheckBox, QComboBox, QLabel, QWidget

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="1">
    <widget class="QLineEdit" name="invoiceDateEdit"/>
   </item>
   <item row="1" column="1">
    <widget class="QCheckBox" name="paidCheck"><property name="text"><string>Paid</string></property></widget>
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
                Column("id", "integer", False),
                Column("invoice_date", "date", True),
            ),
            key="id",
        ),
    ),
)


@pytest.fixture
def schema():
    set_schema_reader(lambda _doc, _name: _SCHEMA)
    try:
        yield
    finally:
        set_schema_reader(None)


def test_the_document_root_is_a_form_token(schema) -> None:
    del schema
    session = _open()
    try:
        root = session.document.root.id
        assert selected_class(session.document, (root,)) == "@form"
        assert selected_class(session.document, (session.document.by_name("invoiceDateEdit")[0],)) == "QLineEdit"
    finally:
        session.dispose()


def test_the_root_section_hides_the_not_bound_placeholder(qapp, schema) -> None:
    del qapp, schema
    session = _open()
    try:
        host = _host(session)
        host.show()
        page = DataPage(host)
        page.show()
        page.paint("@form")
        assert page.findChild(QWidget, "formBuilder.inspectorData.formSource") is not None
        placeholder = page.findChild(QWidget, "formBuilder.inspectorData.notBound")
        assert placeholder is None or not placeholder.isVisible()
    finally:
        session.dispose()


def test_a_bound_field_shows_its_column_and_read_only_is_one_undo(qapp, schema) -> None:
    del qapp, schema
    session = _open()
    try:
        connect_form(session, RecordSource("office", "invoices", "id"))
        field = session.document.by_name("invoiceDateEdit")[0]
        bind_field(session, field, "invoice_date")
        session.selection.set((field,), source=SelectionSource.PROGRAM)
        host = _host(session)
        page = DataPage(host)
        page.paint("QLineEdit")
        combo = page.findChild(QComboBox, "formBuilder.inspectorData.column")
        assert combo is not None and combo.currentData() == "invoice_date"
        words = page.findChild(QLabel, "formBuilder.inspectorData.typeWords")
        assert words is not None and words.text() == "date"
        box = page.findChild(QCheckBox, "formBuilder.inspectorData.readOnly")
        assert box is not None
        before = len(session.log.entries())
        box.setChecked(True)
        assert len(session.log.entries()) == before + 1
        node = session.document.node(field)
        entry = node.prop("cbcsBindMode")
        value = getattr(entry, "value", None)
        assert isinstance(value, StringValue) and value.text == "readOnly"
        assert session.log.undo()
        node = session.document.node(field)
        assert node.prop("cbcsBindMode") is None
    finally:
        session.dispose()


def test_a_mismatched_binding_shows_the_problem_badge(qapp, schema) -> None:
    del qapp, schema
    session = _open()
    try:
        connect_form(session, RecordSource("office", "invoices", "id"))
        field = session.document.by_name("paidCheck")[0]
        bind_field(session, field, "invoice_date")
        session.selection.set((field,), source=SelectionSource.PROGRAM)
        host = _host(session)
        host.show()
        page = DataPage(host)
        page.show()
        page.paint("QCheckBox")
        badge = page.findChild(QLabel, "formBuilder.inspectorData.problem")
        assert badge is not None and badge.isVisible()
        assert badge.text() == "A date column can't be shown in a check box."
    finally:
        session.dispose()


def _open() -> FormSession:
    scope = FormScope(kind="external", ui_path="/tmp/cbcs-m82-inspector.ui")
    return FormSession.open(_FORM, path="/tmp/cbcs-m82-inspector.ui", scope=scope)


def _host(session: FormSession) -> QWidget:
    host = QWidget()
    host.session = session
    return host
