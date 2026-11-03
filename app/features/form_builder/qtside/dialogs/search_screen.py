"""The command behind "[Use a search screen instead]" (FB312).

M8.3a shows the button once this module is registered. The command makes a
list screen for the lookup's table and keys it to the record form for that
table.
"""

from __future__ import annotations

import os
from typing import Optional

from app.features.form_builder.engine.data.schema import schema_for
from app.features.form_builder.engine.data.source import singular
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.create import create_form
from app.features.form_builder.engine.project.from_table_plan import (
    TableRequest,
    choice_for,
    include_column,
)
from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.qtside.data_panel.column_insert_hooks import register_search_screen
from app.features.form_builder.qtside.data_panel.host import session_of
from app.features.form_builder.qtside.data_panel.listing_edits import form_stems
from app.features.form_builder.qtside.data_panel.model import record_source
from app.features.form_builder.qtside.dialogs.table_apply import render_plans


def install() -> None:
    register_search_screen(open_search_screen)


def open_search_screen(table_name: str) -> None:
    window = _main_window()
    session = _session(window)
    if window is None or session is None or not table_name:
        return
    source = record_source(session.document)
    if source is None:
        _say(window, "Connect this form to a table first.")
        return
    project = getattr(window, "_loaded_project", None)
    root = os.path.abspath(getattr(project, "project_root", "") or "")
    if not root:
        return
    record_stem = _record_stem(root, source.connection, table_name, session)
    if not record_stem:
        _say(window, "Create a %s record form first." % singular(table_name))
        return
    schema = schema_for(session.document, source.connection)
    if schema is None:
        _say(window, "Refresh the columns for %s first." % source.connection)
        return
    table = None
    for item in schema.tables:
        if item.name == table_name:
            table = item
            break
    if table is None or not table.key:
        _say(window, "%s has no single key column. Record forms need one." % table_name)
        return
    list_stem = record_stem + "_list"
    path = os.path.join(root, "forms", list_stem + ".ui")
    if not os.path.isfile(path):
        engine = schema.engine if schema.engine in ("sqlite", "postgres") else "sqlite"
        columns = tuple(
            choice_for(column, engine)
            for column in table.columns
            if include_column(column, table.key or "", engine)
        )
        request = TableRequest(
            source.connection,
            table.name,
            columns,
            "list",
            "",
            list_stem,
            "yyyy-MM-dd",
            open_form=record_stem,
        )
        made = render_plans(request, schema, root)
        if not made:
            _say(window, "Include at least one column.")
            return
        stem, text = made[0]
        result = create_form(root, stem, OsFileSystem(), template="widget", ui_text=text)
        if result.refused or result.scope is None:
            _say(window, result.refused or "The list screen was not created.")
            return
        path = result.scope.ui_path
    factory = getattr(window, "_editor_tab_factory", None)
    if factory is not None:
        factory.open_file_in_editor(path)
    _focus_data(window, path)


def _record_stem(root: str, connection: str, table: str, session: object) -> str:
    current = record_source(getattr(session, "document", None))
    if current is not None and current.table == table and current.connection == connection:
        return _stem(getattr(session, "path", "") or "")
    folder = os.path.join(root, "forms")
    for stem in form_stems(root):
        path = os.path.join(folder, stem + ".ui")
        try:
            text = OsFileSystem().read_text(path)
            document = read_ui(text, allocator=IdAllocator()).document
        except (OSError, UnicodeError, ProjectOpError, UiReadError):
            continue
        source = record_source(document)
        if source is not None and source.table == table and source.connection == connection:
            return stem
    return ""


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _session(window: object) -> object:
    if window is None:
        return None
    found = session_of(window)
    if found is not None:
        return found
    surface = getattr(window, "_form_undo_surface", None)
    getter = getattr(surface, "session", None)
    session = getter() if callable(getter) else getter
    if getattr(session, "document", None) is not None:
        return session
    return None


def _main_window() -> Optional[object]:
    from app.qt.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return None
    for widget in app.topLevelWidgets():
        if getattr(widget, "_loaded_project", None) is not None:
            return widget
    return app.activeWindow()


def _focus_data(window: object, path: str) -> None:
    registry = getattr(window, "_tab_content_registry", None)
    if registry is None:
        return
    surface = registry.surface_for_path(os.path.abspath(path))
    workbench = getattr(surface, "workbench", None)
    if workbench is None:
        return
    from app.features.form_builder.qtside.inspector.pane import TabId

    focus_tab = getattr(workbench, "focus_inspector_tab", None)
    focus_section = getattr(workbench, "focus_section", None)
    if callable(focus_tab):
        focus_tab(TabId.DATA)
    if callable(focus_section):
        focus_section("data")


def _say(window: object, text: str) -> None:
    from app.qt.QtWidgets import QMessageBox, QWidget

    parent = window if isinstance(window, QWidget) else None
    QMessageBox.information(parent, "Search screen", text)
