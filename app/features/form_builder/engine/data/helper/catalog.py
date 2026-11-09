"""PostgreSQL catalog reads. A DB-API connection in, a schema out. No driver import.

The SQL is valid on PostgreSQL 9.3. ``pg_catalog`` only.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.data.schema import (
    ROW_PROBE_LIMIT,
    Column,
    Reference,
    Schema,
    Table,
)


def server_version(connection: object) -> str:
    row = _one(connection, "SELECT current_setting('server_version')")
    text = "" if row is None or row[0] is None else str(row[0])
    return "PostgreSQL " + text


def table_count(connection: object, schema_name: str) -> int:
    row = _one(
        connection,
        "SELECT count(*) FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relkind = 'r'",
        (schema_name,),
    )
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def read_postgres(
    connection: object,
    name: str,
    read_at: str,
    server: str,
    driver: str,
    schema_name: str,
) -> Schema:
    rows = _all(
        connection,
        "SELECT c.oid, c.relname, c.reltuples "
        "FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relkind = 'r' "
        "ORDER BY c.relname",
        (schema_name,),
    )
    tables = tuple(_table(connection, row) for row in rows)
    return Schema(name, "postgres", server, read_at, driver, tables)


def probe_postgres(connection: object, sql: str) -> Tuple[Tuple[str, str], ...]:
    """``BEGIN``, read-only, the shared subquery wrap, ``LIMIT 0``, then rollback."""

    cursor = _cursor(connection)
    try:
        cursor.execute("BEGIN")
        cursor.execute("SET TRANSACTION READ ONLY")
        from app.features.form_builder.engine.data.sql import select_subquery, user_sql_for_wrap

        cursor.execute(
            "SELECT * FROM %s LIMIT 0" % select_subquery(user_sql_for_wrap("postgres", sql))
        )
        description = list(cursor.description or ())
        found = []
        for column in description:
            found.append((str(column[0]), _type_name(connection, column[1])))
        return tuple(found)
    finally:
        rollback = getattr(connection, "rollback", None)
        if callable(rollback):
            try:
                rollback()
            except Exception:
                pass
        _close(cursor)


def _table(connection: object, row: Sequence[object]) -> Table:
    oid = row[0]
    name = str(row[1])
    reltuples = _float(row[2])
    columns_raw = _all(
        connection,
        "SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull, "
        "pg_catalog.pg_get_expr(d.adbin, d.adrelid) "
        "FROM pg_catalog.pg_attribute a "
        "LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
        "WHERE a.attrelid = %s AND a.attnum > 0 AND NOT a.attisdropped "
        "ORDER BY a.attnum",
        (oid,),
    )
    key = _one_name(
        connection,
        "SELECT a.attname FROM pg_catalog.pg_index i "
        "JOIN pg_catalog.pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0] "
        "WHERE i.indrelid = %s AND i.indisprimary AND i.indnatts = 1",
        (oid,),
    )
    unique = set(
        _names(
            connection,
            "SELECT a.attname FROM pg_catalog.pg_index i "
            "JOIN pg_catalog.pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0] "
            "WHERE i.indrelid = %s AND i.indisunique AND i.indnatts = 1",
            (oid,),
        )
    )
    if key:
        unique.add(key)
    references = _references(connection, oid)
    columns: List[Column] = []
    for item in columns_raw:
        column = str(item[0])
        declared = item[1]
        type_name = declared.lower() if isinstance(declared, str) else ""
        default = item[3]
        columns.append(
            Column(
                column,
                type_name,
                not bool(item[2]),
                None if default is None else str(default),
                column in unique,
                references.get(column),
            )
        )
    trigger = _one(
        connection,
        "SELECT 1 FROM pg_catalog.pg_trigger WHERE tgrelid = %s AND NOT tgisinternal LIMIT 1",
        (oid,),
    )
    return Table(
        name,
        tuple(columns),
        key or None,
        trigger is not None,
        _rows(connection, name, reltuples),
        False,
        _composite_unique(connection, oid),
    )


def _composite_unique(connection: object, oid: object) -> Tuple[Tuple[str, ...], ...]:
    rows = _all(
        connection,
        "SELECT i.indexrelid, a.attname FROM pg_catalog.pg_index i "
        "JOIN LATERAL generate_series(0, i.indnatts - 1) AS k(ord) ON true "
        "JOIN pg_catalog.pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[k.ord] "
        "WHERE i.indrelid = %s AND i.indisunique AND i.indnatts > 1 "
        "ORDER BY i.indexrelid, k.ord",
        (oid,),
    )
    grouped: Dict[object, List[str]] = {}
    order: List[object] = []
    for row in rows:
        if len(row) < 2 or row[1] is None:
            continue
        if row[0] not in grouped:
            order.append(row[0])
            grouped[row[0]] = []
        grouped[row[0]].append(str(row[1]))
    return tuple(tuple(grouped[key]) for key in order if len(grouped[key]) > 1)


def _references(connection: object, oid: object) -> Dict[str, Reference]:
    rows = _all(
        connection,
        "SELECT src.attname, refcls.relname, dst.attname "
        "FROM pg_catalog.pg_constraint con "
        "JOIN pg_catalog.pg_class refcls ON refcls.oid = con.confrelid "
        "JOIN pg_catalog.pg_attribute src "
        "ON src.attrelid = con.conrelid AND src.attnum = con.conkey[1] "
        "JOIN pg_catalog.pg_attribute dst "
        "ON dst.attrelid = con.confrelid AND dst.attnum = con.confkey[1] "
        "WHERE con.conrelid = %s AND con.contype = 'f' "
        "AND pg_catalog.array_length(con.conkey, 1) = 1",
        (oid,),
    )
    found: Dict[str, Reference] = {}
    for column, table, target in rows:
        if isinstance(column, str) and isinstance(table, str) and isinstance(target, str):
            found[column] = Reference(table, target)
    return found


def _rows(connection: object, table: str, reltuples: float) -> int:
    if reltuples > 0:
        estimated = int(round(reltuples))
        if estimated >= ROW_PROBE_LIMIT:
            return ROW_PROBE_LIMIT
        return estimated
    quoted = '"' + table.replace('"', '""') + '"'
    row = _one(
        connection,
        "SELECT count(*) FROM (SELECT 1 FROM %s LIMIT %d) AS c" % (quoted, ROW_PROBE_LIMIT),
    )
    count = int(row[0]) if row and row[0] is not None else 0
    if count >= ROW_PROBE_LIMIT:
        return ROW_PROBE_LIMIT
    return count


def _type_name(connection: object, type_code: object) -> str:
    if isinstance(type_code, bool) or not isinstance(type_code, int):
        return "" if type_code is None else str(type_code)
    row = _one(connection, "SELECT typname FROM pg_catalog.pg_type WHERE oid = %s", (type_code,))
    if row is None or row[0] is None:
        return str(type_code)
    return str(row[0])


def _one_name(connection: object, sql: str, params: Tuple[object, ...]) -> str:
    names = _names(connection, sql, params)
    return names[0] if len(names) == 1 else ""


def _names(connection: object, sql: str, params: Tuple[object, ...]) -> Tuple[str, ...]:
    return tuple(str(row[0]) for row in _all(connection, sql, params) if row and row[0] is not None)


def _one(connection: object, sql: str, params: Optional[Tuple[object, ...]] = None) -> Optional[Sequence[object]]:
    rows = _all(connection, sql, params)
    return rows[0] if rows else None


def _all(connection: object, sql: str, params: Optional[Tuple[object, ...]] = None) -> Tuple[Sequence[object], ...]:
    cursor = _cursor(connection)
    try:
        if params is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, params)
        return tuple(cursor.fetchall())
    finally:
        _close(cursor)


def _cursor(connection: object) -> object:
    factory = getattr(connection, "cursor", None)
    if not callable(factory):
        raise TypeError("the connection has no cursor")
    return factory()


def _close(cursor: object) -> None:
    close = getattr(cursor, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            return


def _float(value: object) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
