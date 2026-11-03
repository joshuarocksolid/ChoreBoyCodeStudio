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
        "INTO",
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
    """Double-quote ``name``. A space stays inside the quotes. A break-out is refused."""

    if not name or any(mark in name for mark in ("\x00", "\n", "\r", ";", "--", "/*", "*/")):
        raise IdentifierError(name or "")
    if not is_identifier(name) and not all(ch == " " or ch.isalnum() or ch in "_-" for ch in name):
        raise IdentifierError(name)
    return '"%s"' % name.replace('"', '""')


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
    """The person's statement, ready to sit inside a subquery.

    One trailing ``;`` is removed when only comments and whitespace follow it.
    Percent signs stay as written. ``adapt_user_sql`` encodes them when a
    driver would otherwise consume them.
    """

    _dialect(dialect)
    return _strip_trailing_semicolon(sql.strip())


def select_subquery(sql: str) -> str:
    """``(sql) AS q`` with the statement on its own lines.

    A trailing ``--`` comment then stays inside the subquery.
    """

    return "(\n%s\n) AS q" % sql


def adapt_user_sql(_driver: str, _sql: str, _has_params: bool) -> str:
    """User SQL to embed in a statement ``_driver`` will execute.

    With no parameters both drivers send the text unchanged, so nothing is
    doubled. psycopg with parameters turns every ``%%`` into ``%``, including
    inside quotes, so every ``%`` is doubled. pg8000 turns ``%%`` into ``%``
    only outside quotes and comments, so only those are doubled.
    """

    if not _has_params or _driver not in ("psycopg", "pg8000"):
        return _sql
    if _driver == "psycopg":
        return _sql.replace("%", "%%")
    return _double_percent_outside(_sql)


def select_source_error(sql: str) -> Optional[str]:
    """The FB314 sentence when ``sql`` is not one read-only SELECT. ``None`` when it is.

    One statement, starting with SELECT or WITH. Subqueries are allowed.
    ``SELECT … INTO``, a row lock (``FOR UPDATE``, ``FOR SHARE``,
    ``FOR KEY SHARE``, ``FOR NO KEY UPDATE``), unbalanced parentheses, and a
    second statement are not.
    """

    sentence = "Only a single SELECT can be a list's source."
    words = _sql_words(sql)
    if not words:
        return sentence
    if ";" in words:
        if words.count(";") != 1 or words[-1] != ";":
            return sentence
        words = [word for word in words if word != ";"]
    significant = [word for word in words if word != "("]
    if not significant:
        return sentence
    upper = [word.upper() for word in significant]
    if upper[0] not in ("SELECT", "WITH"):
        return sentence
    if "SELECT" not in upper:
        return sentence
    if any(word in _BANNED_SQL for word in upper):
        return sentence
    if _has_row_lock(upper) or not _parens_balance(words):
        return sentence
    return None


