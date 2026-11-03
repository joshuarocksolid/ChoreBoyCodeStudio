"""Master-detail lines: the save plan, the generated grid, and the database rows."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

import pytest

from app.features.form_builder.engine.data.check import run_checks
from app.features.form_builder.engine.data.lines import line_plan_source, plan_lines
from app.features.form_builder.engine.data.schema import Column, Reference, Schema, Table, set_schema_reader
from app.features.form_builder.engine.data.source import CalcColumn, DataColumn, Lookup, RecordSource, Rows, read_rows, write_rows
from app.features.form_builder.engine.logic.codec import parse_steps
from app.features.form_builder.engine.logic.storage import signal_property
from app.features.form_builder.engine.ui4.values import StringValue
from tests.form_builder.engine.test_m8_2_scenario import _document, _xml, record_window

pytestmark = pytest.mark.unit

_ROWS = Rows(
    "invoice_lines",
    "invoice_id",
    "id",
    (
        DataColumn("product_id", "Product", "whole", Lookup("products", "id", "name", "name", ("price",))),
        DataColumn("description", "Description"),
        DataColumn("qty", "Qty", "whole", None, "1"),
        DataColumn("price", "Price", "money", None, "product_id.price"),
        DataColumn("needed", "Needed"),
        CalcColumn("lineTotal", "qty * price", "Line total", "money"),
    ),
    "line_no",
    "line_no",
)


def test_plan_matches_the_shipped_source() -> None:
    namespace: dict = {}
    exec(line_plan_source(), namespace)  # noqa: S102 - the generated module runs this source
    snapshot = ({"id": 1, "qty": 1, "line_no": 1}, {"id": 2, "qty": 1, "line_no": 2})
    current = ({"id": 2, "qty": 1}, {"id": 1, "qty": 4})
    args = (snapshot, current, (), "id", "line_no", ("qty",), True)
    assert namespace["_cbcs_plan_lines"](*args) == plan_lines(*args)
    assert namespace["_cbcs_lines_differ"](snapshot, current, "id", ("qty",)) is True


def test_plan_covers_edits_nulls_and_keys() -> None:
    snap = (
        {"id": "L1", "qty": Decimal("1.50"), "note": None, "line_no": 1},
        {"id": "L2", "qty": Decimal("2.00"), "note": "Gadget", "line_no": 2},
    )
    gapped = (
        {"id": "L1", "qty": Decimal("1.50"), "note": None, "line_no": 1},
        {"id": "L2", "qty": Decimal("2.00"), "note": "Gadget", "line_no": 5},
    )
    same = (
        {"id": "L1", "qty": Decimal("1.5"), "note": None},
        {"id": "L2", "qty": Decimal("2"), "note": "Gadget"},
    )
    assert plan_lines(snap, same, (), "id", "line_no", ("qty", "note"), True) == ()
    from app.features.form_builder.engine.data.lines import _cbcs_lines_differ

    assert _cbcs_lines_differ(gapped, same, "id", ("qty", "note")) is False
    edited = ({"id": "L1", "qty": Decimal("1.50"), "note": "x"}, {"id": "L2", "qty": Decimal("2.00"), "note": "Gadget"})
    assert plan_lines(snap, edited, (), "id", "line_no", ("qty", "note"), True) == (("update", "L1", (("note", "x"),)),)
    swapped = (same[1], same[0])
    ops = plan_lines(snap, swapped, (), "id", "line_no", ("qty", "note"), True)
    assert [op[0] for op in ops] == ["park", "park", "position", "position"]
    assert all(isinstance(op[2], int) and op[2] < 0 for op in ops if op[0] == "park")
    plain = plan_lines(snap, swapped, (), "id", "line_no", ("qty", "note"), False)
    assert [op[0] for op in plain] == ["position", "position"]
    removed = plan_lines(snap, (same[1],), ("L1",), "id", "line_no", ("qty", "note"), True)
    assert removed[0] == ("delete", "L1")
    added = plan_lines(snap, same + ({"id": None, "qty": Decimal("3"), "note": ""},), (), "id", "line_no", ("qty", "note"), False)
    assert added[-1][0] == "insert"
    inserted = added[-1][1]
    assert isinstance(inserted, tuple) and ("note", "") in inserted
    with pytest.raises(ValueError):
        plan_lines(snap, same, (None,), "id", "line_no", ("qty", "note"), False)
    dated = ({"id": 1, "needed": date(2026, 4, 2)},)
    assert plan_lines(dated, dated, (), "id", "", ("needed",), False) == ()


def test_a_link_that_does_not_point_here_is_fb313() -> None:
    doc = _document(_xml(RecordSource("shop", "invoices", "id"), (("QTableView", "linesView", "", _rows_xml(_ROWS)),)))
    schema = Schema(
        "shop",
        "sqlite",
        "",
        "2026-01-01T00:00:00",
        "sqlite3",
        (
            Table("invoices", (Column("id", "INTEGER", False),), key="id"),
            Table(
                "invoice_lines",
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_id", "INTEGER", False, references=Reference("customers", "id")),
                    Column("qty", "INTEGER", False),
                ),
                key="id",
            ),
        ),
    )
    found = [item for item in run_checks(doc, None, schema) if item.code == "FB313"]
    assert len(found) == 1
    assert found[0].message == "invoice_id in invoice_lines doesn't point to invoices."
    pointed = Schema(
        "shop",
        "sqlite",
        "",
        "2026-01-01T00:00:00",
        "sqlite3",
        (
            Table("invoices", (Column("id", "INTEGER", False),), key="id"),
            Table(
                "invoice_lines",
                (Column("invoice_id", "INTEGER", False, references=Reference("invoices", "id")),),
                key="id",
            ),
        ),
    )
    assert [item.code for item in run_checks(doc, None, pointed) if item.code == "FB313"] == []


def test_add_lines_is_one_undo_step(qapp, tmp_path: Path) -> None:
    del qapp
    schema = Schema(
        "office",
        "sqlite",
        "",
        "2026-01-01T00:00:00",
        "sqlite3",
        (
            Table("invoices", (Column("id", "INTEGER", False),), key="id"),
            Table(
                "invoice_lines",
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_id", "INTEGER", False, references=Reference("invoices", "id")),
                    Column("qty", "INTEGER", False),
                    Column("line_no", "INTEGER", False),
                ),
                key="id",
                unique_keys=(("invoice_id", "line_no"),),
            ),
        ),
    )
    set_schema_reader(lambda _doc, _name: schema)
    try:
        from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
        from app.features.form_builder.engine.project.forms import FormScope
        from app.features.form_builder.engine.session import FormSession
        from app.features.form_builder.qtside.data_panel.edits import connect_form
        from app.features.form_builder.qtside.data_panel.lines_sheet import add_lines
        from app.features.form_builder.qtside.data_panel.panel import DataPanel
        from app.qt.QtWidgets import QWidget  # type: ignore[reportAttributeAccessIssue]

        save_connections(str(tmp_path), ConnectionSet((Connection("office", "Office", "sqlite", file="shop.db"),)))
        session = FormSession.open(
            _xml(RecordSource("office", "invoices", "id"), (("QLineEdit", "notesEdit", "notes", ""),)),
            path="/tmp/cbcs-m83b.ui",
            scope=FormScope(kind="external", ui_path="/tmp/cbcs-m83b.ui", project_root=str(tmp_path)),
        )
        host = QWidget()
        host.session = session
        host.project_root = str(tmp_path)
        connect_form(session, RecordSource("office", "invoices", "id"))
        panel = DataPanel(host)
        panel.reload()
        assert panel.findChild(QWidget, "formBuilder.data.linesAdd") is not None
        before = len(session.log.entries())
        name = add_lines(session, Rows("invoice_lines", "invoice_id", "id", (DataColumn("qty", "Qty", "whole", None, "1"),), "line_no", "line_no"))
        assert name == "invoice_linesView"
        assert len(session.log.entries()) == before + 1
        assert session.log.undo_label() == "Add lines"
        node = session.document.node(session.document.by_name(name)[0])
        rows_entry = node.prop("cbcsRows")
        assert rows_entry is not None and isinstance(rows_entry.value, StringValue)
        parsed, error = read_rows(rows_entry.value.text)
        assert error is None and parsed is not None and parsed.table == "invoice_lines"
        clicked = session.document.node(session.document.by_name("addLineButton")[0]).prop(signal_property("clicked"))
        assert clicked is not None and isinstance(clicked.value, StringValue)
        steps = parse_steps(clicked.value.text).steps
        assert [step.verb for step in steps] == ["addRow"]
        assert session.log.undo()
        assert session.document.by_name("invoice_linesView") == ()
        session.dispose()
    finally:
        set_schema_reader(None)


def test_lines_round_trip_on_sqlite(tmp_path: Path) -> None:
    seen: List[str] = []

    def choose(text: str) -> str:
        if text.startswith("Delete line"):
            return "Delete"
        if text.startswith("Delete this"):
            return "Cancel"
        return "Close"

    with record_window(tmp_path, _ui(), _prepare, choose=choose, seen=seen, schema=_invoice_schema()) as (host, db):
        _story(host, lambda: _read(db))
        print("SPEED", _speed(host, db))


def test_a_text_line_key_updates_on_sqlite(tmp_path: Path) -> None:
    with record_window(tmp_path, _text_ui(), _prepare_text, schema=_text_schema(tmp_path)) as (host, db):
        assert host.ui._cbcs_is_dirty() is False
        _set(host.ui, 0, "note", "changed")
        assert host.ui.cbcs_save() is True
        connection = sqlite3.connect(str(db))
        try:
            found = connection.execute("SELECT id, note FROM coded_lines").fetchall()
        finally:
            connection.close()
        assert found == [("L1", "changed")]


def _story(host: Any, read: Callable[[], Sequence[Tuple[Any, ...]]]) -> None:
    ui = host.ui
    assert ui.linesView.model().rowCount() == 3
    assert ui._cbcs_is_dirty() is False
    assert _value(ui, 0, "description") is None
    assert _value(ui, 0, "needed") == date(2026, 4, 2)
    assert _value(ui, 0, "price") == Decimal("1.50")
    assert ui.cbcs_read_lines()[0]["id"] == 1
    total = ui.totalLabel.text()
    assert "7" in total
    _set(ui, 0, "qty", 5)
    _set(ui, 0, "qty", 1)
    assert ui._cbcs_is_dirty() is False
    _set(ui, 0, "qty", 9)
    assert ui._cbcs_is_dirty() is True
    ui.cbcs_revert()
    assert _value(ui, 0, "qty") == 1
    assert ui._cbcs_is_dirty() is False
    assert read()[0][3] == 1
    _set(ui, 0, "qty", None)
    assert ui.cbcs_save() is False
    assert "Line 1: Qty is required" in ui.linesView.model().item(0, _index(ui, "qty")).toolTip()
    _set(ui, 0, "qty", 1)
    _set(ui, 0, "description", None)
    assert ui.cbcs_save() is True
    assert read()[0][2] is None
    _set(ui, 0, "needed", date(2026, 5, 1))
    _set(ui, 0, "price", Decimal("1.25"))
    assert ui.cbcs_save() is True
    saved = read()
    assert saved[0][4] == Decimal("1.25") or str(saved[0][4]) in ("1.25", "1.250")
    assert str(saved[0][5]).startswith("2026-05-01")
    _move(ui, 1, 0)
    assert ui.cbcs_save() is True
    ordered = read()
    assert [row[0] for row in ordered] == [2, 1, 3]
    assert [row[1] for row in ordered] == [1, 2, 3]
    ui.linesView.setCurrentIndex(ui.linesView.model().index(2, 0))
    ui._cbcs_delete_row()
    assert ui.cbcs_save() is True
    assert [row[0] for row in read()] == [2, 1]
    ui._cbcs_add_row()
    last = ui.linesView.model().rowCount() - 1
    _set(ui, last, "product_id", 1)
    _set(ui, last, "qty", 3)
    _set(ui, last, "price", Decimal("2.00"))
    _set(ui, last, "description", "Added")
    assert ui.cbcs_save() is True
    added = read()
    assert added[-1][2] == "Added"
    assert added[-1][3] == 3
    assert added[-1][1] == 3


def _speed(host: Any, db: Path) -> Tuple[Tuple[float, ...], Tuple[float, ...], Tuple[float, ...], Tuple[float, ...]]:
    import cbcs_connections  # type: ignore[reportMissingImports]

    key = host.ui.cbcs_current_key()
    connection = sqlite3.connect(str(db))
    try:
        connection.execute("DELETE FROM invoice_lines")
        connection.executemany(
            "INSERT INTO invoice_lines (invoice_id, line_no, product_id, description, qty, price, needed) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, index, 1, "Row %d" % index, 1, "1.50", None) for index in range(1, 21)],
        )
        connection.commit()
    finally:
        connection.close()
    with cbcs_connections.work("shop") as conn:
        host.ui._cbcs_load_lines(conn, key)
    small: List[float] = []
    for _ in range(3):
        started = time.perf_counter()
        assert host.ui._cbcs_is_dirty() is False
        small.append(time.perf_counter() - started)
    assert max(small) < 0.001
    connection = sqlite3.connect(str(db))
    try:
        connection.execute("DELETE FROM invoice_lines")
        connection.executemany(
            "INSERT INTO invoice_lines (invoice_id, line_no, product_id, description, qty, price, needed) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, index, 1, "Row %d" % index, 1, "1.50", None) for index in range(1, 201)],
        )
        connection.commit()
    finally:
        connection.close()
    samples: List[float] = []
    for _ in range(3):
        started = time.perf_counter()
        with cbcs_connections.work("shop") as conn:
            host.ui._cbcs_load_lines(conn, key)
        samples.append(time.perf_counter() - started)
    assert host.ui.linesView.model().rowCount() == 200
    host.ui._cbcs_line_snapshot = host.ui._cbcs_line_rows()
    dirty: List[float] = []
    for _ in range(3):
        started = time.perf_counter()
        host.ui._cbcs_is_dirty()
        dirty.append(time.perf_counter() - started)
    assert max(dirty) < 0.005
    saves: List[float] = []
    for sample in range(3):
        for row in range(20):
            _set(host.ui, row, "description", "S%d-%d" % (sample, row))
        started = time.perf_counter()
        assert host.ui.cbcs_save() is True
        saves.append(time.perf_counter() - started)
    with cbcs_connections.work("shop") as conn:
        host.ui._cbcs_delete_lines(conn, key)
    connection = sqlite3.connect(str(db))
    try:
        left = connection.execute("SELECT COUNT(*) FROM invoice_lines").fetchone()[0]
    finally:
        connection.close()
    assert left == 0
    return (tuple(small), tuple(samples), tuple(dirty), tuple(saves))


def _prepare(root: Path) -> Path:
    path = root / "data" / "shop.db"
    path.parent.mkdir(parents=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, price NUMERIC NOT NULL);
            CREATE TABLE invoices (
                id INTEGER PRIMARY KEY,
                invoice_no TEXT NOT NULL UNIQUE,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                invoice_date TEXT,
                notes TEXT,
                total NUMERIC
            );
            CREATE TABLE invoice_lines (
                id INTEGER PRIMARY KEY,
                invoice_id INTEGER NOT NULL REFERENCES invoices(id),
                line_no INTEGER NOT NULL,
                product_id INTEGER REFERENCES products(id),
                description TEXT,
                qty INTEGER NOT NULL,
                price NUMERIC NOT NULL,
                needed DATE,
                UNIQUE (invoice_id, line_no)
            );
            """
        )
        connection.execute("INSERT INTO customers (id, name) VALUES (1, 'Acme')")
        connection.executemany(
            "INSERT INTO products (id, name, price) VALUES (?, ?, ?)",
            ((1, "Widget", "1.50"), (2, "Gadget", "2.00")),
        )
        connection.execute(
            "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (1, 'INV-1', 1, '2026-04-02', '', '7.00')"
        )
        connection.executemany(
            "INSERT INTO invoice_lines (id, invoice_id, line_no, product_id, description, qty, price, needed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (1, 1, 1, 1, None, 1, "1.50", "2026-04-02"),
                (2, 1, 2, 2, "Gadget", 2, "2.00", None),
                (3, 1, 3, 1, "Extra", 1, "1.50", None),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _prepare_text(root: Path) -> Path:
    path = root / "data" / "shop.db"
    path.parent.mkdir(parents=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(
            """
            CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_no TEXT NOT NULL, customer_id INTEGER NOT NULL, invoice_date TEXT, notes TEXT);
            CREATE TABLE coded_lines (
                id TEXT PRIMARY KEY,
                invoice_id INTEGER NOT NULL REFERENCES invoices(id),
                line_no INTEGER NOT NULL,
                note TEXT,
                UNIQUE (invoice_id, line_no)
            );
            """
        )
        connection.execute("INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes) VALUES (1, 'INV-1', 1, '2026-04-02', '')")
        connection.execute("INSERT INTO coded_lines (id, invoice_id, line_no, note) VALUES ('L1', 1, 1, 'hello')")
        connection.commit()
    finally:
        connection.close()
    return path


def _invoice_schema(parent: str = "invoices", lines: str = "invoice_lines") -> Schema:
    return Schema(
        "shop",
        "sqlite",
        "",
        "2026-04-02T00:00:00",
        "sqlite3",
        (
            Table(
                parent,
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_no", "TEXT", False),
                    Column("customer_id", "INTEGER", False, references=Reference("customers", "id")),
                    Column("invoice_date", "TEXT", True),
                    Column("notes", "TEXT", True),
                    Column("total", "NUMERIC", True),
                ),
                key="id",
            ),
            Table(
                "products",
                (
                    Column("id", "INTEGER", False),
                    Column("name", "TEXT", False),
                    Column("price", "NUMERIC", False),
                ),
                key="id",
            ),
            Table(
                lines,
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_id", "INTEGER", False, references=Reference(parent, "id")),
                    Column("line_no", "INTEGER", False),
                    Column("product_id", "INTEGER", True, references=Reference("products", "id")),
                    Column("description", "TEXT", True),
                    Column("qty", "INTEGER", False),
                    Column("price", "NUMERIC", False),
                    Column("needed", "DATE", True),
                ),
                key="id",
                unique_keys=(("invoice_id", "line_no"),),
            ),
        ),
    )


