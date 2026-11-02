# pyright: reportMissingImports=false
"""PostgreSQL 9.3 checks for the generated connection module. Opt-in via CBCS_PG93_DSN."""

from __future__ import annotations

import os
import uuid

import pytest

from app.features.form_builder.engine.data.connections import Connection, ConnectionSet
from app.features.form_builder.engine.data.tester import classify_connect_error

pytestmark = pytest.mark.pg93


@pytest.fixture
def pg93_dsn() -> str:
    raw = os.environ.get("CBCS_PG93_DSN", "").strip()
    if not raw:
        pytest.skip("set CBCS_PG93_DSN to run PostgreSQL 9.3 tests")
    return raw


def _fields(dsn: str) -> dict:
    found = {}
    for part in dsn.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        found[key] = value
    return found


def _module(tmp_path, fields, driver, connections_module):
    port = int(fields.get("port") or "5432")
    value = ConnectionSet(
        (
            Connection(
                "office",
                "Office",
                "postgres",
                host=fields.get("host") or "127.0.0.1",
                port=None if port == 5432 else port,
                database=fields.get("dbname") or fields.get("database") or "cbcs",
                user=fields["user"],
                password="none",
            ),
        )
    )
    module, _text = connections_module(tmp_path, value, "pg93")
    module._CBCS_DRIVERS = (driver,)
    module.set_password("office", fields["password"])
    return module


def _import_driver(driver: str) -> None:
    if driver == "psycopg":
        import psycopg  # noqa: F401
        return
    import pg8000.dbapi  # noqa: F401


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_open_connection(tmp_path, pg93_dsn: str, driver: str, connections_module) -> None:
    _import_driver(driver)
    module = _module(tmp_path, _fields(pg93_dsn), driver, connections_module)
    try:
        connection = module.open_connection("office")
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        assert int(row[0]) == 1
    finally:
        module.close_all()


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_work_commits_an_insert(tmp_path, pg93_dsn: str, driver: str, connections_module) -> None:
    _import_driver(driver)
    module = _module(tmp_path, _fields(pg93_dsn), driver, connections_module)
    table = "t_%s" % uuid.uuid4().hex
    try:
        with module.work("office") as connection:
            cursor = connection.cursor()
            cursor.execute("CREATE TABLE %s (id integer)" % table)
            cursor.execute("INSERT INTO %s (id) VALUES (1)" % table)
        with module.work("office") as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT id FROM %s" % table)
            row = cursor.fetchone()
        assert int(row[0]) == 1
    finally:
        try:
            with module.work("office") as connection:
                connection.cursor().execute("DROP TABLE IF EXISTS %s" % table)
        except Exception:
            pass
        module.close_all()


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_work_rolls_back_an_exception(tmp_path, pg93_dsn: str, driver: str, connections_module) -> None:
    _import_driver(driver)
    module = _module(tmp_path, _fields(pg93_dsn), driver, connections_module)
    table = "t_%s" % uuid.uuid4().hex
    try:
        with module.work("office") as connection:
            connection.cursor().execute("CREATE TABLE %s (id integer)" % table)
        try:
            with module.work("office") as connection:
                connection.cursor().execute("INSERT INTO %s (id) VALUES (7)" % table)
                raise RuntimeError("stop")
        except RuntimeError:
            pass
        with module.work("office") as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT count(*) FROM %s" % table)
            row = cursor.fetchone()
        assert int(row[0]) == 0
    finally:
        try:
            with module.work("office") as connection:
                connection.cursor().execute("DROP TABLE IF EXISTS %s" % table)
        except Exception:
            pass
        module.close_all()


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_a_bad_password_is_auth(pg93_dsn: str, driver: str) -> None:
    fields = _fields(pg93_dsn)
    port = int(fields.get("port") or "5432")
    host = fields.get("host") or "127.0.0.1"
    database = fields.get("dbname") or fields.get("database") or "cbcs"
    user = fields["user"]
    try:
        if driver == "psycopg":
            import psycopg

            psycopg.connect(
                host=host,
                port=port,
                dbname=database,
                user=user,
                password="definitely-wrong",
                connect_timeout=5,
            )
        else:
            import pg8000.dbapi as pg8000

            pg8000.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password="definitely-wrong",
                timeout=5,
            )
    except Exception as exc:
        assert classify_connect_error(exc) == "auth"
        return
    raise AssertionError("expected the server to reject a bad password")
