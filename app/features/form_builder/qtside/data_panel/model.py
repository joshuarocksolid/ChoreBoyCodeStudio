"""What the Data tab reads off a form. Qt-free."""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Tuple, cast

from app.features.form_builder.engine.data.connections import load_connections
from app.features.form_builder.engine.data.schema import schema_for
from app.features.form_builder.engine.data.source import (
    Hooks,
    ListSource,
    RecordSource,
    has_data_source,
    read_bind,
    read_bind_mode,
    read_data,
    singular,
)
from app.features.form_builder.engine.data.types import describe
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue

COLUMN_MIME = "application/x-cbcs-column"
FIELD_CLASSES = frozenset(
    {
        "QLineEdit",
        "QPlainTextEdit",
        "QTextEdit",
        "QSpinBox",
        "QDoubleSpinBox",
        "QCheckBox",
        "QRadioButton",
        "QDateEdit",
        "QTimeEdit",
        "QDateTimeEdit",
        "QComboBox",
        "QSlider",
        "QDial",
    }
)
_SUFFIXES = ("Edit", "Spin", "Combo", "Check", "Box", "View", "Label", "Button", "Field")
HOOK_ROWS = (
    ("after_load", "After a record is shown", "after_load", ""),
    ("before_save", "Before saving", "before_save", ""),
    ("after_save", "After saving", "after_save", ""),
    ("before_delete", "Before deleting", "before_delete", ""),
    ("after_delete", "After deleting", "after_delete", ""),
    ("new_record", "When a new record starts", "new_record", ""),
    ("connection", "Connection", "db_connection", "name"),
)


def project_root(session: object, host: object = None) -> str:
    scope = getattr(session, "scope", None)
    root = getattr(scope, "project_root", None)
    if isinstance(root, str) and root:
        return root
    for owner in (host, getattr(host, "_workbench", None) if host is not None else None):
        if owner is None:
            continue
        found = getattr(owner, "project_root", None)
        if isinstance(found, str) and found:
            return found
        window = getattr(owner, "window", None)
        if not callable(window):
            continue
        try:
            loaded = getattr(window(), "_loaded_project", None)
        except Exception:
            loaded = None
        path = getattr(loaded, "project_root", None)
        if path:
            return str(path)
    return ""


def connections_of(session: object, host: object = None) -> Tuple[Any, ...]:
    root = project_root(session, host)
    if not root:
        return ()
    loaded, _error = load_connections(root)
    if loaded is None:
        return ()
    return tuple(loaded.connections)


def connection_title(session: object, name: str, host: object = None) -> str:
    for item in connections_of(session, host):
        if item.name == name:
            return item.title or name
    return name


def dialect_of(session: object, name: str, host: object = None) -> str:
    for item in connections_of(session, host):
        if item.name == name and item.engine in ("sqlite", "postgres"):
            return str(item.engine)
    return "sqlite"


def list_source(document: object) -> Optional[ListSource]:
    """The form's list source, or None when this form is not a list."""

    if not has_data_source(document):
        return None
    root = getattr(document, "root", None)
    entry = root.prop("cbcsData") if root is not None and hasattr(root, "prop") else None
    value = getattr(entry, "value", None)
    text = getattr(value, "text", "")
    if not isinstance(text, str):
        return None
    found = read_data(text).value
    if isinstance(found, ListSource):
        return found
    return None


def record_source(document: object) -> Optional[RecordSource]:
    if not has_data_source(document):
        return None
    root = getattr(document, "root", None)
    entry = root.prop("cbcsData") if root is not None and hasattr(root, "prop") else None
    value = getattr(entry, "value", None)
    text = getattr(value, "text", "")
    if not isinstance(text, str):
        return None
    found = read_data(text).value
    if isinstance(found, RecordSource):
        return found
    return None


def table_of(document: object, source: RecordSource) -> Optional[object]:
    cached = schema_for(document, source.connection)
    if cached is None:
        return None
    for table in cached.tables:
        if table.name == source.table:
            return table
    return None


def column_engine(document: object, source: RecordSource, session: object = None, host: object = None) -> str:
    cached = schema_for(document, source.connection)
    engine = getattr(cached, "engine", None)
    if engine in ("sqlite", "postgres"):
        return str(engine)
    if session is not None:
        return dialect_of(session, source.connection, host)
    return "sqlite"


def column_kind(column: object, engine: str, *, lookup: bool) -> object:
    reference = ""
    if lookup:
        ref = getattr(column, "references", None)
        reference = getattr(ref, "table", "") or ""
    return describe(
        getattr(column, "type", "") or "",
        engine=engine,
        column_name=getattr(column, "name", "") or "",
        references_table=reference,
        nullable=bool(getattr(column, "nullable", True)),
    )


def widget_class_for(column: object, engine: str) -> Tuple[str, object]:
    """The widget to insert. A pointing column can become a lookup combo."""

    from app.features.form_builder.qtside.data_panel.column_insert_hooks import widget_class_override

    decided = widget_class_override(column, engine)
    if decided is not None:
        return decided
    kind = column_kind(column, engine, lookup=False)
    widget = str(getattr(kind, "widget", "QLineEdit"))
    if widget == "QComboBox" and getattr(kind, "direction", "") == "int":
        widget = "QSpinBox"
    return widget, kind