def _text_schema(tmp_path: Path) -> Schema:
    del tmp_path
    path_holder: List[Schema] = []
    del path_holder
    return Schema(
        "shop",
        "sqlite",
        "",
        "2026-04-02T00:00:00",
        "sqlite3",
        (
            Table(
                "invoices",
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_no", "TEXT", False),
                    Column("customer_id", "INTEGER", False),
                    Column("invoice_date", "TEXT", True),
                    Column("notes", "TEXT", True),
                ),
                key="id",
            ),
            Table(
                "coded_lines",
                (
                    Column("id", "TEXT", False),
                    Column("invoice_id", "INTEGER", False, references=Reference("invoices", "id")),
                    Column("line_no", "INTEGER", False),
                    Column("note", "TEXT", True),
                ),
                key="id",
                unique_keys=(("invoice_id", "line_no"),),
            ),
        ),
    )


def _spec(lines: str = "invoice_lines", products: str = "products") -> Rows:
    columns = []
    for column in _ROWS.columns:
        if isinstance(column, DataColumn) and column.lookup is not None:
            columns.append(replace(column, lookup=replace(column.lookup, table=products)))
        else:
            columns.append(column)
    return replace(_ROWS, table=lines, columns=tuple(columns))


def _ui(parent: str = "invoices", lines: str = "invoice_lines", products: str = "products") -> str:
    rows = '    <property name="cbcsRows" stdset="0"><string notr="true">%s</string></property>\n' % escape(
        write_rows(_spec(lines, products))
    )
    total = '    <property name="cbcsValue" stdset="0"><string notr="true">sum(linesView.lineTotal)</string></property>\n'
    return _xml(
        RecordSource("shop", parent, "id"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QSpinBox", "customerIdSpin", "customer_id", ""),
            ("QLineEdit", "invoiceDateEdit", "invoice_date", ""),
            ("QLineEdit", "notesEdit", "notes", ""),
            ("QTableView", "linesView", "", rows),
            ("QLabel", "totalLabel", "", total),
            ("QPushButton", "saveButton", "", ""),
        ),
    )


