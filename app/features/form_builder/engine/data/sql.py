"""Statement builders for SQLite and PostgreSQL 9.3 (CONTRACTS.md section 19.5).

This is the only place SQL text is made. Identifiers are double-quoted and must
match the name rule. Values stay parameters: ``?`` on SQLite, ``%s`` on
PostgreSQL. There is no upsert, no ``ON CONFLICT``, and no JSON.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence, Tuple

from app.features.form_builder.engine.data.source import singular

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DIALECTS = ("sqlite", "postgres")


class IdentifierError(ValueError):
    """``name`` is not a plain identifier, so it is not quoted."""


@dataclass(frozen=True)
class Statement:
    """One statement. ``params_order`` names the placeholders left to right."""

    text: str
    params_order: Tuple[str, ...]
    caption: str


def is_identifier(name: str) -> bool:
    """True when ``name`` matches ``^[A-Za-z_][A-Za-z0-9_]*$``."""

    return bool(_IDENT.match(name))


def quote_ident(name: str) -> str:
    """Double-quote ``name``. Raises ``IdentifierError`` instead of quoting a bad name."""

    if not is_identifier(name):
        raise IdentifierError(name)
    return '"%s"' % name


def placeholder(dialect: str) -> str:
    """``?`` for SQLite, ``%s`` for PostgreSQL."""

    _dialect(dialect)
    if dialect == "postgres":
        return "%s"
    return "?"


def update_head(dialect: str, table: str) -> str:
    """``UPDATE "table" SET`` with no trailing space."""

    _dialect(dialect)
    return "UPDATE %s SET" % quote_ident(table)


def assignment_piece(dialect: str, column: str) -> str:
    """``"column" = ?`` or ``"column" = %s``."""

    return "%s = %s" % (quote_ident(column), placeholder(dialect))


def key_clause(dialect: str, key: str) -> str:
    """Leading space included: `` WHERE "key" = ?``."""

    return " WHERE %s = %s" % (quote_ident(key), placeholder(dialect))


def conflict_piece(dialect: str, column: str) -> str:
    """``"column" IS ?`` or ``"column" IS NOT DISTINCT FROM %s``."""

    _dialect(dialect)
    if dialect == "postgres":
        return "%s IS NOT DISTINCT FROM %s" % (quote_ident(column), "%s")
    return "%s IS %s" % (quote_ident(column), "?")


def like_piece(dialect: str, column: str) -> str:
    """``CAST("column" AS TEXT) LIKE ? ESCAPE '\\'``, or ``ILIKE`` on PostgreSQL.

    The SQL text contains one backslash, which is the escape character.
    """

    op = "ILIKE" if _dialect(dialect) == "postgres" else "LIKE"
    # A date or number has no LIKE operator on PostgreSQL 9.3. Text does.
    # standard_conforming_strings is on, so a plain '\\' is two characters.
    # E'\\' is one backslash. SQLite keeps the ordinary string.
    one = "\\"
    escape = "E'%s%s'" % (one, one) if dialect == "postgres" else "'%s'" % one
    return "CAST(%s AS TEXT) %s %s ESCAPE %s" % (quote_ident(column), op, placeholder(dialect), escape)


def assign_sql(dialect: str, column: str) -> str:
    """Same text as ``assignment_piece``."""

    return assignment_piece(dialect, column)


def conflict_sql(dialect: str, column: str) -> str:
    """Same text as ``conflict_piece``."""

    return conflict_piece(dialect, column)


def select_keys(
    dialect: str,
    table: str,
    key: str,
    order: Sequence[Sequence[str]] = (),
) -> Statement:
    """Keys only, ordered by the source order, then the key as the last tie-break."""

    caption = "List %s keys" % singular(table)
    text = "SELECT %s FROM %s%s" % (quote_ident(key), quote_ident(table), _order_by(key, order))
    _dialect(dialect)
    return Statement(text, (), caption)


def load_one(
    dialect: str,
    table: str,
    columns: Sequence[str],
    key: str,
    caption_noun: str,
) -> Statement:
    """One row by key. An empty column list selects the key itself."""

    chosen = tuple(columns) if columns else (key,)
    body = ", ".join(quote_ident(column) for column in chosen)
    text = "SELECT %s FROM %s%s" % (body, quote_ident(table), key_clause(dialect, key))
    return Statement(text, ("key",), "Load one %s" % caption_noun)


def insert_row(dialect: str, table: str, columns: Sequence[str], key: str) -> Statement:
    """Insert. PostgreSQL appends ``RETURNING``. An empty column list is ``DEFAULT VALUES``."""

    _dialect(dialect)
    table_sql = quote_ident(table)
    if columns:
        names = ", ".join(quote_ident(column) for column in columns)
        marks = ", ".join(placeholder(dialect) for _column in columns)
        text = "INSERT INTO %s (%s) VALUES (%s)" % (table_sql, names, marks)
    else:
        text = "INSERT INTO %s DEFAULT VALUES" % table_sql
    if dialect == "postgres":
        text = "%s RETURNING %s" % (text, quote_ident(key))
    return Statement(text, tuple(columns), "Insert %s" % singular(table))


def update_changed(
    dialect: str,
    table: str,
    key: str,
    changed_columns: Sequence[str],
    conflict_columns: Sequence[str],
    check: bool,
) -> Statement:
    """SET the changed columns. The conflict predicate is added only when ``check`` is true.

    An empty change list is an empty statement so the caller skips the write.
    ``params_order`` is the changed columns, then ``"key"``, then ``"old:"+column``
    for each conflict column.
    """

    caption = "Update %s" % singular(table)
    if not changed_columns:
        return Statement("", (), caption)
    sets = ", ".join(assignment_piece(dialect, column) for column in changed_columns)
    text = update_head(dialect, table) + " " + sets + key_clause(dialect, key)
    params = tuple(changed_columns) + ("key",)
    if check:
        for column in conflict_columns:
            text += " AND " + conflict_piece(dialect, column)
        params = params + tuple("old:" + column for column in conflict_columns)
    return Statement(text, params, caption)


def delete_row(dialect: str, table: str, key: str) -> Statement:
    """Delete the row with this key."""

    text = "DELETE FROM %s%s" % (quote_ident(table), key_clause(dialect, key))
    return Statement(text, ("key",), "Delete %s" % singular(table))


def select_lines(
    dialect: str,
    table: str,
    columns: Sequence[str],
    link: str,
    order_by: str,
    key: str,
) -> Statement:
    """Child rows for one parent. Ordered by ``order_by`` when it is set, then the key."""

    _dialect(dialect)
    chosen = tuple(columns) if columns else (key,)
    body = ", ".join(quote_ident(column) for column in chosen)
    order = ((order_by, "asc"),) if order_by else ()
    text = "SELECT %s FROM %s WHERE %s = %s%s" % (
        body,
        quote_ident(table),
        quote_ident(link),
        placeholder(dialect),
        _order_by(key, order),
    )
    return Statement(text, ("link",), "Load %s lines" % singular(table))


def delete_lines_for_link(dialect: str, table: str, link: str) -> Statement:
    """Delete every child row for one parent. Used when the parent itself is deleted."""

    _dialect(dialect)
    text = "DELETE FROM %s WHERE %s = %s" % (quote_ident(table), quote_ident(link), placeholder(dialect))
    return Statement(text, ("link",), "Delete %s lines" % singular(table))


def set_line_position(dialect: str, table: str, position: str, key: str) -> Statement:
    """Write one line's position. The caller runs the negative pass first when it must."""

    _dialect(dialect)
    text = update_head(dialect, table) + " " + assignment_piece(dialect, position) + key_clause(dialect, key)
    return Statement(text, ("position", "key"), "Number %s" % singular(table))


