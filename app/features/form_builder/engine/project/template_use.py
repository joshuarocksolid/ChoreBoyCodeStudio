"""Make a new form from a saved template (UX-TMPL-003). Qt-free.

The rules, in the order they matter:

* The template folder is only read. Its ``form.ui``, ``template.json`` and
  pictures are the same bytes afterwards.
* The root object and the form class take the name row's name (``back_office``
  becomes ``BackOffice``); every other object name, connection and logic
  property is kept.
* A picture is copied to ``{forms}/pictures/``. A name that already holds a
  different file gets ``_2`` (so does a name that differs only in case); the
  same bytes are reused. Nothing already in the project is overwritten, and the
  pictures file ``forms/resources.qrc`` only gains entries.
* When creating the form fails after the pictures went in, the copied pictures
  and the pictures file are put back as they were.
* An own class keeps its declaration; its code is not copied. The result
  carries the FB035 sentences for modules this project lacks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.create import CreateResult, create_form
from app.features.form_builder.engine.project.custom_checks import custom_diagnostics
from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError, inside_project, restore, snapshot
from app.features.form_builder.engine.project.names import class_name_for_stem, explain_form_name
from app.features.form_builder.engine.project.pictures import canon_resource, picture_uses
from app.features.form_builder.engine.project.qrc_write import (
    PICTURES_FOLDER,
    add_pictures,
    default_qrc_path,
    include_location,
)
from app.features.form_builder.engine.project.user_templates import (
    FORM_FILE,
    TemplateInfo,
    renamed_root,
    rewritten_form,
)
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui

#: UX-TMPL-003 (the toast for FB035).
OWN_CLASS_TOAST = "%s comes from %s, which isn't in this project. The form shows a stand-in."


@dataclass(frozen=True)
class TemplateCreateResult:
    """``result`` is ``create_form``'s. ``notices`` are sentences for a toast, first first."""

    result: CreateResult
    notices: Tuple[str, ...] = ()


def create_from_template(
    project_root: str,
    info: TemplateInfo,
    stem: str,
    fs: OsFileSystem,
    *,
    directory: Optional[str] = None,
) -> TemplateCreateResult:
    """Write ``<stem>.ui`` and its Python files from ``info``, merging its pictures into the project."""
    root = os.path.abspath(project_root)
    folder = os.path.abspath(directory) if directory else os.path.join(root, "forms")
    if info.error:
        return _refused("That template can't be opened: %s" % info.error)
    if not inside_project(folder, root):
        return _refused("The form folder is outside the project.")
    reason = explain_form_name(stem, folder=folder, fs=fs)
    if reason is not None:
        return _refused(reason)
    try:
        template_text = fs.read_text(os.path.join(info.folder, FORM_FILE))
    except (OSError, UnicodeError):
        return _refused("That template can't be opened: %s can't be read." % FORM_FILE)
    class_name = class_name_for_stem(stem.strip())
    try:
        text = renamed_root(template_text, class_name)
    except ProjectOpError as exc:
        return _refused(str(exc))
    qrc = default_qrc_path(root)
    before = snapshot(fs, (qrc,))
    copied: List[str] = []
    try:
        text, copied = _merge_pictures(root, info, text, os.path.join(folder, stem.strip() + ".ui"), qrc, fs)
    except ProjectOpError as exc:
        _put_back(fs, before, copied)
        return _refused(str(exc))
    created = create_form(root, stem, fs, directory=folder, ui_text=text)
    if created.refused or created.scope is None:
        _put_back(fs, before, copied)
        return TemplateCreateResult(created)
    return TemplateCreateResult(created, _own_class_notices(text, root))


def _merge_pictures(
    root: str, info: TemplateInfo, text: str, ui_path: str, qrc: str, fs: OsFileSystem
) -> Tuple[str, List[str]]:
    """Copy the pictures ``text`` uses into the project and point ``text`` at the copies.

    Returns the new text and the files this call wrote (to undo them).
    """
    document = read_ui(text, allocator=IdAllocator()).document
    wanted: List[str] = []
    for use in picture_uses(document):
        resource = canon_resource(use.path)
        if resource.startswith(":/%s/" % PICTURES_FOLDER) and resource not in wanted:
            wanted.append(resource)
    if not wanted:
        return text, []
    sources: List[str] = []
    for resource in wanted:
        source = os.path.join(info.folder, PICTURES_FOLDER, resource[len(":/%s/" % PICTURES_FOLDER):])
        if not os.path.isfile(source):
            raise ProjectOpError("The template is missing the picture %s." % os.path.basename(source))
        sources.append(source)
    outcome = add_pictures(root, qrc, sources, fs)
    mapping: Dict[str, str] = dict(zip(wanted, outcome.resource_paths))
    edited = rewritten_form(text, rewrite=mapping, includes=(include_location(ui_path, outcome.qrc_path),))
    return edited, list(outcome.copied)


def _put_back(fs: OsFileSystem, before: Dict[str, Optional[bytes]], copied: List[str]) -> None:
    """Undo the pictures a failed create wrote. Only files this call made are removed."""
    for path in copied:
        try:
            if fs.is_file(path):
                fs.remove(path)
        except OSError:
            pass
    try:
        restore(fs, before)
    except OSError:
        pass
    for path in copied:
        folder = os.path.dirname(path)
        try:
            if fs.is_dir(folder) and not fs.listdir(folder):
                os.rmdir(folder)
        except OSError:
            pass


def _own_class_notices(text: str, root: str) -> Tuple[str, ...]:
    try:
        document = read_ui(text, allocator=IdAllocator()).document
    except UiReadError:
        return ()
    sentences: List[str] = []
    for item in custom_diagnostics(document, root):
        location = item.location
        class_name = location.rule_path[0] if location is not None and location.rule_path else ""
        module = item.message.split(" comes from ", 1)[-1].split(", which", 1)[0]
        if class_name:
            sentences.append(OWN_CLASS_TOAST % (class_name, module))
    return tuple(sentences)


def _refused(reason: str) -> TemplateCreateResult:
    return TemplateCreateResult(CreateResult(files=(), diagnostics=(), scope=None, refused=reason))

