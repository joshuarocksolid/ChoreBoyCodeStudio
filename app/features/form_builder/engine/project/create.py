"""Create a form from a template stem, then generate its Python files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.diagnostics import FormDiagnostic
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.adoption import scope_for
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.project.fs import Journal, OsFileSystem, inside_project
from app.features.form_builder.engine.project.names import explain_form_name
from app.features.form_builder.engine.project.save import write_generated
from app.features.form_builder.engine.ui4.reader import read_ui

_TEMPLATES = {
    "widget": "QWidget",
    "dialog": "QDialog",
    "main_window": "QMainWindow",
}


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
    text = _template_xml(widget, _class_name(clean))
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


def _template_xml(widget: str, class_name: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n'
        " <class>%s</class>\n"
        ' <widget class="%s" name="%s">\n'
        '  <property name="windowTitle"><string>%s</string></property>\n'
        " </widget>\n"
        "</ui>\n"
    ) % (class_name, widget, class_name, class_name)


def _refused(reason: str) -> CreateResult:
    return CreateResult(files=(), diagnostics=(), scope=None, refused=reason)
