"""Starter documents."""

from __future__ import annotations

from spikes.form_builder.mapping import ColumnPlan
from spikes.form_builder.model import (
    Action,
    ActionRef,
    Document,
    Widget,
    blank_widget,
    make_item,
    make_layout,
    make_spacer,
    make_widget,
    prop_cstring,
    prop_enum,
    prop_set,
    prop_string,
    set_attribute,
    set_property,
    unique_name,
)


def _title(doc: Document, text: str) -> None:
    set_property(doc.root, prop_string("windowTitle", text), "windowTitle")


def _form_row(doc, layout, row: int, label_text: str, field: Widget, required: bool = False) -> None:
    label = make_widget(doc, "QLabel")
    text = label_text + (" *" if required else "")
    label.body.append(prop_string("text", text))
    label.body.append(prop_cstring("buddy", field.object_name))
    layout.body.append(make_item(doc, label, row=str(row), column="0"))
    layout.body.append(make_item(doc, field, row=str(row), column="1"))


def _button_box(doc, layout, row: int) -> None:
    box = make_widget(doc, "QDialogButtonBox")
    box.body.append(prop_set("standardButtons", "QDialogButtonBox::Cancel|QDialogButtonBox::Ok"))
    layout.body.append(make_item(doc, box, row=str(row), column="0", colspan="2"))


def data_entry() -> Document:
    doc = blank_widget("QWidget", "DataEntry")
    _title(doc, "Data entry")
    layout = make_layout(doc, "QFormLayout")
    doc.root.body.append(layout)
    name = make_widget(doc, "QLineEdit", "name")
    name.body.append(prop_string("placeholderText", "Full name"))
    email = make_widget(doc, "QLineEdit", "email")
    notes = make_widget(doc, "QPlainTextEdit", "notes")
    _form_row(doc, layout, 0, "Name", name, True)
    _form_row(doc, layout, 1, "Email", email)
    _form_row(doc, layout, 2, "Notes", notes)
    _button_box(doc, layout, 3)
    _tabstops(doc, ["name", "email", "notes"])
    return doc


def list_detail() -> Document:
    doc = blank_widget("QWidget", "ListDetail")
    _title(doc, "List and detail")
    splitter = make_widget(doc, "QSplitter", "splitter")
    splitter.body.append(prop_enum("orientation", "Qt::Horizontal"))
    listing = make_widget(doc, "QListWidget", "records")
    detail = make_widget(doc, "QWidget", "detail")
    form = make_layout(doc, "QFormLayout")
    detail.body.append(form)
    title = make_widget(doc, "QLineEdit", "title")
    _form_row(doc, form, 0, "Title", title, True)
    splitter.body.extend([listing, detail])
    outer = make_layout(doc, "QVBoxLayout")
    doc.root.body.append(outer)
    outer.body.append(make_item(doc, splitter))
    return doc


def table_search() -> Document:
    doc = blank_widget("QWidget", "TableSearch")
    _title(doc, "Table")
    layout = make_layout(doc, "QVBoxLayout")
    doc.root.body.append(layout)
    search = make_widget(doc, "QLineEdit", "search")
    search.body.append(prop_string("placeholderText", "Search"))
    table = make_widget(doc, "QTableWidget", "results")
    layout.body.append(make_item(doc, search))
    layout.body.append(make_item(doc, table))
    return doc


def dialog_buttons() -> Document:
    doc = blank_widget("QDialog", "Dialog")
    _title(doc, "Dialog")
    layout = make_layout(doc, "QFormLayout")
    doc.root.body.append(layout)
    field = make_widget(doc, "QLineEdit", "value")
    _form_row(doc, layout, 0, "Value", field, True)
    _button_box(doc, layout, 1)
    return doc


def blank_main_window() -> Document:
    doc = blank_widget("QMainWindow", "MainWindow")
    _title(doc, "Main window")
    central = make_widget(doc, "QWidget", "centralwidget")
    layout = make_layout(doc, "QVBoxLayout")
    central.body.append(layout)
    layout.body.append(make_item(doc, make_spacer(doc, "Qt::Vertical")))
    menu_bar = make_widget(doc, "QMenuBar", "menubar")
    menu = make_widget(doc, "QMenu", "menuFile")
    menu.body.append(prop_string("title", "File"))
    action = Action(id=doc.alloc(), name="actionQuit")
    action.body.append(prop_string("text", "Quit"))
    doc.root.body.append(action)
    menu.body.append(ActionRef("actionQuit"))
    menu_bar.body.append(menu)
    menu_bar.body.append(ActionRef("menuFile"))
    toolbar = make_widget(doc, "QToolBar", "toolBar")
    toolbar.body.append(ActionRef("actionQuit"))
    status = make_widget(doc, "QStatusBar", "statusbar")
    doc.root.body.extend([central, menu_bar, toolbar, status])
    return doc


def from_columns(table: str, columns: list[ColumnPlan]) -> Document:
    class_name = "".join(part.capitalize() for part in table.split("_")) or "Form"
    doc = blank_widget("QWidget", class_name)
    _title(doc, table.replace("_", " ").title())
    layout = make_layout(doc, "QFormLayout")
    doc.root.body.append(layout)
    names = []
    for index, column in enumerate(columns):
        field = make_widget(doc, column.widget, column.name)
        if column.widget == "QLineEdit":
            field.body.append(prop_string("placeholderText", column.name.replace("_", " ")))
        if column.widget == "QComboBox":
            from spikes.form_builder.model import ItemEntry, Property, XmlNode

            field.body.append(ItemEntry(body=[Property({"name": "text"}, XmlNode("string", {}, ""))]))
        label = column.name.replace("_", " ").capitalize()
        _form_row(doc, layout, index, label, field, column.required_marker)
        names.append(column.name)
    _button_box(doc, layout, len(columns))
    _tabstops(doc, names)
    return doc


def _tabstops(doc: Document, names: list[str]) -> None:
    from spikes.form_builder.model import ensure_tabstops

    ensure_tabstops(doc).names = list(names)
