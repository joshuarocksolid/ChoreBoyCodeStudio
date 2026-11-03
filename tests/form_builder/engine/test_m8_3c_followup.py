"""pg8000 percent scan, trailing semicolon, probe wrap, and publish without a live probe."""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, List

import pytest

from app.features.form_builder.engine.data.check import run_checks
from app.features.form_builder.engine.data.checks.listing import cached_list_probe, remember_list_probe
from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
from app.features.form_builder.engine.data.publish import publish_session
from app.features.form_builder.engine.data.schema_cache import (
    ProbeOutcome,
    install_schema_reader,
    probe_select,
    set_schema_runner,
)
from app.features.form_builder.engine.data.sql import (
    adapt_user_sql,
    list_read,
    select_source_error,
    user_sql_for_wrap,
)
from app.features.form_builder.engine.diagnostics import DiagnosticsStore
from tests.form_builder.engine.test_m8_3c_list import _doc, _source

pytestmark = pytest.mark.unit

_PG8000 = "/Users/local/Projects/ChoreBoyCodeStudio_artifacts/vendor_pgtest"

_OPEN = (
    "SELECT id /* don't */, id % 2 AS odd FROM t",
    "SELECT id, E'\\\\' AS b, id % 2 AS odd FROM t",
    "SELECT id, $$$$ AS e, id % 2 AS odd FROM t",
    "SELECT id, e'it\\'s 50%' AS b FROM t",
)


@pytest.fixture
def _unload_postgres_drivers():
    yield
    for name in list(sys.modules):
        if name.split(".")[0] in ("pg8000", "psycopg"):
            del sys.modules[name]


def test_pg8000_sees_the_authors_sql(_unload_postgres_drivers: None) -> None:
    convert = _convert_paramstyle()
    generated = _generated_adapt()
    cases = _OPEN + (
        "SELECT id /* % */ FROM t",
        "SELECT id, $x$50%$x$ AS tag FROM t",
        "SELECT id, '50%' AS tag FROM t",
        "SELECT id, E'50%' AS tag FROM t",
        "SELECT id, $$50%$$ AS tag FROM t",
        "SELECT id FROM t -- 50%",
        "SELECT id, id % 2 AS odd FROM t WHERE id % 2 = 0",
        "SELECT id, '%s' AS lit FROM t",
        'SELECT id AS "50%" FROM t',
    )
    for user in cases:
        made = list_read("postgres", "", ("id",), user, ("id",), (), (), 10, "id")
        inner = generated._cbcs_adapt_user_sql("pg8000", made.inner, True)
        assert inner == adapt_user_sql("pg8000", made.inner, True)
        wrapped = "SELECT * FROM (\n%s\n) AS q%s" % (inner, made.row_tail)
        got = convert("format", wrapped, ("%a%", 0))[0]
        assert _body(got) == user
        if user not in _OPEN:
            number = iter(range(1, 99))
            tail = re.sub("%s", lambda _match: "$%d" % next(number), made.row_tail)
            assert got == "SELECT * FROM (\n%s\n) AS q%s" % (user, tail)


def test_a_trailing_semicolon_is_not_wrapped() -> None:
    for text in (
        "SELECT * FROM t;",
        "SELECT * FROM t; -- x",
        "SELECT * FROM t; /* x */",
        "SELECT * FROM t ; \n -- x",
    ):
        assert select_source_error(text) is None
        assert user_sql_for_wrap("postgres", text) == "SELECT * FROM t"
        made = list_read("postgres", "t", ("id",), text, (), (), (), None, "id")
        assert made.inner == "SELECT * FROM t"
        assert made.rows.text.startswith("SELECT * FROM (\nSELECT * FROM t\n) AS q")
    assert user_sql_for_wrap("postgres", "SELECT ';'") == "SELECT ';'"
    assert select_source_error("SELECT * FROM t; SELECT 1") is not None


def test_row_locks_and_unbalanced_parentheses_are_refused() -> None:
    sentence = "Only a single SELECT can be a list's source."
    for text in (
        "SELECT * FROM t FOR KEY SHARE",
        "SELECT * FROM t FOR NO KEY UPDATE",
        "SELECT * FROM t FOR UPDATE",
        "SELECT * FROM t FOR SHARE",
        "SELECT * FROM t) AS q, u WHERE (1=1",
        "SELECT * FROM (t",
    ):
        assert select_source_error(text) == sentence
    assert select_source_error("SELECT (1)") is None
    assert select_source_error("SELECT * FROM t -- FOR KEY SHARE") is None
    assert select_source_error("SELECT * FROM t WHERE name = ')'") is None


