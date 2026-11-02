"""FB309 when nothing has been read, FB310 after seven days, FB303 for a missing column."""

from __future__ import annotations

import datetime

import pytest

from app.features.form_builder.engine.data.check import run_checks
from app.features.form_builder.engine.data.checks import schema_columns
from app.features.form_builder.engine.data.schema import Column, Schema, Table, set_schema_reader
from app.features.form_builder.engine.data.source import RecordSource, write_data
from app.features.form_builder.engine.diagnostics import CODES
from app.features.form_builder.engine.ui4.values import StringValue

pytestmark = pytest.mark.unit

_NOW = datetime.datetime(2026, 11, 2, 12, 0, 0)


class _Entry:
    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.value = StringValue(text)


class _Node:
    def __init__(self, name: str, props: tuple, node_id: int) -> None:
        self._name = name
        self._props = props
        self.node_id = node_id

    def object_name(self) -> str:
        return self._name

    def properties(self):
        return self._props

    def prop(self, name: str):
        for entry in self._props:
            if entry.name == name:
                return entry
        return None


class _Doc:
    def __init__(self, nodes: tuple) -> None:
        self._nodes = nodes
        self.root = nodes[0]

    def iter_preorder(self):
        return iter(self._nodes)


def test_a_source_with_no_cache_is_fb309_and_not_fb303() -> None:
    document = _form(("nope",))
    set_schema_reader(lambda _doc, _name: None)
    try:
        found = run_checks(document)
    finally:
        set_schema_reader(None)
    codes = [item.code for item in found]
    assert codes.count("FB309") == 1
    assert "FB303" not in codes
    assert any(item.message == CODES["FB309"].title for item in found)


def test_exactly_seven_days_is_fresh_and_older_is_fb310(monkeypatch: pytest.MonkeyPatch) -> None:
    class Frozen(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return _NOW

    monkeypatch.setattr(schema_columns.datetime, "datetime", Frozen)
    fresh_at = (_NOW - datetime.timedelta(days=7)).isoformat(timespec="seconds")
    stale_at = (_NOW - datetime.timedelta(days=7, seconds=1)).isoformat(timespec="seconds")
    set_schema_reader(lambda _doc, name: _schema(fresh_at) if name == "m86cols" else None)
    try:
        assert [item.code for item in run_checks(_form(("id",)))] == []
        set_schema_reader(lambda _doc, name: _schema(stale_at) if name == "m86cols" else None)
        found = run_checks(_form(("id", "missing")))
    finally:
        set_schema_reader(None)
    assert any(item.code == "FB310" for item in found)
    assert any(item.code == "FB303" and item.message == "invoices has no column named missing." for item in found)
    assert not any(item.code == "FB303" and "id" in item.message for item in found)


def test_a_missing_column_is_fb303_and_the_bind_is_unchanged() -> None:
    bind = _Entry("cbcsBind", "missing")
    document = _form_with((bind,))
    set_schema_reader(lambda _doc, name: _schema("2026-11-02T12:00:00") if name == "m86cols" else None)
    try:
        found = run_checks(document)
    finally:
        set_schema_reader(None)
    assert [item.message for item in found if item.code == "FB303"] == ["invoices has no column named missing."]
    assert bind.value.text == "missing"
    located = [item for item in found if item.code == "FB303"][0]
    assert located.location.property == "cbcsBind"
    assert located.location.object_name == "nameEdit"


def _form(columns: tuple) -> _Doc:
    binds = tuple(_Entry("cbcsBind", column) for column in columns)
    return _form_with(binds)


def _form_with(binds: tuple) -> _Doc:
    data = _Entry("cbcsData", write_data(RecordSource("m86cols", "invoices", "id")))
    root = _Node("Form", (data,), 1)
    widget = _Node("nameEdit", binds, 2)
    return _Doc((root, widget))


def _schema(read_at: str) -> Schema:
    return Schema(
        "m86cols",
        "postgres",
        "PostgreSQL 9.3.25",
        read_at,
        "psycopg",
        (Table("invoices", (Column("id", "integer", False),), key="id"),),
    )
