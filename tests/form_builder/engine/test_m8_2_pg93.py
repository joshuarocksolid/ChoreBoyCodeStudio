"""PostgreSQL 9.3 record story. Skipped unless CBCS_PG93_DSN is set."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Tuple

import pytest

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.connections_module import render_connections_module
from app.features.form_builder.engine.data.sql import (
    delete_row,
    find_keys,
    insert_row,
    load_one,
    select_keys,
    update_changed,
)
from tests.form_builder.engine.test_m8_2_scenario import _generate, _install_boxes, _load_module, _ui_class, invoice_ui

pytestmark = pytest.mark.pg93

_SKIP = "set CBCS_PG93_DSN to run PostgreSQL 9.3 tests"


def test_invoice_story_on_postgres(tmp_path: Path) -> None:
    dsn, connect = _driver()
    fields = _fields(dsn)
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    ui_path = forms / "invoice.ui"
    ui_text = invoice_ui()
    ui_path.write_text(ui_text, encoding="utf-8")
    value = _connection(fields)
    save_connections(str(root), value)
    (root / "cbcs_connections.py").write_text(render_connections_module(value, project_slug="m82"), encoding="utf-8")
    module = _load_module(root / "cbcs_connections.py", "cbcs_connections_pg93")
    module.set_password("shop", fields["password"])
    side = connect(dsn, fields)
    try:
        _create_shop(module)
        source = _generate(root, ui_path, ui_text)
        generated = forms / "ui_invoice.py"
        generated.write_text(source, encoding="utf-8")
        ui_module = _load_module(generated, "ui_invoice_pg93")
        seen = []
        _install_boxes(
            ui_module,
            seen,
            None,
            lambda text: "Delete" if text.startswith("Delete this") else "Cancel" if text.startswith("Someone else") else "Close",
            lambda: ("INV-3", True),
        )
        import sys

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
            from tests.form_builder.engine.test_m8_2_scenario import run_invoice_story

            run_invoice_story(host, _PgDb(side), seen)
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
        closer = getattr(side, "close", None)
        if closer is not None:
            closer()


def test_statements_execute_on_postgres(tmp_path: Path) -> None:
    del tmp_path
    _dsn, connect = _driver()
    fields = _fields(os.environ["CBCS_PG93_DSN"])
    side = connect(os.environ["CBCS_PG93_DSN"], fields)
    name = "m82_sql"
    try:
        cursor = side.cursor()
        cursor.execute("DROP TABLE IF EXISTS %s" % name)
        cursor.execute("CREATE TABLE %s (id serial PRIMARY KEY, invoice_no text, notes text)" % name)
        side.commit()
        inserted = insert_row("postgres", name, ("invoice_no", "notes"), "id")
        cursor.execute(inserted.text, ("INV-PG", "hello"))
        new_id = cursor.fetchone()[0]
        side.commit()
        loaded = load_one("postgres", name, ("invoice_no", "notes"), "id", "row")
        cursor.execute(loaded.text, (new_id,))
        assert cursor.fetchone() == ("INV-PG", "hello")
        changed = update_changed("postgres", name, "id", ("notes",), ("invoice_no", "notes"), True)
        cursor.execute(changed.text, ("mine", new_id, "INV-PG", "nope"))
        assert cursor.rowcount == 0
        side.commit()
        cursor.execute(changed.text, ("mine", new_id, "INV-PG", "hello"))
        assert cursor.rowcount == 1
        side.commit()
        keys = select_keys("postgres", name, "id", (("invoice_no", "asc"),))
        cursor.execute(keys.text)
        assert cursor.fetchone()[0] == new_id
        finder = find_keys("postgres", name, "id", (), ("invoice_no",))
        cursor.execute(finder.text, ("%INV-PG%",))
        assert cursor.fetchone()[0] == new_id
        removed = delete_row("postgres", name, "id")
        cursor.execute(removed.text, (new_id,))
        side.commit()
        cursor.execute(loaded.text, (new_id,))
        assert cursor.fetchone() is None
    finally:
        try:
            side.cursor().execute("DROP TABLE IF EXISTS %s" % name)
            side.commit()
        except Exception:
            pass
        closer = getattr(side, "close", None)
        if closer is not None:
            closer()


class _PgDb:
    """The small surface ``run_invoice_story`` uses, backed by a second connection."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def row(self, invoice_no: str) -> Optional[tuple]:
        cursor = self._connection.cursor()
        cursor.execute(
            "SELECT id, invoice_no, customer_id, invoice_date, notes FROM invoices WHERE invoice_no = %s",
            (invoice_no,),
        )
        found = cursor.fetchone()
        self._connection.commit()
        if found is None:
            return None
        day = found[3]
        text = day.isoformat()[:10] if hasattr(day, "isoformat") else str(day)
        notes = "" if found[4] is None else found[4]
        return (found[0], found[1], int(found[2]), text, notes)

    def change(self, invoice_no: str, notes: str) -> None:
        cursor = self._connection.cursor()
        cursor.execute("UPDATE invoices SET notes = %s WHERE invoice_no = %s", (notes, invoice_no))
        self._connection.commit()

    def remove(self, invoice_no: str) -> None:
        cursor = self._connection.cursor()
        cursor.execute("DELETE FROM invoices WHERE invoice_no = %s", (invoice_no,))
        self._connection.commit()

    def with_notes(self, notes: str) -> Optional[tuple]:
        cursor = self._connection.cursor()
        cursor.execute("SELECT id FROM invoices WHERE notes = %s", (notes,))
        found = cursor.fetchone()
        self._connection.commit()
        return found