def test_a_trailing_comment_probes_as_its_own_subquery(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "data").mkdir(parents=True)
    path = root / "data" / "shop.db"
    db = sqlite3.connect(str(path))
    db.execute("CREATE TABLE customers (id TEXT, name TEXT)")
    db.commit()
    db.close()
    connection = Connection("shop", "Shop", "sqlite", file="data/shop.db")
    sql = "SELECT id, name FROM customers -- keep"
    outcome = probe_select(str(root), connection, sql, lambda _item: "")
    assert outcome.ok is True
    assert [column.name for column in outcome.columns] == ["id", "name"]
    ended = probe_select(str(root), connection, "SELECT id, name FROM customers;", lambda _item: "")
    assert ended.ok is True
    assert [column.name for column in ended.columns] == ["id", "name"]


def test_postgres_probe_uses_the_same_subquery() -> None:
    from app.features.form_builder.engine.data.helper.catalog import probe_postgres

    cursor = _Cursor()
    probe_postgres(_Connection(cursor), "SELECT id, name FROM customers -- keep")
    assert (
        "SELECT * FROM (\nSELECT id, name FROM customers -- keep\n) AS q LIMIT 0" in cursor.calls
    )
    cursor.calls.clear()
    probe_postgres(_Connection(cursor), "SELECT id FROM customers;")
    assert "SELECT * FROM (\nSELECT id FROM customers\n) AS q LIMIT 0" in cursor.calls


def test_publishing_edits_does_not_probe_postgres(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    save_connections(
        str(root),
        ConnectionSet(
            (
                Connection(
                    "shop",
                    "Shop",
                    "postgres",
                    host="127.0.0.1",
                    port=5432,
                    database="cbcs",
                    user="cbcs",
                    password="ask",
                ),
            )
        ),
    )
    install_schema_reader(str(root))
    calls: List[str] = []

    class _Runner:
        def probe_select(self, *_args: object) -> dict:
            calls.append("probe")
            return {"ok": False, "kind": "other", "message": "no"}

        def schema(self, *_args: object) -> dict:
            calls.append("schema")
            return {"ok": False, "kind": "other", "message": "no"}

    set_schema_runner(_Runner())
    import app.features.form_builder.qtside.schema_prompt as prompt

    monkeypatch.setattr(prompt, "ask_connection_secret", lambda *_args, **_kwargs: calls.append("ask") or "")
    document = _doc(_source(10, sql="SELECT id, name FROM customers"))
    session = _PublishSession(document)
    try:
        for _index in range(20):
            publish_session(session)
    finally:
        set_schema_runner(None)
        from app.features.form_builder.engine.data.schema import set_schema_reader

        set_schema_reader(None)
    assert calls == []
    assert cached_list_probe(document, "SELECT id, name FROM customers") is None


def test_a_remembered_refusal_is_what_publish_shows() -> None:
    document = _doc(_source(10, sql="SELECT * FROM missing_table"))
    remember_list_probe(
        document,
        "SELECT * FROM missing_table",
        ProbeOutcome(False, (), "other", "no such table: missing_table", False),
    )
    found = [item for item in run_checks(document) if item.code == "FB314"]
    assert [item.message for item in found] == ["no such table: missing_table"]


class _PublishSession:
    def __init__(self, document: object) -> None:
        self.document = document
        self.diagnostics = DiagnosticsStore()
        self.disposed = False


class _Cursor:
    def __init__(self) -> None:
        self.calls: List[str] = []
        self.description = [("id", 23), ("name", 25)]

    def execute(self, sql: str, _params: object = None) -> None:
        self.calls.append(sql)

    def fetchall(self) -> List[tuple]:
        return [("text",)]

    def close(self) -> None:
        return None


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _Cursor:
        return self._cursor

    def rollback(self) -> None:
        return None


def _body(statement: str) -> str:
    start = statement.find("(\n")
    end = statement.find("\n) AS q", start)
    assert start >= 0 and end > start
    return statement[start + 2 : end]


def _convert_paramstyle() -> Any:
    import importlib

    try:
        module = importlib.import_module("pg8000.dbapi")
    except ImportError:
        if not os.path.isdir(_PG8000):
            pytest.skip("pg8000 1.31.5 is not installed")
        sys.path.append(_PG8000)
        module = importlib.import_module("pg8000.dbapi")
    return module.convert_paramstyle


def _generated_adapt() -> Any:
    from app.features.form_builder.engine.codegen.expanders.listing import _copied_body
    from app.features.form_builder.engine.data.sql import _double_percent_outside, adapt_user_sql

    def block(name: str, params: str, lines: List[str]) -> str:
        body = "\n".join(("        " + line) if line else "" for line in lines)
        return "    def %s(self, %s):\n%s" % (name, params, body)

    percent = block("_cbcs_double_percent", "_sql", _copied_body(_double_percent_outside, ()))
    replacements = (("_double_percent_outside(", "self._cbcs_double_percent("),)
    adapt = block(
        "_cbcs_adapt_user_sql",
        "_driver, _sql, _has_params",
        _copied_body(adapt_user_sql, replacements),
    )
    namespace: dict = {}
    exec("class _Gen:\n%s\n%s" % (percent, adapt), namespace)  # noqa: S102
    return namespace["_Gen"]()
