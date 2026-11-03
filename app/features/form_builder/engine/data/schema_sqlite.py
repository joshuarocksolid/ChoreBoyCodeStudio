"""Read a SQLite file into a schema cache. Read-only. No writes."""

from __future__ import annotations

import sqlite3
import urllib.parse
from typing import Dict, List, Sequence

from app.features.form_builder.engine.data.schema import (
    ROW_PROBE_LIMIT,
    Column,
    Reference,
    Schema,
    Table,
)


def read_sqlite_file(path: str, connection_name: str, *, read_at: str) -> Schema:
    """Tables, columns, and a capped row count. ``path`` may contain spaces or ``?``."""

    uri = "file:%s?mode=ro" % urllib.parse.quote(path)
    connection = sqlite3.connect(uri, uri=True)
    try:
        return _read(connection, connection_name, read_at)
    finally:
        connection.close()


def _read(connection: sqlite3.Connection, connection_name: str, read_at: str) -> Schema:
    version = connection.execute("SELECT sqlite_version()").fetchone()
    server = "" if version is None or version[0] is None else str(version[0])
    names = [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    triggered = {
        str(row[0])
        for row in connection.execute("SELECT tbl_name FROM sqlite_master WHERE type = 'trigger'")
        if row and row[0]
    }
    tables = tuple(_table(connection, name, name in triggered) for name in names)
    return Schema(connection_name, "sqlite", server, read_at, "sqlite3", tables)


def _table(connection: sqlite3.Connection, name: str, triggers: bool) -> Table:
    info = _pragma(connection, "table_info", name)
    pk = [str(row["name"]) for row in info if row.get("pk")]
    key = pk[0] if len(pk) == 1 else None
    unique = _unique_columns(connection, name)
    if key is not None:
        unique.add(key)
    references = _references(connection, name)
    columns = []
    for row in info:
        column = str(row.get("name") or "")
        declared = row.get("type")
        type_name = declared.lower() if isinstance(declared, str) else ""
        default = row.get("dflt_value")
        columns.append(
            Column(
                column,
                type_name,
                not row.get("notnull"),
                None if default is None else str(default),
                column in unique,
                references.get(column),
            )
        )
    return Table(
        name,
        tuple(columns),
        key,
        triggers,
        _rows(connection, name),
        _without_rowid(connection, name),
    )


def _unique_columns(connection: sqlite3.Connection, table: str) -> set:
    found = set()
    for index in _pragma(connection, "index_list", table):
        if not index.get("unique"):
            continue
        info = _pragma(connection, "index_info", str(index.get("name") or ""))
        names = [str(row["name"]) for row in info if row.get("name")]
        if len(names) == 1:
            found.add(names[0])
    return found


def _references(connection: sqlite3.Connection, table: str) -> Dict[str, Reference]:
    grouped: Dict[object, List[dict]] = {}
    for row in _pragma(connection, "foreign_key_list", table):
        grouped.setdefault(row.get("id"), []).append(row)
    found: Dict[str, Reference] = {}
    for rows in grouped.values():
        if len(rows) != 1:
            continue
        row = rows[0]
        column = row.get("from")
        target = row.get("table")
        target_column = row.get("to")
        if isinstance(column, str) and isinstance(target, str) and isinstance(target_column, str):
            found[column] = Reference(target, target_column)
    return found


def _rows(connection: sqlite3.Connection, table: str) -> int:
    quoted = _ident(table)
    row = connection.execute(
        "SELECT count(*) FROM (SELECT 1 FROM %s LIMIT %d) AS c" % (quoted, ROW_PROBE_LIMIT)
    ).fetchone()
    count = int(row[0]) if row and row[0] is not None else 0
    if count >= ROW_PROBE_LIMIT:
        return ROW_PROBE_LIMIT
    return count


def _pragma(connection: sqlite3.Connection, name: str, argument: str) -> Sequence[dict]:
    cursor = connection.execute("PRAGMA %s(%s)" % (name, _ident(argument)))
    description = cursor.description or ()
    keys = [str(item[0]) for item in description]
    return [dict(zip(keys, row)) for row in cursor.fetchall()]


def _without_rowid(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    text = "" if row is None or row[0] is None else str(row[0]).upper()
    return "WITHOUT ROWID" in text


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


__all__ = ["read_sqlite_file"]
