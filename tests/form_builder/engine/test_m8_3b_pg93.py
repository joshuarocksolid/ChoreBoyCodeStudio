"""PostgreSQL 9.3 lines story. Tables are prefixed so another lane's shop tables stay put."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Tuple

import pytest

from app.features.form_builder.engine.data.connections_module import render_connections_module
from app.features.form_builder.engine.data.schema import write_schema
from app.features.form_builder.engine.data.schema_cache import install_schema_reader, set_schema_reader
from tests.form_builder.engine.test_m8_2_pg93 import _connection, _driver, _fields
from tests.form_builder.engine.test_m8_2_scenario import _generate, _install_boxes, _load_module, _ui_class
from tests.form_builder.engine.test_m8_3b_lines import _edit, _invoice_schema, _story, _ui

pytestmark = pytest.mark.pg93

_PARENT = "m83b_invoices"
_LINES = "m83b_lines"
_CUSTOMERS = "m83b_customers"
_PRODUCTS = "m83b_products"


def test_lines_round_trip_on_postgres(tmp_path: Path) -> None:
    dsn, connect = _driver()
    fields = _fields(dsn)
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    ui_text = _ui(_PARENT, _LINES, _PRODUCTS)
    ui_path = forms / "invoice.ui"
    ui_path.write_text(ui_text, encoding="utf-8")
    value = _connection(fields)
    from app.features.form_builder.engine.data.connections import save_connections

    save_connections(str(root), value)
    (root / "cbcs_connections.py").write_text(render_connections_module(value, project_slug="m83b"), encoding="utf-8")
    schema = _invoice_schema(_PARENT, _LINES)
    folder = root / "cbcs" / "schema"
    folder.mkdir(parents=True)
    (folder / "shop.json").write_text(write_schema(schema), encoding="utf-8")
    install_schema_reader(str(root))
    module = _load_module(root / "cbcs_connections.py", "cbcs_connections_m83b")
    module.set_password("shop", fields["password"])
    side = connect(dsn, fields)
    try:
        _create(module)
        source = _generate(root, ui_path, ui_text)
        generated = forms / "ui_invoice.py"
        generated.write_text(source, encoding="utf-8")
        ui_module = _load_module(generated, "ui_invoice_m83b")
        seen: List[str] = []
        _install_boxes(
            ui_module,
            seen,
            None,
            lambda text: "Delete" if text.startswith("Delete line") else "Cancel",
            None,
        )
        previous = sys.modules.get("cbcs_connections")
        sys.modules["cbcs_connections"] = module
        sys.path.insert(0, str(root))
        try:
            from PySide6.QtWidgets import QApplication, QDialog

            app = QApplication.instance() or QApplication([])

            class Host(QDialog):
                def __init__(self) -> None:
                    super().__init__()
                    self.ui = _ui_class(ui_module)()
                    self.ui.setupUi(self)

            host = Host()
            host.show()
            app.processEvents()
            _story(host, lambda: _read(side))
            with module.work("shop") as connection:
                host.ui._cbcs_delete_lines(connection, host.ui.cbcs_current_key())
            assert _count(side) == 0
            host.ui.cbcs_new()
            host.ui.invoiceNoEdit.setText("INV-NEW")
            host.ui.customerIdSpin.setValue(1)
            host.ui.invoiceDateEdit.setText("2026-04-03")
            host.ui._cbcs_add_row()
            _edit(host.ui, 0, "description", lambda editor: editor.setText("fresh"))
            _edit(host.ui, 0, "price", lambda editor: editor.setValue(1.25))
            assert host.ui.cbcs_save() is True
            with module.work("shop") as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT id FROM %s WHERE invoice_no = %%s" % _PARENT, ("INV-NEW",))
                parent = cursor.fetchone()
                cursor.execute(
                    "SELECT invoice_id, description FROM %s WHERE invoice_id = %%s" % _LINES,
                    (parent[0],),
                )
                assert cursor.fetchall() == [(parent[0], "fresh")]
            host.close()
            host.deleteLater()
            app.processEvents()
        finally:
            if previous is None:
                sys.modules.pop("cbcs_connections", None)
            else:
                sys.modules["cbcs_connections"] = previous
            if sys.path and sys.path[0] == str(root):
                sys.path.pop(0)
            module.close_all()
    finally:
        _drop(module)
        module.close_all()
        set_schema_reader(None)
        closer = getattr(side, "close", None)
        if closer is not None:
            closer()


def _create(module: Any) -> None:
    with module.work("shop") as connection:
        cursor = connection.cursor()
        _drop_sql(cursor)
        cursor.execute("CREATE TABLE %s (id serial PRIMARY KEY, name text NOT NULL)" % _CUSTOMERS)
        cursor.execute("CREATE TABLE %s (id serial PRIMARY KEY, name text NOT NULL, price numeric NOT NULL)" % _PRODUCTS)
        cursor.execute(
            """
            CREATE TABLE %s (
                id serial PRIMARY KEY,
                invoice_no text NOT NULL UNIQUE,
                customer_id integer NOT NULL REFERENCES %s(id),
                invoice_date date,
                notes text,
                total numeric
            )
            """
            % (_PARENT, _CUSTOMERS)
        )
        cursor.execute(
            """
            CREATE TABLE %s (
                id serial PRIMARY KEY,
                invoice_id integer NOT NULL REFERENCES %s(id),
                line_no integer NOT NULL,
                product_id integer REFERENCES %s(id),
                description text,
                qty integer NOT NULL,
                price numeric NOT NULL,
                needed date,
                UNIQUE (invoice_id, line_no)
            )
            """
            % (_LINES, _PARENT, _PRODUCTS)
        )
        cursor.execute("INSERT INTO %s (id, name) VALUES (1, 'Acme')" % _CUSTOMERS)
        cursor.execute("INSERT INTO %s (id, name, price) VALUES (1, 'Widget', 1.50), (2, 'Gadget', 2.00)" % _PRODUCTS)
        cursor.execute(
            "INSERT INTO %s (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (1, 'INV-1', 1, '2026-04-02', '', 7)"
            % _PARENT
        )
        cursor.execute(
            "INSERT INTO %s (id, invoice_id, line_no, product_id, description, qty, price, needed) VALUES "
            "(1, 1, 1, 1, NULL, 1, 1.50, '2026-04-02'),"
            "(2, 1, 2, 2, 'Gadget', 2, 2.00, NULL),"
            "(3, 1, 3, 1, 'Extra', 1, 1.50, NULL)"
            % _LINES
        )
        cursor.execute("SELECT setval(pg_get_serial_sequence('%s', 'id'), 1)" % _CUSTOMERS)
        cursor.execute("SELECT setval(pg_get_serial_sequence('%s', 'id'), 2)" % _PRODUCTS)
        cursor.execute("SELECT setval(pg_get_serial_sequence('%s', 'id'), 1)" % _PARENT)
        cursor.execute("SELECT setval(pg_get_serial_sequence('%s', 'id'), 3)" % _LINES)


def _read(connection: Any) -> List[Tuple[Any, ...]]:
    cursor = connection.cursor()
    cursor.execute(
        "SELECT id, line_no, description, qty, price, needed FROM %s WHERE invoice_id = 1 ORDER BY line_no" % _LINES
    )
    found = cursor.fetchall()
    connection.commit()
    rows = []
    for item in found:
        needed = item[5]
        text = needed.isoformat()[:10] if hasattr(needed, "isoformat") else needed
        rows.append((item[0], item[1], item[2], item[3], item[4], text))
    return rows


def _count(connection: Any) -> int:
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM %s" % _LINES)
    found = cursor.fetchone()
    connection.commit()
    return 0 if found is None else int(found[0])


def _drop(module: Any) -> None:
    try:
        with module.work("shop") as connection:
            _drop_sql(connection.cursor())
    except Exception:
        return None
    return None


def _drop_sql(cursor: Any) -> None:
    cursor.execute("DROP TABLE IF EXISTS %s" % _LINES)
    cursor.execute("DROP TABLE IF EXISTS %s" % _PARENT)
    cursor.execute("DROP TABLE IF EXISTS %s" % _PRODUCTS)
    cursor.execute("DROP TABLE IF EXISTS %s" % _CUSTOMERS)

