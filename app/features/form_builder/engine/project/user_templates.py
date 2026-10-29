"""Templates the user saved from their own forms (UX-TMPL-002, UX-TMPL-004). Qt-free.

A template is a folder: ``form.ui``, ``template.json``, ``thumbnail.png`` and,
when the form uses pictures, ``pictures/`` and a ``resources.qrc`` that lists
only those pictures. "All my projects" folders live in ``form_templates/`` in
the Code Studio settings folder; "This project only" ones in
``cbcs/form_builder/templates/`` of the project (pruned from packages).

What this module touches. A save writes into a hidden staging folder next to
the final one and swaps it in, so a failed save never leaves half a template.
Rename and description change ``template.json`` only. Delete removes the one
folder it is given, after checking that the folder sits directly inside the
templates folder of its scope; a folder that is a symlink is unlinked, never
followed. Nothing here edits a project's forms or pictures: using a template
is ``template_use``.

Files here are not on any form's undo stack.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import secrets
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.catalog import (
    Rename,
    SetProperty,
    SetResourceIncludes,
)
from app.features.form_builder.engine.commands.log import CommandLog, SelectionSnapshot
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError, inside_project
from app.features.form_builder.engine.project.picture_adopt import with_picture
from app.features.form_builder.engine.project.pictures import (
    canon_resource,
    is_image_name,
    picture_uses,
    resource_locations,
)
from app.features.form_builder.engine.project.qrc_write import (
    MAX_PICTURE_BYTES,
    PICTURES_FOLDER,
    QrcEntry,
    QrcGroup,
    QrcLayout,
    entry_disk_path,
    read_layout,
    render_qrc,
    resource_of,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.ui4.writer import write_ui

SCOPE_USER = "user"
SCOPE_PROJECT = "project"
USER_FOLDER = "form_templates"
PROJECT_PARTS = ("cbcs", "form_builder", "templates")
FORM_FILE = "form.ui"
META_FILE = "template.json"
THUMBNAIL_FILE = "thumbnail.png"
QRC_FILE = "resources.qrc"
FORMAT_VERSION = 1
BUILDER_VERSION = "form-builder 1"
NAME_LIMIT = 80
DESCRIPTION_LIMIT = 200
_META_LIMIT = 64 * 1024
_FORM_LIMIT = 8 * 1024 * 1024


class TemplateExists(ProjectOpError):
    """A template with this name is already kept in that scope. ``existing`` is it."""

    def __init__(self, existing: "TemplateInfo") -> None:
        super().__init__('A template named "%s" already exists.' % existing.name)
        self.existing = existing


@dataclass(frozen=True)
class TemplateInfo:
    """One folder under a templates directory. ``error`` is a sentence when it can't be read."""

    scope: str
    folder: str
    name: str
    description: str = ""
    root_class: str = ""
    created: str = ""
    error: str = ""

    @property
    def key(self) -> str:
        return os.path.basename(self.folder)

    @property
    def card_key(self) -> str:
        return "template:%s:%s" % (self.scope, self.key)

    @property
    def title(self) -> str:
        """The card title. A template that can't be read says so (UX-TMPL-004)."""
        return "Can't open %s" % self.key if self.error else self.name

    @property
    def form_path(self) -> str:
        return os.path.join(self.folder, FORM_FILE)

    @property
    def thumbnail_path(self) -> str:
        return os.path.join(self.folder, THUMBNAIL_FILE)


@dataclass(frozen=True)
class PictureCarry:
    """Pictures a form uses, as ``(file name, bytes)``, and the path rewrite that points at them."""

    files: Tuple[Tuple[str, bytes], ...]
    #: ``:/old/path`` to ``:/pictures/name`` for every picture carried.
    rewrite: Dict[str, str]


# --- locations -------------------------------------------------------------


def user_templates_dir(state_root: str) -> str:
    return os.path.join(os.path.abspath(state_root), USER_FOLDER)


def project_templates_dir(project_root: str) -> str:
    return os.path.join(os.path.abspath(project_root), *PROJECT_PARTS)


