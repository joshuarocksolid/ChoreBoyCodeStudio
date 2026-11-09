"""Dragging a pointing column inserts a lookup combo (UX-LKP-002)."""

from __future__ import annotations

import weakref
from dataclasses import dataclass
from typing import ClassVar, Optional

from app.features.form_builder.engine.commands.catalog import SetLogic
from app.features.form_builder.engine.data.schema import schema_for
from app.features.form_builder.engine.data.source import write_lookup
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.qtside.data_panel.column_insert_hooks import (
    register_after_insert,
    register_insert_label,
    register_widget_class,
)

_FOCUS = weakref.WeakKeyDictionary()
_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    register_widget_class(_class_for)
    register_insert_label(_label_for)
    register_after_insert(_after)
    _INSTALLED = True


def pending_show_focus(document: object) -> object:
    return _FOCUS.get(document)


def clear_show_focus(document: object) -> None:
    _FOCUS.pop(document, None)


def _class_for(column: object, engine: str):
    ref = getattr(column, "references", None)
    if not getattr(ref, "table", ""):
        return None
    from app.features.form_builder.qtside.data_panel.model import column_kind

    return "QComboBox", column_kind(column, engine, lookup=True)


def _label_for(column: object, class_name: str, kind: object) -> str:
    del class_name, kind
    ref = getattr(column, "references", None)
    if getattr(ref, "table", ""):
        return "Add lookup"
    return ""


def _after(txn: object, session: object, field_id: object, column: object, class_name: str, kind: object) -> None:
    del class_name, kind
    document = getattr(session, "document", None)
    from app.features.form_builder.qtside.data_panel.model import record_source

    source = record_source(document) if document is not None else None
    tables = ()
    if document is not None and source is not None:
        schema = schema_for(document, source.connection)
        tables = getattr(schema, "tables", ()) or ()
    from app.features.form_builder.engine.codegen.lookup_plan import suggest_lookup

    lookup = suggest_lookup(column, tables)
    if lookup is None:
        return
    execute = getattr(txn, "execute", None)
    if not callable(execute):
        return
    execute(SetLogic(field_id, "cbcsLookup", write_lookup(lookup)))
    execute(_SelectField(field_id))
    if isinstance(document, UiDocument):
        _FOCUS[document] = field_id


@dataclass(frozen=True)
class _SelectField:
    """Leave the new combo selected so the Data tab opens on it."""

    command_type: ClassVar[str] = "lookup_select"
    node_id: object
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return ""

    def merge_key(self) -> None:
        return None

    def apply(self, doc: object, ctx: object) -> None:
        del doc
        select = getattr(ctx, "select", None)
        if callable(select):
            select((self.node_id,), self.node_id)
