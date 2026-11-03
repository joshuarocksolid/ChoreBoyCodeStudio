"""Record-form checks FB301 and FB304–FB308 and FB319.

FB305 compares a sibling ``cbcs_connections.py`` header with the current
connections file when the project can be found from the document. If it cannot,
FB305 stays quiet rather than warning about a file it has not seen.
Schema-dependent checks are skipped when the cache is absent (FB309 already
covers that). Nothing here publishes to the diagnostics store.
"""

from __future__ import annotations

import hashlib
import os
from typing import Iterable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.data.check import DataCheck
from app.features.form_builder.engine.data.schema import Schema, schema_for
from app.features.form_builder.engine.data.source import read_bind, read_bind_mode, read_data, singular
from app.features.form_builder.engine.data.sql import is_identifier
from app.features.form_builder.engine.data.types import describe, sqlite_affinity
from app.features.form_builder.engine.diagnostics import CODES, DiagnosticLocation, FormDiagnostic
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue

import app.features.form_builder.engine.diagnostic_codes.fb3xx_data  # noqa: F401

_CLASS_WORDS = {
    "QLineEdit": "field",
    "QPlainTextEdit": "text box",
    "QTextEdit": "text box",
    "QLabel": "label",
    "QSpinBox": "spin box",
    "QDoubleSpinBox": "spin box",
    "QDateEdit": "date field",
    "QTimeEdit": "time field",
    "QDateTimeEdit": "date field",
    "QCheckBox": "check box",
    "QRadioButton": "radio button",
    "QComboBox": "combo box",
}
_TEXT_WIDGETS = ("QLineEdit", "QPlainTextEdit", "QTextEdit", "QLabel", "QComboBox")
_INT_TYPES = ("integer", "int", "int2", "int4", "int8", "smallint", "bigint", "serial", "bigserial", "smallserial")


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if not callable(add):
        return
    add(DataCheck("record-connection", _connection, 200))
    add(DataCheck("record-binding", _bindings, 210))
    add(DataCheck("record-hash", _hash, 220))
    add(DataCheck("record-key", _key, 230))
    add(DataCheck("record-names", _names, 240))
    add(DataCheck("record-required", _required, 250))


