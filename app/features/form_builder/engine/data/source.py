"""Typed codecs for the five data properties (LOGIC_DESIGN section 6.2 and 6.3, CONTRACTS section 19.12).

Canonical JSON is the logic codec's writer: known keys in schema order, defaults
omitted, unknown keys after the known ones in the order they were read.
A list's ``query`` is read as ``sql`` and written as ``sql``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.logic.codec import (
    JsonObject,
    JsonValue,
    Pairs,
    parse_json,
    write_json,
)
from app.features.form_builder.engine.ui4.values import StringValue

HOOK_KEYS: Tuple[str, ...] = (
    "afterLoad",
    "beforeSave",
    "afterSave",
    "beforeDelete",
    "afterDelete",
    "newRecord",
    "connection",
)
_RECORD_KEYS = (
    "connection",
    "table",
    "recordWord",
    "key",
    "order",
    "openAt",
    "conflicts",
    "allowOverwrite",
    "deleteLines",
    "search",
    "hooks",
)
_LIST_KEYS = (
    "mode",
    "connection",
    "table",
    "sql",
    "columns",
    "search",
    "searchField",
    "filters",
    "order",
    "limit",
    "open",
)
_LOOKUP_KEYS = ("table", "key", "show", "order", "also", "blank")
_ROWS_KEYS = ("table", "link", "key", "order", "position", "columns")


@dataclass(frozen=True)
class Hooks:
    after_load: str = ""
    before_save: str = ""
    after_save: str = ""
    before_delete: str = ""
    after_delete: str = ""
    new_record: str = ""
    connection: str = ""
    unknown: Pairs = ()


@dataclass(frozen=True)
class RecordSource:
    connection: str
    table: str
    key: str
    record_word: Optional[str] = None
    order: Optional[Tuple[Tuple[str, str], ...]] = None
    open_at: Optional[str] = None
    conflicts: Optional[str] = None
    allow_overwrite: bool = False
    delete_lines: Optional[bool] = None
    search: Tuple[str, ...] = ()
    hooks: Optional[Hooks] = None
    unknown: Pairs = ()


@dataclass(frozen=True)
class ListFilter:
    field: str
    column: str
    unknown: Pairs = ()


@dataclass(frozen=True)
class ListOpen:
    form: str
    key: str
    unknown: Pairs = ()


@dataclass(frozen=True)
class ListSource:
    connection: str
    columns: Tuple[str, ...]
    table: str = ""
    sql: str = ""
    search: Tuple[str, ...] = ()
    search_field: str = ""
    filters: Tuple[ListFilter, ...] = ()
    order: Tuple[Tuple[str, str], ...] = ()
    limit: Optional[int] = None
    open: Optional[ListOpen] = None
    unknown: Pairs = ()


@dataclass(frozen=True)
class Lookup:
    table: str
    key: str
    show: str
    order: str = ""
    also: Tuple[str, ...] = ()
    blank: str = ""
    unknown: Pairs = ()


@dataclass(frozen=True)
class DataColumn:
    column: str
    header: str = ""
    kind: str = ""
    lookup: Optional[Lookup] = None
    default: str = ""
    read_only: bool = False
    validate: Tuple[JsonValue, ...] = ()
    unknown: Pairs = ()


@dataclass(frozen=True)
class CalcColumn:
    name: str
    formula: str
    header: str = ""
    kind: str = ""
    unknown: Pairs = ()


ColumnSpec = Union[DataColumn, CalcColumn]


@dataclass(frozen=True)
class Rows:
    table: str
    link: str
    key: str
    columns: Tuple[ColumnSpec, ...]
    order: str = ""
    position: str = ""
    unknown: Pairs = ()


@dataclass(frozen=True)
class Bind:
    column: str


@dataclass(frozen=True)
class BindMode:
    read_only: bool


Source = Union[RecordSource, ListSource]


@dataclass(frozen=True)
class DataRead:
    value: Optional[Source]
    error: Optional[str] = None


def singular(table: str) -> str:
    """The default record word. Any other plural is stored by hand (CONTRACTS section 19.12)."""

    if table.endswith("ies"):
        return table[:-3] + "y"
    if table.endswith("sses"):
        return table[:-2]
    if table.endswith("xes"):
        return table[:-2]
    if table.endswith("s") and not table.endswith("ss"):
        return table[:-1]
    return table


def read_data(text: str) -> DataRead:
    """``cbcsData``. Never raises. ``query`` is accepted as ``sql``."""

    parsed = parse_json(text)
    if parsed.error is not None:
        return DataRead(None, parsed.error[1])
    if not isinstance(parsed.value, JsonObject):
        return DataRead(None, "expected an object")
    if parsed.value.get("mode") == "list":
        return _read_list(parsed.value)
    return _read_record(parsed.value)


def write_data(value: Source) -> str:
    if isinstance(value, ListSource):
        return write_json(_list_object(value))
    return write_json(_record_object(value))


def read_bind(text: str) -> Bind:
    return Bind(text)


def write_bind(value: Bind) -> str:
    return value.column


def read_bind_mode(text: str) -> BindMode:
    return BindMode(text.strip() == "readOnly")


def write_bind_mode(value: BindMode) -> str:
    return "readOnly" if value.read_only else ""


def read_lookup(text: str) -> Tuple[Optional[Lookup], Optional[str]]:
    parsed = parse_json(text)
    if parsed.error is not None:
        return None, parsed.error[1]
    if not isinstance(parsed.value, JsonObject):
        return None, "expected an object"
    return _lookup(parsed.value)


def write_lookup(value: Lookup) -> str:
    return write_json(_lookup_object(value))


def read_rows(text: str) -> Tuple[Optional[Rows], Optional[str]]:
    parsed = parse_json(text)
    if parsed.error is not None:
        return None, parsed.error[1]
    if not isinstance(parsed.value, JsonObject):
        return None, "expected an object"
    return _rows(parsed.value)


def write_rows(value: Rows) -> str:
    return write_json(_rows_object(value))


def has_data_source(doc: object) -> bool:
    """True when the form root's ``cbcsData`` reads as a record or a list."""

    root = getattr(doc, "root", None)
    prop = getattr(root, "prop", None)
    if not callable(prop):
        return False
    entry = prop("cbcsData")
    if entry is None:
        return False
    value = getattr(entry, "value", None)
    if not isinstance(value, StringValue) or not value.text.strip():
        return False
    return read_data(value.text).value is not None


