"""Lookup combos read from the document. Codegen and the Data tab share this plan.

The plan is the ``cbcsLookup`` object plus whether the bound column is nullable
and whether the combo is editable. SQL text is not built here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.data.schema import schema_for
from app.features.form_builder.engine.data.source import Lookup, read_data, read_lookup, singular
from app.features.form_builder.engine.data.sql import is_identifier
from app.features.form_builder.engine.data.types import describe
from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import BoolValue, StringValue

_SHOW_NAMES = ("name", "title", "description")


@dataclass(frozen=True)
class LookupPlan:
    widget: str
    connection: str
    table: str
    key: str
    show: str
    order: str
    also: Tuple[str, ...] = ()
    blank: str = ""
    editable: bool = False
    nullable: bool = False


def select_columns(key: str, show: str, also: Sequence[str]) -> List[str]:
    """Key, shown column, then also columns, with each name once.

    ``select_lookup`` emits this order. Both expanders index a fetched row with it.
    """

    columns: List[str] = []
    for name in (key, show):
        if name not in columns:
            columns.append(name)
    for name in also:
        if name not in columns:
            columns.append(name)
    return columns


def also_indexes(also: Sequence[str], columns: Sequence[str]) -> Tuple[Tuple[str, int], ...]:
    """``(name, index)`` for each also column that the SELECT actually returns."""

    found = list(columns)
    return tuple((name, found.index(name)) for name in also if name in found)


def lookup_plans(doc: UiDocument, names: Sequence[str]) -> Tuple[LookupPlan, ...]:
    """Valid lookup combos whose object names are in ``names``."""

    source = _record(doc)
    if source is None:
        return ()
    allowed = set(names)
    nullable = _nullable_columns(doc, source.connection, source.table)
    found = []
    for node in _widgets(doc):
        widget = node.object_name or ""
        if widget not in allowed or not compat.is_name(widget):
            continue
        if (node.class_name or "").rsplit(".", 1)[-1] != "QComboBox":
            continue
        lookup = _lookup(node)
        if lookup is None or not _names_ok(lookup):
            continue
        column = _bind(node)
        found.append(
            LookupPlan(
                widget,
                source.connection,
                lookup.table,
                lookup.key,
                lookup.show,
                lookup.order or lookup.show,
                lookup.also,
                lookup.blank,
                _editable(node),
                bool(column and nullable.get(column, False)),
            )
        )
    return tuple(found)


def lookup_names(doc: UiDocument, names: Sequence[str]) -> Tuple[str, ...]:
    return tuple(plan.widget for plan in lookup_plans(doc, names))


def suggest_lookup(column: object, tables: Sequence[object]) -> Optional[Lookup]:
    """Defaults for a column that points at another table (UX-LKP-002)."""

    ref = getattr(column, "references", None)
    table_name = getattr(ref, "table", "") or ""
    if not table_name or not is_identifier(table_name):
        return None
    key = getattr(ref, "column", "") or "id"
    if not is_identifier(key):
        return None
    target = None
    for table in tables:
        if getattr(table, "name", "") == table_name:
            target = table
            break
    show = _show_column(target, key)
    if not show:
        return None
    return Lookup(
        table_name,
        key,
        show,
        order=show,
        blank="(choose a %s)" % singular(table_name),
    )


def _record(doc: UiDocument):
    from app.features.form_builder.engine.data.source import RecordSource

    text = _text(getattr(doc, "root", None), "cbcsData")
    if not text:
        return None
    found = read_data(text).value
    if isinstance(found, RecordSource):
        return found
    return None


def _lookup(node: object) -> Optional[Lookup]:
    text = _text(node, "cbcsLookup")
    if not text:
        return None
    found, _error = read_lookup(text)
    return found


def _names_ok(lookup: Lookup) -> bool:
    if not is_identifier(lookup.table) or not is_identifier(lookup.key) or not is_identifier(lookup.show):
        return False
    if lookup.order and not is_identifier(lookup.order):
        return False
    return all(is_identifier(name) for name in lookup.also)


def _show_column(table: object, key: str) -> str:
    if table is None:
        return "name" if key != "name" else key
    texts = []
    for column in getattr(table, "columns", ()) or ():
        name = getattr(column, "name", "") or ""
        if not name or not is_identifier(name):
            continue
        kind = describe(
            getattr(column, "type", "") or "",
            column_name=name,
            nullable=bool(getattr(column, "nullable", True)),
        )
        if kind.kind == "text" or kind.direction == "text":
            texts.append(name)
    for preferred in _SHOW_NAMES:
        if preferred in texts:
            return preferred
    if texts:
        return texts[0]
    return key


def _nullable_columns(doc: UiDocument, connection: str, table_name: str) -> dict:
    schema = schema_for(doc, connection)
    if schema is None:
        return {}
    for table in schema.tables:
        if table.name != table_name:
            continue
        return {column.name: column.nullable for column in table.columns}
    return {}


def _bind(node: object) -> str:
    from app.features.form_builder.engine.data.source import read_bind

    text = _text(node, "cbcsBind")
    if not text:
        return ""
    return read_bind(text).column


def _editable(node: object) -> bool:
    entry = node.prop("editable") if hasattr(node, "prop") else None
    value = getattr(entry, "value", None)
    return isinstance(value, BoolValue) and bool(value.value)


def _text(node: object, name: str) -> str:
    prop = getattr(node, "prop", None)
    if not callable(prop):
        return ""
    entry = prop(name)
    value = getattr(entry, "value", None)
    if isinstance(value, StringValue):
        return value.text
    text = getattr(value, "text", "")
    return text if isinstance(text, str) else ""


def _widgets(doc: UiDocument):
    walk = getattr(doc, "iter_widgets", None)
    if not callable(walk):
        return ()
    try:
        return tuple(walk())
    except Exception:
        return ()
