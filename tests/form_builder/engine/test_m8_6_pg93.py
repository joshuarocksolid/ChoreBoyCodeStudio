"""PostgreSQL 9.3 schema helper. Opt-in via CBCS_PG93_DSN. The parent never imports a driver."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

from app.features.form_builder.engine.data.connections import Connection
from app.features.form_builder.engine.data.schema_cache import (
    install_schema_reader,
    postgres_tester,
    probe_select,
    refresh,
    set_schema_runner,
)
from app.features.form_builder.qtside.schema_runner import register_schema_runner, set_helper_command, set_helper_timeouts

pytestmark = pytest.mark.pg93

_SETUP = textwrap.dedent(
    """
    import os
    driver = os.environ["CBCS_FB_SCHEMA_DRIVER"]
    fields = {}
    for part in os.environ["CBCS_PG93_DSN"].split():
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key] = value
    if driver == "psycopg":
        import psycopg
        connection = psycopg.connect(os.environ["CBCS_PG93_DSN"])
    else:
        import pg8000.dbapi
        connection = pg8000.dbapi.connect(
            user=fields["user"],
            password=fields.get("password") or "",
            host=fields.get("host") or "127.0.0.1",
            port=int(fields.get("port") or "5432"),
            database=fields.get("dbname") or fields.get("database") or "cbcs",
        )
    cursor = connection.cursor()
    cursor.execute("DROP TABLE IF EXISTS invoice_lines")
    cursor.execute("DROP TABLE IF EXISTS invoices")
    cursor.execute("DROP TABLE IF EXISTS customers")
    cursor.execute(
        "CREATE TABLE customers (id integer PRIMARY KEY, name text NOT NULL, email text UNIQUE)"
    )
    cursor.execute(
        "CREATE TABLE invoices (id integer PRIMARY KEY, customer_id integer REFERENCES customers (id))"
    )
    cursor.execute("INSERT INTO customers (id, name, email) VALUES (1, 'Acme', 'acme@example.com')")
    cursor.execute("INSERT INTO customers (id, name, email) VALUES (2, 'Northwind', 'north@example.com')")
    cursor.execute("INSERT INTO invoices (id, customer_id) VALUES (1, 1)")
    connection.commit()
    cursor.close()
    connection.close()
    """
)


@pytest.fixture
def pg93_dsn() -> str:
    raw = os.environ.get("CBCS_PG93_DSN", "").strip()
    if not raw:
        pytest.skip("set CBCS_PG93_DSN to run PostgreSQL 9.3 tests")
    return raw


@pytest.fixture
def fields(pg93_dsn: str) -> dict:
    found = {}
    for part in pg93_dsn.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        found[key] = value
    return found


@pytest.fixture
def runner():
    register_schema_runner()
    set_helper_command(None)
    set_helper_timeouts(10, 20)
    try:
        yield
    finally:
        from app.features.form_builder.engine.data.schema_cache import cancel_schema_work

        cancel_schema_work()
        set_schema_runner(None)
        set_helper_timeouts(10, 20)


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_schema_and_test_leave_the_driver_out_of_the_editor(tmp_path, fields, driver, runner) -> None:
    del runner
    assert "psycopg" not in sys.modules
    assert "pg8000" not in sys.modules
    _setup(driver)
    os.environ["CBCS_FB_SCHEMA_DRIVER"] = driver
    install_schema_reader(str(tmp_path))
    connection = _connection(fields)
    try:
        outcome = refresh(str(tmp_path), connection, lambda _item: fields["password"])
        result = postgres_tester(connection, lambda: fields["password"])
        assert outcome.ok and outcome.schema is not None
        tables = {table.name: table for table in outcome.schema.tables}
        assert tables["customers"].key == "id"
        assert tables["customers"].rows == 2
        link = next(column for column in tables["invoices"].columns if column.name == "customer_id")
        assert link.references is not None
        assert link.references.table == "customers"
        assert result == {
            "ok": True,
            "server": outcome.schema.server,
            "tables": len(outcome.schema.tables),
            "driver": driver,
        }
        probed = probe_select(
            str(tmp_path),
            connection,
            "SELECT id, name FROM customers",
            lambda _item: fields["password"],
        )
        assert probed.ok
        assert [column.name for column in probed.columns] == ["id", "name"]
        again = postgres_tester(connection, lambda: fields["password"])
        assert again["ok"] is True
        assert _count(driver) == 2
        assert "psycopg" not in sys.modules
        assert "pg8000" not in sys.modules
    finally:
        os.environ.pop("CBCS_FB_SCHEMA_DRIVER", None)


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_auth_unreachable_and_missing_database(tmp_path, fields, driver, runner) -> None:
    del runner
    os.environ["CBCS_FB_SCHEMA_DRIVER"] = driver
    install_schema_reader(str(tmp_path))
    try:
        auth = postgres_tester(_connection(fields), lambda: "not-the-password")
        assert auth["kind"] == "auth"
        missed = postgres_tester(_connection(fields, database="cbcs_missing"), lambda: fields["password"])
        assert missed["kind"] == "no_database"
        down = postgres_tester(_connection(fields, host="127.0.0.1", port=1), lambda: fields["password"])
        assert down["kind"] == "unreachable"
    finally:
        os.environ.pop("CBCS_FB_SCHEMA_DRIVER", None)


def _connection(fields: dict, **overrides) -> Connection:
    port = int(fields.get("port") or "5432")
    values = {
        "host": fields.get("host") or "127.0.0.1",
        "port": None if port == 5432 else port,
        "database": fields.get("dbname") or fields.get("database") or "cbcs",
        "user": fields["user"],
    }
    values.update(overrides)
    return Connection("office", "Office", "postgres", password="ask", **values)


def _setup(driver: str) -> None:
    env = dict(os.environ)
    env["CBCS_FB_SCHEMA_DRIVER"] = driver
    subprocess.check_call([sys.executable, "-c", _SETUP], env=env)


def _count(driver: str) -> int:
    script = textwrap.dedent(
        """
        import os
        driver = os.environ["CBCS_FB_SCHEMA_DRIVER"]
        fields = {}
        for part in os.environ["CBCS_PG93_DSN"].split():
            if "=" in part:
                key, value = part.split("=", 1)
                fields[key] = value
        if driver == "psycopg":
            import psycopg
            connection = psycopg.connect(os.environ["CBCS_PG93_DSN"])
        else:
            import pg8000.dbapi
            connection = pg8000.dbapi.connect(
                user=fields["user"],
                password=fields.get("password") or "",
                host=fields.get("host") or "127.0.0.1",
                port=int(fields.get("port") or "5432"),
                database=fields.get("dbname") or fields.get("database") or "cbcs",
            )
        cursor = connection.cursor()
        cursor.execute("SELECT count(*) FROM customers")
        row = cursor.fetchone()
        print(row[0])
        cursor.close()
        connection.close()
        """
    )
    env = dict(os.environ)
    env["CBCS_FB_SCHEMA_DRIVER"] = driver
    out = subprocess.check_output([sys.executable, "-c", script], env=env, text=True)
    return int(out.strip())
