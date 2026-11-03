# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
"""Form from a table on PostgreSQL 9.3. Both drivers, unique table names."""

from __future__ import annotations

import datetime
import os
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from app.features.form_builder.engine.data.connections import save_connections
from app.features.form_builder.engine.data.schema import Column, Reference, Schema, Table, set_schema_reader, write_schema
from app.features.form_builder.engine.data.schema_cache import install_schema_reader
from app.features.form_builder.engine.project.from_table_plan import ColumnChoice, TableRequest
from app.qt.QtCore import QDate
from app.qt.QtWidgets import QApplication, QDialog
from tests.form_builder.engine.test_m8_2_followup_pg93 import _fields, _import, _module, _value
from tests.form_builder.engine.test_m8_2_scenario import _install_boxes, _load_module, _ui_class
from tests.form_builder.engine.test_m8_3d_from_table import (
    _line,
    _open_selected,
    _pick,
    _write_generated,
)
from app.features.form_builder.qtside.dialogs.table_apply import render_plans

pytestmark = pytest.mark.pg93


@pytest.fixture
def pg93_dsn() -> str:
    raw = os.environ.get("CBCS_PG93_DSN", "").strip()
    if not raw:
        pytest.skip("set CBCS_PG93_DSN to run PostgreSQL 9.3 tests")
    return raw


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_postgres_invoice_saves_lines_then_opens_from_the_list(
    tmp_path: Path, pg93_dsn: str, driver: str, connections_module
) -> None:
    _import(driver)
    names = _names()
    module = _module(tmp_path, _fields(pg93_dsn), driver, connections_module)
    root = _project(tmp_path)
    previous = sys.modules.get("cbcs_connections")
    sys.modules["cbcs_connections"] = module
    sys.path.insert(0, str(root))
    try:
        _create_shop(module, names)
        schema = _schema(names)
        _cache(root, schema)
        save_connections(str(root), _value(_fields(pg93_dsn)))
        _write_generated(root, _invoice_texts(root, schema, names) + _customer_texts(root, schema, names))
        samples = _drive_invoice(root, module, names)
        print("PG_SAVE_MS=%s" % ",".join("%.3f" % (sample * 1000) for sample in samples))
        assert max(samples) < 5.0
    finally:
        _drop_shop(module, names)
        _release(root, previous, module)


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_postgres_text_key_keeps_null_decimal_and_date(
    tmp_path: Path, pg93_dsn: str, driver: str, connections_module
) -> None:
    _import(driver)
    table = "m83d_job_%s" % uuid.uuid4().hex[:8]
    module = _module(tmp_path, _fields(pg93_dsn), driver, connections_module)
    root = _project(tmp_path)
    previous = sys.modules.get("cbcs_connections")
    sys.modules["cbcs_connections"] = module
    sys.path.insert(0, str(root))
    try:
        with module.work("shop") as connection:
            connection.cursor().execute(
                "CREATE TABLE %s (code text PRIMARY KEY, title text, due date, amount numeric, note text)" % table
            )
        schema = Schema(
            "shop",
            "postgres",
            "PostgreSQL 9.3",
            "2026-11-03T00:00:00",
            driver,
            (
                Table(
                    table,
                    (
                        Column("code", "text", False, unique=True),
                        Column("title", "text", True),
                        Column("due", "date", True),
                        Column("amount", "numeric", True),
                        Column("note", "text", True),
                    ),
                    key="code",
                ),
            ),
        )
        _cache(root, schema)
        save_connections(str(root), _value(_fields(pg93_dsn)))
        request = TableRequest(
            "shop",
            table,
            (
                ColumnChoice("code", "QLineEdit", "Code"),
                ColumnChoice("title", "QLineEdit", "Title"),
                ColumnChoice("due", "QDateEdit", "Due"),
                ColumnChoice("amount", "QDoubleSpinBox", "Amount"),
                ColumnChoice("note", "QLineEdit", "Note"),
            ),
            "record",
            "",
            "job",
            "yyyy-MM-dd",
        )
        _write_generated(root, render_plans(request, schema, str(root)))
        with _form(root, "job") as host:
            ui = host.ui
            ui.cbcs_new()
            ui.code.setText("J-1")
            ui.title.setText("Roof")
            ui.due.setDate(QDate(2026, 4, 5))
            ui.amount.setValue(3.25)
            ui.note.clear()
            assert ui.cbcs_save() is True
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT code, title, due, amount, note FROM %s" % table)
            row = cursor.fetchone()
        assert row is not None
        assert row[0] == "J-1" and row[1] == "Roof"
        assert row[2] == datetime.date(2026, 4, 5)
        assert Decimal(str(row[3])) == Decimal("3.25")
        assert row[4] is None
    finally:
        _drop(module, table)
        _release(root, previous, module)


