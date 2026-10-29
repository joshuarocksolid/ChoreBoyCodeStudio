"""Add a picture to a form: the file work and the commands that follow it (UX-RES-002, UX-RES-005).

Qt-free. ``plan_add`` does the file work (copy, ``.qrc``) and returns the form
commands to run. The caller runs them as one undo step; the files stay on disk
after Undo, and ``notice`` says so. ``adopt_raw_picture`` is the same for a
property that holds a file path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.commands.catalog import SetProperty, SetResourceIncludes
from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError, inside_project
from app.features.form_builder.engine.project.pictures import RawPicture, resource_locations
from app.features.form_builder.engine.project.qrc_write import (
    DEFAULT_QRC,
    AddOutcome,
    add_pictures,
    default_qrc_path,
    include_location,
)
from app.features.form_builder.engine.ui4.values import (
    ICON_STATES,
    IconSetValue,
    ResourcePixmap,
    Value,
)


@dataclass(frozen=True)
class PicturePlan:
    """``outcome`` is what was written. ``commands`` are for the form. ``label`` names the undo step."""

    outcome: AddOutcome
    commands: Tuple[Command, ...]
    label: str
    notice: str


def included_qrcs(document: object, ui_path: str) -> Tuple[str, ...]:
    """Absolute paths of the ``.qrc`` files the form includes, in file order."""
    if not ui_path:
        return ()
    folder = os.path.dirname(os.path.abspath(ui_path))
    found: List[str] = []
    for location in resource_locations(document):
        path = location if os.path.isabs(location) else os.path.normpath(os.path.join(folder, location))
        found.append(path)
    return tuple(found)


def default_target(document: object, ui_path: str, project_root: str) -> str:
    """The first included ``.qrc`` inside the project, else ``forms/resources.qrc`` (UX-RES-002)."""
    for path in included_qrcs(document, ui_path):
        if path.lower().endswith(".qrc") and inside_project(path, project_root):
            return path
    return default_qrc_path(project_root)


def include_commands(document: object, ui_path: str, qrc_path: str) -> Tuple[Command, ...]:
    """The command that adds the include, or nothing when the form already has it."""
    target = os.path.normcase(os.path.abspath(qrc_path))
    if any(os.path.normcase(os.path.abspath(path)) == target for path in included_qrcs(document, ui_path)):
        return ()
    location = include_location(ui_path, qrc_path)
    return (SetResourceIncludes(resource_locations(document) + (location,)),)


def plan_add(
    document: object,
    ui_path: str,
    project_root: str,
    sources: Sequence[str],
    target_qrc: str = "",
    fs: Optional[OsFileSystem] = None,
) -> PicturePlan:
    """Copy ``sources`` into the project and list them; return the include command and the notice."""
    if not project_root or not ui_path:
        raise ProjectOpError("Save the form in a project before adding pictures.")
    qrc = target_qrc or default_target(document, ui_path, project_root)
    outcome = add_pictures(project_root, qrc, sources, fs)
    commands = include_commands(document, ui_path, outcome.qrc_path)
    return PicturePlan(outcome, commands, _label(outcome), _notice(outcome))


def with_picture(value: Optional[Value], state: str, path: str) -> Value:
    """``value`` with the picture at ``state`` (``""`` for a plain pixmap) set to ``path``."""
    if state == "":
        return ResourcePixmap(path)
    if not isinstance(value, IconSetValue):
        raise ProjectOpError("That icon changed. Try again.")
    if state == "text":
        return replace(value, text=path)
    if state not in ICON_STATES:
        raise ProjectOpError("That icon changed. Try again.")
    old = getattr(value, state)
    pixmap = replace(old, path=path) if isinstance(old, ResourcePixmap) else ResourcePixmap(path)
    changed = replace(value, **{state: pixmap})
    # The legacy text is a copy of the normal picture; keep them together.
    if state == "normaloff" and value.text and value.text == (old.path if isinstance(old, ResourcePixmap) else ""):
        changed = replace(changed, text=path)
    return changed


def raw_source(raw: RawPicture, ui_path: str) -> str:
    """The absolute file a raw path names."""
    if os.path.isabs(raw.path):
        return raw.path
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(ui_path)), raw.path))


def adopt_raw_picture(
    document: object,
    ui_path: str,
    project_root: str,
    raw: RawPicture,
    fs: Optional[OsFileSystem] = None,
) -> PicturePlan:
    """UX-RES-005: add the file to the project's pictures and point the property at it.

    Raises ``ProjectOpError`` when the file is gone or the property changed.
    """
    node = document.node(raw.node_id)  # type: ignore[attr-defined]
    entry = node.prop(raw.property_name)
    if entry is None:
        raise ProjectOpError("That picture is no longer on the form.")
    source = raw_source(raw, ui_path)
    if not os.path.isfile(source):
        raise ProjectOpError("Code Studio can't find %s." % os.path.basename(source))
    plan = plan_add(document, ui_path, project_root, [source], fs=fs)
    value = with_picture(entry.value, raw.state, plan.outcome.resource_paths[0])
    set_value = SetProperty(raw.node_id, raw.property_name, value, undo_label=plan.label)  # type: ignore[arg-type]
    return replace(plan, commands=plan.commands + (set_value,))


def stop_using(document: object, qrc_location: str) -> Command:
    """The command that removes one include."""
    return SetResourceIncludes(tuple(loc for loc in resource_locations(document) if loc != qrc_location))


def _label(outcome: AddOutcome) -> str:
    if len(outcome.file_names) == 1:
        return "Add picture %s" % outcome.file_names[0]
    return "Add %d pictures" % len(outcome.file_names)


def _notice(outcome: AddOutcome) -> str:
    sentence = _added(outcome)
    if outcome.dropped_parts:
        sentence += " Comments in %s were not kept." % os.path.basename(outcome.qrc_relative)
    return sentence


def _added(outcome: AddOutcome) -> str:
    if len(outcome.file_names) == 1:
        name = outcome.file_names[0]
        if outcome.qrc_created and outcome.qrc_relative == DEFAULT_QRC:
            return "Made %s for this project's pictures and added %s." % (outcome.qrc_relative, name)
        return "Added %s to %s. Undo keeps the copied file." % (name, outcome.qrc_relative)
    count = len(outcome.file_names)
    if outcome.qrc_created and outcome.qrc_relative == DEFAULT_QRC:
        return "Made %s for this project's pictures and added %d pictures." % (outcome.qrc_relative, count)
    return "Added %d pictures to %s. Undo keeps the copied files." % (count, outcome.qrc_relative)


__all__ = [
    "PicturePlan",
    "adopt_raw_picture",
    "default_target",
    "include_commands",
    "included_qrcs",
    "plan_add",
    "raw_source",
    "stop_using",
    "with_picture",
]
