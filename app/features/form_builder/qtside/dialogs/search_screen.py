"""The command behind "[Use a search screen instead]" (FB312).

M8.3a shows the button once this module is registered. The command makes a
list screen for the lookup's table and keys it to the record form for that
table.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from app.features.form_builder.engine.data.schema import schema_for
from app.features.form_builder.engine.data.source import singular
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.data.source import ListSource, read_data
from app.features.form_builder.engine.project.from_table_plan import (
    TableRequest,
    choice_for,
    include_column,
)
from app.features.form_builder.engine.project.create import create_form
from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError
from app.features.form_builder.engine.project.names import unique_form_stem
from app.features.form_builder.engine.project.recents import remember_form
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.qtside.data_panel.column_insert_hooks import register_search_screen
from app.features.form_builder.qtside.data_panel.host import session_of
from app.features.form_builder.qtside.data_panel.listing_edits import form_stems
from app.features.form_builder.qtside.data_panel.model import record_source
from app.features.form_builder.qtside.dialogs.table_apply import render_plans


_creator = None


def install() -> None:
    register_search_screen(open_search_screen)


def register_form_creator(fn: object) -> None:
    """Integration registers ``perform_create`` so this module never imports it."""
    global _creator
    _creator = fn


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
    record_stem = _record_stem(root, source.connection, table_name, session, window)
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
    folder = os.path.join(root, "forms")
    earlier = _earlier_list(folder, record_stem, table_name, source.connection)
    if earlier:
        factory = getattr(window, "_editor_tab_factory", None)
        if factory is not None:
            factory.open_file_in_editor(earlier)
        _focus_data(window, earlier)
        return
    list_stem = unique_form_stem(folder, OsFileSystem(), record_stem + "_list")
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
    result = _write_list(window, root, folder, stem, text)
    refused = getattr(result, "refused", None)
    scope = getattr(result, "scope", None)
    if result is None or refused or scope is None:
        _say(window, refused or "The list screen was not created.")
        return
    _focus_data(window, getattr(scope, "ui_path", ""))


def _write_list(window: object, root: str, folder: str, stem: str, text: str) -> object:
    creator = _creator
    if callable(creator):
        return creator(window, template="widget", stem=stem, directory=folder, ui_text=text)
    fs = OsFileSystem()
    result = create_form(root, stem, fs, template="widget", directory=folder, ui_text=text)
    if result.refused or result.scope is None:
        return result
    try:
        remember_form(root, result.scope.ui_path, fs)
    except ProjectOpError:
        pass
    factory = getattr(window, "_editor_tab_factory", None)
    if factory is not None:
        factory.open_file_in_editor(result.scope.ui_path)
    tree = getattr(window, "_project_tree_ui_workflow", None)
    refresh = getattr(tree, "refresh_project_tree_from_disk", None)
    if callable(refresh):
        refresh()
    return result


def _record_stem(root: str, connection: str, table: str, session: object, window: object) -> str:
    current = record_source(getattr(session, "document", None))
    if current is not None and current.table == table and current.connection == connection:
        return _stem(getattr(session, "path", "") or "")
    matches = _record_stems(root, connection, table)
    if not matches:
        return ""
    if len(matches) == 1:
        return matches[0]
    from app.qt.QtWidgets import QInputDialog, QWidget

    parent = window if isinstance(window, QWidget) else None
    choice, ok = QInputDialog.getItem(
        parent,
        "Search screen",
        "Which record form should the list open?",
        list(matches),
        0,
        False,
    )
    if not ok:
        return ""
    return str(choice)


def _record_stems(root: str, connection: str, table: str) -> Tuple[str, ...]:
    folder = os.path.join(root, "forms")
    found = []
    for stem in form_stems(root):
        path = os.path.join(folder, stem + ".ui")
        source = _record_at(path)
        if source is not None and source.table == table and source.connection == connection:
            found.append(stem)
    return tuple(found)


def _record_at(path: str) -> object:
    try:
        text = OsFileSystem().read_text(path)
        document = read_ui(text, allocator=IdAllocator()).document
    except (OSError, UnicodeError, ProjectOpError, UiReadError):
        return None
    return record_source(document)


def _earlier_list(folder: str, record_stem: str, table: str, connection: str) -> str:
    """An existing ``<stem>_list`` or ``<stem>_list_N`` screen for this table."""

    prefix = record_stem + "_list"
    found = []
    try:
        names = os.listdir(folder)
    except OSError:
        return ""
    for name in names:
        if not name.endswith(".ui"):
            continue
        stem = name[:-3]
        if stem != prefix and not _numbered_list(stem, prefix):
            continue
        path = os.path.join(folder, name)
        if _is_list_of(path, table, connection):
            found.append((0 if stem == prefix else int(stem[len(prefix) + 1 :]), path))
    if not found:
        return ""
    found.sort()
    return found[0][1]


def _numbered_list(stem: str, prefix: str) -> bool:
    if not stem.startswith(prefix + "_"):
        return False
    suffix = stem[len(prefix) + 1 :]
    return suffix.isdigit() and not suffix.startswith("0")


def _is_list_of(path: str, table: str, connection: str) -> bool:
    try:
        text = OsFileSystem().read_text(path)
        document = read_ui(text, allocator=IdAllocator()).document
    except (OSError, UnicodeError, ProjectOpError, UiReadError):
        return False
    raw = ""
    root = getattr(document, "root", None)
    entry = root.prop("cbcsData") if root is not None and hasattr(root, "prop") else None
    value = getattr(entry, "value", None)
    raw = getattr(value, "text", "") if value is not None else ""
    if not raw:
        return False
    parsed = read_data(raw)
    data = getattr(parsed, "value", None)
    return isinstance(data, ListSource) and data.table == table and data.connection == connection


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
    from app.features.form_builder.qtside.inspector import TabId

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
