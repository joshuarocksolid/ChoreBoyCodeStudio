# pyright: reportMissingImports=false
"""Ejected and bound forms run the same statements on PostgreSQL 9.3."""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, List, Sequence, Tuple

import pytest

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.schema import Column, Reference, Schema, Table, set_schema_reader, write_schema
from app.features.form_builder.engine.data.schema_cache import install_schema_reader
from app.features.form_builder.engine.data.source import Lookup, RecordSource, write_lookup
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.session import FormSession
from tests.form_builder.engine.test_m8_2_followup_pg93 import _import
from tests.form_builder.engine.test_m8_2_pg93 import _fields
from tests.form_builder.engine.test_m8_3b_lines import _ROWS, _rows_xml
from tests.form_builder.engine.test_m8_3c_list import _widgets
from tests.form_builder.engine.test_m8_5_eject import (
    _host_bound,
    _host_ejected,
    _line_values,
    _restore_connections,
    _set_product,
    _write_customer_window,
)
from tests.form_builder.engine.test_m8_2_scenario import _xml
from xml.sax.saxutils import escape
from dataclasses import replace

pytestmark = pytest.mark.pg93


@pytest.fixture
def pg93_dsn() -> str:
    raw = os.environ.get("CBCS_PG93_DSN", "").strip()
    if not raw:
        pytest.skip("set CBCS_PG93_DSN to run PostgreSQL 9.3 tests")
    return raw


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_ejected_invoice_matches_on_postgres(tmp_path: Path, pg93_dsn: str, driver: str, connections_module: Any) -> None:
    _import(driver)
    names = _names("inv")
    bound = _invoice(tmp_path / "bound", pg93_dsn, driver, connections_module, names, ejected=False)
    ejected = _invoice(tmp_path / "ejected", pg93_dsn, driver, connections_module, names, ejected=True)
    assert _only(ejected.sql, names) == _only(bound.sql, names)
    assert ejected.fields == bound.fields
    assert ejected.lines == bound.lines
    assert ejected.saved == bound.saved
    assert ejected.left == bound.left == 0
    assert len(bound.saved) == len(bound.lines) + 1


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_ejected_list_matches_on_postgres(tmp_path: Path, pg93_dsn: str, driver: str, connections_module: Any) -> None:
    _import(driver)
    table = "m85_list_%s" % uuid.uuid4().hex[:8]
    bound = _list(tmp_path / "bound", pg93_dsn, driver, connections_module, table, ejected=False)
    ejected = _list(tmp_path / "ejected", pg93_dsn, driver, connections_module, table, ejected=True)
    assert _only(ejected.sql, {"table": table}) == _only(bound.sql, {"table": table})
    assert ejected.names == bound.names
    assert ejected.opened == bound.opened
    assert bound.opened


def _only(sql: Sequence[str], names: dict) -> Tuple[str, ...]:
    needles = tuple(names.values())
    return tuple(statement for statement in sql if any(name in statement for name in needles))


class _Shot:
    def __init__(self, sql: Sequence[str], fields: Tuple[Any, ...], lines: Sequence[Any], saved: Sequence[Any], left: int) -> None:
        self.sql = tuple(sql)
        self.fields = fields
        self.lines = tuple(lines)
        self.saved = tuple(saved)
        self.left = left


def _invoice(tmp_path: Path, dsn: str, driver: str, connections_module: Any, names: dict, *, ejected: bool) -> _Shot:
    module = _module(tmp_path, dsn, driver, connections_module)
    sql: List[str] = []
    host = None
    try:
        _seed_invoice(module, names)
        _wrap(module, sql)
        root, scope, ui_text = _invoice_project(tmp_path, dsn, names)
        session = FormSession.open(ui_text, path=scope.ui_path, scope=scope)
        choose = lambda text: "Delete" if str(text).startswith("Delete this") else "Close"  # noqa: E731
        if ejected:
            from app.features.form_builder.engine.codegen.eject import plan_eject

            plan = plan_eject(session.document, scope)
            with session.log.transaction("Eject to code"):
                for command in plan.commands:
                    session.log.execute(command)
            host = _host_ejected(root, scope, session.text(), plan, module, choose)
            ui = host.ui
            owner = host
            save, delete, add, find = host.save_record, host.delete_record, host.add_line, host.find_record
        else:
            host = _host_bound(root, scope, session.text(), module, choose)
            ui = host.ui
            owner = ui
            save, delete, add, find = ui.cbcs_save, ui.cbcs_delete, ui._cbcs_add_row, ui.cbcs_find
        fields = (ui.invoiceNoEdit.text(), ui.customerCombo.currentText())
        lines = _line_values(owner)
        find()
        add()
        _set_product(owner, 1)
        assert save() is True
        saved = _fetch(module, "SELECT product_id, description, qty, price, needed FROM %s ORDER BY line_no" % names["lines"])
        assert delete() is True
        left = _fetch(module, "SELECT COUNT(*) FROM %s" % names["invoices"])
        return _Shot(sql, fields, lines, saved, int(left[0][0]))
    finally:
        if host is not None:
            host.close()
        _restore_connections(module)
        _unwrap(module)
        _drop_invoice(module, names)
        module.close_all()
        set_schema_reader(None)