def _drive_invoice(root: Path, module: Any, names: Dict[str, str]) -> List[float]:
    samples: List[float] = []
    with _form(root, "invoice") as host:
        ui = host.ui
        ui.cbcs_new()
        ui.cbcs_load_lookups()
        ui.invoice_no.setText("INV-9")
        ui.invoice_date.setDate(QDate(2026, 5, 2))
        _pick(ui.customer_id, _id(module, names["customers"], "name", "Acme"))
        ui._cbcs_add_row()
        ui._cbcs_add_row()
        product = _id(module, names["products"], "name", "Widget")
        _line(ui, 0, "qty", 2, names["lines"] + "View")
        _line(ui, 0, "price", Decimal("1.50"), names["lines"] + "View")
        _line(ui, 0, "product_id", product, names["lines"] + "View")
        _line(ui, 1, "qty", 1, names["lines"] + "View")
        _line(ui, 1, "price", Decimal("2.00"), names["lines"] + "View")
        _line(ui, 1, "description", None, names["lines"] + "View")
        ui.notes.clear()
        started = time.perf_counter()
        assert ui.cbcs_save() is True
        samples.append(time.perf_counter() - started)
        for _index in range(2):
            ui.notes.setText("edited")
            started = time.perf_counter()
            assert ui.cbcs_save() is True
            samples.append(time.perf_counter() - started)
    _assert_invoice(module, names)
    with _form(root, "invoice_list") as host:
        host.ui.searchEdit.setText("INV-9")
        host.ui.cbcs_refresh_list()
        opened = _open_selected(host, "INV-9", "invoice")
        opened.ui.notes.setText("from the list")
        assert opened.ui.cbcs_save() is True
        opened.close()
    with module.work("shop") as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT notes FROM %s WHERE invoice_no = %%s" % names["invoices"], ("INV-9",))
        assert cursor.fetchone()[0] == "from the list"
    with _form(root, "customer_list") as host:
        host.ui.cbcs_refresh_list()
        opened = _open_selected(host, "Acme", "customer")
        opened.ui.name.setText("Acme Goods")
        assert opened.ui.cbcs_save() is True
        opened.close()
    with module.work("shop") as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT name FROM %s WHERE name = %%s" % names["customers"], ("Acme Goods",))
        assert cursor.fetchone() is not None
    return samples


def _assert_invoice(module: Any, names: Dict[str, str]) -> None:
    with module.work("shop") as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT customer_id, invoice_date, notes FROM %s WHERE invoice_no = %%s" % names["invoices"],
            ("INV-9",),
        )
        row = cursor.fetchone()
        cursor.execute(
            "SELECT qty, price, description FROM %s WHERE invoice_id = "
            "(SELECT id FROM %s WHERE invoice_no = %%s) ORDER BY line_no" % (names["lines"], names["invoices"]),
            ("INV-9",),
        )
        lines = cursor.fetchall()
    assert row is not None
    assert row[0] == _id(module, names["customers"], "name", "Acme")
    assert row[1] == datetime.date(2026, 5, 2)
    assert row[2] == "edited"
    assert len(lines) == 2
    assert lines[0][0] == 2
    assert Decimal(str(lines[0][1])) == Decimal("1.50")
    assert lines[1][2] is None


def _names() -> Dict[str, str]:
    prefix = "m83d_%s" % uuid.uuid4().hex[:8]
    return {role: "%s_%s" % (prefix, role) for role in ("customers", "products", "invoices", "lines")}


def _create_shop(module: Any, names: Dict[str, str]) -> None:
    customers, products, invoices, lines = names["customers"], names["products"], names["invoices"], names["lines"]
    with module.work("shop") as connection:
        cursor = connection.cursor()
        cursor.execute("CREATE TABLE %s (id serial PRIMARY KEY, name text NOT NULL, phone text, city text, email text)" % customers)
        cursor.execute("CREATE TABLE %s (id serial PRIMARY KEY, name text NOT NULL, price numeric)" % products)
        cursor.execute(
            "CREATE TABLE %s (id serial PRIMARY KEY, invoice_no text NOT NULL, customer_id integer NOT NULL "
            "REFERENCES %s (id), invoice_date date, notes text, total numeric)" % (invoices, customers)
        )
        cursor.execute(
            "CREATE TABLE %s (id serial PRIMARY KEY, invoice_id integer NOT NULL REFERENCES %s (id), "
            "line_no integer, product_id integer REFERENCES %s (id), description text, qty numeric NOT NULL, "
            "price numeric NOT NULL)" % (lines, invoices, products)
        )
        cursor.execute(
            "INSERT INTO %s (name, phone, city, email) VALUES (%%s, %%s, %%s, %%s)" % customers,
            ("Acme", "555", "Austin", "a@example.com"),
        )
        cursor.execute("INSERT INTO %s (name, price) VALUES (%%s, %%s)" % products, ("Widget", Decimal("1.50")))
        cursor.execute("INSERT INTO %s (name, price) VALUES (%%s, %%s)" % products, ("Gadget", Decimal("2.00")))