def _text_ui() -> str:
    rows = Rows(
        "coded_lines",
        "invoice_id",
        "id",
        (DataColumn("note", "Note"),),
        "line_no",
        "line_no",
    )
    extra = '    <property name="cbcsRows" stdset="0"><string notr="true">%s</string></property>\n' % escape(write_rows(rows))
    return _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QSpinBox", "customerIdSpin", "customer_id", ""),
            ("QLineEdit", "notesEdit", "notes", ""),
            ("QTableView", "linesView", "", extra),
        ),
    )


def _rows_xml(rows: Rows) -> str:
    return '    <property name="cbcsRows" stdset="0"><string notr="true">%s</string></property>\n' % escape(write_rows(rows))


def _read(db: Path) -> List[Tuple[Any, ...]]:
    connection = sqlite3.connect(str(db))
    try:
        found = connection.execute(
            "SELECT id, line_no, description, qty, price, needed FROM invoice_lines WHERE invoice_id = 1 ORDER BY line_no"
        ).fetchall()
    finally:
        connection.close()
    return list(found)


def _index(ui: Any, name: str) -> int:
    return ui._cbcs_line_names.index(name)


def _value(ui: Any, row: int, name: str) -> Any:
    item = ui.linesView.model().item(row, _index(ui, name))
    return None if item is None else item.data(ui._cbcs_line_role)


def _set(ui: Any, row: int, name: str, value: Any) -> None:
    item = ui.linesView.model().item(row, _index(ui, name))
    item.setData(value, ui._cbcs_line_role)
    item.setText("" if value is None else str(value))


def _move(ui: Any, source: int, target: int) -> None:
    model = ui.linesView.model()
    row = model.takeRow(source)
    model.insertRow(target, row)