def templates_dir(scope: str, state_root: str, project_root: Optional[str]) -> str:
    if scope == SCOPE_USER:
        if not state_root:
            raise ProjectOpError("Code Studio has no settings folder to keep templates in.")
        return user_templates_dir(state_root)
    if scope == SCOPE_PROJECT:
        if not project_root:
            raise ProjectOpError("Open a project to keep a template for this project only.")
        return project_templates_dir(project_root)
    raise ProjectOpError("Choose where to keep the template.")


# --- reading ---------------------------------------------------------------


def list_templates(state_root: str, project_root: Optional[str] = None) -> Tuple[TemplateInfo, ...]:
    """Every template of both scopes, by name. Reads ``template.json`` only, never the form or pictures."""
    found: List[TemplateInfo] = []
    if state_root:
        found.extend(_scan(user_templates_dir(state_root), SCOPE_USER))
    if project_root:
        found.extend(_scan(project_templates_dir(project_root), SCOPE_PROJECT))
    found.sort(key=lambda info: (info.title.casefold(), info.scope, info.key))
    return tuple(found)


def read_template(folder: str, scope: str) -> TemplateInfo:
    """The info for one template folder. A bad folder gives an info whose ``error`` says why."""
    key = os.path.basename(os.path.abspath(folder))
    meta_path = os.path.join(folder, META_FILE)
    form_path = os.path.join(folder, FORM_FILE)
    try:
        if os.path.getsize(meta_path) > _META_LIMIT:
            return _broken(scope, folder, "%s is too large to be a template description." % META_FILE)
        with open(meta_path, "rb") as handle:
            payload = json.loads(handle.read().decode("utf-8"))
    except FileNotFoundError:
        return _broken(scope, folder, "%s is missing." % META_FILE)
    except (OSError, UnicodeError, ValueError):
        return _broken(scope, folder, "%s can't be read." % META_FILE)
    if not isinstance(payload, dict) or not isinstance(payload.get("name"), str) or not payload["name"].strip():
        return _broken(scope, folder, "%s has no name." % META_FILE)
    if not os.path.isfile(form_path):
        return _broken(scope, folder, "%s is missing." % FORM_FILE)
    description = payload.get("description")
    root_class = payload.get("root_class")
    created = payload.get("created")
    return TemplateInfo(
        scope=scope,
        folder=folder,
        name=payload["name"].strip(),
        description=description if isinstance(description, str) else "",
        root_class=root_class if isinstance(root_class, str) else "",
        created=created if isinstance(created, str) else "",
    ) if key else _broken(scope, folder, "The template folder has no name.")


def find_by_name(
    templates: Sequence[TemplateInfo], name: str, scope: str, *, skip: Optional[TemplateInfo] = None
) -> Optional[TemplateInfo]:
    wanted = name.strip().casefold()
    for info in templates:
        if info.scope != scope or info.error or (skip is not None and info.folder == skip.folder):
            continue
        if info.name.casefold() == wanted:
            return info
    return None


def _scan(directory: str, scope: str) -> List[TemplateInfo]:
    try:
        entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
    except OSError:
        return []
    found: List[TemplateInfo] = []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue
        found.append(read_template(entry.path, scope))
    return found


def _broken(scope: str, folder: str, reason: str) -> TemplateInfo:
    return TemplateInfo(scope=scope, folder=folder, name=os.path.basename(folder), error=reason)


# --- saving ----------------------------------------------------------------