def _schema(names: Dict[str, str]) -> Schema:
    customers, products, invoices, lines = names["customers"], names["products"], names["invoices"], names["lines"]
    return Schema(
        "shop",
        "postgres",
        "PostgreSQL 9.3",
        "2026-11-03T00:00:00",
        "psycopg",
        (
            Table(
                customers,
                (
                    Column("id", "integer", False, unique=True),
                    Column("name", "text", False),
                    Column("phone", "text", True),
                    Column("city", "text", True),
                    Column("email", "text", True),
                ),
                key="id",
            ),
            Table(
                products,
                (
                    Column("id", "integer", False, unique=True),
                    Column("name", "text", False),
                    Column("price", "numeric", True),
                ),
                key="id",
            ),
            Table(
                invoices,
                (
                    Column("id", "integer", False, unique=True),
                    Column("invoice_no", "text", False),
                    Column("customer_id", "integer", False, references=Reference(customers, "id")),
                    Column("invoice_date", "date", True),
                    Column("notes", "text", True),
                    Column("total", "numeric", True),
                ),
                key="id",
            ),
            Table(
                lines,
                (
                    Column("id", "integer", False, unique=True),
                    Column("invoice_id", "integer", False, references=Reference(invoices, "id")),
                    Column("line_no", "integer", True),
                    Column("product_id", "integer", True, references=Reference(products, "id")),
                    Column("description", "text", True),
                    Column("qty", "numeric", False),
                    Column("price", "numeric", False),
                ),
                key="id",
            ),
        ),
    )


def _invoice_texts(root: Path, schema: Schema, names: Dict[str, str]) -> Tuple[Tuple[str, str], ...]:
    request = TableRequest(
        "shop",
        names["invoices"],
        (
            ColumnChoice("invoice_no", "QLineEdit", "Invoice No"),
            ColumnChoice("customer_id", "QComboBox", "Customer"),
            ColumnChoice("invoice_date", "QDateEdit", "Invoice Date"),
            ColumnChoice("notes", "QLineEdit", "Notes"),
            ColumnChoice("total", "QDoubleSpinBox", "Total"),
        ),
        "both",
        names["lines"],
        "invoice",
        "yyyy-MM-dd",
    )
    return render_plans(request, schema, str(root))


def _customer_texts(root: Path, schema: Schema, names: Dict[str, str]) -> Tuple[Tuple[str, str], ...]:
    request = TableRequest(
        "shop",
        names["customers"],
        (
            ColumnChoice("name", "QLineEdit", "Name"),
            ColumnChoice("phone", "QLineEdit", "Phone"),
            ColumnChoice("city", "QLineEdit", "City"),
            ColumnChoice("email", "QLineEdit", "Email"),
        ),
        "both",
        "",
        "customer",
        "yyyy-MM-dd",
    )
    return render_plans(request, schema, str(root))


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "forms").mkdir(parents=True)
    return root


def _cache(root: Path, schema: Schema) -> None:
    folder = root / "cbcs" / "schema"
    folder.mkdir(parents=True)
    (folder / "shop.json").write_text(write_schema(schema), encoding="utf-8")
    install_schema_reader(str(root))


class _form:
    def __init__(self, root: Path, stem: str) -> None:
        self._root = root
        self._stem = stem
        self._host: Any = None
        self._stashed: dict = {}

    def __enter__(self) -> Any:
        from tests.form_builder.engine.test_m8_3d_from_table import _restore_forms, _stash_forms

        self._stashed = _stash_forms()
        forms = self._root / "forms"
        module = _load_module(forms / ("ui_%s.py" % self._stem), "ui_%s_%s" % (self._stem, uuid.uuid4().hex))
        _install_boxes(module, [], None, lambda message: "Save" if str(message).startswith("Save") else "Cancel", None)
        app = QApplication.instance() or QApplication([])

        class Host(QDialog):
            def __init__(self, ui_module: Any) -> None:
                super().__init__()
                self.ui = _ui_class(ui_module)()
                self.ui.setupUi(self)

        self._host = Host(module)
        self._host.show()
        app.processEvents()
        return self._host

    def __exit__(self, *_exc: object) -> None:
        from tests.form_builder.engine.test_m8_3d_from_table import _restore_forms

        if self._host is not None:
            self._host.close()
            self._host.deleteLater()
        _restore_forms(self._stashed)


def _id(module: Any, table: str, column: str, value: str) -> int:
    with module.work("shop") as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM %s WHERE %s = %%s" % (table, column), (value,))
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _drop_shop(module: Any, names: Dict[str, str]) -> None:
    for table in (names["lines"], names["invoices"], names["products"], names["customers"]):
        _drop(module, table)


def _drop(module: Any, table: str) -> None:
    try:
        with module.work("shop") as connection:
            connection.cursor().execute("DROP TABLE IF EXISTS %s CASCADE" % table)
    except Exception:
        return


def _release(root: Path, previous: Any, module: Any) -> None:
    set_schema_reader(None)
    closer = getattr(module, "close_all", None)
    if closer is not None:
        closer()
    if previous is None:
        sys.modules.pop("cbcs_connections", None)
    else:
        sys.modules["cbcs_connections"] = previous
    root_s = str(root)
    if sys.path and sys.path[0] == root_s:
        sys.path.pop(0)