def _connection(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del schema
    source = _record(doc)
    names = _connection_names(connections)
    if source is None or names is None:
        return ()
    if source.connection in names:
        return ()
    return (_problem(doc, "FB301", _root(doc), "cbcsData", name=source.connection),)


def _bindings(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections
    source = _record(doc)
    if source is None:
        return ()
    cached = _schema(doc, schema, source)
    table = _table(cached, source.table) if cached is not None else None
    columns = {column.name: column for column in table.columns} if table is not None else {}
    found: List[FormDiagnostic] = []
    seen = {}
    for node, column, mode in _bound(doc):
        owners = seen.setdefault(column, [])
        owners.append(_node_name(node))
        if table is None:
            continue
        spec = columns.get(column)
        if spec is None or cached is None:
            continue
        kind = describe(
            spec.type,
            engine=cached.engine or "sqlite",
            column_name=spec.name,
            references_table=spec.references.table if spec.references is not None else "",
            nullable=spec.nullable,
        )
        widget = _class_name(node)
        if not widget:
            continue
        if _fits(kind, widget, mode != "readOnly", _decimals(node), _kind_text(node)):
            continue
        info = CODES["FB304"]
        message = info.title.replace("{type words}", kind.words).replace("{class words}", _class_words(widget))
        found.append(_at(info.code, info.severity, message, node, "cbcsBind"))
    for column, owners in seen.items():
        if len(owners) < 2:
            continue
        found.append(_problem(doc, "FB308", _root(doc), "cbcsBind", column=column, a=owners[0], b=owners[1]))
    return tuple(found)


def _hash(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    """FB305 when a sibling ``cbcs_connections.py`` header hash differs.

    The header is the sha256 of ``write_connections`` for the set that generated
    the module. A ``project_root`` (or a ui path) on the document or the
    connection argument is enough to find that file. If the project or the
    module cannot be read, this returns nothing.
    """

    del schema
    source = _record(doc)
    if source is None:
        return ()
    root = _project_root(doc, connections)
    if root is None:
        return ()
    module_path = os.path.join(root, "cbcs_connections.py")
    if not os.path.isfile(module_path):
        return ()
    try:
        embedded = _header_hash(module_path)
    except OSError:
        return ()
    current = _current_hash(root, connections)
    if not embedded or not current or embedded == current:
        return ()
    return (_problem(doc, "FB305", _root(doc), "cbcsData"),)


def _key(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections
    source = _record(doc)
    cached = _schema(doc, schema, source)
    if source is None or cached is None:
        return ()
    table = _table(cached, source.table)
    if table is None:
        return ()
    if not table.key:
        return (_problem(doc, "FB306", _root(doc), "cbcsData", table=source.table),)
    if (cached.engine or "sqlite") != "sqlite":
        return ()
    column = _column(table, table.key)
    if column is None:
        return ()
    if sqlite_affinity(column.type) == "INTEGER":
        return ()
    if _writable_bound(doc, table.key):
        return ()
    return (_problem(doc, "FB306", _root(doc), "cbcsData", table=source.table),)


def _names(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections
    source = _record(doc)
    if source is None:
        return ()
    found = []
    if source.table and not is_identifier(source.table):
        found.append(_problem(doc, "FB307", _root(doc), "cbcsData", name=source.table))
    if source.key and not is_identifier(source.key):
        found.append(_problem(doc, "FB307", _root(doc), "cbcsData", name=source.key))
    for _node, column, _mode in _bound(doc):
        if column and not is_identifier(column):
            found.append(_problem(doc, "FB307", _root(doc), "cbcsBind", name=column))
    cached = _schema(doc, schema, source)
    table = _table(cached, source.table) if cached is not None else None
    if table is not None:
        for column in table.columns:
            if column.name and not is_identifier(column.name):
                found.append(_problem(doc, "FB307", _root(doc), "cbcsData", name=column.name))
    return tuple(found)


def _required(doc: object, connections: object, schema: object) -> Iterable[FormDiagnostic]:
    del connections
    source = _record(doc)
    cached = _schema(doc, schema, source)
    if source is None or cached is None:
        return ()
    table = _table(cached, source.table)
    if table is None:
        return ()
    record = source.record_word or singular(source.table)
    found = []
    for column in table.columns:
        if column.nullable or column.default:
            continue
        if table.key == column.name and _integer_key(column, cached.engine or "sqlite"):
            continue
        if _writable_bound(doc, column.name):
            continue
        found.append(
            _problem(doc, "FB319", _root(doc), "cbcsData", record=record, column=column.name)
        )
    return tuple(found)


def _integer_key(column: object, engine: str) -> bool:
    declared = str(getattr(column, "type", "") or "")
    if engine == "sqlite":
        return sqlite_affinity(declared) == "INTEGER"
    base = declared.strip().lower().split("(", 1)[0].strip()
    return base in _INT_TYPES


def _fits(kind: object, widget: str, writable: bool, decimals: Optional[int], widget_kind: str) -> bool:
    if getattr(kind, "read_only", False) and writable:
        return False
    direction = getattr(kind, "direction", "text")
    if direction == "text":
        return widget in _TEXT_WIDGETS
    if direction == "int":
        return widget in ("QSpinBox", "QDoubleSpinBox", "QComboBox", "QLineEdit")
    if direction == "decimal":
        scale = getattr(kind, "decimals", None)
        if widget == "QSpinBox":
            return scale in (None, 0)
        if widget == "QDoubleSpinBox":
            if scale is None:
                return True
            shown = 2 if decimals is None else decimals
            return shown >= scale
        return widget in ("QLineEdit", "QPlainTextEdit")
    if direction == "date":
        if widget in ("QDateEdit", "QDateTimeEdit"):
            return True
        return widget == "QLineEdit" and widget_kind == "date"
    if direction == "time":
        if widget == "QTimeEdit":
            return True
        return widget == "QLineEdit" and widget_kind == "time"
    if direction == "datetime":
        return widget == "QDateTimeEdit"
    if direction == "bool":
        return widget in ("QCheckBox", "QRadioButton")
    return True


def _class_words(widget: str) -> str:
    found = _CLASS_WORDS.get(widget)
    if found:
        return found
    bare = widget[1:] if widget[:1] == "Q" and len(widget) > 1 else widget
    parts = []
    current = ""
    for char in bare:
        if char.isupper() and current:
            parts.append(current)
            current = char
        else:
            current += char
    if current:
        parts.append(current)
    return " ".join(part.lower() for part in parts) or widget


def _record(doc: object):
    from app.features.form_builder.engine.data.source import RecordSource

    root = _root(doc)
    prop = getattr(root, "prop", None)
    if not callable(prop):
        return None
    entry = prop("cbcsData")
    if entry is None:
        return None
    value = getattr(entry, "value", None)
    text = getattr(value, "text", None)
    if not isinstance(text, str) or not text.strip():
        return None
    found = read_data(text).value
    if isinstance(found, RecordSource):
        return found
    return None


def _current_hash(root: str, connections: object) -> str:
    from app.features.form_builder.engine.data.connections import ConnectionSet, read_connections, write_connections

    chosen = connections if isinstance(connections, ConnectionSet) else None
    if chosen is None:
        path = os.path.join(root, "connections.json")
        if not os.path.isfile(path):
            return ""
        try:
            handle = open(path, "r", encoding="utf-8")
            try:
                text = handle.read()
            finally:
                handle.close()
        except OSError:
            return ""
        chosen, _error = read_connections(text, project_root=root)
    if not isinstance(chosen, ConnectionSet):
        return ""
    return hashlib.sha256(write_connections(chosen).encode("utf-8")).hexdigest()


def _schema(doc: object, schema: object, source: object) -> Optional[Schema]:
    if isinstance(schema, Schema):
        return schema
    if source is None:
        return None
    return schema_for(doc, getattr(source, "connection", "") or "")


def _table(schema: Optional[Schema], name: str):
    if schema is None:
        return None
    for table in schema.tables:
        if table.name == name:
            return table
    return None


def _column(table: object, name: str):
    for column in getattr(table, "columns", ()) or ():
        if getattr(column, "name", None) == name:
            return column
    return None


def _bound(doc: object) -> List[Tuple[object, str, str]]:
    found = []
    for node in _nodes(doc):
        column = ""
        mode = ""
        for entry in _properties(node):
            if entry.name == "cbcsBind" and isinstance(entry.value, StringValue):
                column = read_bind(entry.value.text).column
            elif entry.name == "cbcsBindMode" and isinstance(entry.value, StringValue):
                mode = "readOnly" if read_bind_mode(entry.value.text).read_only else ""
        if column:
            found.append((node, column, mode))
    return found


def _writable_bound(doc: object, column: str) -> bool:
    for node, name, mode in _bound(doc):
        if name != column or mode == "readOnly":
            continue
        if _has_text(node, "cbcsValue"):
            continue
        return True
    return False


def _connection_names(connections: object) -> Optional[Sequence[str]]:
    rows = getattr(connections, "connections", None)
    if rows is None:
        return None
    names = []
    for item in rows:
        name = getattr(item, "name", None)
        if isinstance(name, str):
            names.append(name)
    return names


def _project_root(doc: object, connections: object) -> Optional[str]:
    candidates = []
    for obj in (doc, connections):
        if obj is None:
            continue
        for attr in ("project_root", "ui_path", "path", "forms_dir"):
            value = getattr(obj, attr, None)
            if isinstance(value, str) and value:
                candidates.append(value)
    for raw in candidates:
        path = raw if os.path.isdir(raw) else os.path.dirname(raw)
        for _step in range(4):
            if os.path.isfile(os.path.join(path, "cbcs_connections.py")):
                return path
            parent = os.path.dirname(path)
            if parent == path:
                break
            path = parent
    return None


def _header_hash(path: str) -> str:
    handle = open(path, "r", encoding="utf-8")
    try:
        for _index in range(16):
            line = handle.readline()
            if not line:
                break
            if line.startswith("## cbcs-source-sha256:"):
                return line.split(":", 1)[1].strip()
    finally:
        handle.close()
    return ""


def _decimals(node: object) -> Optional[int]:
    prop = getattr(node, "prop", None)
    if not callable(prop):
        return None
    entry = prop("decimals")
    value = getattr(entry, "value", None)
    if isinstance(value, NumberValue) and isinstance(value.value, int) and not isinstance(value.value, bool):
        return value.value
    return None


def _kind_text(node: object) -> str:
    prop = getattr(node, "prop", None)
    if not callable(prop):
        return ""
    entry = prop("cbcsKind")
    value = getattr(entry, "value", None)
    text = getattr(value, "text", "")
    return text.strip() if isinstance(text, str) else ""


def _has_text(node: object, name: str) -> bool:
    prop = getattr(node, "prop", None)
    if not callable(prop):
        return False
    entry = prop(name)
    value = getattr(entry, "value", None)
    text = getattr(value, "text", "")
    return isinstance(text, str) and bool(text.strip())


def _class_name(node: object) -> str:
    value = getattr(node, "class_name", "")
    return value if isinstance(value, str) else ""


def _problem(doc: object, code: str, node: object, prop_name: str, **words: str) -> FormDiagnostic:
    info = CODES[code]
    message = info.title.format(**words) if words else info.title
    return _at(info.code, info.severity, message, node, prop_name)


def _at(code: str, severity: object, message: str, node: object, prop_name: str) -> FormDiagnostic:
    return FormDiagnostic(code, severity, message, _location(node, prop_name), "data.check")


def _location(node: object, prop_name: str) -> DiagnosticLocation:
    node_id = getattr(node, "id", None)
    return DiagnosticLocation(
        node_id if isinstance(node_id, int) else None,
        _node_name(node) or None,
        prop_name,
        (prop_name,),
    )


def _root(doc: object) -> object:
    return getattr(doc, "root", None)


def _nodes(doc: object) -> Sequence[object]:
    walk = getattr(doc, "iter_widgets", None)
    if not callable(walk):
        walk = getattr(doc, "iter_preorder", None)
    if not callable(walk):
        return ()
    try:
        return tuple(walk())
    except Exception:
        return ()


def _properties(node: object) -> Sequence[object]:
    props = getattr(node, "properties", None)
    if not callable(props):
        return ()
    try:
        return tuple(props())
    except Exception:
        return ()


def _node_name(node: object) -> str:
    for field in ("object_name", "name"):
        value = getattr(node, field, "")
        if isinstance(value, str) and value:
            return value
    return ""
