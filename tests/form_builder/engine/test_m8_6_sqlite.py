"""SQLite schema read, the cache file, and the paths a package must ignore."""

from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path

import pytest

from app.features.form_builder.engine.data.connections import Connection
from app.features.form_builder.engine.data.schema import write_schema
from app.features.form_builder.engine.data.schema_cache import format_read_at, refresh
from app.packaging.payload_policy import PackagingPayloadPolicy
from app.shell.project_tree_utils import filter_tree_signature_entries
from tests.form_builder.fixtures.m8.make_shop import build

pytestmark = pytest.mark.unit

_NOW = datetime.datetime(2026, 11, 2, 14, 2, 11)


@pytest.mark.logic("L-schema-cache")
def test_refresh_reads_the_shop_and_a_second_read_is_the_same_bytes(tmp_path: Path) -> None:
    database = tmp_path / "my shop" / "shop.db"
    build(str(database))
    opened = sqlite3.connect(str(database))
    try:
        opened.execute(
            "CREATE TRIGGER customer_touch AFTER UPDATE ON customers BEGIN SELECT 1; END"
        )
        opened.commit()
    finally:
        opened.close()
    connection = Connection("shop", "Shop", "sqlite", file="my shop/shop.db")
    outcome = refresh(str(tmp_path), connection, lambda _connection: "", now=_NOW)
    assert outcome.ok and outcome.schema is not None
    assert outcome.kept_previous is False
    tables = {table.name: table for table in outcome.schema.tables}
    assert tables["customers"].key == "id"
    assert tables["products"].key == "id"
    assert tables["invoices"].key == "id"
    assert tables["invoice_lines"].key == "id"
    assert tables["customers"].triggers is True
    assert tables["invoices"].triggers is False
    name = _column(tables["customers"], "name")
    email = _column(tables["customers"], "email")
    customer = _column(tables["invoices"], "customer_id")
    assert name.nullable is False
    assert email.unique is True
    assert customer.references is not None
    assert customer.references.table == "customers"
    assert customer.references.column == "id"
    assert tables["customers"].rows == 2
    assert tables["products"].rows == 2
    assert tables["invoices"].rows == 1
    assert tables["invoice_lines"].rows == 1
    assert outcome.schema.server == sqlite3.sqlite_version
    assert outcome.schema.driver == "sqlite3"
    cache = tmp_path / "cbcs" / "schema" / "shop.json"
    text = write_schema(outcome.schema)
    assert cache.read_bytes() == text.encode("utf-8")
    assert not (tmp_path / "cbcs" / "schema" / "shop.json.writing").exists()
    again = refresh(str(tmp_path), connection, lambda _connection: "", now=_NOW)
    assert again.ok and again.schema is not None
    assert cache.read_bytes() == write_schema(again.schema).encode("utf-8")
    assert cache.read_bytes() == text.encode("utf-8")
    database.unlink()
    missed = refresh(str(tmp_path), connection, lambda _connection: "", now=_NOW)
    assert missed.ok is False
    assert missed.kept_previous is True
    assert missed.reason.endswith("is missing.")
    assert cache.read_bytes() == text.encode("utf-8")
    assert format_read_at("2026-11-02T14:02:11") == "2 Nov 14:02"


def test_schema_cache_is_left_out_of_a_package_and_the_tree_signature() -> None:
    policy = PackagingPayloadPolicy()
    assert policy.is_payload_excluded(Path("cbcs/schema/office.json"))
    assert policy.is_payload_excluded(Path("cbcs/cache/office.json"))
    kept = filter_tree_signature_entries(("cbcs/schema/office.json", "src/main.py"))
    assert kept == ("src/main.py",)


def _column(table, name):
    for column in table.columns:
        if column.name == name:
            return column
    raise AssertionError(name)