def _create_shop(module: Any) -> None:
    with module.work("shop") as connection:
        cursor = connection.cursor()
        cursor.execute("DROP TABLE IF EXISTS invoice_lines")
        cursor.execute("DROP TABLE IF EXISTS invoices")
        cursor.execute("DROP TABLE IF EXISTS products")
        cursor.execute("DROP TABLE IF EXISTS customers")
        cursor.execute("CREATE TABLE customers (id serial PRIMARY KEY, name text NOT NULL)")
        cursor.execute(
            """
            CREATE TABLE invoices (
                id serial PRIMARY KEY,
                invoice_no text NOT NULL UNIQUE,
                customer_id integer NOT NULL REFERENCES customers(id),
                invoice_date date,
                notes text,
                total numeric
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE invoice_lines (
                id serial PRIMARY KEY,
                invoice_id integer NOT NULL REFERENCES invoices(id)
            )
            """
        )
        cursor.execute("INSERT INTO customers (id, name) VALUES (1, 'Acme')")
        cursor.execute("SELECT setval(pg_get_serial_sequence('customers', 'id'), 1)")
        cursor.execute(
            "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (1, 'INV-1', 1, '2026-01-15', '', 1.50)"
        )
        cursor.execute("INSERT INTO invoice_lines (invoice_id) VALUES (1)")
        cursor.execute(
            "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (2, 'INV-2', 1, '2026-02-01', '', 0)"
        )
        cursor.execute(
            "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (3, 'INV-3', 1, '2026-03-01', '', 0)"
        )
        cursor.execute("SELECT setval(pg_get_serial_sequence('invoices', 'id'), 3)")


def _drop(module: Any) -> None:
    try:
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute("DROP TABLE IF EXISTS invoice_lines")
            cursor.execute("DROP TABLE IF EXISTS invoices")
            cursor.execute("DROP TABLE IF EXISTS products")
            cursor.execute("DROP TABLE IF EXISTS customers")
    except Exception:
        return None
    return None


def _connection(fields: dict) -> ConnectionSet:
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


def _driver() -> Tuple[str, Any]:
    raw = os.environ.get("CBCS_PG93_DSN", "").strip()
    if not raw:
        pytest.skip(_SKIP)
    try:
        import psycopg  # type: ignore[import]
    except ImportError:
        psycopg = None
    if psycopg is not None:
        def open_psycopg(dsn: str, _fields: dict) -> Any:
            connection = psycopg.connect(dsn)
            connection.autocommit = False
            return connection

        return raw, open_psycopg
    try:
        import pg8000.dbapi as pg8000  # type: ignore[import]
    except ImportError:
        pg8000 = None
    if pg8000 is None:
        pytest.skip("neither psycopg nor pg8000 is installed")
        raise RuntimeError("neither psycopg nor pg8000 is installed")
    driver = pg8000

    def open_pg8000(_dsn: str, found: dict) -> Any:
        port = int(found.get("port") or "5432")
        return driver.connect(
            user=found["user"],
            password=found["password"],
            host=found.get("host") or "127.0.0.1",
            database=found.get("dbname") or found.get("database") or "cbcs",
            port=port,
        )

    return raw, open_pg8000


def _fields(dsn: str) -> dict:
    found = {}
    for part in dsn.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        found[key] = value
    return found