def _list(tmp_path: Path, dsn: str, driver: str, connections_module: Any, table: str, *, ejected: bool) -> Any:
    from app.features.form_builder.engine.data.source import ListFilter, ListOpen, ListSource

    module = _module(tmp_path, dsn, driver, connections_module)
    sql: List[str] = []
    root = tmp_path / "proj"
    host = None
    try:
        _seed_list(module, table)
        _wrap(module, sql)
        forms = root / "forms"
        forms.mkdir(parents=True)
        _write_customer_window(root)
        import sys

        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        for name in ("forms", "forms.customer_window"):
            sys.modules.pop(name, None)
        source = ListSource(
            "shop",
            ("name", "price", "when_on"),
            table=table,
            search=("name",),
            search_field="searchEdit",
            filters=(ListFilter("statusCombo", "status"),),
            order=(("name", "asc"),),
            limit=10,
            open=ListOpen("customer", "id"),
        )
        ui_text = _xml(source, _widgets())
        ui_path = forms / "customers.ui"
        ui_path.write_text(ui_text, encoding="utf-8")
        save_connections(str(root), _value(_fields(dsn)))
        scope = FormScope(
            kind="project",
            ui_path=str(ui_path),
            project_root=str(root),
            generated_path=str(forms / "ui_customers.py"),
            window_path=str(forms / "customers_window.py"),
            module_name="forms.ui_customers",
        )
        session = FormSession.open(ui_text, path=str(ui_path), scope=scope)
        if ejected:
            from app.features.form_builder.engine.codegen.eject import plan_eject

            plan = plan_eject(session.document, scope)
            with session.log.transaction("Eject to code"):
                for command in plan.commands:
                    session.log.execute(command)
            host = _host_ejected(root, scope, session.text(), plan, module, lambda _text: "Close")
            host.ui.customersView.selectRow(0)
            host.open_record("selected")
        else:
            host = _host_bound(root, scope, session.text(), module, lambda _text: "Close")
            host.ui.customersView.selectRow(0)
            host.ui.cbcs_open_record("selected")
        model = host.ui.customersView.model()
        shown = [model.item(row, 0).text() for row in range(model.rowCount())]
        import forms.customer_window as window_mod

        opened = list(window_mod.CustomerWindow.opened)
        return type("List", (), {"sql": tuple(sql), "names": tuple(shown), "opened": tuple(opened)})()
    finally:
        if host is not None:
            host.close()
        _restore_connections(module)
        _unwrap(module)
        try:
            with module.work("shop") as connection:
                connection.cursor().execute("DROP TABLE IF EXISTS %s" % table)
        except Exception:
            pass
        module.close_all()
        import sys

        if sys.path and sys.path[0] == str(root):
            sys.path.pop(0)
        for name in ("forms", "forms.customer_window"):
            sys.modules.pop(name, None)


