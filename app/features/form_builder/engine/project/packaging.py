"""Which generated files a project package must ship, and whether they are current.

Staleness of ``ui_*.py`` uses ``is_stale`` (the codegen version and the form's
sha256). ``*_rc.py`` has no source sha, so a missing banner or a different
codegen version is stale. ``cbcs_connections.py`` is listed when it exists.
It is missing only when a generated module names it and the file is absent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.codegen.api_types import CODEGEN_VERSION
from app.features.form_builder.engine.codegen.header import is_stale, read_header
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.adoption import scope_for
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.project.fs import (
    OsFileSystem,
    inside_project,
    relative_posix,
)
from app.features.form_builder.engine.project.picture_checks import raw_picture_message
from app.features.form_builder.engine.project.pictures import raw_pictures
from app.features.form_builder.engine.project.save import (
    project_ui_files,
    resource_destination,
    write_generated,
)
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui

CONNECTIONS_FILENAME = "cbcs_connections.py"

FileRole = str
FileState = str


@dataclass(frozen=True)
class GeneratedFile:
    """One generated path the packager should ship or flag."""

    relative_path: str
    role: FileRole
    state: FileState
    source_relative: str
    message: str


@dataclass(frozen=True)
class FormPackageReport:
    """Generated files for every project or adopted form."""

    files: Tuple[GeneratedFile, ...]


def inspect_forms(project_root: str, fs: Optional[OsFileSystem] = None) -> FormPackageReport:
    """Read the project and classify each generated file."""
    files = fs if fs is not None else OsFileSystem()
    root = os.path.abspath(project_root)
    rows: List[GeneratedFile] = []
    mentions_connections = False
    for ui_path in _ui_files(root):
        form_rows, mentions = _rows_for_form(root, ui_path, files)
        rows.extend(form_rows)
        mentions_connections = mentions_connections or mentions
    rows.extend(_connection_rows(root, files, mentions_connections))
    return FormPackageReport(files=tuple(rows))


def save_form_now(
    project_root: str,
    ui_path: str,
    fs: Optional[OsFileSystem] = None,
):
    """Regenerate Python for one form from the ``.ui`` on disk. No tab is opened."""
    files = fs if fs is not None else OsFileSystem()
    root = os.path.abspath(project_root)
    scope = scope_for(ui_path, root, files)
    ui_bytes = files.read_bytes(scope.ui_path)
    document = read_ui(ui_bytes.decode("utf-8"), allocator=IdAllocator()).document
    return write_generated(scope, document, ui_bytes, files)


def adopt_pictures_now(
    project_root: str,
    ui_path: str,
    fs: Optional[OsFileSystem] = None,
) -> Tuple[int, str]:
    """The packaging fix for FB031 (UX-RES-005): add each file-path picture of one form to the project's
    pictures, point the property at it, write the ``.ui`` and regenerate its Python.

    Returns ``(pictures fixed, sentence)``; the sentence is ``""`` when every file-path picture was fixed,
    else the reason the first one was not. Nothing is changed for a picture whose file is missing.
    """
    from app.features.form_builder.engine.project.fs import ProjectOpError
    from app.features.form_builder.engine.project.picture_adopt import adopt_raw_picture
    from app.features.form_builder.engine.session import FormSession
    from app.features.form_builder.engine.ui4.writer import write_ui

    files = fs if fs is not None else OsFileSystem()
    root = os.path.abspath(project_root)
    text = files.read_text(ui_path)
    session = FormSession.open(text, path=ui_path, scope=scope_for(ui_path, root, files))
    fixed = 0
    reason = ""
    tried = set()
    try:
        while True:
            pending = [
                item
                for item in raw_pictures(session.document)
                if (item.node_id, item.property_name, item.state) not in tried
            ]
            if not pending:
                break
            item = pending[0]
            tried.add((item.node_id, item.property_name, item.state))
            try:
                plan = adopt_raw_picture(session.document, ui_path, root, item, files)
            except ProjectOpError as exc:
                reason = reason or str(exc)
                continue
            with session.log.transaction(plan.label) as txn:
                for command in plan.commands:
                    txn.execute(command)
            fixed += 1
        if fixed:
            files.write_text(ui_path, write_ui(session.document).text)
    finally:
        session.dispose()
    if fixed:
        save_form_now(root, ui_path, files)
    return fixed, reason


def _ui_files(root: str) -> List[str]:
    return list(project_ui_files(root))


def _rows_for_form(
    root: str,
    ui_path: str,
    fs: OsFileSystem,
) -> Tuple[List[GeneratedFile], bool]:
    scope = scope_for(ui_path, root, fs)
    if not scope.generates or not scope.generated_path or not scope.project_root:
        return [], False
    ui_rel = relative_posix(ui_path, root)
    ui_name = os.path.basename(ui_path)
    generated_rel = relative_posix(scope.generated_path, root)
    try:
        ui_bytes = fs.read_bytes(ui_path)
        document = read_ui(ui_bytes.decode("utf-8"), allocator=IdAllocator()).document
    except (OSError, UnicodeError, UiReadError):
        return [
            GeneratedFile(
                relative_path=generated_rel,
                role="ui_module",
                state="unreadable",
                source_relative=ui_rel,
                message="%s could not be read." % ui_name,
            )
        ], False
    rows = [_module_row(scope, ui_bytes, ui_rel, ui_name, fs)]
    mentions = _mentions_connections(scope, fs)
    result = generate_form_module(document, scope=scope, source_bytes=ui_bytes)
    rows.extend(
        _resource_rows(
            root,
            scope,
            document,
            result.resource_modules,
            ui_rel,
            ui_name,
            fs,
        )
    )
    rows.extend(_picture_rows(document, ui_rel))
    return rows, mentions


def _picture_rows(document: object, ui_rel: str) -> List[GeneratedFile]:
    """A packaging error for each pixmap or icon that stores a file path (UX-RES-005)."""
    rows: List[GeneratedFile] = []
    for item in raw_pictures(document):
        name = item.object_name or "A widget"
        rows.append(
            GeneratedFile(
                relative_path=item.path,
                role="picture",
                state="raw_path",
                source_relative=ui_rel,
                message=raw_picture_message(name, item.path),
            )
        )
    return rows


def _module_row(
    scope: FormScope,
    ui_bytes: bytes,
    ui_rel: str,
    ui_name: str,
    fs: OsFileSystem,
) -> GeneratedFile:
    path = scope.generated_path or ""
    rel = relative_posix(path, scope.project_root or "")
    name = os.path.basename(path)
    if not fs.is_file(path):
        return GeneratedFile(
            relative_path=rel,
            role="ui_module",
            state="missing",
            source_relative=ui_rel,
            message="%s is missing." % name,
        )
    text = fs.read_text(path)
    if is_stale(text, ui_bytes):
        return GeneratedFile(
            relative_path=rel,
            role="ui_module",
            state="stale",
            source_relative=ui_rel,
            message="%s is older than %s." % (name, ui_name),
        )
    return GeneratedFile(
        relative_path=rel,
        role="ui_module",
        state="current",
        source_relative=ui_rel,
        message="",
    )


def _resource_rows(
    root: str,
    scope: FormScope,
    document: object,
    modules: Sequence[str],
    ui_rel: str,
    ui_name: str,
    fs: OsFileSystem,
) -> List[GeneratedFile]:
    locations = _resource_locations(document)
    rows: List[GeneratedFile] = []
    project_root = scope.project_root or root
    for index, location in enumerate(locations):
        module = modules[index] if index < len(modules) else _rc_module_name(location)
        dest = resource_destination(project_root, scope.ui_path, location, module)
        if not inside_project(dest, project_root):
            continue
        rel = relative_posix(dest, project_root)
        name = os.path.basename(dest)
        if not fs.is_file(dest):
            rows.append(
                GeneratedFile(
                    relative_path=rel,
                    role="resource",
                    state="missing",
                    source_relative=ui_rel,
                    message="%s is missing." % name,
                )
            )
            continue
        text = fs.read_text(dest)
        parsed = read_header(text)
        if parsed is None or parsed.codegen_version != CODEGEN_VERSION:
            rows.append(
                GeneratedFile(
                    relative_path=rel,
                    role="resource",
                    state="stale",
                    source_relative=ui_rel,
                    message="%s is older than %s." % (name, ui_name),
                )
            )
            continue
        rows.append(
            GeneratedFile(
                relative_path=rel,
                role="resource",
                state="current",
                source_relative=ui_rel,
                message="",
            )
        )
    return rows


def _resource_locations(document: object) -> List[str]:
    ui = getattr(document, "ui", None)
    if ui is None:
        return []
    found: List[str] = []
    for node in ui.children("resources"):
        location = node.field("location")
        if isinstance(location, str) and location.strip():
            found.append(location)
    return found


def _rc_module_name(location: str) -> str:
    stem = os.path.splitext(os.path.basename(location.replace("\\", "/")))[0]
    return stem + "_rc"


def _mentions_connections(scope: FormScope, fs: OsFileSystem) -> bool:
    path = scope.generated_path
    if not path or not fs.is_file(path):
        return False
    return "cbcs_connections" in fs.read_text(path)


def _connection_rows(
    root: str,
    fs: OsFileSystem,
    mentions: bool,
) -> List[GeneratedFile]:
    path = os.path.join(root, CONNECTIONS_FILENAME)
    if fs.is_file(path):
        return [
            GeneratedFile(
                relative_path=CONNECTIONS_FILENAME,
                role="connections",
                state="current",
                source_relative="",
                message="",
            )
        ]
    if not mentions:
        return []
    return [
        GeneratedFile(
            relative_path=CONNECTIONS_FILENAME,
            role="connections",
            state="missing",
            source_relative="",
            message="%s is missing." % CONNECTIONS_FILENAME,
        )
    ]