def save_template(
    *,
    scope: str,
    state_root: str,
    project_root: Optional[str],
    name: str,
    description: str,
    ui_text: str,
    ui_path: str = "",
    thumbnail: bytes = b"",
    replace: bool = False,
    today: Optional[datetime.date] = None,
    fs: Optional[OsFileSystem] = None,
) -> TemplateInfo:
    """Keep a copy of ``ui_text`` and the pictures it uses (UX-TMPL-001, UX-TMPL-002).

    ``ui_path`` is where the form lives; the ``.qrc`` files it includes are
    read from there, and only when they are inside ``project_root``. Raises
    ``TemplateExists`` when ``name`` is taken in that scope and ``replace`` is
    False; with ``replace`` the old folder is swapped for the new one whole.
    Raises ``ProjectOpError`` with a sentence, having changed nothing.
    """
    files = fs or OsFileSystem()
    clean = _clean_name(name)
    about = description.strip()[:DESCRIPTION_LIMIT]
    directory = templates_dir(scope, state_root, project_root)
    taken = find_by_name(_scan(directory, scope), clean, scope)
    if taken is not None and not replace:
        raise TemplateExists(taken)
    text, root_class, carried = _prepare(ui_text, ui_path, project_root, files)
    staging = os.path.join(directory, ".saving-" + secrets.token_hex(6))
    key = taken.key if taken is not None else _free_key(directory, clean)
    final = os.path.join(directory, key)
    try:
        os.makedirs(staging)
        files.write_text(os.path.join(staging, FORM_FILE), text)
        meta = {
            "format": FORMAT_VERSION,
            "name": clean,
            "description": about,
            "root_class": root_class,
            "created": (today or datetime.date.today()).isoformat(),
            "builder_version": BUILDER_VERSION,
        }
        files.write_text(os.path.join(staging, META_FILE), json.dumps(meta, indent=2, sort_keys=True) + "\n")
        if thumbnail:
            files.write_bytes(os.path.join(staging, THUMBNAIL_FILE), thumbnail)
        _write_pictures(staging, carried, files)
        _swap_in(staging, final)
    except (OSError, ProjectOpError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        if isinstance(exc, ProjectOpError):
            raise
        raise ProjectOpError("Code Studio couldn't save the template.") from exc
    return read_template(final, scope)


def rename_template(info: TemplateInfo, name: str, *, state_root: str, project_root: Optional[str]) -> TemplateInfo:
    """Change the name shown on the card. The folder keeps its name."""
    clean = _clean_name(name)
    directory = _owned_directory(info, state_root, project_root)
    clash = find_by_name(_scan(directory, info.scope), clean, info.scope, skip=info)
    if clash is not None:
        raise TemplateExists(clash)
    return _update_meta(info, {"name": clean})


def change_description(info: TemplateInfo, description: str) -> TemplateInfo:
    return _update_meta(info, {"description": description.strip()[:DESCRIPTION_LIMIT]})


def delete_template(info: TemplateInfo, *, state_root: str, project_root: Optional[str]) -> None:
    """Remove this template's folder and nothing else (UX-TMPL-004).

    Raises ``ProjectOpError`` when the folder is not a direct child of the
    templates folder of its scope, so a stale or forged info deletes nothing.
    """
    _owned_directory(info, state_root, project_root)
    folder = os.path.abspath(info.folder)
    try:
        if os.path.islink(folder):
            os.unlink(folder)
        else:
            shutil.rmtree(folder)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ProjectOpError("Code Studio couldn't delete the template.") from exc


def _update_meta(info: TemplateInfo, changes: Dict[str, str]) -> TemplateInfo:
    if info.error:
        raise ProjectOpError("That template can't be read, so it can only be deleted.")
    meta_path = os.path.join(info.folder, META_FILE)
    try:
        with open(meta_path, "rb") as handle:
            payload = json.loads(handle.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(META_FILE)
        payload.update(changes)
        OsFileSystem().write_text(meta_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    except (OSError, UnicodeError, ValueError) as exc:
        raise ProjectOpError("Code Studio couldn't change the template.") from exc
    return read_template(info.folder, info.scope)


def _owned_directory(info: TemplateInfo, state_root: str, project_root: Optional[str]) -> str:
    directory = os.path.abspath(templates_dir(info.scope, state_root, project_root))
    folder = os.path.abspath(info.folder)
    if os.path.dirname(folder) != directory or os.path.basename(folder).startswith("."):
        raise ProjectOpError("That folder is not one of your templates.")
    return directory


def _clean_name(name: str) -> str:
    clean = " ".join(name.split())
    if not clean:
        return _refuse("A template needs a name.")
    if len(clean) > NAME_LIMIT:
        return _refuse("Use a shorter name for the template.")
    return clean


def _refuse(sentence: str) -> str:
    raise ProjectOpError(sentence)


def _free_key(directory: str, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")[:40] or "template"
    try:
        existing = {entry.casefold() for entry in os.listdir(directory)}
    except OSError:
        existing = set()
    key, number = base, 1
    while key.casefold() in existing:
        number += 1
        key = "%s_%d" % (base, number)
    return key


def _swap_in(staging: str, final: str) -> None:
    if not os.path.lexists(final):
        os.replace(staging, final)
        return
    backup = "%s.old-%s" % (os.path.join(os.path.dirname(final), "." + os.path.basename(final)), secrets.token_hex(4))
    os.replace(final, backup)
    try:
        os.replace(staging, final)
    except OSError:
        os.replace(backup, final)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def _write_pictures(staging: str, carried: PictureCarry, files: OsFileSystem) -> None:
    if not carried.files:
        return
    layout = QrcLayout(
        groups=(QrcGroup("/", None, tuple(QrcEntry("%s/%s" % (PICTURES_FOLDER, name)) for name, _data in carried.files)),)
    )
    for name, data in carried.files:
        files.write_bytes(os.path.join(staging, PICTURES_FOLDER, name), data)
    files.write_text(os.path.join(staging, QRC_FILE), render_qrc(layout))


# --- the form text, its pictures --------------------------------------------


def _prepare(
    ui_text: str, ui_path: str, project_root: Optional[str], files: OsFileSystem
) -> Tuple[str, str, PictureCarry]:
    """``(form.ui text, root class, pictures)`` for a template made from ``ui_text``."""
    if len(ui_text) > _FORM_LIMIT:
        raise ProjectOpError("This form is too large to keep as a template.")
    try:
        document = read_ui(ui_text, allocator=IdAllocator()).document
    except UiReadError as exc:
        raise ProjectOpError("The form can't be read, so it can't be kept as a template: %s" % exc) from exc
    root_class = document.root.class_name
    carried = collect_pictures(document, ui_path, project_root, files)
    if not carried.files and not resource_locations(document):
        return write_ui(document).text, root_class, carried
    includes = (QRC_FILE,) if carried.files else ()
    edited = rewritten_form(ui_text, rewrite=carried.rewrite, includes=includes)
    return edited, root_class, carried


def collect_pictures(
    document: UiDocument, ui_path: str, project_root: Optional[str], files: OsFileSystem
) -> PictureCarry:
    """The pictures ``document`` uses that live in a ``.qrc`` it includes, inside the project.

    A picture that is a raw file path, is missing, is over the size limit or is
    not a picture type is left out. Two different files with one name get
    ``name_2`` so none is lost.
    """
    if not ui_path or not project_root:
        return PictureCarry((), {})
    sources = _resource_sources(document, ui_path, project_root, files)
    kept: List[Tuple[str, bytes]] = []
    by_name: Dict[str, bytes] = {}
    named: Dict[str, str] = {}
    rewrite: Dict[str, str] = {}
    for use in picture_uses(document):
        resource = canon_resource(use.path)
        if resource in rewrite or not resource.startswith(":/"):
            continue
        disk = sources.get(resource)
        if not disk or not os.path.isfile(disk) or not is_image_name(disk):
            continue
        try:
            if os.path.getsize(disk) > MAX_PICTURE_BYTES:
                continue
            data = files.read_bytes(disk)
        except OSError:
            continue
        if disk in named:
            name = named[disk]
        else:
            name = _carried_name(os.path.basename(disk), by_name)
            named[disk] = name
            by_name[name.casefold()] = data
            kept.append((name, data))
        rewrite[resource] = ":/%s/%s" % (PICTURES_FOLDER, name)
    return PictureCarry(tuple(kept), rewrite)


def _resource_sources(document: UiDocument, ui_path: str, project_root: str, files: OsFileSystem) -> Dict[str, str]:
    """``:/path`` to the file that provides it, over the form's includes, first include first."""
    folder = os.path.dirname(os.path.abspath(ui_path))
    found: Dict[str, str] = {}
    for location in resource_locations(document):
        qrc = location if os.path.isabs(location) else os.path.normpath(os.path.join(folder, location))
        if not qrc.lower().endswith(".qrc") or not inside_project(qrc, project_root):
            continue
        try:
            layout = read_layout(qrc, files)
        except ProjectOpError:
            continue
        for group in layout.groups:
            if group.lang:
                continue
            for entry in group.entries:
                disk = entry_disk_path(qrc, entry, project_root)
                if disk:
                    found.setdefault(canon_resource(resource_of(group, entry)), disk)
    return found


def _carried_name(base: str, taken: Dict[str, bytes]) -> str:
    stem, ext = os.path.splitext(base)
    number = 1
    while True:
        candidate = base if number == 1 else "%s_%d%s" % (stem, number, ext)
        if candidate.casefold() not in taken:
            return candidate
        number += 1


def rewritten_form(text: str, *, rewrite: Dict[str, str], includes: Optional[Tuple[str, ...]] = None) -> str:
    """``text`` with picture paths changed by ``rewrite`` and, when given, the include list replaced.

    Done through the form's own commands on a throwaway log, so the result is
    the writer's text. Raises ``ProjectOpError`` when the form refuses a change.
    """
    document, log = _open(text)
    try:
        for use in picture_uses(document):
            new_path = rewrite.get(canon_resource(use.path))
            if new_path is None:
                continue
            entry = document.node(use.node_id).prop(use.property_name)  # type: ignore[arg-type]
            if entry is None:
                continue
            value = with_picture(entry.value, use.state, new_path)
            log.execute(SetProperty(use.node_id, use.property_name, value))  # type: ignore[arg-type]
        if includes is not None and tuple(resource_locations(document)) != includes:
            log.execute(SetResourceIncludes(includes))
    except Exception as exc:  # the command layer rejects with its own types
        raise ProjectOpError("The template's pictures could not be set: %s" % exc) from exc
    return write_ui(document).text


def renamed_root(text: str, new_name: str) -> str:
    """``text`` with the root object and the form class named ``new_name`` (UX-TMPL-003).

    Connections, buddies and other references to the old name follow through
    the form's own rename. A window title that was the old name becomes the new.
    """
    document, log = _open(text)
    old = document.root.object_name or ""
    try:
        log.execute(Rename(document.root.id, new_name))
        title = document.root.prop("windowTitle")
        if title is not None and isinstance(title.value, StringValue) and old and title.value.text == old:
            log.execute(SetProperty(document.root.id, "windowTitle", StringValue(new_name)))
    except Exception as exc:
        raise ProjectOpError("The form could not be named %s: %s" % (new_name, exc)) from exc
    return write_ui(document).text


def _open(text: str) -> Tuple[UiDocument, CommandLog]:
    allocator = IdAllocator()
    try:
        document = read_ui(text, allocator=allocator).document
    except UiReadError as exc:
        raise ProjectOpError("The template's form can't be read: %s" % exc) from exc
    log = CommandLog(document, allocator, selection_provider=lambda: SelectionSnapshot((), None))
    return document, log


__all__: Sequence[str] = [
    "BUILDER_VERSION",
    "FORM_FILE",
    "META_FILE",
    "PROJECT_PARTS",
    "QRC_FILE",
    "SCOPE_PROJECT",
    "SCOPE_USER",
    "THUMBNAIL_FILE",
    "USER_FOLDER",
    "PictureCarry",
    "TemplateExists",
    "TemplateInfo",
    "change_description",
    "collect_pictures",
    "delete_template",
    "find_by_name",
    "list_templates",
    "project_templates_dir",
    "read_template",
    "rename_template",
    "renamed_root",
    "rewritten_form",
    "save_template",
    "templates_dir",
    "user_templates_dir",
]