def _read_record(obj: JsonObject) -> DataRead:
    values, unknown = _split(obj, _RECORD_KEYS)
    connection = values.get("connection")
    table = values.get("table")
    key = values.get("key")
    if not isinstance(connection, str) or not isinstance(table, str) or not isinstance(key, str):
        return DataRead(None, "a record source needs connection, table and key")
    word = values.get("recordWord")
    record_word = word if isinstance(word, str) and word != singular(table) else None
    order = _order_pairs(values.get("order"))
    if order == ((key, "asc"),):
        order = None
    open_at = values.get("openAt")
    if not isinstance(open_at, str) or open_at in ("", "first"):
        open_at = None
    conflicts = values.get("conflicts")
    if not isinstance(conflicts, str) or conflicts in ("", "check"):
        conflicts = None
    allow_raw = values.get("allowOverwrite")
    if allow_raw is None:
        allow_overwrite = False
    elif isinstance(allow_raw, bool):
        allow_overwrite = allow_raw
    else:
        return DataRead(None, "allowOverwrite must be true or false")
    delete_lines = values.get("deleteLines")
    if delete_lines is True or delete_lines is None:
        stored_delete: Optional[bool] = None
    elif delete_lines is False:
        stored_delete = False
    else:
        return DataRead(None, "deleteLines must be true or false")
    hooks_value = values.get("hooks")
    hooks: Optional[Hooks] = None
    if isinstance(hooks_value, JsonObject):
        hooks = _hooks(hooks_value)
        if hooks == Hooks():
            hooks = None
    elif hooks_value is not None:
        return DataRead(None, "hooks must be an object")
    return DataRead(
        RecordSource(
            connection,
            table,
            key,
            record_word,
            order,
            open_at,
            conflicts,
            allow_overwrite,
            stored_delete,
            _strings(values.get("search")),
            hooks,
            unknown,
        )
    )


def _record_object(value: RecordSource) -> JsonObject:
    pairs = [("connection", value.connection), ("table", value.table)]
    if value.record_word and value.record_word != singular(value.table):
        pairs.append(("recordWord", value.record_word))
    pairs.append(("key", value.key))
    order = value.order
    if order is not None and order != ((value.key, "asc"),):
        pairs.append(("order", tuple(tuple(item) for item in order)))
    if value.open_at and value.open_at != "first":
        pairs.append(("openAt", value.open_at))
    if value.conflicts and value.conflicts != "check":
        pairs.append(("conflicts", value.conflicts))
    if value.allow_overwrite:
        pairs.append(("allowOverwrite", True))
    if value.delete_lines is False:
        pairs.append(("deleteLines", False))
    if value.search:
        pairs.append(("search", value.search))
    if value.hooks is not None and value.hooks != Hooks():
        pairs.append(("hooks", _hooks_object(value.hooks)))
    pairs.extend(value.unknown)
    return JsonObject(tuple(pairs))