def bind_text(node: object) -> str:
    entry = node.prop("cbcsBind") if hasattr(node, "prop") else None
    if entry is None or not isinstance(getattr(entry, "value", None), StringValue):
        return ""
    return read_bind(entry.value.text).column


def read_only(node: object) -> bool:
    entry = node.prop("cbcsBindMode") if hasattr(node, "prop") else None
    if entry is None or not isinstance(getattr(entry, "value", None), StringValue):
        return False
    return read_bind_mode(entry.value.text).read_only


def kind_name(node: object) -> str:
    entry = node.prop("cbcsKind") if hasattr(node, "prop") else None
    if entry is None or not isinstance(getattr(entry, "value", None), StringValue):
        return ""
    return entry.value.text


def caption_for(column: str) -> str:
    words = column.replace("_", " ").strip()
    if not words:
        return "Field:"
    return words[:1].upper() + words[1:] + ":"


def stem_of(object_name: str) -> str:
    """``invoiceDateEdit`` → ``invoice_date``. One widget suffix, then snake case."""

    base = object_name
    cut = ""
    for suffix in _SUFFIXES:
        if base.endswith(suffix) and len(base) > len(suffix) and len(suffix) > len(cut):
            cut = suffix
    if cut:
        base = base[: -len(cut)]
    return _camel_to_snake(base)


def match_by_name(document: object, source: RecordSource) -> List[Tuple[str, str]]:
    """Unbound fields to columns. Exact object names claim a column before stems do."""

    table = table_of(document, source)
    names = [column.name for column in getattr(table, "columns", ()) or ()]
    if not names:
        return []
    claimed = set()
    widgets = _unbound_fields(document)
    pairs: List[Tuple[str, str]] = []
    for node in widgets:
        if node.object_name in names and node.object_name not in claimed:
            claimed.add(node.object_name)
            pairs.append((node.object_name, node.object_name))
    for node in widgets:
        if any(name == node.object_name for name, _column in pairs):
            continue
        stem = stem_of(node.object_name)
        if stem in names and stem not in claimed:
            claimed.add(stem)
            pairs.append((node.object_name, stem))
    return pairs


def bound_field(document: object, column: str) -> str:
    """The object name bound to ``column``, or ``""``."""

    for node in _widgets(document):
        if bind_text(node) == column:
            return node.object_name
    return ""


def hook_method(source: RecordSource, field: str) -> str:
    hooks = source.hooks or Hooks()
    return str(getattr(hooks, field, "") or "")


def _widgets(document: object) -> List[WidgetNode]:
    walk = getattr(document, "iter_widgets", None)
    if not callable(walk):
        return []
    root_id = getattr(getattr(document, "root", None), "id", None)
    return [
        node
        for node in cast(Iterable[object], walk())
        if isinstance(node, WidgetNode) and node.id != root_id
    ]


def _unbound_fields(document: object) -> List[WidgetNode]:
    found = []
    for node in _widgets(document):
        if node.class_name not in FIELD_CLASSES:
            continue
        if bind_text(node):
            continue
        found.append(node)
    return found


def _camel_to_snake(text: str) -> str:
    chars: List[str] = []
    for index, char in enumerate(text):
        if char.isupper() and index:
            prev = text[index - 1]
            nxt = text[index + 1] if index + 1 < len(text) else ""
            if prev.islower() or (prev.isupper() and nxt.islower()):
                chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


def order_of(source: RecordSource) -> Tuple[Tuple[str, str], ...]:
    if source.order:
        return tuple(source.order[:3])
    return ((source.key, "asc"),)


def record_word(source: RecordSource) -> str:
    return source.record_word or singular(source.table)


def writable_columns(document: object, source: RecordSource) -> Tuple[str, ...]:
    """Bound columns that save. Read-only bindings are left out. Schema order when we have it."""

    table = table_of(document, source)
    known = [column.name for column in getattr(table, "columns", ()) or ()]
    bound: List[Tuple[str, bool]] = []
    for node in _widgets(document):
        column = bind_text(node)
        if not column:
            continue
        bound.append((column, read_only(node)))
    if known:
        ordered = [
            name
            for name in known
            if any((item == name and not flag) for item, flag in bound)
        ]
        return tuple(ordered)
    return tuple(column for column, flag in bound if not flag)


def load_columns(document: object, source: RecordSource) -> Tuple[str, ...]:
    table = table_of(document, source)
    names = tuple(column.name for column in getattr(table, "columns", ()) or ())
    if names:
        return names
    extra = [source.key] if source.key else []
    for column in writable_columns(document, source):
        if column not in extra:
            extra.append(column)
    return tuple(extra)


def _install_lookup_columns() -> None:
    from app.features.form_builder.qtside.data_panel.lookup_columns import install

    install()


_install_lookup_columns()
