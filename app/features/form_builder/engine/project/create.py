"""Create a form from a template stem, then generate its Python files."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple
from xml.sax.saxutils import escape as xml_escape

from app.features.form_builder.engine.diagnostics import FormDiagnostic
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.adoption import scope_for
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.project.fs import (
    Journal,
    OsFileSystem,
    ProjectOpError,
    inside_project,
)
from app.features.form_builder.engine.project.names import explain_form_name
from app.features.form_builder.engine.project.save import write_generated
from app.features.form_builder.engine.ui4.reader import read_ui

_TEMPLATES = {
    "widget": "QWidget",
    "dialog": "QDialog",
    "main_window": "QMainWindow",
    "app_window": "QMainWindow",
}
_WINDOW_TITLE = re.compile(
    r'(<property name="windowTitle"><string(?:\s[^>]*)?>)(.*?)(</string></property>)',
    re.DOTALL,
)
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

# Start blank: an empty main window with its central widget.
_MAIN_WINDOW_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<ui version="4.0">\n'
    " <class>%s</class>\n"
    ' <widget class="QMainWindow" name="%s">\n'
    '  <property name="windowTitle"><string>%s</string></property>\n'
    '  <widget class="QWidget" name="central"/>\n'
    " </widget>\n"
    "</ui>\n"
)


@dataclass(frozen=True)
class CreateResult:
    """``files`` is every path this call created. ``refused`` explains why none were."""

    files: Tuple[str, ...]
    diagnostics: Tuple[FormDiagnostic, ...]
    scope: Optional[FormScope]
    refused: Optional[str]


def create_form(
    project_root: str,
    stem: str,
    fs: OsFileSystem,
    *,
    template: str = "widget",
    directory: Optional[str] = None,
    title: Optional[str] = None,
) -> CreateResult:
    """Write ``<stem>.ui``, generate ``ui_<stem>.py``, and create the window once."""
    root = os.path.abspath(project_root)
    folder = os.path.abspath(directory) if directory else os.path.join(root, "forms")
    if not inside_project(folder, root):
        return _refused("The form folder is outside the project.")
    widget = _TEMPLATES.get(template)
    if widget is None:
        known = ", ".join(sorted(_TEMPLATES))
        return _refused("There is no form template named %s. Use %s." % (template, known))
    reason = explain_form_name(stem, folder=folder, fs=fs)
    if reason is not None:
        return _refused(reason)
    clean = stem.strip()
    ui_path = os.path.join(folder, clean + ".ui")
    text = _template_xml(template, widget, _class_name(clean), title)
    journal = Journal(fs)
    try:
        fs.makedirs(folder)
        journal.put(ui_path, text.encode("utf-8"))
        scope = scope_for(ui_path, root, fs)
        document = read_ui(text, allocator=IdAllocator()).document
        written = write_generated(scope, document, text.encode("utf-8"), fs)
    except Exception as exc:
        journal.rollback()
        return CreateResult(
            files=(),
            diagnostics=(),
            scope=None,
            refused="The form could not be created: %s" % exc,
        )
    if not written.text_written:
        journal.rollback()
        detail = written.diagnostics[0].message if written.diagnostics else "the form could not be generated"
        return CreateResult(
            files=(),
            diagnostics=written.diagnostics,
            scope=None,
            refused="The form could not be created: %s" % detail,
        )
    files = [ui_path]
    for path in written.files:
        if path not in files:
            files.append(path)
    return CreateResult(
        files=tuple(files),
        diagnostics=written.diagnostics,
        scope=scope,
        refused=None,
    )


def _class_name(stem: str) -> str:
    parts = [part for part in stem.split("_") if part]
    joined = "".join(part[:1].upper() + part[1:] for part in parts)
    return joined or "Form"


def stamp_window_title(project_root: str, ui_path: str, title: str, fs: OsFileSystem) -> None:
    """Set the form's window title and regenerate its Python module."""
    text = fs.read_text(ui_path)
    updated = _replace_window_title(text, title)
    if updated == text:
        return
    fs.write_text(ui_path, updated)
    scope = scope_for(ui_path, project_root, fs)
    document = read_ui(updated, allocator=IdAllocator()).document
    written = write_generated(scope, document, updated.encode("utf-8"), fs)
    if not written.text_written:
        detail = written.diagnostics[0].message if written.diagnostics else "the form could not be generated"
        raise ProjectOpError(detail)


def _replace_window_title(xml: str, title: str) -> str:
    escaped = xml_escape(title)
    updated, count = _WINDOW_TITLE.subn(lambda match: match.group(1) + escaped + match.group(3), xml, count=1)
    if count != 1:
        return xml
    return updated


def _template_xml(template: str, widget: str, class_name: str, title: Optional[str]) -> str:
    shown = title.strip() if title and title.strip() else ""
    if widget == "QMainWindow":
        if not shown:
            shown = "Main window"
        safe = xml_escape(shown)
        if template == "app_window":
            return _APP_WINDOW_TEMPLATE % (class_name, class_name, safe, class_name)
        return _MAIN_WINDOW_TEMPLATE % (class_name, class_name, safe)
    if not shown:
        shown = class_name
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n'
        " <class>%s</class>\n"
        ' <widget class="%s" name="%s">\n'
        '  <property name="windowTitle"><string>%s</string></property>\n'
        " </widget>\n"
        "</ui>\n"
    ) % (class_name, widget, class_name, xml_escape(shown))


def _refused(reason: str) -> CreateResult:
    return CreateResult(files=(), diagnostics=(), scope=None, refused=reason)