def _invoice_project(tmp_path: Path, dsn: str, names: dict) -> Tuple[Path, FormScope, str]:
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    lookup = (
        '    <property name="cbcsLookup" stdset="0"><string notr="true">%s</string></property>\n'
        % escape(write_lookup(Lookup(names["customers"], "id", "name", "name")))
    )
    rows = replace(_ROWS, table=names["lines"])
    product = rows.columns[0]
    rows = replace(rows, columns=(replace(product, lookup=Lookup(names["products"], "id", "name", "name", ("price",))),) + rows.columns[1:])
    ui_text = _xml(
        RecordSource("shop", names["invoices"], "id"),
        (
            ("QLineEdit", "invoiceNoEdit", "invoice_no", ""),
            ("QComboBox", "customerCombo", "customer_id", lookup),
            ("QTableView", "linesView", "", _rows_xml(rows)),
            ("QPushButton", "saveButton", "", ""),
        ),
    )
    ui_path = forms / "invoice.ui"
    ui_path.write_text(ui_text, encoding="utf-8")
    save_connections(str(root), _value(_fields(dsn)))
    folder = root / "cbcs" / "schema"
    folder.mkdir(parents=True)
    (folder / "shop.json").write_text(write_schema(_schema(names)), encoding="utf-8")
    install_schema_reader(str(root))
    scope = FormScope(
        kind="project",
        ui_path=str(ui_path),
        project_root=str(root),
        generated_path=str(forms / "ui_invoice.py"),
        window_path=str(forms / "invoice_window.py"),
        module_name="forms.ui_invoice",
    )
    return root, scope, ui_text


def _schema(names: dict) -> Schema:
    return Schema(
        "shop",
        "postgres",
        "PostgreSQL 9.3",
        "2026-04-02T00:00:00",
        "psycopg",
        (
            Table(names["customers"], (Column("id", "INTEGER", False), Column("name", "TEXT", False)), key="id"),
            Table(
                names["products"],
                (Column("id", "INTEGER", False), Column("name", "TEXT", False), Column("price", "NUMERIC", False)),
                key="id",
            ),
            Table(
                names["invoices"],
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_no", "TEXT", False),
                    Column("customer_id", "INTEGER", False, references=Reference(names["customers"], "id")),
                    Column("invoice_date", "TEXT", True),
                    Column("notes", "TEXT", True),
                    Column("total", "NUMERIC", True),
                ),
                key="id",
            ),
            Table(
                names["lines"],
                (
                    Column("id", "INTEGER", False),
                    Column("invoice_id", "INTEGER", False, references=Reference(names["invoices"], "id")),
                    Column("line_no", "INTEGER", False),
                    Column("product_id", "INTEGER", True, references=Reference(names["products"], "id")),
                    Column("description", "TEXT", True),
                    Column("qty", "INTEGER", False),
                    Column("price", "NUMERIC", False),
                    Column("needed", "DATE", True),
                ),
                key="id",
            ),
        ),
    )


def _names(kind: str) -> dict:
    suffix = uuid.uuid4().hex[:8]
    return {
        "customers": "m85_%s_cust_%s" % (kind, suffix),
        "products": "m85_%s_prod_%s" % (kind, suffix),
        "invoices": "m85_%s_inv_%s" % (kind, suffix),
        "lines": "m85_%s_lines_%s" % (kind, suffix),
    }


def _module(tmp_path: Path, dsn: str, driver: str, connections_module: Any) -> Any:
    tmp_path.mkdir(parents=True, exist_ok=True)
    fields = _fields(dsn)
    module, _text = connections_module(tmp_path, _value(fields), "m85")
    module._CBCS_DRIVERS = (driver,)
    module.set_password("shop", fields["password"])
    module._cbcs_wrapped = []
    return module


def _value(fields: dict) -> ConnectionSet:
    port = int(fields.get("port") or "5432")
    return ConnectionSet(
        (
            Connection(
                "shop",
                "Shop",
                "postgres",
                host=fields.get("host") or "127.0.0.1",
                port=None if port == 5432 else port,
                database=fields.get("dbname") or fields.get("database") or "cbcs",
                user=fields["user"],
                password="none",
            ),
        )
    )


def _wrap(module: Any, sql: List[str]) -> None:
    from tests.form_builder.engine.test_m8_5_eject import _TracingConnection

    wrapped = []
    if "psycopg" in module._CBCS_DRIVERS:
        import psycopg

        original = psycopg.connect

        def connect(*args: Any, **kwargs: Any) -> _TracingConnection:
            return _TracingConnection(original(*args, **kwargs), sql)

        psycopg.connect = connect
        wrapped.append((psycopg, "connect", original))
    if "pg8000" in module._CBCS_DRIVERS:
        import pg8000.dbapi as pg8000

        original = pg8000.connect

        def connect_pg(*args: Any, **kwargs: Any) -> _TracingConnection:
            return _TracingConnection(original(*args, **kwargs), sql)

        pg8000.connect = connect_pg
        wrapped.append((pg8000, "connect", original))
    module._cbcs_wrapped = wrapped


