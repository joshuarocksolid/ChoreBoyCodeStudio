"""Schema cache model (CONTRACTS.md section 19.6).

M8.0s owns the model, the canonical read and write, and the staleness rule.
``schema_for`` calls the installed reader on every lookup. That reader caches
on the document object, never on ``id(doc)``, and re-reads when the file changes.
``set_schema_reader(None)`` restores the reader that returns None.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from app.features.form_builder.engine.logic.codec import JsonObject, parse_json, write_json

STALE_AFTER = datetime.timedelta(days=7)
#: Stored row count when the capped probe hits its limit. It means more than 100000.
ROW_PROBE_LIMIT = 100001

Reader = Callable[[object, str], Optional["Schema"]]

_READER: Reader = lambda _doc, _name: None


@dataclass(frozen=True)
class Reference:
    table: str
    column: str


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    nullable: bool
    default: Optional[str] = None
    unique: bool = False
    references: Optional[Reference] = None


@dataclass(frozen=True)
class Table:
    name: str
    columns: Tuple[Column, ...]
    key: Optional[str] = None
    triggers: bool = False
    rows: Optional[int] = None
    without_rowid: bool = False


@dataclass(frozen=True)
class Schema:
    connection: str
    engine: str
    server: str
    read_at: str
    driver: str
    tables: Tuple[Table, ...]
    version: int = 1


def set_schema_reader(reader: Optional[Reader]) -> None:
    """Install the cache reader. ``None`` restores the M8.0s reader, which returns None."""

    global _READER
    _READER = reader if reader is not None else (lambda _doc, _name: None)


def schema_for(doc: object, connection: str) -> Optional[Schema]:
    """The schema for ``connection``. The installed reader owns the cache."""

    return _READER(doc, connection)


def is_stale(schema: Schema, now: datetime.datetime) -> bool:
    """True after 7 days. A missing cache is not stale. It is absent (FB309)."""

    try:
        read_at = datetime.datetime.fromisoformat(schema.read_at)
    except ValueError:
        return True
    return now - read_at > STALE_AFTER


def read_schema(text: str) -> Tuple[Optional[Schema], Optional[str]]:
    parsed = parse_json(text)
    if parsed.error is not None:
        return None, parsed.error[1]
    if not isinstance(parsed.value, JsonObject):
        return None, "expected an object"
    obj = parsed.value
    tables = obj.get("tables")
    if not isinstance(tables, tuple):
        return None, "expected tables"
    found = []
    for item in tables:
        if not isinstance(item, JsonObject):
            return None, "a table must be an object"
        table, error = _table(item)
        if error is not None or table is None:
            return None, error or "a table can't be read"
        found.append(table)
    connection = obj.get("connection")
    engine = obj.get("engine")
    server = obj.get("server")
    read_at = obj.get("readAt")
    driver = obj.get("driver")
    if not all(isinstance(item, str) for item in (connection, engine, server, read_at, driver)):
        return None, "the cache header is incomplete"
    version = obj.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        version = 1
    return (
        Schema(
            str(connection),
            str(engine),
            str(server),
            str(read_at),
            str(driver),
            tuple(found),
            int(version),
        ),
        None,
    )


def write_schema(schema: Schema) -> str:
    tables = tuple(_table_object(table) for table in schema.tables)
    return write_json(
        JsonObject(
            (
                ("version", schema.version),
                ("connection", schema.connection),
                ("engine", schema.engine),
                ("server", schema.server),
                ("readAt", schema.read_at),
                ("driver", schema.driver),
                ("tables", tables),
            )
        )
    )


def _table(obj: JsonObject) -> Tuple[Optional[Table], Optional[str]]:
    name = obj.get("name")
    columns = obj.get("columns")
    if not isinstance(name, str) or not isinstance(columns, tuple):
        return None, "a table needs a name and columns"
    found = []
    for item in columns:
        if not isinstance(item, JsonObject):
            return None, "a column must be an object"
        column, error = _column(item)
        if error is not None or column is None:
            return None, error or "a column can't be read"
        found.append(column)
    key = obj.get("key")
    rows = obj.get("rows")
    if rows is not None and (isinstance(rows, bool) or not isinstance(rows, int)):
        return None, "rows must be a whole number"
    return (
        Table(
            name,
            tuple(found),
            key if isinstance(key, str) else None,
            obj.get("triggers") is True,
            None if rows is None else int(rows),
            obj.get("withoutRowid") is True,
        ),
        None,
    )


def _table_object(table: Table) -> JsonObject:
    pairs: list = [("name", table.name)]
    if table.key:
        pairs.append(("key", table.key))
    pairs.append(("triggers", table.triggers))
    if table.rows is not None:
        pairs.append(("rows", table.rows))
    if table.without_rowid:
        pairs.append(("withoutRowid", True))
    pairs.append(("columns", tuple(_column_object(column) for column in table.columns)))
    return JsonObject(tuple(pairs))


def _column(obj: JsonObject) -> Tuple[Optional[Column], Optional[str]]:
    name = obj.get("name")
    type_name = obj.get("type")
    if not isinstance(name, str) or not isinstance(type_name, str):
        return None, "a column needs a name and a type"
    default = obj.get("default")
    reference = obj.get("references")
    ref: Optional[Reference] = None
    if isinstance(reference, JsonObject):
        ref_table = reference.get("table")
        ref_column = reference.get("column")
        if isinstance(ref_table, str) and isinstance(ref_column, str):
            ref = Reference(ref_table, ref_column)
    return (
        Column(
            name,
            type_name,
            obj.get("nullable") is not False,
            default if isinstance(default, str) else None,
            obj.get("unique") is True,
            ref,
        ),
        None,
    )


def _column_object(column: Column) -> JsonObject:
    pairs: list = [
        ("name", column.name),
        ("type", column.type),
        ("nullable", column.nullable),
    ]
    if column.default is not None:
        pairs.append(("default", column.default))
    if column.unique:
        pairs.append(("unique", True))
    if column.references is not None:
        pairs.append(
            (
                "references",
                JsonObject((("table", column.references.table), ("column", column.references.column))),
            )
        )
    return JsonObject(tuple(pairs))


__all__ = [
    "ROW_PROBE_LIMIT",
    "Column",
    "Reference",
    "Schema",
    "Table",
    "is_stale",
    "read_schema",
    "schema_for",
    "set_schema_reader",
    "write_schema",
]
