"""SQL text and SQLite execution for record statements (CONTRACTS.md section 19.5)."""

from __future__ import annotations

import sqlite3

import pytest

from app.features.form_builder.engine.data.sql import (
    IdentifierError,
    assignment_piece,
    conflict_piece,
    delete_row,
    find_keys,
    insert_row,
    is_identifier,
    key_clause,
    load_one,
    quote_ident,
    select_keys,
    update_changed,
    update_head,
)
from tests.form_builder.fixtures.m8.make_shop import build

pytestmark = pytest.mark.unit

_ORDER = (("invoice_date", "desc"), ("id", "desc"))
_DIALECTS = ("sqlite", "postgres")


def _mark(dialect: str) -> str:
    return "?" if dialect == "sqlite" else "%s"


def _like(dialect: str) -> str:
    return "LIKE" if dialect == "sqlite" else "ILIKE"


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_select_keys_orders_by_the_source_then_the_key(dialect: str) -> None:
    statement = select_keys(dialect, "invoices", "id", _ORDER)
    assert statement.text == (
        'SELECT "id" FROM "invoices" ORDER BY "invoice_date" DESC, "id" DESC'
    )
    assert statement.params_order == ()
    assert statement.caption == "List invoice keys"
    dated = select_keys(dialect, "invoices", "id", (("invoice_date", "desc"),))
    assert dated.text == 'SELECT "id" FROM "invoices" ORDER BY "invoice_date" DESC, "id" DESC'
    bare = select_keys(dialect, "invoices", "id", ())
    assert bare.text == 'SELECT "id" FROM "invoices" ORDER BY "id" ASC'


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_load_insert_delete_and_empty_insert(dialect: str) -> None:
    mark = _mark(dialect)
    loaded = load_one(dialect, "invoices", ("invoice_no", "notes"), "id", "invoice")
    assert loaded.text == 'SELECT "invoice_no", "notes" FROM "invoices" WHERE "id" = %s' % mark
    assert loaded.params_order == ("key",)
    assert loaded.caption == "Load one invoice"
    inserted = insert_row(dialect, "invoices", ("invoice_no", "customer_id"), "id")
    values = "VALUES (%s, %s)" % (mark, mark)
    text = 'INSERT INTO "invoices" ("invoice_no", "customer_id") %s' % values
    if dialect == "postgres":
        text += ' RETURNING "id"'
    assert inserted.text == text
    assert inserted.params_order == ("invoice_no", "customer_id")
    assert inserted.caption == "Insert invoice"
    empty = insert_row(dialect, "invoices", (), "id")
    empty_text = 'INSERT INTO "invoices" DEFAULT VALUES'
    if dialect == "postgres":
        empty_text += ' RETURNING "id"'
    assert empty.text == empty_text
    assert empty.params_order == ()
    removed = delete_row(dialect, "invoices", "id")
    assert removed.text == 'DELETE FROM "invoices" WHERE "id" = %s' % mark
    assert removed.params_order == ("key",)
    assert removed.caption == "Delete invoice"


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_update_changed_matches_the_joined_pieces(dialect: str) -> None:
    changed = ("notes",)
    conflict = ("invoice_no", "notes")
    statement = update_changed(dialect, "invoices", "id", changed, conflict, True)
    joined = update_head(dialect, "invoices") + " " + ", ".join(
        assignment_piece(dialect, column) for column in changed
    )
    joined += key_clause(dialect, "id")
    joined += "".join(" AND " + conflict_piece(dialect, column) for column in conflict)
    assert joined == statement.text
    mark = _mark(dialect)
    if dialect == "sqlite":
        assert statement.text == (
            'UPDATE "invoices" SET "notes" = ? WHERE "id" = ? AND "invoice_no" IS ? AND "notes" IS ?'
        )
    else:
        assert '"notes" IS NOT DISTINCT FROM %s' % mark in statement.text
    assert statement.params_order == ("notes", "key", "old:invoice_no", "old:notes")
    skipped = update_changed(dialect, "invoices", "id", (), conflict, True)
    assert skipped.text == ""
    assert skipped.params_order == ()
    assert skipped.caption == "Update invoice"
    quiet = update_changed(dialect, "invoices", "id", changed, conflict, False)
    assert "IS" not in quiet.text
    assert quiet.params_order == ("notes", "key")


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_find_uses_like_or_ilike_with_one_backslash(dialect: str) -> None:
    statement = find_keys(dialect, "invoices", "id", _ORDER, ("invoice_no", "notes"))
    mark = _mark(dialect)
    op = _like(dialect)
    escape = "$$\\$$" if dialect == "postgres" else "'\\'"
    assert statement.text == (
        "SELECT \"id\" FROM \"invoices\" WHERE (CAST(\"invoice_no\" AS TEXT) %s %s ESCAPE %s OR CAST(\"notes\" AS TEXT) %s %s ESCAPE %s)"
        % (op, mark, escape, op, mark, escape)
        + ' ORDER BY "invoice_date" DESC, "id" DESC'
    )
    assert statement.params_order == ("find:invoice_no", "find:notes")
    assert statement.caption == "Find invoice keys"
    assert statement.text.count("\\") == 2