def _unwrap(module: Any) -> None:
    for owner, name, original in getattr(module, "_cbcs_wrapped", ()):
        setattr(owner, name, original)
    module._cbcs_wrapped = []


def _seed_invoice(module: Any, names: dict) -> None:
    with module.work("shop") as connection:
        cursor = connection.cursor()
        cursor.execute("CREATE TABLE %s (id serial PRIMARY KEY, name text NOT NULL)" % names["customers"])
        cursor.execute(
            "CREATE TABLE %s (id serial PRIMARY KEY, name text NOT NULL, price numeric NOT NULL)" % names["products"]
        )
        cursor.execute(
            "CREATE TABLE %s (id serial PRIMARY KEY, invoice_no text NOT NULL UNIQUE, customer_id integer NOT NULL REFERENCES %s(id), invoice_date text, notes text, total numeric)"
            % (names["invoices"], names["customers"])
        )
        cursor.execute(
            "CREATE TABLE %s (id serial PRIMARY KEY, invoice_id integer NOT NULL REFERENCES %s(id), line_no integer NOT NULL, product_id integer REFERENCES %s(id), description text, qty integer NOT NULL, price numeric NOT NULL, needed date, UNIQUE (invoice_id, line_no))"
            % (names["lines"], names["invoices"], names["products"])
        )
        cursor.execute("INSERT INTO %s (id, name) VALUES (1, 'Acme')" % names["customers"])
        cursor.execute(
            "INSERT INTO %s (id, name, price) VALUES (1, 'Widget', %%s), (2, 'Gadget', %%s)" % names["products"],
            (Decimal("1.50"), Decimal("2.00")),
        )
        cursor.execute(
            "INSERT INTO %s (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (1, 'INV-1', 1, '2026-04-02', '', 7.00)"
            % names["invoices"]
        )
        cursor.execute(
            "INSERT INTO %s (id, invoice_id, line_no, product_id, description, qty, price, needed) VALUES (1, 1, 1, 1, NULL, 1, %%s, '2026-04-02'), (2, 1, 2, 2, 'Gadget', 2, %%s, NULL), (3, 1, 3, 1, 'Extra', 1, %%s, NULL)"
            % names["lines"],
            (Decimal("1.50"), Decimal("2.00"), Decimal("1.50")),
        )
        for table in (names["customers"], names["products"], names["invoices"], names["lines"]):
            cursor.execute("SELECT setval(pg_get_serial_sequence('%s', 'id'), (SELECT MAX(id) FROM %s))" % (table, table))


def _seed_list(module: Any, table: str) -> None:
    with module.work("shop") as connection:
        cursor = connection.cursor()
        cursor.execute(
            "CREATE TABLE %s (id text PRIMARY KEY, name text, price numeric, when_on date, note text, status text)" % table
        )
        cursor.execute(
            "INSERT INTO %s (id, name, price, when_on, note, status) VALUES (%%s, %%s, %%s, %%s, %%s, %%s)" % table,
            ("A1", "Ann", Decimal("12.50"), "2026-04-01", "keep me", "open"),
        )
        cursor.execute(
            "INSERT INTO %s (id, name, price, when_on, note, status) VALUES (%%s, %%s, %%s, %%s, %%s, %%s)" % table,
            ("A2", "Bob", Decimal("3.00"), None, "drop", "closed"),
        )
        cursor.execute(
            "INSERT INTO %s (id, name, price, when_on, note, status) VALUES (%%s, %%s, %%s, %%s, %%s, %%s)" % table,
            ("A3", None, None, "2026-05-01", "also", "open"),
        )


def _fetch(module: Any, statement: str) -> List[Tuple[Any, ...]]:
    with module.work("shop") as connection:
        cursor = connection.cursor()
        cursor.execute(statement)
        return [tuple(row) for row in cursor.fetchall()]


def _drop_invoice(module: Any, names: dict) -> None:
    try:
        with module.work("shop") as connection:
            cursor = connection.cursor()
            for table in (names["lines"], names["invoices"], names["products"], names["customers"]):
                cursor.execute("DROP TABLE IF EXISTS %s" % table)
    except Exception:
        return
