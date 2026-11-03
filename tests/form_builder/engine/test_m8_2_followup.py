"""Review fixes for the record form. Each test checks a database row or the text on screen."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.data.schema import Column, Reference, Schema, Table
from app.features.form_builder.engine.data.source import RecordSource, read_data, write_data
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui
from tests.form_builder.engine.test_m8_2_scenario import _xml, invoice_ui, record_window, shop_with_three

pytestmark = pytest.mark.unit


def test_find_with_one_column_returns_the_matching_row(tmp_path: Path) -> None:
    source = RecordSource(
        "shop",
        "invoices",
        "id",
        order=(("invoice_date", "desc"), ("id", "desc")),
        search=("invoice_no",),
    )
    ui = _xml(
        source,
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QLineEdit", "notesEdit", "notes", ""),
        ),
    )
    with record_window(tmp_path, ui, shop_with_three, finder=lambda: ("INV-2", True), schema=_shop_schema()) as (host, db):
        host.ui.cbcs_find()
        assert host.ui.invoiceNoEdit.text() == "INV-2"
        assert _one(db, "SELECT invoice_no FROM invoices WHERE invoice_no = ?", ("INV-2",)) == ("INV-2",)


def test_time_and_datetime_round_trip(tmp_path: Path) -> None:
    schema = _table_schema(
        "clocks",
        (Column("id", "INTEGER", False), Column("at_time", "time", True), Column("at_stamp", "timestamp", True)),
        "id",
    )
    ui = _xml(
        RecordSource("shop", "clocks", "id"),
        (("QTimeEdit", "timeEdit", "at_time", ""), ("QDateTimeEdit", "stampEdit", "at_stamp", "")),
    )

    def prepare(root: Path) -> Path:
        return _sqlite(
            root,
            ("CREATE TABLE clocks (id INTEGER PRIMARY KEY, at_time TEXT, at_stamp TEXT)",),
            (("INSERT INTO clocks (id, at_time, at_stamp) VALUES (?, ?, ?)", (1, "09:30:00", "2026-04-01 09:30:00")),),
        )

    with record_window(tmp_path, ui, prepare, schema=schema) as (host, db):
        from PySide6.QtCore import QDate, QDateTime, QTime

        assert host.ui.timeEdit.time() == QTime(9, 30, 0)
        host.ui.timeEdit.setTime(QTime(10, 15, 0))
        host.ui.stampEdit.setDateTime(QDateTime(QDate(2026, 4, 2), QTime(11, 0, 0)))
        assert host.ui.cbcs_save() is True
        assert _one(db, "SELECT at_time, at_stamp FROM clocks WHERE id = 1") == ("10:15:00", "2026-04-02 11:00:00")


def test_a_typed_text_key_is_inserted(tmp_path: Path) -> None:
    schema = _table_schema(
        "codes",
        (Column("code", "TEXT", False), Column("label", "TEXT", False)),
        "code",
    )
    ui = _xml(
        RecordSource("shop", "codes", "code", open_at="new"),
        (("QLineEdit", "codeEdit", "code", ""), ("QLineEdit", "labelEdit", "label", "")),
    )

    def prepare(root: Path) -> Path:
        return _sqlite(root, ("CREATE TABLE codes (code TEXT PRIMARY KEY, label TEXT NOT NULL)",))

    with record_window(tmp_path, ui, prepare, schema=schema) as (host, db):
        host.ui.codeEdit.setText("A1")
        host.ui.labelEdit.setText("hello")
        assert host.ui.cbcs_save() is True
        assert host.ui.cbcs_current_key() == "A1"
        assert _one(db, "SELECT label FROM codes WHERE code = ?", ("A1",)) == ("hello",)


def test_a_null_date_stays_blank_and_saves_null(tmp_path: Path) -> None:
    schema = _table_schema(
        "days",
        (Column("id", "INTEGER", False), Column("when_on", "date", True)),
        "id",
    )
    ui = _xml(RecordSource("shop", "days", "id"), (("QDateEdit", "whenEdit", "when_on", ""),))

    def prepare(root: Path) -> Path:
        return _sqlite(
            root,
            ("CREATE TABLE days (id INTEGER PRIMARY KEY, when_on TEXT)",),
            (
                ("INSERT INTO days (id, when_on) VALUES (?, ?)", (1, "2026-04-01")),
                ("INSERT INTO days (id, when_on) VALUES (?, ?)", (2, None)),
            ),
        )

    with record_window(tmp_path, ui, prepare, schema=schema) as (host, db):
        assert host.ui.whenEdit.date().year() == 2026
        host.ui.cbcs_next()
        assert host.ui.whenEdit.text().strip() == ""
        assert host.ui.cbcs_save() is True
        assert _one(db, "SELECT when_on FROM days WHERE id = 2") == (None,)
        assert _one(db, "SELECT when_on FROM days WHERE id = 1") == ("2026-04-01",)


def test_a_nullable_spin_saves_null_not_zero(tmp_path: Path) -> None:
    schema = _table_schema(
        "links",
        (
            Column("id", "INTEGER", False),
            Column("customer_id", "INTEGER", True, references=Reference("customers", "id")),
        ),
        "id",
    )
    ui = _xml(
        RecordSource("shop", "links", "id", open_at="new"),
        (("QSpinBox", "customerIdSpin", "customer_id", ""),),
    )

    def prepare(root: Path) -> Path:
        return _sqlite(
            root,
            (
                "CREATE TABLE customers (id INTEGER PRIMARY KEY)",
                "CREATE TABLE links (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id))",
            ),
            (("INSERT INTO customers (id) VALUES (?)", (1,)),),
        )

    with record_window(tmp_path, ui, prepare, schema=schema) as (host, db):
        assert host.ui.cbcs_save() is True
        assert _one(db, "SELECT customer_id FROM links") == (None,)


def test_a_nullable_spin_keeps_a_real_zero(tmp_path: Path) -> None:
    schema = _table_schema(
        "stock",
        (Column("id", "INTEGER", False), Column("quantity", "INTEGER", True)),
        "id",
    )
    ui = _xml(
        RecordSource("shop", "stock", "id", open_at="new"),
        (("QSpinBox", "quantitySpin", "quantity", ""),),
    )

    def prepare(root: Path) -> Path:
        return _sqlite(root, ("CREATE TABLE stock (id INTEGER PRIMARY KEY, quantity INTEGER)",), ())

    with record_window(tmp_path, ui, prepare, schema=schema) as (host, db):
        spin = host.ui.quantitySpin
        assert spin.text().strip() == ""
        spin.setValue(0)
        assert spin.text().strip() == "0"
        assert host.ui.cbcs_save() is True
        assert _one(db, "SELECT quantity FROM stock") == (0,)


def test_a_nullable_check_box_saves_null(tmp_path: Path) -> None:
    schema = _table_schema(
        "flags",
        (Column("id", "INTEGER", False), Column("paid", "INTEGER", True)),
        "id",
    )
    ui = _xml(RecordSource("shop", "flags", "id"), (("QCheckBox", "paidBox", "paid", ""),))

    def prepare(root: Path) -> Path:
        return _sqlite(
            root,
            ("CREATE TABLE flags (id INTEGER PRIMARY KEY, paid INTEGER)",),
            (("INSERT INTO flags (id, paid) VALUES (?, ?)", (1, None)),),
        )

    with record_window(tmp_path, ui, prepare, schema=schema) as (host, db):
        from PySide6.QtCore import Qt

        assert host.ui.paidBox.checkState() == Qt.CheckState.PartiallyChecked
        host.ui.cbcs_new()
        assert host.ui.cbcs_save() is True
        assert _one(db, "SELECT paid FROM flags WHERE id != 1") == (None,)


def test_a_deferred_foreign_key_is_shown_after_rollback(tmp_path: Path) -> None:
    seen: List[str] = []
    schema = _table_schema(
        "kids",
        (
            Column("id", "INTEGER", False),
            Column("parent_id", "INTEGER", True, references=Reference("parents", "id")),
        ),
        "id",
    )
    ui = _xml(
        RecordSource("shop", "kids", "id", open_at="new"),
        (("QSpinBox", "parentIdSpin", "parent_id", ""),),
    )
    probe: List[str] = []

    def prepare(root: Path) -> Path:
        return _sqlite(
            root,
            (
                "CREATE TABLE parents (id INTEGER PRIMARY KEY)",
                "CREATE TABLE kids (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parents(id) DEFERRABLE INITIALLY DEFERRED)",
            ),
        )

    def during() -> None:
        _probe_write(db_holder[0], probe)

    db_holder: List[Path] = []

    def wrapped(root: Path) -> Path:
        path = prepare(root)
        db_holder.append(path)
        return path

    with record_window(tmp_path, ui, wrapped, schema=schema, seen=seen, during=during) as (host, _db):
        host.ui.parentIdSpin.setValue(99)
        assert host.ui.cbcs_save() is False
        assert host.ui.parentIdSpin.value() == 99
        assert _one(_db, "SELECT COUNT(*) FROM kids") == (0,)
        assert probe == ["unlocked"]
        assert any("FOREIGN KEY" in text for text in seen)
        assert all(not text.startswith("{") for text in seen)


def test_unique_violation_uses_the_field_label(tmp_path: Path) -> None:
    ui = _labeled(
        RecordSource("shop", "invoices", "id", order=(("id", "asc"),)),
        "invoice_no",
        "invoiceNoEdit",
        "Invoice number",
        "QLineEdit",
    )

    def prepare(root: Path) -> Path:
        return _sqlite(
            root,
            ("CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_no TEXT NOT NULL UNIQUE)",),
            (
                ("INSERT INTO invoices (id, invoice_no) VALUES (?, ?)", (1, "INV-1")),
                ("INSERT INTO invoices (id, invoice_no) VALUES (?, ?)", (2, "INV-2")),
            ),
        )

    schema = _table_schema(
        "invoices",
        (Column("id", "INTEGER", False), Column("invoice_no", "TEXT", False, unique=True)),
        "id",
    )
    with record_window(tmp_path, ui, prepare, schema=schema) as (host, db):
        host.ui.cbcs_next()
        host.ui.invoiceNoEdit.setText("INV-1")
        assert host.ui.cbcs_save() is False
        assert host.ui.invoiceNoEditError.text() == "Another invoice already uses this invoice number."
        assert host.ui.invoiceNoEditError.isVisible() is True
        assert _one(db, "SELECT invoice_no FROM invoices WHERE id = 2") == ("INV-2",)


def test_not_null_violation_uses_the_field_label(tmp_path: Path) -> None:
    ui = _labeled(
        RecordSource("shop", "notes", "id"),
        "body",
        "bodyEdit",
        "Body",
        "QLineEdit",
    )
    schema = _table_schema(
        "notes",
        (Column("id", "INTEGER", False), Column("body", "TEXT", True)),
        "id",
    )

    def prepare(root: Path) -> Path:
        return _sqlite(
            root,
            ("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT NOT NULL)",),
            (("INSERT INTO notes (id, body) VALUES (?, ?)", (1, "kept")),),
        )

    with record_window(tmp_path, ui, prepare, schema=schema) as (host, db):
        host.ui.bodyEdit.setText("")
        assert host.ui.cbcs_save() is False
        assert host.ui.bodyEditError.text() == "Body is required."
        assert _one(db, "SELECT body FROM notes WHERE id = 1") == ("kept",)


def test_not_null_text_saves_an_empty_string(tmp_path: Path) -> None:
    schema = _table_schema(
        "notes",
        (Column("id", "INTEGER", False), Column("body", "TEXT", False)),
        "id",
    )
    ui = _xml(RecordSource("shop", "notes", "id"), (("QLineEdit", "bodyEdit", "body", ""),))

    def prepare(root: Path) -> Path:
        return _sqlite(
            root,
            ("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)",),
            (("INSERT INTO notes (id, body) VALUES (?, ?)", (1, "kept")),),
        )

    with record_window(tmp_path, ui, prepare, schema=schema) as (host, db):
        host.ui.bodyEdit.setText("")
        assert host.ui.cbcs_save() is True
        assert _one(db, "SELECT body FROM notes WHERE id = 1") == ("",)


def test_a_json_column_is_not_written(tmp_path: Path) -> None:
    schema = _table_schema(
        "docs",
        (Column("id", "INTEGER", False), Column("notes", "TEXT", True), Column("payload", "json", True)),
        "id",
    )
    ui = _xml(
        RecordSource("shop", "docs", "id"),
        (("QLineEdit", "notesEdit", "notes", ""), ("QLineEdit", "payloadEdit", "payload", "")),
    )

    def prepare(root: Path) -> Path:
        return _sqlite(
            root,
            ("CREATE TABLE docs (id INTEGER PRIMARY KEY, notes TEXT, payload TEXT)",),
            (("INSERT INTO docs (id, notes, payload) VALUES (?, ?, ?)", (1, "hi", '{"a": 1}')),),
        )

    with record_window(tmp_path, ui, prepare, schema=schema) as (host, db):
        host.ui.payloadEdit.setText("nope")
        host.ui.notesEdit.setText("changed")
        assert host.ui.cbcs_save() is True
        assert _one(db, "SELECT notes, payload FROM docs WHERE id = 1") == ("changed", '{"a": 1}')


def test_a_text_combo_saves_its_current_text(tmp_path: Path) -> None:
    items = (
        '    <item><property name="text"><string>open</string></property></item>\n'
        '    <item><property name="text"><string>paid</string></property></item>\n'
    )
    schema = _table_schema(
        "jobs",
        (Column("id", "INTEGER", False), Column("status", "TEXT", True)),
        "id",
    )
    ui = _xml(RecordSource("shop", "jobs", "id"), (("QComboBox", "statusBox", "status", items),))

    def prepare(root: Path) -> Path:
        return _sqlite(
            root,
            ("CREATE TABLE jobs (id INTEGER PRIMARY KEY, status TEXT)",),
            (("INSERT INTO jobs (id, status) VALUES (?, ?)", (1, "open")),),
        )

    with record_window(tmp_path, ui, prepare, schema=schema) as (host, db):
        host.ui.statusBox.setCurrentIndex(1)
        assert host.ui.cbcs_save() is True
        assert _one(db, "SELECT status FROM jobs WHERE id = 1") == ("paid",)


def test_keep_mine_writes_the_typed_value(tmp_path: Path) -> None:
    source = RecordSource(
        "shop",
        "invoices",
        "id",
        order=(("invoice_date", "desc"), ("id", "desc")),
        allow_overwrite=True,
    )
    ui = _xml(source, (("QLineEdit", "invoiceNoEdit", "invoice_no", ""), ("QLineEdit", "notesEdit", "notes", "")))

    def choose(text: str) -> str:
        if text.startswith("Someone else"):
            return "Keep mine and save"
        return "Close"

    with record_window(tmp_path, ui, shop_with_three, choose=choose, schema=_shop_schema()) as (host, db):
        _exec(db, "UPDATE invoices SET notes = ? WHERE invoice_no = ?", ("other", "INV-3"))
        host.ui.notesEdit.setText("mine")
        assert host.ui.cbcs_save() is True
        assert _one(db, "SELECT notes FROM invoices WHERE invoice_no = ?", ("INV-3",)) == ("mine",)


def test_allow_overwrite_round_trips_in_cbcs_data() -> None:
    stored = write_data(RecordSource("shop", "invoices", "id", allow_overwrite=True))
    assert "allowOverwrite" in stored
    read = read_data(stored)
    value = read.value
    assert isinstance(value, RecordSource)
    assert value.allow_overwrite is True
    omitted = write_data(RecordSource("shop", "invoices", "id"))
    assert "allowOverwrite" not in omitted
    rejected = read_data(stored.replace("true", '"nope"', 1))
    assert rejected.value is None
    assert rejected.error is not None and "allowOverwrite" in rejected.error


def test_a_missing_connections_file_is_fb301(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    ui_path = forms / "invoice.ui"
    ui_text = invoice_ui()
    ui_path.write_text(ui_text, encoding="utf-8")
    result = _generate_result(root, ui_path, ui_text)
    assert any(item.code == "FB301" for item in result.diagnostics)
    assert result.text is None or "cbcs_save" not in result.text
    (root / "connections.json").write_text("{", encoding="utf-8")
    broken = _generate_result(root, ui_path, ui_text)
    assert any(item.code == "FB302" for item in broken.diagnostics)


def _labeled(source: RecordSource, column: str, name: str, caption: str, class_name: str) -> str:
    label = (
        '    <property name="text"><string>%s</string></property>\n'
        '    <property name="buddy"><cstring>%s</cstring></property>\n' % (caption, name)
    )
    error = '    <property name="cbcsErrorLabel" stdset="0"><string notr="true">%sError</string></property>\n' % name
    return _xml(
        source,
        (
            ("QLabel", "%sLabel" % name, "", label),
            (class_name, name, column, error),
            ("QLabel", "%sError" % name, "", '    <property name="text"><string></string></property>\n'),
        ),
    )


def _shop_schema() -> Schema:
    return Schema(
        "shop",
        "sqlite",
        "",
        "2026-01-01T00:00:00",
        "sqlite3",
        (
            Table("customers", (Column("id", "INTEGER", False), Column("name", "TEXT", False)), key="id"),
            Table(
                "invoices",
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_no", "TEXT", False, unique=True),
                    Column("customer_id", "INTEGER", False, references=Reference("customers", "id")),
                    Column("invoice_date", "TEXT", True),
                    Column("notes", "TEXT", True),
                    Column("total", "NUMERIC", True),
                ),
                key="id",
            ),
        ),
    )


def _table_schema(name: str, columns: Tuple[Column, ...], key: str) -> Schema:
    return Schema("shop", "sqlite", "", "2026-01-01T00:00:00", "sqlite3", (Table(name, columns, key=key),))


def _sqlite(root: Path, statements: Sequence[str], rows: Sequence[Tuple[str, Tuple[Any, ...]]] = ()) -> Path:
    path = root / "data" / "shop.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        for statement in statements:
            connection.execute(statement)
        for statement, params in rows:
            connection.execute(statement, params)
        connection.commit()
    finally:
        connection.close()
    return path


def _one(db: Path, sql: str, params: Tuple[Any, ...] = ()) -> Optional[tuple]:
    connection = sqlite3.connect(str(db), timeout=2)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        return connection.execute(sql, params).fetchone()
    finally:
        connection.close()


def _exec(db: Path, sql: str, params: Tuple[Any, ...]) -> None:
    connection = sqlite3.connect(str(db), timeout=2)
    try:
        connection.execute(sql, params)
        connection.commit()
    finally:
        connection.close()


def _probe_write(db: Path, probe: List[str]) -> None:
    connection = sqlite3.connect(str(db), timeout=0.2)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS probe (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO probe (id) VALUES (1)")
        connection.commit()
        probe.append("unlocked")
    except sqlite3.OperationalError:
        probe.append("locked")
    finally:
        connection.close()


def _generate_result(root: Path, ui_path: Path, ui_text: str) -> Any:
    read = read_ui(ui_text, allocator=IdAllocator())
    scope = FormScope(
        kind="project",
        ui_path=str(ui_path),
        project_root=str(root),
        generated_path=str(ui_path.parent / "ui_invoice.py"),
        window_path=str(ui_path.parent / "invoice_window.py"),
        module_name="forms.ui_invoice",
    )
    return generate_form_module(read.document, scope=scope, source_bytes=ui_text.encode("utf-8"))