@pytest.mark.logic("L-safe-sql")
def test_a_bad_name_is_not_quoted() -> None:
    assert is_identifier("invoice_no") is True
    assert is_identifier("a b") is False
    assert quote_ident("a b") == '"a b"'
    assert quote_ident("bad name") == '"bad name"'
    with pytest.raises(IdentifierError):
        quote_ident("a;b")
    assert select_keys("sqlite", "bad name", "id", ()).text.startswith('SELECT "id" FROM "bad name"')
    with pytest.raises(ValueError):
        select_keys("mysql", "invoices", "id", ())


@pytest.mark.logic("L-safe-sql")
def test_sqlite_statements_change_the_shop_rows(tmp_path) -> None:
    path = tmp_path / "shop.db"
    build(str(path))
    connection = sqlite3.connect(str(path))
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (2, 'INV-2', 1, '2026-02-01', '', '0')"
        )
        connection.execute(
            "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (3, 'INV-3', 1, '2026-03-01', '', '0')"
        )
        connection.execute(
            "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (4, '100%', 1, '2026-05-01', '', '0')"
        )
        connection.execute(
            "INSERT INTO invoices (id, invoice_no, customer_id, invoice_date, notes, total) VALUES (5, '100X', 1, '2026-05-02', '', '0')"
        )
        connection.commit()
        keys = select_keys("sqlite", "invoices", "id", _ORDER)
        found = [row[0] for row in connection.execute(keys.text)]
        assert found[:3] == [5, 4, 3]
        inserted = insert_row("sqlite", "invoices", ("invoice_no", "customer_id", "invoice_date", "notes"), "id")
        cursor = connection.execute(inserted.text, ("INV-SQL", 1, "2026-06-01", "hello"))
        new_id = cursor.lastrowid
        loaded = load_one(
            "sqlite",
            "invoices",
            ("invoice_no", "customer_id", "invoice_date", "notes", "total"),
            "id",
            "invoice",
        )
        row = connection.execute(loaded.text, (new_id,)).fetchone()
        assert row == ("INV-SQL", 1, "2026-06-01", "hello", None)
        changed = update_changed(
            "sqlite",
            "invoices",
            "id",
            ("notes",),
            ("invoice_no", "customer_id", "invoice_date", "notes"),
            True,
        )
        missed = connection.execute(changed.text, ("mine", new_id, "INV-SQL", 1, "2026-06-01", "nope"))
        assert missed.rowcount == 0
        assert connection.execute("SELECT notes, invoice_no, total FROM invoices WHERE id = ?", (new_id,)).fetchone() == (
            "hello",
            "INV-SQL",
            None,
        )
        hit = connection.execute(changed.text, ("mine", new_id, "INV-SQL", 1, "2026-06-01", "hello"))
        assert hit.rowcount == 1
        assert connection.execute(
            "SELECT invoice_no, customer_id, invoice_date, notes FROM invoices WHERE id = ?",
            (new_id,),
        ).fetchone() == ("INV-SQL", 1, "2026-06-01", "mine")
        pattern = "%" + "100%".replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        finder = find_keys("sqlite", "invoices", "id", _ORDER, ("invoice_no",))
        matches = [item[0] for item in connection.execute(finder.text, (pattern,))]
        assert matches == [4]
        removed = delete_row("sqlite", "invoices", "id")
        connection.execute(removed.text, (new_id,))
        connection.commit()
        assert connection.execute("SELECT id FROM invoices WHERE id = ?", (new_id,)).fetchone() is None
        assert connection.execute("SELECT invoice_no FROM invoices WHERE id = 3").fetchone() == ("INV-3",)
    finally:
        connection.close()
