# pyright: reportMissingImports=false
"""PostgreSQL 9.3 coverage for the record-form review fixes. Both drivers."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Tuple

import pytest

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.schema import Column, Schema, Table, set_schema_reader, write_schema
from app.features.form_builder.engine.data.schema_cache import install_schema_reader
from app.features.form_builder.engine.data.source import RecordSource
from app.features.form_builder.engine.data.sql import find_keys
from tests.form_builder.engine.test_m8_2_followup import _labeled
from tests.form_builder.engine.test_m8_2_scenario import _generate, _install_boxes, _load_module, _ui_class, _xml

pytestmark = pytest.mark.pg93


@pytest.fixture
def pg93_dsn() -> str:
    raw = os.environ.get("CBCS_PG93_DSN", "").strip()
    if not raw:
        pytest.skip("set CBCS_PG93_DSN to run PostgreSQL 9.3 tests")
    return raw


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_postgres_unique_violation_uses_the_field_label(tmp_path: Path, pg93_dsn: str, driver: str, connections_module) -> None:
    _import(driver)
    table = "m82u_%s" % uuid.uuid4().hex[:8]
    ui = _labeled(RecordSource("shop", table, "id"), "code", "codeEdit", "Code", "QLineEdit")

    def build(module: Any) -> None:
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute("CREATE TABLE %s (id serial PRIMARY KEY, code text UNIQUE NOT NULL)" % table)
            cursor.execute("INSERT INTO %s (code) VALUES (%%s)" % table, ("A",))
            cursor.execute("INSERT INTO %s (code) VALUES (%%s)" % table, ("B",))

    def check(host: Any, module: Any) -> None:
        host.ui.cbcs_next()
        host.ui.codeEdit.setText("A")
        assert host.ui.cbcs_save() is False
        assert host.ui.codeEditError.text() == "Another %s already uses this code." % _noun(table)
        assert host.ui.codeEditError.isVisible() is True
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT code FROM %s WHERE id = 2" % table)
            assert cursor.fetchone()[0] == "B"

    _run(tmp_path, pg93_dsn, driver, connections_module, table, ui, _schema(table, (Column("id", "integer", False), Column("code", "text", False, unique=True)), "id"), build, check)


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_postgres_time_and_datetime_round_trip(tmp_path: Path, pg93_dsn: str, driver: str, connections_module) -> None:
    _import(driver)
    table = "m82c_%s" % uuid.uuid4().hex[:8]
    ui = _xml(
        RecordSource("shop", table, "id"),
        (("QTimeEdit", "timeEdit", "at_time", ""), ("QDateTimeEdit", "stampEdit", "at_stamp", "")),
    )

    def build(module: Any) -> None:
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute("CREATE TABLE %s (id serial PRIMARY KEY, at_time time, at_stamp timestamp)" % table)
            cursor.execute(
                "INSERT INTO %s (at_time, at_stamp) VALUES (%%s, %%s)" % table,
                ("09:30:00", "2026-04-01 09:30:00"),
            )

    def check(host: Any, module: Any) -> None:
        from PySide6.QtCore import QDate, QDateTime, QTime

        assert host.ui.timeEdit.time() == QTime(9, 30, 0)
        host.ui.timeEdit.setTime(QTime(10, 15, 0))
        host.ui.stampEdit.setDateTime(QDateTime(QDate(2026, 4, 2), QTime(11, 0, 0)))
        assert host.ui.cbcs_save() is True
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT at_time, at_stamp FROM %s" % table)
            clock, stamp = cursor.fetchone()
        assert (clock.hour, clock.minute) == (10, 15)
        assert (stamp.year, stamp.month, stamp.day, stamp.hour) == (2026, 4, 2, 11)

    schema = _schema(
        table,
        (Column("id", "integer", False), Column("at_time", "time", True), Column("at_stamp", "timestamp", True)),
        "id",
    )
    _run(tmp_path, pg93_dsn, driver, connections_module, table, ui, schema, build, check)


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_postgres_typed_text_key_is_inserted(tmp_path: Path, pg93_dsn: str, driver: str, connections_module) -> None:
    _import(driver)
    table = "m82k_%s" % uuid.uuid4().hex[:8]
    ui = _xml(
        RecordSource("shop", table, "code", open_at="new"),
        (("QLineEdit", "codeEdit", "code", ""), ("QLineEdit", "labelEdit", "label", "")),
    )

    def build(module: Any) -> None:
        with module.work("shop") as connection:
            connection.cursor().execute("CREATE TABLE %s (code text PRIMARY KEY, label text NOT NULL)" % table)

    def check(host: Any, module: Any) -> None:
        host.ui.codeEdit.setText("A1")
        host.ui.labelEdit.setText("hello")
        assert host.ui.cbcs_save() is True
        assert host.ui.cbcs_current_key() == "A1"
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT label FROM %s WHERE code = %%s" % table, ("A1",))
            assert cursor.fetchone()[0] == "hello"

    schema = _schema(table, (Column("code", "text", False), Column("label", "text", False)), "code")
    _run(tmp_path, pg93_dsn, driver, connections_module, table, ui, schema, build, check)


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_postgres_find_escape_matches_one_column(tmp_path: Path, pg93_dsn: str, driver: str, connections_module) -> None:
    _import(driver)
    module = _module(tmp_path, _fields(pg93_dsn), driver, connections_module)
    table = "m82f_%s" % uuid.uuid4().hex[:8]
    try:
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute("CREATE TABLE %s (id serial PRIMARY KEY, code text)" % table)
            cursor.execute("INSERT INTO %s (code) VALUES (%%s)" % table, ("a_b",))
            cursor.execute("INSERT INTO %s (code) VALUES (%%s)" % table, ("axb",))
        statement = find_keys("postgres", table, "id", (), ("code",))
        assert "E'\\\\'" in statement.text
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute(statement.text, (r"%a\_b%",))
            found = cursor.fetchone()
        assert found is not None
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT code FROM %s WHERE id = %%s" % table, (found[0],))
            assert cursor.fetchone()[0] == "a_b"
    finally:
        _drop(module, table)


def _run(
    tmp_path: Path,
    dsn: str,
    driver: str,
    connections_module,
    table: str,
    ui_text: str,
    schema: Schema,
    build: Callable[[Any], None],
    check: Callable[[Any, Any], None],
) -> None:
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    ui_path = forms / "invoice.ui"
    ui_path.write_text(ui_text, encoding="utf-8")
    module = _module(tmp_path, _fields(dsn), driver, connections_module)
    previous = sys.modules.get("cbcs_connections")
    sys.modules["cbcs_connections"] = module
    sys.path.insert(0, str(root))
    try:
        build(module)
        folder = root / "cbcs" / "schema"
        folder.mkdir(parents=True)
        (folder / "shop.json").write_text(write_schema(schema), encoding="utf-8")
        save_connections(str(root), _value(_fields(dsn)))
        install_schema_reader(str(root))
        source = _generate(root, ui_path, ui_text)
        generated = forms / "ui_invoice.py"
        generated.write_text(source, encoding="utf-8")
        ui_module = _load_module(generated, "ui_invoice_%s" % uuid.uuid4().hex)
        _install_boxes(ui_module, [], None, lambda _text: "Close", None)
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
        check(host, module)
        host.close()
        host.deleteLater()
        app.processEvents()
    finally:
        set_schema_reader(None)
        _drop(module, table)
        module.close_all()
        if previous is None:
            sys.modules.pop("cbcs_connections", None)
        else:
            sys.modules["cbcs_connections"] = previous
        if sys.path and sys.path[0] == str(root):
            sys.path.pop(0)


def _module(tmp_path: Path, fields: dict, driver: str, connections_module) -> Any:
    module, _text = connections_module(tmp_path, _value(fields), "m82")
    module._CBCS_DRIVERS = (driver,)
    module.set_password("shop", fields["password"])
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


def _schema(name: str, columns: Tuple[Column, ...], key: str) -> Schema:
    return Schema("shop", "postgres", "PostgreSQL 9.3", "2026-01-01T00:00:00", "psycopg", (Table(name, columns, key=key),))


def _fields(dsn: str) -> dict:
    found = {}
    for part in dsn.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        found[key] = value
    return found


def _import(driver: str) -> None:
    if driver == "psycopg":
        import psycopg  # noqa: F401
        return
    import pg8000.dbapi  # noqa: F401


def _noun(table: str) -> str:
    if table.endswith("s"):
        return table[:-1]
    return table


def _drop(module: Any, table: str) -> None:
    try:
        with module.work("shop") as connection:
            connection.cursor().execute("DROP TABLE IF EXISTS %s" % table)
    except Exception:
        return
