"""Built-in form templates. Stdlib and the engine only.

Each template is already inside a layout, so the window resize moves the
fields. Object names say what they hold (``nameEdit``), never ``label_2``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from app.features.form_builder.engine.project.form_xml import (
    form_document,
    form_row,
    string_property,
    tabstop_block,
)

GROUP_TEMPLATES = "templates"
GROUP_BLANK = "blank"
GROUP_FROM_EXISTING = "from_existing"


@dataclass(frozen=True)
class FormTemplate:
    """One card on the New form tab, except the two that open another flow."""

    key: str
    title: str
    description: str
    group: str
    root_class: str
    creates_immediately: bool
    first_widget: Optional[str]


def _templates() -> Tuple[FormTemplate, ...]:
    return (
        FormTemplate(
            "data_entry",
            "Data entry form",
            "Labels and fields in a form layout.",
            GROUP_TEMPLATES,
            "QWidget",
            True,
            "nameEdit",
        ),
        FormTemplate(
            "list_detail",
            "List and detail",
            "A list beside the fields for one item.",
            GROUP_TEMPLATES,
            "QWidget",
            True,
            "itemList",
        ),
        FormTemplate(
            "table_search",
            "Table with search",
            "A search box above a table.",
            GROUP_TEMPLATES,
            "QWidget",
            True,
            "searchEdit",
        ),
        FormTemplate(
            "dialog_ok_cancel",
            "Dialog with OK and Cancel",
            "Fields and a button box.",
            GROUP_TEMPLATES,
            "QDialog",
            True,
            "nameEdit",
        ),
        FormTemplate(
            "widget",
            "Widget",
            "An empty form with a vertical layout.",
            GROUP_BLANK,
            "QWidget",
            True,
            None,
        ),
        FormTemplate(
            "main_window",
            "Main window",
            "A main window with an empty central layout.",
            GROUP_BLANK,
            "QMainWindow",
            True,
            None,
        ),
        FormTemplate(
            "dialog",
            "Dialog",
            "An empty dialog with a vertical layout.",
            GROUP_BLANK,
            "QDialog",
            True,
            None,
        ),
        FormTemplate(
            "from_table",
            "Build a form from a table",
            "Fields from a SQLite table.",
            GROUP_FROM_EXISTING,
            "QWidget",
            False,
            None,
        ),
        FormTemplate(
            "adopt",
            "Adopt a form your code already loads",
            "Keep a .ui file that your app already opens.",
            GROUP_FROM_EXISTING,
            "QWidget",
            False,
            None,
        ),
    )


_BY_KEY: Dict[str, FormTemplate] = {item.key: item for item in _templates()}


def template_catalog() -> Tuple[FormTemplate, ...]:
    """Cards in Start-screen order."""
    return _templates()


def template_keys() -> Tuple[str, ...]:
    """Keys ``create_form`` accepts. Adopt and from-table are not files yet."""
    return tuple(item.key for item in _templates() if item.creates_immediately)


def template_for(key: str) -> Optional[FormTemplate]:
    return _BY_KEY.get(key)


def first_useful_widget(key: str) -> Optional[str]:
    """Object name to select after create. None means the root widget."""
    item = _BY_KEY.get(key)
    if item is None:
        return None
    return item.first_widget


def build_template_ui(key: str, class_name: str) -> str:
    """Writer-canonical ``.ui`` text for ``key``.

    Raises ``KeyError`` for adopt and from-table, which are not documents.
    """
    builder = _BUILDERS.get(key)
    if builder is None:
        raise KeyError(key)
    return builder(class_name)


def _data_entry(class_name: str) -> str:
    rows = (
        ("nameLabel", "Name", "nameEdit", "QLineEdit"),
        ("emailLabel", "Email", "emailEdit", "QLineEdit"),
        ("notesLabel", "Notes", "notesEdit", "QPlainTextEdit"),
    )
    inner = _form("formLayout", rows)
    stops = tabstop_block(("nameEdit", "emailEdit", "notesEdit"))
    return form_document(class_name, "QWidget", inner, tabstops=stops)


def _list_detail(class_name: str) -> str:
    rows = (
        ("nameLabel", "Name", "nameEdit", "QLineEdit"),
        ("emailLabel", "Email", "emailEdit", "QLineEdit"),
        ("notesLabel", "Notes", "notesEdit", "QPlainTextEdit"),
    )
    detail = (
        '    <widget class="QWidget" name="detailPanel">\n'
        "%s"
        "    </widget>\n"
    ) % _form("formLayout", rows, indent="  ")
    inner = (
        '  <layout class="QHBoxLayout" name="horizontalLayout" stretch="1,2">\n'
        "   <item>\n"
        '    <widget class="QListWidget" name="itemList"/>\n'
        "   </item>\n"
        "   <item>\n"
        "%s"
        "   </item>\n"
        "  </layout>\n"
    ) % detail
    stops = tabstop_block(("itemList", "nameEdit", "emailEdit", "notesEdit"))
    return form_document(class_name, "QWidget", inner, tabstops=stops)


def _table_search(class_name: str) -> str:
    search = string_property("placeholderText", "Search")
    inner = (
        '  <layout class="QVBoxLayout" name="verticalLayout">\n'
        "   <item>\n"
        '    <widget class="QLineEdit" name="searchEdit">\n'
        "%s"
        "    </widget>\n"
        "   </item>\n"
        "   <item>\n"
        '    <widget class="QTableView" name="resultTable"/>\n'
        "   </item>\n"
        "  </layout>\n"
    ) % search
    return form_document(
        class_name,
        "QWidget",
        inner,
        tabstops=tabstop_block(("searchEdit", "resultTable")),
    )


def _dialog_ok_cancel(class_name: str) -> str:
    rows = (
        ("nameLabel", "Name", "nameEdit", "QLineEdit"),
        ("emailLabel", "Email", "emailEdit", "QLineEdit"),
    )
    buttons = (
        "    <widget class=\"QDialogButtonBox\" name=\"buttonBox\">\n"
        "     <property name=\"standardButtons\">\n"
        "      <set>QDialogButtonBox::StandardButton::Cancel|QDialogButtonBox::StandardButton::Ok</set>\n"
        "     </property>\n"
        "    </widget>\n"
    )
    inner = (
        '  <layout class="QVBoxLayout" name="verticalLayout">\n'
        "   <item>\n"
        "%s"
        "   </item>\n"
        "   <item>\n"
        "%s"
        "   </item>\n"
        "  </layout>\n"
    ) % (_form("formLayout", rows, indent="  "), buttons)
    return form_document(
        class_name,
        "QDialog",
        inner,
        tabstops=tabstop_block(("nameEdit", "emailEdit", "buttonBox")),
    )


def _blank(root_class: str):
    def build(class_name: str) -> str:
        inner = '  <layout class="QVBoxLayout" name="verticalLayout"/>\n'
        return form_document(class_name, root_class, inner)

    return build


def _main_window(class_name: str) -> str:
    inner = (
        '  <widget class="QWidget" name="centralwidget">\n'
        '   <layout class="QVBoxLayout" name="verticalLayout"/>\n'
        "  </widget>\n"
    )
    return form_document(class_name, "QMainWindow", inner)


def _form(layout_name: str, rows: tuple, indent: str = "") -> str:
    body = []
    for index, (label_name, label_text, widget_name, widget_class) in enumerate(rows):
        body.append(
            form_row(index, label_name, label_text, widget_name, widget_class, widget_name)
        )
    pad = indent
    text = (
        '%s  <layout class="QFormLayout" name="%s">\n'
        "%s"
        "%s  </layout>\n"
    ) % (pad, layout_name, "".join(body), pad)
    if not pad:
        return text
    return "".join(pad + line if line else line for line in text.splitlines(keepends=True))


_BUILDERS = {
    "data_entry": _data_entry,
    "list_detail": _list_detail,
    "table_search": _table_search,
    "dialog_ok_cancel": _dialog_ok_cancel,
    "widget": _blank("QWidget"),
    "dialog": _blank("QDialog"),
    "main_window": _main_window,
}