def _read_list(obj: JsonObject) -> DataRead:
    values, unknown = _split(obj, _LIST_KEYS, alias=(("query", "sql"),))
    connection = values.get("connection")
    columns = values.get("columns")
    if not isinstance(connection, str) or not isinstance(columns, tuple):
        return DataRead(None, "a list source needs connection and columns")
    names = _strings(columns)
    filters: list = []
    raw_filters = values.get("filters")
    if isinstance(raw_filters, tuple):
        for item in raw_filters:
            if not isinstance(item, JsonObject):
                return DataRead(None, "a filter must be an object")
            found, error = _filter(item)
            if error is not None or found is None:
                return DataRead(None, error or "a filter needs field and column")
            filters.append(found)
    opened: Optional[ListOpen] = None
    raw_open = values.get("open")
    if isinstance(raw_open, JsonObject):
        opened, error = _open(raw_open)
        if error is not None:
            return DataRead(None, error)
    limit = values.get("limit")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int)):
        return DataRead(None, "limit must be a whole number")
    return DataRead(
        ListSource(
            connection,
            names,
            _optional_text(values.get("table")),
            _optional_text(values.get("sql")),
            _strings(values.get("search")),
            _optional_text(values.get("searchField")),
            tuple(filters),
            _order_pairs(values.get("order")) or (),
            None if limit is None else int(limit),
            opened,
            unknown,
        )
    )


def _list_object(value: ListSource) -> JsonObject:
    pairs: list = [("mode", "list"), ("connection", value.connection)]
    if value.table:
        pairs.append(("table", value.table))
    if value.sql:
        pairs.append(("sql", value.sql))
    pairs.append(("columns", value.columns))
    if value.search:
        pairs.append(("search", value.search))
    if value.search_field:
        pairs.append(("searchField", value.search_field))
    if value.filters:
        pairs.append(("filters", tuple(_filter_object(item) for item in value.filters)))
    if value.order:
        pairs.append(("order", tuple(tuple(item) for item in value.order)))
    if value.limit is not None:
        pairs.append(("limit", value.limit))
    if value.open is not None:
        pairs.append(("open", _open_object(value.open)))
    pairs.extend(value.unknown)
    return JsonObject(tuple(pairs))


def _lookup(obj: JsonObject) -> Tuple[Optional[Lookup], Optional[str]]:
    values, unknown = _split(obj, _LOOKUP_KEYS)
    table = values.get("table")
    key = values.get("key")
    show = values.get("show")
    if not isinstance(table, str) or not isinstance(key, str) or not isinstance(show, str):
        return None, "a lookup needs table, key and show"
    return (
        Lookup(
            table,
            key,
            show,
            _optional_text(values.get("order")),
            _strings(values.get("also")),
            _optional_text(values.get("blank")),
            unknown,
        ),
        None,
    )


def _lookup_object(value: Lookup) -> JsonObject:
    pairs = [("table", value.table), ("key", value.key), ("show", value.show)]
    if value.order:
        pairs.append(("order", value.order))
    if value.also:
        pairs.append(("also", value.also))
    if value.blank:
        pairs.append(("blank", value.blank))
    pairs.extend(value.unknown)
    return JsonObject(tuple(pairs))


def _rows(obj: JsonObject) -> Tuple[Optional[Rows], Optional[str]]:
    values, unknown = _split(obj, _ROWS_KEYS)
    table = values.get("table")
    link = values.get("link")
    key = values.get("key")
    raw_columns = values.get("columns")
    if not isinstance(table, str) or not isinstance(link, str) or not isinstance(key, str):
        return None, "a lines grid needs table, link and key"
    if not isinstance(raw_columns, tuple):
        return None, "a lines grid needs columns"
    columns = []
    for item in raw_columns:
        if not isinstance(item, JsonObject):
            return None, "a column must be an object"
        column, error = _column(item)
        if error is not None or column is None:
            return None, error or "a column can't be read"
        columns.append(column)
    return (
        Rows(
            table,
            link,
            key,
            tuple(columns),
            _optional_text(values.get("order")),
            _optional_text(values.get("position")),
            unknown,
        ),
        None,
    )


def _rows_object(value: Rows) -> JsonObject:
    pairs = [("table", value.table), ("link", value.link), ("key", value.key)]
    if value.order:
        pairs.append(("order", value.order))
    if value.position:
        pairs.append(("position", value.position))
    pairs.append(("columns", tuple(_column_object(item) for item in value.columns)))
    pairs.extend(value.unknown)
    return JsonObject(tuple(pairs))