@dataclass(frozen=True)
class ListRead:
    """The row statement and the matching count. Both bind ``params_order`` the same way."""

    rows: Statement
    total: Statement
    columns: Tuple[str, ...]
    key: str
    inner: str = ""
    count_tail: str = ""
    row_tail: str = ""
    plain_tail: str = ""


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
    inner = user_sql_for_wrap(dialect, user_sql) if user_sql.strip() else ""
    if inner:
        source_sql = select_subquery(inner)
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
    order_sql = _list_order(order, "" if inner else key)
    limit_sql = "" if limit is None else " LIMIT %d" % limit
    noun = singular(table) if table else "row"
    rows = "SELECT %s FROM %s%s%s%s" % (select_sql, source_sql, where, order_sql, limit_sql)
    total = "SELECT COUNT(*) FROM %s%s" % (source_sql, where)
    return ListRead(
        Statement(rows, params, "List %s" % noun),
        Statement(total, params, "Count %s" % noun),
        shown,
        key,
        inner,
        where,
        where + order_sql + limit_sql,
        order_sql + limit_sql,
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


PG8000_SCAN_SENTENCE = (
    "This SQL can't be searched with the pg8000 driver. "
    "Remove the quote or comment that confuses it."
)


def pg8000_scan_closed(sql: str) -> bool:
    """True when pg8000 would be outside quotes before a placeholder.

    The wrap writes a newline after the statement, and that newline ends a
    ``--`` comment. A quote or comment that is still open after that newline
    would swallow the search placeholders.
    """

    body = user_sql_for_wrap("postgres", sql)
    _text, closed = _pg8000_walk(body + "\n")
    return closed


def _double_percent_outside(_sql: str) -> str:
    """Double ``%`` that pg8000 would read as a placeholder."""

    text, _closed = _pg8000_walk(_sql)
    return text


def _pg8000_walk(_sql: str) -> Tuple[str, bool]:
    """pg8000 1.31.5 ``convert_paramstyle``, and whether it finished outside.

    No block-comment state, only untagged ``$$``, only an uppercase ``E'``.
    An escape string ends at a quote whose previous character is not a
    backslash. The body is copied into the generated form.
    """

    outside = 0
    inside_sq = 1
    inside_qi = 2
    inside_es = 3
    inside_co = 5
    inside_dq = 6
    in_quote_escape = False
    state = outside
    prev = None
    out = []
    length = len(_sql)
    for index, char in enumerate(_sql):
        nxt = _sql[index + 1] if index + 1 < length else None
        if state == outside:
            if char == "'":
                out.append(char)
                state = inside_es if prev == "E" else inside_sq
            elif char == '"':
                out.append(char)
                state = inside_qi
            elif char == "-":
                out.append(char)
                if prev == "-":
                    state = inside_co
            elif char == "$":
                out.append(char)
                if prev == "$":
                    state = inside_dq
            elif char == "%":
                out.append("%%")
            else:
                out.append(char)
        elif state == inside_sq:
            if char == "'":
                if in_quote_escape:
                    in_quote_escape = False
                elif nxt == "'":
                    in_quote_escape = True
                else:
                    state = outside
            out.append(char)
        elif state == inside_qi:
            if char == '"':
                state = outside
            out.append(char)
        elif state == inside_es:
            if char == "'" and prev != "\\":
                state = outside
            out.append(char)
        elif state == inside_dq:
            if char == "$" and prev == "$":
                state = outside
            out.append(char)
        elif state == inside_co:
            out.append(char)
            if char == "\n":
                state = outside
        prev = char
    return "".join(out), state == outside


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
        if char in ("E", "e") and nxt == "'" and not _ident_before(sql, index):
            flush()
            end = _end_escape_string(sql, index + 2)
            if end > length:
                return None
            index = end
            continue
        tag = _dollar_tag(sql, index)
        if tag is not None:
            flush()
            closer = "$%s$" % tag
            end = sql.find(closer, index + len(closer))
            if end < 0:
                return None
            index = end + len(closer)
            continue
        if char in ("'", '"'):
            flush()
            end = _end_quote(sql, index + 1, char)
            if end > length:
                return None
            index = end
            continue
        if char == ";":
            flush()
            found.append(";")
            index += 1
            continue
        if char == "(" or char == ")":
            flush()
            found.append(char)
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


def _ident_before(sql: str, index: int) -> bool:
    if index <= 0:
        return False
    prev = sql[index - 1]
    return prev.isalnum() or prev == "_"


def _dollar_tag(sql: str, index: int) -> Optional[str]:
    if index >= len(sql) or sql[index] != "$":
        return None
    cursor = index + 1
    while cursor < len(sql) and (sql[cursor].isalnum() or sql[cursor] == "_"):
        cursor += 1
    if cursor < len(sql) and sql[cursor] == "$":
        return sql[index + 1:cursor]
    return None


def _end_quote(sql: str, index: int, quote: str) -> int:
    length = len(sql)
    while index < length:
        if sql[index] == quote:
            if index + 1 < length and sql[index + 1] == quote:
                index += 2
                continue
            return index + 1
        index += 1
    return length + 1


def _end_escape_string(sql: str, index: int) -> int:
    length = len(sql)
    while index < length:
        if sql[index] == "\\":
            index += 2 if index + 1 < length else 1
            continue
        if sql[index] == "'":
            return index + 1
        index += 1
    return length + 1


def _strip_trailing_semicolon(sql: str) -> str:
    """Drop one ``;`` outside quotes when the rest is comments and whitespace."""

    cut = -1
    index = 0
    length = len(sql)
    while index < length:
        char = sql[index]
        nxt = sql[index + 1] if index + 1 < length else ""
        if char == "-" and nxt == "-":
            end = sql.find("\n", index + 2)
            index = length if end < 0 else end + 1
            continue
        if char == "/" and nxt == "*":
            end = sql.find("*/", index + 2)
            if end < 0:
                return sql
            index = end + 2
            continue
        if char in ("E", "e") and nxt == "'" and not _ident_before(sql, index):
            end = _end_escape_string(sql, index + 2)
            if end > length:
                return sql
            index = end
            continue
        tag = _dollar_tag(sql, index)
        if tag is not None:
            closer = "$%s$" % tag
            end = sql.find(closer, index + len(closer))
            if end < 0:
                return sql
            index = end + len(closer)
            continue
        if char in ("'", '"'):
            end = _end_quote(sql, index + 1, char)
            if end > length:
                return sql
            index = end
            continue
        if char == ";":
            cut = index
            index += 1
            continue
        if char.isspace():
            index += 1
            continue
        cut = -1
        index += 1
    if cut < 0:
        return sql
    return sql[:cut].rstrip()


def _has_row_lock(upper: Sequence[str]) -> bool:
    index = 0
    size = len(upper)
    while index < size:
        if upper[index] == "FOR" and _lock_tail(upper, index + 1):
            return True
        index += 1
    return False


def _lock_tail(upper: Sequence[str], index: int) -> bool:
    size = len(upper)
    if index >= size:
        return False
    word = upper[index]
    if word in ("UPDATE", "SHARE"):
        return True
    if word == "KEY" and index + 1 < size and upper[index + 1] == "SHARE":
        return True
    if word == "NO" and index + 2 < size and upper[index + 1] == "KEY" and upper[index + 2] == "UPDATE":
        return True
    return False


def _parens_balance(words: Sequence[str]) -> bool:
    depth = 0
    for word in words:
        if word == "(":
            depth += 1
        elif word == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


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
    "adapt_user_sql",
    "like_pattern",
    "like_piece",
    "list_read",
    "load_one",
    "PG8000_SCAN_SENTENCE",
    "pg8000_scan_closed",
    "placeholder",
    "quote_ident",
    "select_keys",
    "select_lines",
    "select_lookup",
    "select_source_error",
    "select_subquery",
    "set_line_position",
    "update_changed",
    "update_head",
    "user_sql_for_wrap",
]
