"""Picture files dropped on the form (UX-RES-003): what each target takes and what the drop does.

The canvas owns the drag and drop events (M5.1 exposes a hook for file drops).
This module is the handler behind that hook: it says whether a drop is
accepted, runs the file work of "Add picture" and returns the commands for
one undo step. It never touches the canvas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError
from app.features.form_builder.engine.project.picture_adopt import PicturePlan, plan_add
from app.features.form_builder.engine.project.pictures import is_image_name
from app.features.form_builder.engine.project.qrc_write import NOT_A_PICTURE
from app.features.form_builder.engine.ui4.values import IconSetValue, ResourcePixmap

#: Class -> the property a dropped picture sets (UX-RES-003).
TARGETS = {
    "QLabel": "pixmap",
    "QPushButton": "icon",
    "QToolButton": "icon",
}
FORM_PROPERTY = "windowIcon"


@dataclass(frozen=True)
class FileDrop:
    plan: PicturePlan
    commands: Tuple[Command, ...]
    label: str
    notice: str


def accepts(class_name: str, is_root: bool) -> Optional[str]:
    """The property a picture dropped on this widget would set, or None when it takes none."""
    if is_root:
        return FORM_PROPERTY
    return TARGETS.get(class_name)


def refusal(paths: Sequence[str]) -> Optional[str]:
    """"Only pictures can go here." when any dropped file is not a picture, else None."""
    if not paths or not all(is_image_name(path) for path in paths):
        return NOT_A_PICTURE
    return None


def plan_file_drop(
    document: object,
    ui_path: str,
    project_root: str,
    target_id: object,
    paths: Sequence[str],
    fs: Optional[OsFileSystem] = None,
) -> FileDrop:
    """Copy the pictures in and build the commands; ``ProjectOpError`` carries the sentence to show."""
    wrong = refusal(paths)
    if wrong:
        raise ProjectOpError(wrong)
    node = document.node(target_id)  # type: ignore[attr-defined]
    is_root = document.root.id == node.id  # type: ignore[attr-defined]
    property_name = accepts(getattr(node, "class_name", ""), is_root)
    if property_name is None:
        raise ProjectOpError("Pictures can't go on this widget.")
    plan = plan_add(document, ui_path, project_root, paths, fs=fs)
    stored = plan.outcome.resource_paths[0]
    if property_name == "pixmap":
        value: object = ResourcePixmap(stored)
    else:
        value = IconSetValue(normaloff=ResourcePixmap(stored), text=stored)
    write = SetProperty(target_id, property_name, value, undo_label=plan.label)  # type: ignore[arg-type]
    return FileDrop(plan, plan.commands + (write,), plan.label, plan.notice)


__all__ = ["FORM_PROPERTY", "FileDrop", "TARGETS", "accepts", "plan_file_drop", "refusal"]
