"""Document edits for the Data tab. Each public function is one undo step."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import InsertFragment, SetLogic, SetProperty
from app.features.form_builder.engine.commands.catalog_ext.drop import InsertFormRow
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.commands.catalog_ext.tab_order import SetLabelBuddy
from app.features.form_builder.engine.commands.placement import InBoxLayout, InFormRow, InGridCell
from app.features.form_builder.engine.data.source import Hooks, RecordSource, singular, write_data
from app.features.form_builder.engine.logic.codec import Step
from app.features.form_builder.engine.logic.events_codec import EventStep
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue
from app.features.form_builder.qtside.data_panel.model import (
    HOOK_ROWS,
    bind_text,
    caption_for,
    column_engine,
    match_by_name,
    record_source,
    widget_class_for,
)

_BUTTONS = frozenset(
    {"QPushButton", "QToolButton", "QDialogButtonBox", "QCommandLinkButton", "QRadioButton"}
)
_OWN_TEXT = frozenset({"QCheckBox", "QRadioButton", "QPushButton", "QToolButton", "QCommandLinkButton"})
_MARGINS = ("leftMargin", "topMargin", "rightMargin", "bottomMargin")

_BAR = (
    ("firstButton", "QPushButton", "First", "Ctrl+Home", "form.position > 1", "first"),
    ("previousButton", "QPushButton", "Previous", "PgUp", "form.position > 1", "previous"),
    ("positionLabel", "QLabel", "Record 1 of 1", "", "", ""),
    ("nextButton", "QPushButton", "Next", "PgDown", "form.position < form.count", "next"),
    ("lastButton", "QPushButton", "Last", "Ctrl+End", "form.position < form.count", "last"),
    ("newButton", "QPushButton", "New", "Ctrl+N", "", "new"),
    ("saveButton", "QPushButton", "Save", "Ctrl+S", "form.isDirty or form.isNew", "save"),
    ("revertButton", "QPushButton", "Undo", "", "form.isDirty", "revert"),
    ("deleteButton", "QPushButton", "Delete", "", "not form.isNew", "delete"),
    ("findButton", "QPushButton", "Find", "Ctrl+F", "", "find"),
)
_POSITION = '"Record " + text(form.position) + " of " + text(form.count)'


def connect_form(session: object, source: RecordSource) -> None:
    text = write_data(source)
    with session.log.transaction("Connect to %s" % source.table) as txn:
        txn.execute(SetLogic(session.document.root.id, "cbcsData", text))


def disconnect_form(session: object) -> None:
    with session.log.transaction("Disconnect") as txn:
        txn.execute(SetLogic(session.document.root.id, "cbcsData", None))


def bind_field(session: object, node_id: object, column: str, *, read_only: bool = False) -> None:
    label = "Bind %s" % column if column else "Unbind"
    with session.log.transaction(label) as txn:
        txn.execute(SetLogic(node_id, "cbcsBind", column or None))
        txn.execute(SetLogic(node_id, "cbcsBindMode", "readOnly" if read_only and column else None))


def set_read_only(session: object, node_id: object, read_only: bool) -> None:
    with session.log.transaction("Only show, never save" if read_only else "Save this column") as txn:
        txn.execute(SetLogic(node_id, "cbcsBindMode", "readOnly" if read_only else None))


def bind_named(session: object, pairs: Sequence[Tuple[str, str]]) -> int:
    """Bind each ``(object name, column)``. One undo step. Returns how many changed."""

    document = session.document
    if not pairs:
        return 0
    with session.log.transaction("Bind fields by name") as txn:
        for object_name, column in pairs:
            ids = document.by_name(object_name)
            if not ids:
                continue
            txn.execute(SetLogic(ids[0], "cbcsBind", column))
    return len(pairs)


def insert_column_field(session: object, column: object) -> object:
    """Insert a labelled field bound to ``column``. One undo step. Returns the field id."""

    document = session.document
    source = record_source(document)
    if source is None:
        raise CommandRejected("Connect this form to a table first.")
    layout = document.root.layout
    if layout is None:
        raise CommandRejected("This form has no layout to put the field in.")
    engine = column_engine(document, source, session)
    class_name, kind = widget_class_for(column, engine)
    name = str(getattr(column, "name", "") or "")
    caption = caption_for(name)
    own_text = class_name in _OWN_TEXT
    spec = _field_spec(
        class_name,
        name,
        text=caption[:-1] if own_text and caption.endswith(":") else None,
        max_length=getattr(kind, "max_length", None),
    )
    with session.log.transaction("Bind %s" % name) as txn:
        if layout.class_name == "QFormLayout":
            label_id, field_id = txn.execute(
                InsertFormRow(layout.id, _next_row(layout), fragment=Fragment((spec,)))
            )
            if label_id != field_id:
                txn.execute(SetProperty(label_id, "text", StringValue(caption)))
        else:
            field_id = _insert_labelled(txn, document, layout, spec, name, caption, own_text)
        txn.execute(SetLogic(field_id, "cbcsBind", name))
        if getattr(kind, "read_only", False):
            txn.execute(SetLogic(field_id, "cbcsBindMode", "readOnly"))
    return field_id


def bind_or_insert(session: object, column: object, node_id: object = None) -> str:
    """Drop a column. Returns a sentence when the field cannot show it, else ``""``."""

    from app.features.form_builder.engine.data.checks.binding_fit import compatible, mismatch_sentence

    document = session.document
    if node_id is not None and document.contains(node_id):
        node = document.node(node_id)
        if isinstance(node, WidgetNode) and node.class_name in _field_classes() and node.id != document.root.id:
            source = record_source(document)
            engine = column_engine(document, source, session) if source is not None else "sqlite"
            _class_name, kind = widget_class_for(column, engine)
            from app.features.form_builder.qtside.data_panel.model import kind_name

            if compatible(kind.direction, node.class_name, kind_name(node)):
                bind_field(session, node.id, str(column.name))
                return ""
            return mismatch_sentence(kind.words, node.class_name)
    insert_column_field(session, column)
    return ""


def insert_record_toolbar(session: object) -> None:
    """The ten record controls, in one undo step. Delete has no Ask step."""

    document = session.document
    layout = document.root.layout
    if layout is None:
        raise CommandRejected("This form has no layout to put the toolbar in.")
    bar = _toolbar_spec()
    placement = _toolbar_placement(layout)
    with session.log.transaction("Add record toolbar") as txn:
        result = txn.execute(InsertFragment(placement, Fragment((bar,)), undo_label="Add record toolbar"))
        mapping = dict(result.renames)
        for name, _class_name, _text, _shortcut, formula, verb in _BAR:
            final = mapping.get(name, name)
            ids = document.by_name(final)
            if not ids:
                continue
            if formula:
                txn.execute(SetLogic(ids[0], "cbcsEnabledWhen", formula))
            if name == "positionLabel":
                txn.execute(SetLogic(ids[0], "cbcsValue", _POSITION))
            if verb:
                txn.execute(
                    SetEventSteps(
                        final,
                        "clicked",
                        (EventStep(verb, raw=Step(verb)),),
                        caption="Add record toolbar",
                    )
                )


def proposals(session: object) -> Tuple[Tuple[str, str], ...]:
    source = record_source(session.document)
    if source is None:
        return ()
    return tuple(match_by_name(session.document, source))


def assign_hook(session: object, field: str, method: str, surface: object = None) -> str:
    """Store the hook. A window file gets the stub through the M6 method path.

    Returns a sentence when the file could not be written and only the form changed.
    """

    source = record_source(session.document)
    if source is None:
        raise CommandRejected("Connect this form to a table first.")
    updated = _with_hook(source, field, method)
    command = SetLogic(session.document.root.id, "cbcsData", write_data(updated))
    params = ""
    for key, _label, default, extra in HOOK_ROWS:
        if key == field:
            params = extra
            break
    label = "Create %s" % method if method else "Clear hook"
    if method and surface is not None:
        outcome = _make_method(surface, label, command, method, params, session)
        if outcome is True:
            return ""
        if outcome:
            note = outcome
        else:
            note = ""
    else:
        note = "" if surface is None or not method else "The window file was not changed."
    with session.log.transaction(label) as txn:
        txn.execute(command)
    return note


@dataclass(frozen=True)
class _HookRequest:
    label: str
    commands: Tuple[object, ...]
    method: str
    params: str
    sender: str = ""
    event_words: str = ""


def _make_method(surface: object, label: str, command: object, method: str, params: str, session: object) -> object:
    from app.features.form_builder.qtside.pickers import method_actions

    service = method_actions()
    make = getattr(service, "make_method", None)
    if not callable(make):
        return "The window-file path is not available, so only the hook name was stored."
    root = session.document.root
    request = _HookRequest(
        label,
        (command,),
        method,
        params,
        getattr(root, "object_name", "") or "",
        label,
    )
    try:
        outcome = make(surface, request)
    except Exception:
        return "The window file was not changed, so only the hook name was stored."
    if getattr(outcome, "ok", False):
        return True
    return getattr(outcome, "reason", "") or "The window file was not changed, so only the hook name was stored."


def _with_hook(source: RecordSource, field: str, method: str) -> RecordSource:
    current = source.hooks or Hooks()
    updated = replace(current, **{field: method})
    hooks: Optional[Hooks] = None if updated == Hooks() else updated
    return replace(source, hooks=hooks)


def _field_classes():
    from app.features.form_builder.qtside.data_panel.model import FIELD_CLASSES

    return FIELD_CLASSES


def _field_spec(class_name: str, object_name: str, text: Optional[str], max_length: Optional[int]) -> NodeSpec:
    props = []
    if text:
        props.append(PropertyEntry("property", "text", StringValue(text)))
    if max_length and class_name == "QLineEdit":
        props.append(PropertyEntry("property", "maxLength", NumberValue(int(max_length))))
    return NodeSpec(
        "widget",
        None,
        (("class_name", class_name), ("object_name", object_name)),
        tuple(props),
    )


def _insert_labelled(txn: object, document: object, layout: LayoutNode, spec: NodeSpec, name: str, caption: str, own_text: bool) -> object:
    if own_text:
        fragment = Fragment((spec,))
    else:
        label = NodeSpec(
            "widget",
            None,
            (("class_name", "QLabel"), ("object_name", name + "Label")),
            (PropertyEntry("property", "text", StringValue(caption)),),
        )
        fragment = Fragment((_row_layout(name + "Row", (label, spec)),))
    result = txn.execute(InsertFragment(_box_placement(layout), fragment, undo_label="Bind %s" % name))
    mapping = dict(result.renames)
    final = mapping.get(name, name)
    ids = document.by_name(final)
    if not ids:
        raise CommandRejected("The field could not be added.")
    if not own_text:
        label_name = mapping.get(name + "Label", name + "Label")
        label_ids = document.by_name(label_name)
        if label_ids:
            txn.execute(SetLabelBuddy(label_ids[0], final, caption))
    return ids[0]


def _row_layout(object_name: str, widgets: Sequence[NodeSpec]) -> NodeSpec:
    items = tuple(
        NodeSpec("layoutitem", None, (), (), (), (("content", (widget,)),)) for widget in widgets
    )
    return NodeSpec(
        "layout",
        None,
        (("class_name", "QHBoxLayout"), ("object_name", object_name)),
        tuple(PropertyEntry("property", margin, NumberValue(0)) for margin in _MARGINS),
        (),
        (("layout_items", items),),
    )


def _box_placement(layout: LayoutNode):
    index = len(layout.items)
    if layout.class_name == "QGridLayout":
        return InGridCell(layout.id, _next_row(layout), 0, colspan=2, mode="insert_row")
    if layout.class_name == "QFormLayout":
        return InFormRow(layout.id, _next_row(layout), "spanning", True)
    return InBoxLayout(layout.id, index)


def _toolbar_spec() -> NodeSpec:
    widgets = []
    for name, class_name, text, shortcut, _formula, _verb in _BAR:
        props = [PropertyEntry("property", "text", StringValue(text))]
        if shortcut:
            props.append(PropertyEntry("property", "shortcut", StringValue(shortcut)))
        widgets.append(
            NodeSpec(
                "widget",
                None,
                (("class_name", class_name), ("object_name", name)),
                tuple(props),
            )
        )
    return _row_layout("recordBar", widgets)


def _toolbar_placement(layout: LayoutNode):
    at_end = _ends_with_buttons(layout)
    if layout.class_name == "QFormLayout":
        row = _next_row(layout) if at_end else 0
        return InFormRow(layout.id, row, "spanning", True)
    if layout.class_name == "QGridLayout":
        row = _next_row(layout) if at_end else 0
        return InGridCell(layout.id, row, 0, colspan=2, mode="insert_row")
    index = len(layout.items) if at_end else 0
    return InBoxLayout(layout.id, index)


def _ends_with_buttons(layout: LayoutNode) -> bool:
    items = layout.items
    if not items:
        return False
    if layout.class_name in ("QFormLayout", "QGridLayout"):
        last = max(item.row or 0 for item in items)
        contents = [item.content for item in items if item.row == last]
    else:
        contents = [items[-1].content]
    useful = [node for node in contents if node is not None]
    return bool(useful) and all(_buttonish(node) for node in useful)


def _buttonish(node: object) -> bool:
    if isinstance(node, WidgetNode) and node.class_name in _BUTTONS:
        return True
    if isinstance(node, LayoutNode) and node.class_name == "QHBoxLayout":
        kids = [item.content for item in node.items]
        return bool(kids) and all(isinstance(kid, WidgetNode) and kid.class_name in _BUTTONS for kid in kids)
    return False


def _next_row(layout: LayoutNode) -> int:
    rows = [item.row for item in layout.items if isinstance(item.row, int)]
    if not rows:
        return 0
    return max(rows) + 1


def already_bound(session: object, column: str) -> str:
    return bind_text_of(session, column)


def bind_text_of(session: object, column: str) -> str:
    from app.features.form_builder.qtside.data_panel.model import bound_field

    return bound_field(session.document, column)


def default_record_word(table: str) -> str:
    return singular(table)
