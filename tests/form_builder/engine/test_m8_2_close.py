"""Unsaved-changes answers on close, Next, and New."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.form_builder.engine.test_m8_2_scenario import CANCEL, DISCARD, SAVE, invoice_ui, record_window, shop_with_three

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("action", ["close", "next", "new"])
def test_cancel_leaves_the_record_and_the_value(tmp_path: Path, action: str) -> None:
    with record_window(tmp_path, invoice_ui(), shop_with_three, questions=[CANCEL]) as (host, db):
        host.ui.notesEdit.setText("kept")
        _leave(host, action)
        assert host.ui.invoiceNoEdit.text() == "INV-3"
        assert host.ui.notesEdit.text() == "kept"
        assert host.ui._cbcs_form_is_new() is False
        assert _notes(db, "INV-3") == ""


@pytest.mark.parametrize("action", ["close", "next", "new"])
def test_discard_drops_the_edit(tmp_path: Path, action: str) -> None:
    with record_window(tmp_path, invoice_ui(), shop_with_three, questions=[DISCARD]) as (host, db):
        host.ui.notesEdit.setText("kept")
        closed = _leave(host, action)
        assert _notes(db, "INV-3") == ""
        if action == "close":
            assert closed is True
        elif action == "next":
            assert host.ui.invoiceNoEdit.text() == "INV-2"
        else:
            assert host.ui._cbcs_form_is_new() is True
            assert host.ui.invoiceNoEdit.text() == ""


@pytest.mark.parametrize("action", ["close", "next", "new"])
def test_save_writes_then_leaves(tmp_path: Path, action: str) -> None:
    with record_window(tmp_path, invoice_ui(), shop_with_three, questions=[SAVE]) as (host, db):
        host.ui.notesEdit.setText("kept")
        closed = _leave(host, action)
        assert _notes(db, "INV-3") == "kept"
        if action == "close":
            assert closed is True
        elif action == "next":
            assert host.ui.invoiceNoEdit.text() == "INV-2"
        else:
            assert host.ui._cbcs_form_is_new() is True
            assert host.ui.invoiceNoEdit.text() == ""


def _leave(host: object, action: str) -> object:
    if action == "close":
        return host.close()  # type: ignore[attr-defined]
    if action == "next":
        host.ui.cbcs_next()  # type: ignore[attr-defined]
        return None
    host.ui.cbcs_new()  # type: ignore[attr-defined]
    return None


def _notes(db: Path, invoice_no: str) -> str:
    import sqlite3

    connection = sqlite3.connect(str(db))
    try:
        row = connection.execute("SELECT notes FROM invoices WHERE invoice_no = ?", (invoice_no,)).fetchone()
    finally:
        connection.close()
    assert row is not None
    return row[0]
