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
#: Templates the user saved (UX-TMPL-004). The first group on Start, shown when there is one.
GROUP_YOURS = "yours"


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
            "Labels and fields.",
            GROUP_TEMPLATES,
            "QWidget",
            True,
            "nameEdit",
        ),
        FormTemplate(
            "list_detail",
            "List and detail",
            "A list beside one item.",
            GROUP_TEMPLATES,
            "QWidget",
            True,
            "itemList",
        ),
        FormTemplate(
            "table_search",
            "Table with search",
            "Search above a table.",
            GROUP_TEMPLATES,
            "QWidget",
            True,
            "searchEdit",
        ),
        FormTemplate(
            "dialog_ok_cancel",
            "Dialog with OK and Cancel",
            "Fields, OK and Cancel.",
            GROUP_TEMPLATES,
            "QDialog",
            True,
            "nameEdit",
        ),
        FormTemplate(
            "dialog_buttons_right",
            "Dialog with side buttons",
            "Fields, buttons at the side.",
            GROUP_TEMPLATES,
            "QDialog",
            True,
            "nameEdit",
        ),
        FormTemplate(
            "widget",
            "Widget",
            "Empty vertical layout.",
            GROUP_BLANK,
            "QWidget",
            True,
            None,
        ),
        FormTemplate(
            "main_window",
            "Main window",
            "Empty central area.",
            GROUP_BLANK,
            "QMainWindow",
            True,
            None,
        ),
        FormTemplate(
            "dialog",
            "Dialog",
            "Empty dialog layout.",
            GROUP_BLANK,
            "QDialog",
            True,
            None,
        ),
        FormTemplate(
            "from_table",
            "Build a form from a table",
            "Fields from a table.",
            GROUP_FROM_EXISTING,
            "QWidget",
            False,
            None,
        ),
        FormTemplate(
            "adopt",
            "Adopt a form your code already loads",
            "Use a form the app opens.",
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
        connections=(
            ("buttonBox", "accepted()", class_name, "accept()"),
            ("buttonBox", "rejected()", class_name, "reject()"),
        ),
    )


def _dialog_buttons_right(class_name: str) -> str:
    """UX-TMPL-005: the content area, then a vertical OK and Cancel box wired to accept and reject."""
    rows = (
        ("nameLabel", "Name", "nameEdit", "QLineEdit"),
        ("emailLabel", "Email", "emailEdit", "QLineEdit"),
    )
    buttons = (
        "    <widget class=\"QDialogButtonBox\" name=\"buttonBox\">\n"
        "     <property name=\"orientation\">\n"
        "      <enum>Qt::Orientation::Vertical</enum>\n"
        "     </property>\n"
        "     <property name=\"standardButtons\">\n"
        "      <set>QDialogButtonBox::StandardButton::Cancel|QDialogButtonBox::StandardButton::Ok</set>\n"
        "     </property>\n"
        "    </widget>\n"
    )
    inner = (
        '  <layout class="QHBoxLayout" name="horizontalLayout">\n'
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
        connections=(
            ("buttonBox", "accepted()", class_name, "accept()"),
            ("buttonBox", "rejected()", class_name, "reject()"),
        ),
    )


def _blank(root_class: str):
    def build(class_name: str) -> str:
        inner = '  <layout class="QVBoxLayout" name="verticalLayout"/>\n'
        return form_document(class_name, root_class, inner)

    return build


def _main_window(class_name: str) -> str:
    inner = (
        '  <widget class="QMenuBar" name="menubar"/>\n'
        '  <widget class="QWidget" name="centralwidget">\n'
        '   <layout class="QVBoxLayout" name="verticalLayout"/>\n'
        "  </widget>\n"
        '  <widget class="QStatusBar" name="statusbar"/>\n'
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


# The "Qt app with a form" project's window: a labelled field, space below it,
# and a right-aligned Save button wired to a stub in the window class.
_APP_WINDOW_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<ui version="4.0">\n'
    " <class>%s</class>\n"
    ' <widget class="QMainWindow" name="%s">\n'
    '  <property name="windowTitle"><string>%s</string></property>\n'
    '  <widget class="QWidget" name="central">\n'
    '   <layout class="QVBoxLayout" name="verticalLayout">\n'
    "    <item>\n"
    '     <layout class="QFormLayout" name="formLayout">\n'
    '      <item row="0" column="0">\n'
    '       <widget class="QLabel" name="nameLabel">\n'
    '        <property name="text"><string>Name</string></property>\n'
    '        <property name="buddy"><cstring>nameEdit</cstring></property>\n'
    "       </widget>\n"
    "      </item>\n"
    '      <item row="0" column="1">\n'
    '       <widget class="QLineEdit" name="nameEdit"/>\n'
    "      </item>\n"
    "     </layout>\n"
    "    </item>\n"
    "    <item>\n"
    '     <spacer name="verticalSpacer">\n'
    '      <property name="orientation"><enum>Qt::Vertical</enum></property>\n'
    '      <property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property>\n'
    "     </spacer>\n"
    "    </item>\n"
    "    <item>\n"
    '     <layout class="QHBoxLayout" name="buttonRow">\n'
    "      <item>\n"
    '       <spacer name="horizontalSpacer">\n'
    '        <property name="orientation"><enum>Qt::Horizontal</enum></property>\n'
    '        <property name="sizeHint" stdset="0"><size><width>40</width><height>20</height></size></property>\n'
    "       </spacer>\n"
    "      </item>\n"
    "      <item>\n"
    '       <widget class="QPushButton" name="saveButton">\n'
    '        <property name="text"><string>Save</string></property>\n'
    "       </widget>\n"
    "      </item>\n"
    "     </layout>\n"
    "    </item>\n"
    "   </layout>\n"
    "  </widget>\n"
    '  <widget class="QStatusBar" name="statusBar">\n'
    '   <property name="currentMessage" stdset="0"><string>Ready</string></property>\n'
    "  </widget>\n"
    " </widget>\n"
    " <connections>\n"
    "  <connection>\n"
    "   <sender>saveButton</sender>\n"
    "   <signal>clicked()</signal>\n"
    "   <receiver>%s</receiver>\n"
    "   <slot>save_clicked()</slot>\n"
    "  </connection>\n"
    " </connections>\n"
    " <slots>\n"
    "  <slot>save_clicked()</slot>\n"
    " </slots>\n"
    "</ui>\n"
)



def _app_window(class_name: str) -> str:
    """The qt_app_with_form project's window; not a New form card."""
    return _APP_WINDOW_TEMPLATE % (class_name, class_name, "Main window", class_name)


_BUILDERS = {
    "data_entry": _data_entry,
    "list_detail": _list_detail,
    "table_search": _table_search,
    "dialog_ok_cancel": _dialog_ok_cancel,
    "dialog_buttons_right": _dialog_buttons_right,
    "widget": _blank("QWidget"),
    "dialog": _blank("QDialog"),
    "main_window": _main_window,
    "app_window": _app_window,
}