def _column(obj: JsonObject) -> Tuple[Optional[ColumnSpec], Optional[str]]:
    if obj.has("formula") or (obj.has("name") and not obj.has("column")):
        values, unknown = _split(obj, ("name", "header", "kind", "formula"))
        name = values.get("name")
        formula = values.get("formula")
        if not isinstance(name, str) or not isinstance(formula, str):
            return None, "a calculated column needs name and formula"
        return (
            CalcColumn(
                name,
                formula,
                _optional_text(values.get("header")),
                _optional_text(values.get("kind")),
                unknown,
            ),
            None,
        )
    values, unknown = _split(obj, ("column", "header", "kind", "lookup", "default", "readOnly", "validate"))
    column = values.get("column")
    if not isinstance(column, str):
        return None, "a column needs a name"
    lookup = None
    raw_lookup = values.get("lookup")
    if isinstance(raw_lookup, JsonObject):
        lookup, error = _lookup(raw_lookup)
        if error is not None:
            return None, error
    validate = values.get("validate")
    checks: Tuple[JsonValue, ...] = ()
    if isinstance(validate, tuple):
        checks = validate
    return (
        DataColumn(
            column,
            _optional_text(values.get("header")),
            _optional_text(values.get("kind")),
            lookup,
            _optional_text(values.get("default")),
            values.get("readOnly") is True,
            checks,
            unknown,
        ),
        None,
    )


def _column_object(value: ColumnSpec) -> JsonObject:
    if isinstance(value, CalcColumn):
        pairs = [("name", value.name)]
        if value.header:
            pairs.append(("header", value.header))
        if value.kind:
            pairs.append(("kind", value.kind))
        pairs.append(("formula", value.formula))
        pairs.extend(value.unknown)
        return JsonObject(tuple(pairs))
    pairs = [("column", value.column)]
    if value.header:
        pairs.append(("header", value.header))
    if value.kind:
        pairs.append(("kind", value.kind))
    if value.lookup is not None:
        pairs.append(("lookup", _lookup_object(value.lookup)))
    if value.default:
        pairs.append(("default", value.default))
    if value.read_only:
        pairs.append(("readOnly", True))
    if value.validate:
        pairs.append(("validate", value.validate))
    pairs.extend(value.unknown)
    return JsonObject(tuple(pairs))


def _hooks(obj: JsonObject) -> Hooks:
    values, unknown = _split(obj, HOOK_KEYS)
    return Hooks(
        _optional_text(values.get("afterLoad")),
        _optional_text(values.get("beforeSave")),
        _optional_text(values.get("afterSave")),
        _optional_text(values.get("beforeDelete")),
        _optional_text(values.get("afterDelete")),
        _optional_text(values.get("newRecord")),
        _optional_text(values.get("connection")),
        unknown,
    )


def _hooks_object(value: Hooks) -> JsonObject:
    mapping = (
        ("afterLoad", value.after_load),
        ("beforeSave", value.before_save),
        ("afterSave", value.after_save),
        ("beforeDelete", value.before_delete),
        ("afterDelete", value.after_delete),
        ("newRecord", value.new_record),
        ("connection", value.connection),
    )
    pairs = [(key, text) for key, text in mapping if text]
    pairs.extend(value.unknown)
    return JsonObject(tuple(pairs))


def _filter(obj: JsonObject) -> Tuple[Optional[ListFilter], Optional[str]]:
    values, unknown = _split(obj, ("field", "column"))
    field = values.get("field")
    column = values.get("column")
    if not isinstance(field, str) or not isinstance(column, str):
        return None, "a filter needs field and column"
    return ListFilter(field, column, unknown), None


def _filter_object(value: ListFilter) -> JsonObject:
    return JsonObject((("field", value.field), ("column", value.column)) + tuple(value.unknown))


def _open(obj: JsonObject) -> Tuple[Optional[ListOpen], Optional[str]]:
    values, unknown = _split(obj, ("form", "key"))
    form = values.get("form")
    key = values.get("key")
    if not isinstance(form, str) or not isinstance(key, str):
        return None, "open needs form and key"
    return ListOpen(form, key, unknown), None


def _open_object(value: ListOpen) -> JsonObject:
    return JsonObject((("form", value.form), ("key", value.key)) + tuple(value.unknown))


def _split(
    obj: JsonObject,
    known: Sequence[str],
    alias: Tuple[Tuple[str, str], ...] = (),
) -> Tuple[dict, Pairs]:
    known_set = set(known)
    aliases = dict(alias)
    values: dict = {}
    unknown: list = []
    for key, value in obj.pairs:
        target = aliases.get(key, key)
        if target in known_set and target not in values:
            values[target] = value
            continue
        if key in aliases:
            continue
        unknown.append((key, value))
    return values, tuple(unknown)


def _strings(value: object) -> Tuple[str, ...]:
    if not isinstance(value, tuple):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _optional_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _order_pairs(value: object) -> Optional[Tuple[Tuple[str, str], ...]]:
    if not isinstance(value, tuple):
        return None
    found = []
    for item in value:
        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) and isinstance(item[1], str):
            found.append((item[0], item[1]))
    return tuple(found)