def find_keys(
    dialect: str,
    table: str,
    key: str,
    order: Sequence[Sequence[str]],
    columns: Sequence[str],
) -> Statement:
    """``select_keys`` with ``WHERE (col LIKE ? ESCAPE '\\' OR ...)`` before ``ORDER BY``.

    The caller builds the pattern, including the backslash escapes. PostgreSQL
    uses ``ILIKE``. The clause is valid on PostgreSQL 9.3. ``AND`` cannot follow
    ``ORDER BY``, so the predicate is a ``WHERE``.
    """

    base = select_keys(dialect, table, key, order)
    if not columns:
        return Statement(base.text, (), "Find %s keys" % singular(table))
    pred = " OR ".join(like_piece(dialect, column) for column in columns)
    marker = " ORDER BY "
    if marker in base.text:
        head, tail = base.text.split(marker, 1)
        text = "%s WHERE (%s) ORDER BY %s" % (head, pred, tail)
    else:
        text = "%s WHERE (%s)" % (base.text, pred)
    return Statement(text, tuple("find:" + column for column in columns), "Find %s keys" % singular(table))


def _dialect(dialect: str) -> str:
    if dialect not in _DIALECTS:
        raise ValueError("dialect must be sqlite or postgres")
    return dialect


def select_lookup(
    dialect: str,
    table: str,
    key: str,
    show: str,
    also: Sequence[str] = (),
    order: str = "",
) -> Statement:
    """Key, shown column, and also columns, ordered by ``order`` or the shown column.

    The same columns are not repeated. There are no placeholders.
    """

    _dialect(dialect)
    columns = []
    for name in (key, show):
        if name not in columns:
            columns.append(name)
    for name in also:
        if name not in columns:
            columns.append(name)
    order_name = order or show
    text = "SELECT %s FROM %s ORDER BY %s" % (
        ", ".join(quote_ident(name) for name in columns),
        quote_ident(table),
        quote_ident(order_name),
    )
    return Statement(text, (), "Lookup %s" % singular(table))


def _direction(text: str) -> str:
    lowered = text.strip().lower()
    if lowered == "desc":
        return "DESC"
    if lowered == "asc":
        return "ASC"
    raise ValueError("order direction must be asc or desc")


def _order_by(key: str, order: Sequence[Sequence[str]]) -> str:
    parts = []
    last = "ASC"
    for item in order:
        if len(item) != 2:
            raise ValueError("an order entry is a column and a direction")
        column, direction = item[0], item[1]
        last = _direction(str(direction))
        parts.append("%s %s" % (quote_ident(str(column)), last))
    if not parts:
        last = "ASC"
    if not any(item[0] == key for item in order if len(item) == 2):
        parts.append("%s %s" % (quote_ident(key), last))
    return " ORDER BY " + ", ".join(parts)


__all__ = [
    "IdentifierError",
    "Statement",
    "assign_sql",
    "assignment_piece",
    "conflict_piece",
    "conflict_sql",
    "delete_row",
    "find_keys",
    "insert_row",
    "is_identifier",
    "key_clause",
    "like_piece",
    "load_one",
    "placeholder",
    "quote_ident",
    "select_keys",
    "select_lines",
    "select_lookup",
    "set_line_position",
    "update_changed",
    "update_head",
]
