"""Apply a form-from-a-table plan through the Data-tab editors.

One ``session.log.transaction`` per file. Nested inserts join that step,
so undo removes the fields, the lines, the toolbar, and the binding together.
"""

from __future__ import annotations

import os
from typing import List, Tuple

from app.features.form_builder.engine.commands.catalog import MorphWidget, SetProperty
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.data.schema import Schema
from app.features.form_builder.engine.data.schema_cache import install_schema_reader
from app.features.form_builder.engine.data.source import ListSource, RecordSource
from app.features.form_builder.engine.logic.codec import Step
from app.features.form_builder.engine.logic.events_codec import EventStep
from app.features.form_builder.engine.project.form_xml import form_document
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.project.from_table_plan import FormPlan, PlannedForms, TableRequest, plan_forms
from app.features.form_builder.engine.project.names import class_name_for_stem
from app.features.form_builder.engine.project.table_form import four_digit_year_format
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import NumberValue, SizePolicyValue, StringValue
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.data_panel.edits import (
    connect_form,
    insert_column_field,
    insert_record_toolbar,
)
from app.features.form_builder.qtside.data_panel.lines_sheet import add_lines
from app.features.form_builder.qtside.data_panel.listing_edits import save_list

_DATE_WIDGETS = frozenset({"QDateEdit", "QDateTimeEdit"})
_MARGINS = ("leftMargin", "topMargin", "rightMargin", "bottomMargin")


def render_plans(request: TableRequest, schema: Schema, project_root: str) -> Tuple[Tuple[str, str], ...]:
    """``(stem, .ui text)`` for each file. Each text is one undo step."""

    planned = plan_forms(request, schema)
    if planned.disabled_reason or not planned.forms:
        return ()
    made: List[Tuple[str, str]] = []
    for plan in planned.forms:
        made.append((plan.stem, render_plan(plan, schema, project_root)))
    return tuple(made)


def render_plan(plan: FormPlan, schema: Schema, project_root: str) -> str:
    session = open_plan(plan, schema, project_root)
    try:
        return write_ui(session.document).text
    finally:
        session.dispose()


def open_plan(plan: FormPlan, schema: Schema, project_root: str) -> FormSession:
    """The session that built ``plan``. Its undo stack has one entry."""

    root = os.path.abspath(project_root) if project_root else ""
    forms = os.path.join(root, "forms") if root else ""
    path = os.path.join(forms, plan.stem + ".ui") if forms else plan.stem + ".ui"
    skeleton = empty_form(class_name_for_stem(plan.stem))
    scope = FormScope(
        kind="project" if root else "external",
        ui_path=path,
        project_root=root or None,
        generated_path=os.path.join(forms, "ui_%s.py" % plan.stem) if forms else None,
        window_path=os.path.join(forms, "%s_window.py" % plan.stem) if forms else None,
        module_name="forms.ui_%s" % plan.stem if root else None,
    )
    session = FormSession.open(skeleton, path=path, scope=scope)
    apply_plan(session, plan, schema)
    return session


def apply_plan(session: FormSession, plan: FormPlan, schema: Schema) -> None:
    root = session.scope.project_root or ""
    if root:
        install_schema_reader(root)
    with session.log.transaction(plan.undo_label) as txn:
        if plan.kind == "list" and isinstance(plan.source, ListSource):
            _list_chrome(txn, session, plan.placeholder)
            save_list(session, plan.source, plan.undo_label)
            return
        if not isinstance(plan.source, RecordSource):
            return
        connect_form(session, plan.source)
        insert_record_toolbar(session)
        for column, choice in zip(plan.columns, plan.choices):
            field_id = insert_column_field(session, column)
            _face(txn, session, field_id, choice.label, choice.shows_as, plan.date_format)
        if plan.lines is not None:
            add_lines(session, plan.lines)


def empty_form(class_name: str) -> str:
    inner = '  <layout class="QVBoxLayout" name="verticalLayout"/>\n'
    return form_document(class_name, "QWidget", inner)


def planned_or_reason(request: TableRequest, schema: Schema) -> PlannedForms:
    return plan_forms(request, schema)


def _face(txn: object, session: FormSession, field_id: object, label: str, shows_as: str, date_format: str) -> None:
    document = session.document
    node = document.node(field_id) if document.contains(field_id) else None
    if isinstance(node, WidgetNode) and shows_as and node.class_name != shows_as:
        txn.execute(MorphWidget(field_id, shows_as))
        node = document.node(field_id)
    name = node.object_name if isinstance(node, WidgetNode) else ""
    if name and label:
        labels = document.by_name(name + "Label")
        if labels:
            txn.execute(SetProperty(labels[0], "text", StringValue(label)))
    if isinstance(node, WidgetNode) and node.class_name in _DATE_WIDGETS:
        pattern = four_digit_year_format(date_format)
        if node.class_name == "QDateTimeEdit" and "h" not in pattern.lower():
            pattern = pattern + " hh:mm"
        txn.execute(SetProperty(node.id, "displayFormat", StringValue(pattern)))


def _list_chrome(txn: object, session: FormSession, placeholder: str) -> None:
    document = session.document
    layout = document.root.layout
    if layout is None:
        return
    from app.features.form_builder.engine.commands.catalog import InsertFragment
    from app.features.form_builder.engine.commands.placement import InBoxLayout

    search = _widget(
        "QLineEdit",
        "searchEdit",
        (PropertyEntry("property", "placeholderText", StringValue(placeholder)),),
    )
    table = _widget(
        "QTableView",
        "resultTable",
        (PropertyEntry("property", "sizePolicy", SizePolicyValue("Expanding", "Expanding")),),
    )
    buttons = _button_row()
    fragment = Fragment((search, table, buttons))
    txn.execute(InsertFragment(InBoxLayout(layout.id, 0), fragment, undo_label="List screen"))
    for name, which in (("newButton", "new"), ("openButton", "selected")):
        step = Step("openRecord", fields=(("which", which),))
        txn.execute(
            SetEventSteps(
                name,
                "clicked",
                (EventStep("openRecord", raw=step),),
                caption="Open record form (%s)" % which,
            )
        )


def _widget(class_name: str, object_name: str, props: Tuple[PropertyEntry, ...]) -> NodeSpec:
    return NodeSpec("widget", None, (("class_name", class_name), ("object_name", object_name)), props)


def _button_row() -> NodeSpec:
    new_button = _widget("QPushButton", "newButton", (PropertyEntry("property", "text", StringValue("New")),))
    open_button = _widget("QPushButton", "openButton", (PropertyEntry("property", "text", StringValue("Open")),))
    items = tuple(
        NodeSpec("layoutitem", None, (), (), (), (("content", (widget,)),))
        for widget in (new_button, open_button)
    )
    return NodeSpec(
        "layout",
        None,
        (("class_name", "QHBoxLayout"), ("object_name", "listButtons")),
        tuple(PropertyEntry("property", margin, NumberValue(0)) for margin in _MARGINS),
        (),
        (("layout_items", items),),
    )
