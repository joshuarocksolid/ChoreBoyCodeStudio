"""Statement builders for SQLite and PostgreSQL 9.3 (CONTRACTS.md section 19.5).

This is the only place SQL text is made. Identifiers are double-quoted and must
match the name rule. Values stay parameters: ``?`` on SQLite, ``%s`` on
PostgreSQL. There is no upsert, no ``ON CONFLICT``, and no JSON.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.data.source import singular

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DIALECTS = ("sqlite", "postgres")
_BANNED_SQL = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "WITH",
        "UNION",
        "INTERSECT",
        "EXCEPT",
        "PRAGMA",
        "ATTACH",
        "DETACH",
        "COPY",
        "GRANT",
        "REVOKE",
        "VACUUM",
        "TRUNCATE",
        "CALL",
        "EXECUTE",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "REPLACE",
    }
)


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

def like_pattern(text: str) -> str:
    """Contains-search value. ``\\``, ``%`` and ``_`` are escaped, then wrapped in ``%``.

    The generated form repeats this escape. ``like_piece`` only writes the SQL.
    """

    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + escaped + "%"


def user_sql_for_wrap(dialect: str, sql: str) -> str:
    """The person's statement, ready to sit inside ``SELECT * FROM ( ... ) AS q``.

    PostgreSQL drivers treat ``%`` as a placeholder, so each one is doubled.
    SQLite keeps the text as written.
    """

    _dialect(dialect)
    body = sql.strip()
    if dialect == "postgres":
        return body.replace("%", "%%")
    return body


def select_source_error(sql: str) -> Optional[str]:
    """The FB314 sentence when ``sql`` is not one SELECT. ``None`` when it is."""

    sentence = "Only a single SELECT can be a list's source."
    words = _sql_words(sql)
    if not words:
        return sentence
    significant = [word for word in words if word != "("]
    if not significant or significant[0].upper() != "SELECT":
        return sentence
    if any(word == ";" for word in words):
        return sentence
    if sum(1 for word in significant if word.upper() == "SELECT") != 1:
        return sentence
    if any(word.upper() in _BANNED_SQL for word in significant):
        return sentence
    return None


@dataclass(frozen=True)
class ListRead:
    """The row statement and the matching count. Both bind ``params_order`` the same way."""

    rows: Statement
    total: Statement
    columns: Tuple[str, ...]
    key: str


def list_read(
    dialect: str,
    table: str,
    columns: Sequence[str],
    user_sql: str,
    search: Sequence[str],
    filters: Sequence[str],
    order: Sequence[Sequence[str]],
    limit: Optional[int],
    key: str = "",
) -> ListRead:
    """One page of a list, and the count of rows that match before the limit.

    A non-empty ``user_sql`` is wrapped. Search and filters are parameters.
    An empty search, or a blank filter, matches every row, including NULL.
    """

    _dialect(dialect)
    if isinstance(limit, bool) or (limit is not None and (not isinstance(limit, int) or limit < 0)):
        raise ValueError("limit must be a whole number")
    shown = tuple(columns)
    for name in shown:
        quote_ident(name)
    for name in tuple(search) + tuple(filters):
        quote_ident(name)
    if key:
        quote_ident(key)
    inner = user_sql.strip()
    if inner:
        source_sql = "(%s) AS q" % user_sql_for_wrap(dialect, inner)
        select_sql = "*"
    else:
        if not table:
            raise ValueError("a list needs a table or a select")
        fetched = list(shown)
        if key and key not in fetched:
            fetched.append(key)
        if not fetched:
            raise ValueError("a list needs a column")
        source_sql = quote_ident(table)
        select_sql = ", ".join(quote_ident(name) for name in fetched)
    where, params = _list_where(dialect, search, filters)
    order_key = key if key and (not inner or key in shown) else ""
    order_sql = _list_order(order, order_key)
    limit_sql = "" if limit is None else " LIMIT %d" % limit
    noun = singular(table) if table else "row"
    rows = "SELECT %s FROM %s%s%s%s" % (select_sql, source_sql, where, order_sql, limit_sql)
    total = "SELECT COUNT(*) FROM %s%s" % (source_sql, where)
    return ListRead(
        Statement(rows, params, "List %s" % noun),
        Statement(total, params, "Count %s" % noun),
        shown,
        key,
    )


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


def _list_where(dialect: str, search: Sequence[str], filters: Sequence[str]) -> Tuple[str, Tuple[str, ...]]:
    parts: List[str] = []
    params: List[str] = []
    if search:
        likes = " OR ".join(_list_like(dialect, column) for column in search)
        parts.append("(%s OR %s = 1)" % (likes, placeholder(dialect)))
        params.extend(["search"] * len(tuple(search)))
        params.append("search_any")
    for column in filters:
        quoted = quote_ident(column)
        mark = placeholder(dialect)
        parts.append("(%s = %s OR %s = 1)" % (quoted, mark, mark))
        params.append("filter:" + column)
        params.append("filter_any:" + column)
    if not parts:
        return "", tuple(params)
    return " WHERE " + " AND ".join(parts), tuple(params)


def _list_like(dialect: str, column: str) -> str:
    """``like_piece`` for a list. PostgreSQL's escape is a dollar quote.

    ``E'\\'`` does not end for pg8000's placeholder scan, so a ``%s`` written
    after it stays in the statement. ``$$\\$$`` is one backslash on PostgreSQL
    9.3, and the scan leaves the quote. SQLite keeps ``like_piece``.
    """

    if _dialect(dialect) != "postgres":
        return like_piece(dialect, column)
    return "CAST(%s AS TEXT) ILIKE %s ESCAPE $$\\$$" % (quote_ident(column), placeholder(dialect))


def _list_order(order: Sequence[Sequence[str]], key: str) -> str:
    parts = []
    seen = []
    for item in order:
        if len(item) != 2:
            raise ValueError("an order entry is a column and a direction")
        column = str(item[0])
        parts.append("%s %s" % (quote_ident(column), _direction(str(item[1]))))
        seen.append(column)
    if key and key not in seen:
        parts.append("%s ASC" % quote_ident(key))
    if not parts:
        return ""
    return " ORDER BY " + ", ".join(parts)


def _sql_words(sql: str) -> Optional[List[str]]:
    """Words outside quotes and comments. ``None`` when a quote or comment is unfinished."""

    if not sql or not sql.strip():
        return []
    found: List[str] = []
    word: List[str] = []
    index = 0
    length = len(sql)

    def flush() -> None:
        if word:
            found.append("".join(word))
            del word[:]

    while index < length:
        char = sql[index]
        nxt = sql[index + 1] if index + 1 < length else ""
        if char == "-" and nxt == "-":
            flush()
            index = sql.find("\n", index + 2)
            if index < 0:
                return found
            continue
        if char == "/" and nxt == "*":
            flush()
            end = sql.find("*/", index + 2)
            if end < 0:
                return None
            index = end + 2
            continue
        if char in ("'", '"'):
            flush()
            index += 1
            closed = False
            while index < length:
                if sql[index] == char:
                    if index + 1 < length and sql[index + 1] == char:
                        index += 2
                        continue
                    index += 1
                    closed = True
                    break
                index += 1
            if not closed:
                return None
            continue
        if char == ";":
            flush()
            found.append(";")
            index += 1
            continue
        if char == "(":
            flush()
            found.append("(")
            index += 1
            continue
        if char.isalnum() or char == "_":
            word.append(char)
            index += 1
            continue
        flush()
        index += 1
    flush()
    return found


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
    "ListRead",
    "like_pattern",
    "like_piece",
    "list_read",
    "load_one",
    "placeholder",
    "quote_ident",
    "select_keys",
    "select_lines",
    "select_lookup",
    "select_source_error",
    "set_line_position",
    "update_changed",
    "update_head",
    "user_sql_for_wrap",
]
