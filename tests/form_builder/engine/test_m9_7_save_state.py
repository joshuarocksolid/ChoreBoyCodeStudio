"""A failed commit must not keep a new key or reloaded lines on the form."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import pytest

from tests.form_builder.engine.test_m8_2_scenario import invoice_ui, record_window, shop_with_three
from tests.form_builder.engine.test_m8_3b_lines import _edit, _invoice_schema, _prepare, _ui

pytestmark = pytest.mark.unit


def test_a_failed_commit_keeps_the_typed_line_for_the_next_save(tmp_path: Path) -> None:
    with record_window(tmp_path, _ui(), _prepare, schema=_invoice_schema()) as (host, db):
        ui = host.ui
        ui.cbcs_new()
        ui.invoiceNoEdit.setText("INV-NEW")
        ui.customerIdSpin.setValue(1)
        ui.invoiceDateEdit.setText("2026-04-03")
        ui._cbcs_add_row()
        _edit(ui, 0, "description", lambda editor: editor.setText("fresh"))
        _edit(ui, 0, "price", lambda editor: editor.setValue(1.25))
        _fail_the_next_commit()
        assert ui.cbcs_save() is False
        assert ui.cbcs_current_key() is None
        assert _descriptions(db, "INV-NEW") == []
        assert ui.cbcs_save() is True
        assert ui.cbcs_current_key() is not None
        assert _descriptions(db, "INV-NEW") == [("fresh",)]


def test_nullable_text_saves_blank_as_null(tmp_path: Path) -> None:
    with record_window(tmp_path, invoice_ui(), shop_with_three) as (host, db):
        ui = host.ui
        number = ui.invoiceNoEdit.text()
        ui.notesEdit.setText("hello")
        assert ui.cbcs_save() is True
        assert _notes(db, number) == "hello"
        ui.notesEdit.setText("   ")
        assert ui.cbcs_read_fields()["notes"] is None
        assert ui.cbcs_save() is True
        assert _notes(db, number) is None
        ui.notesEdit.setText("  a  ")
        assert ui.cbcs_read_fields()["notes"] == "  a  "
        assert ui.cbcs_save() is True
        assert _notes(db, number) == "  a  "


class _CommitProxy:
    """The sqlite3 connection the form already holds. ``commit`` is read-only on the real object."""

    def __init__(self, inner: sqlite3.Connection, armed: dict) -> None:
        self._inner = inner
        self._armed = armed

    def commit(self) -> None:
        if self._armed["pending"]:
            self._armed["pending"] = False
            raise sqlite3.OperationalError("commit failed")
        self._inner.commit()

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


def _fail_the_next_commit() -> None:
    import cbcs_connections  # type: ignore[import-not-found]

    real_open = cbcs_connections.open_connection
    armed = {"pending": True}

    def open_connection(name: str) -> object:
        connection = real_open(name)
        if name == "shop":
            return _CommitProxy(connection, armed)
        return connection

    cbcs_connections.open_connection = open_connection


def _descriptions(db: Path, invoice_no: str) -> list:
    connection = sqlite3.connect(str(db))
    try:
        return connection.execute(
            """
            SELECT invoice_lines.description
            FROM invoice_lines
            JOIN invoices ON invoices.id = invoice_lines.invoice_id
            WHERE invoices.invoice_no = ?
            ORDER BY invoice_lines.line_no
            """,
            (invoice_no,),
        ).fetchall()
    finally:
        connection.close()


def _notes(db: Path, invoice_no: str) -> Optional[str]:
    connection = sqlite3.connect(str(db))
    try:
        row = connection.execute(
            "SELECT notes FROM invoices WHERE invoice_no = ?",
            (invoice_no,),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    return row[0]
