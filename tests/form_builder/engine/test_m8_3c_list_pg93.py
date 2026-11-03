# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
"""List search on PostgreSQL 9.3. Both drivers, unique table names."""

from __future__ import annotations

import datetime
import os
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.features.form_builder.engine.data.schema import Column, Schema, Table
from app.features.form_builder.engine.data.source import ListOpen, ListSource
from tests.form_builder.engine.test_m8_2_followup_pg93 import _import, _run
from tests.form_builder.engine.test_m8_2_scenario import _xml

pytestmark = pytest.mark.pg93


@pytest.fixture
def pg93_dsn() -> str:
    raw = os.environ.get("CBCS_PG93_DSN", "").strip()
    if not raw:
        pytest.skip("set CBCS_PG93_DSN to run PostgreSQL 9.3 tests")
    return raw


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_postgres_search_matches_case_and_keeps_null(tmp_path: Path, pg93_dsn: str, driver: str, connections_module) -> None:
    _import(driver)
    table = "m83c_%s" % uuid.uuid4().hex[:8]
    source = ListSource(
        "shop",
        ("name", "price", "when_on"),
        table=table,
        search=("name",),
        search_field="searchEdit",
        order=(("id", "asc"),),
        limit=10,
        open=ListOpen("customer", "id"),
    )
    ui = _xml(source, (("QLineEdit", "searchEdit", "", ""), ("QTableView", "customersView", "", "")))

    def build(module: Any) -> None:
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute(
                "CREATE TABLE %s (id text PRIMARY KEY, name text, price numeric, when_on date, note text)" % table
            )
            cursor.execute(
                "INSERT INTO %s (id, name, price, when_on, note) VALUES (%%s, %%s, %%s, %%s, %%s)" % table,
                ("A1", "Ann", Decimal("12.50"), datetime.date(2026, 4, 1), "keep"),
            )
            cursor.execute(
                "INSERT INTO %s (id, name, price, when_on, note) VALUES (%%s, %%s, %%s, %%s, %%s)" % table,
                ("B2", None, None, None, "other"),
            )

    def check(host: Any, module: Any) -> None:
        host.ui.searchEdit.setText("ANN")
        host.ui._cbcs_list_timer.timeout.emit()
        assert _names(host) == ["Ann"]
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT price, when_on FROM %s WHERE id = %%s" % table, ("A1",))
            stored = cursor.fetchone()
            cursor.execute("SELECT name FROM %s WHERE id = %%s" % table, ("B2",))
            missing = cursor.fetchone()
        assert stored is not None and missing is not None
        assert missing[0] is None
        assert _cell(host, 1) == str(stored[0])
        assert _cell(host, 2) == str(stored[1])
        host.ui.searchEdit.setText("")
        host.ui._cbcs_list_timer.timeout.emit()
        assert "" in _names(host)
        assert host.ui.limitLabel.isVisible() is False

    _run(tmp_path, pg93_dsn, driver, connections_module, table, ui, _schema(table), build, check)


@pytest.mark.parametrize("driver", ["psycopg", "pg8000"])
def test_postgres_own_sql_keeps_a_percent_literal(tmp_path: Path, pg93_dsn: str, driver: str, connections_module) -> None:
    _import(driver)
    table = "m83p_%s" % uuid.uuid4().hex[:8]
    sql = "SELECT id, name FROM %s WHERE note LIKE '%%keep%%'" % table
    source = ListSource(
        "shop",
        ("name",),
        table=table,
        sql=sql,
        search=("name",),
        search_field="searchEdit",
        limit=10,
        open=ListOpen("customer", "id"),
    )
    ui = _xml(source, (("QLineEdit", "searchEdit", "", ""), ("QTableView", "customersView", "", "")))

    def build(module: Any) -> None:
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute("CREATE TABLE %s (id text PRIMARY KEY, name text, note text)" % table)
            cursor.execute("INSERT INTO %s (id, name, note) VALUES (%%s, %%s, %%s)" % table, ("A1", "Ann", "keep"))
            cursor.execute("INSERT INTO %s (id, name, note) VALUES (%%s, %%s, %%s)" % table, ("B2", "Bob", "drop"))

    def check(host: Any, module: Any) -> None:
        assert _names(host) == ["Ann"]
        with module.work("shop") as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM %s" % table)
            assert cursor.fetchone()[0] == 2

    _run(tmp_path, pg93_dsn, driver, connections_module, table, ui, _schema(table), build, check)


def _schema(name: str) -> Schema:
    return Schema(
        "shop",
        "postgres",
        "PostgreSQL 9.3",
        "2026-01-01T00:00:00",
        "psycopg",
        (
            Table(
                name,
                (
                    Column("id", "text", False),
                    Column("name", "text", True),
                    Column("price", "numeric", True),
                    Column("when_on", "date", True),
                    Column("note", "text", True),
                ),
                key="id",
            ),
        ),
    )


def _names(host: Any) -> list:
    model = host.ui.customersView.model()
    assert model is not None
    return [model.item(row, 0).text() for row in range(model.rowCount())]


def _cell(host: Any, column: int) -> str:
    model = host.ui.customersView.model()
    assert model is not None
    return model.item(0, column).text()
