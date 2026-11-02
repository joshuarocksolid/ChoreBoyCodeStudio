"""Rewrite closed forms, and update open ones as one undo step (CONTRACTS.md section 19.4).

Open forms are not written here. Their ``cbcs*`` text goes through ``SetLogic``.
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Callable, Dict, Optional, Tuple

from app.features.form_builder.engine.commands.catalog import SetLogic
from app.features.form_builder.engine.data.source import (
    Hooks,
    ListSource,
    RecordSource,
    Source,
    read_data,
    write_data,
)
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.storage import is_user_logic_key
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.save import project_ui_files
from app.features.form_builder.engine.project.written_files import note_written_files
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import Node
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.spec import NodeSpec
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.ui4.writer import write_ui

Edit = Callable[[UiDocument], Optional[UiDocument]]


def rewrite_forms(
    project_root: str,
    edit: Edit,
    *,
    open_sessions: Dict[str, object],
    undo_label: str,
) -> Tuple[str, ...]:
    """Edit every project form. Closed files are written when the text changes.

    ``open_sessions`` maps an absolute ``.ui`` path to an object with ``.log`` and ``.document``.
    """

    opened = {os.path.abspath(path): session for path, session in open_sessions.items()}
    changed = []
    files = OsFileSystem()
    for path in project_ui_files(project_root):
        absolute = os.path.abspath(path)
        session = opened.get(absolute)
        if session is not None:
            if _rewrite_open(session, edit, undo_label):
                changed.append(absolute)
            continue
        if _rewrite_closed(absolute, edit, files):
            changed.append(absolute)
    return tuple(changed)


def rename_connection(doc: UiDocument, old: str, new: str) -> Optional[UiDocument]:
    """Point ``cbcsData`` and ``hooks.connection`` from ``old`` to ``new``. None when nothing changed."""

    updates: Dict[object, str] = {}
    for node in doc.iter_preorder():
        updated = _renamed_text(node, old, new)
        if updated is None:
            continue
        updates[node.id] = updated
    if not updates:
        return None
    rebuilt = UiDocument.from_spec(_with_data(doc.ui.to_spec(), updates))
    rebuilt.newline = doc.newline
    return rebuilt


def _with_data(spec: NodeSpec, updates: Dict[object, str]) -> NodeSpec:
    properties = spec.properties
    if spec.id in updates:
        text = updates[spec.id]
        properties = tuple(
            replace(entry, value=StringValue(text))
            if entry.kind == "property" and entry.name == "cbcsData"
            else entry
            for entry in properties
        )
    slots = tuple(
        (name, tuple(_with_data(child, updates) for child in children))
        for name, children in spec.slots
    )
    return replace(spec, properties=properties, slots=slots)


def forms_using_connection(project_root: str, name: str) -> Tuple[str, ...]:
    """Absolute ``.ui`` paths whose ``cbcsData`` uses ``name``."""

    found = []
    files = OsFileSystem()
    for path in project_ui_files(project_root):
        try:
            document = read_ui(files.read_text(path), allocator=IdAllocator()).document
        except (OSError, UnicodeError, UiReadError):
            continue
        if name in _names_in(document):
            found.append(os.path.abspath(path))
    return tuple(found)


def _rewrite_open(session: object, edit: Edit, undo_label: str) -> bool:
    document = session.document  # type: ignore[attr-defined]
    log = session.log  # type: ignore[attr-defined]
    detached = read_ui(write_ui(document).text, allocator=IdAllocator()).document
    before = list(detached.iter_preorder())
    before_maps = [_logic_map(node) for node in before]
    open_nodes = list(document.iter_preorder())
    edited = edit(detached)
    if edited is None:
        return False
    after = list(edited.iter_preorder())
    applied = False
    with log.transaction(undo_label):
        for open_node, left_map, right in zip(open_nodes, before_maps, after):
            right_map = _logic_map(right)
            for key in set(left_map) | set(right_map):
                if left_map.get(key) == right_map.get(key):
                    continue
                outcome = log.execute(SetLogic(open_node.id, key, right_map.get(key)))
                if not getattr(outcome, "noop", False):
                    applied = True
    return applied


def _rewrite_closed(path: str, edit: Edit, files: OsFileSystem) -> bool:
    try:
        current = files.read_bytes(path)
        text = current.decode("utf-8")
        document = read_ui(text, allocator=IdAllocator()).document
    except (OSError, UnicodeError, UiReadError):
        return False
    edited = edit(document)
    if edited is None:
        return False
    new_text = write_ui(edited).text
    if new_text.encode("utf-8") == current:
        return False
    files.write_text(path, new_text)
    note_written_files((path,))
    return True


def _renamed_text(node: Node, old: str, new: str) -> Optional[str]:
    entry = node.prop("cbcsData")
    if entry is None or not isinstance(entry.value, StringValue) or not entry.value.text.strip():
        return None
    read = read_data(entry.value.text)
    if read.value is None:
        return None
    updated = _renamed_source(read.value, old, new)
    if updated is None:
        return None
    text = write_data(updated)
    if text == entry.value.text:
        return None
    return text


def _renamed_source(source: Source, old: str, new: str) -> Optional[Source]:
    connection = source.connection
    changed = False
    if connection == old:
        connection = new
        changed = True
    hooks = getattr(source, "hooks", None)
    if isinstance(hooks, Hooks) and hooks.connection == old:
        hooks = replace(hooks, connection=new)
        changed = True
    if not changed:
        return None
    if isinstance(source, ListSource):
        return replace(source, connection=connection)
    if isinstance(source, RecordSource):
        return replace(source, connection=connection, hooks=hooks)
    return None


def _names_in(document: UiDocument) -> set:
    found = set()
    for node in document.iter_preorder():
        entry = node.prop("cbcsData")
        if entry is None or not isinstance(entry.value, StringValue) or not entry.value.text.strip():
            continue
        read = read_data(entry.value.text)
        source = read.value
        if source is None:
            continue
        if source.connection:
            found.add(source.connection)
        hooks = getattr(source, "hooks", None)
        if isinstance(hooks, Hooks) and hooks.connection:
            found.add(hooks.connection)
    return found


def _logic_map(node: Node) -> Dict[str, Optional[str]]:
    found: Dict[str, Optional[str]] = {}
    for entry in node.properties():
        if not is_user_logic_key(entry.name):
            continue
        value = entry.value
        found[entry.name] = value.text if isinstance(value, StringValue) else None
    return found
