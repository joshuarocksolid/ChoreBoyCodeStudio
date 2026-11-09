"""Stop a form save before it replaces a hand-edited generated file."""

from __future__ import annotations

import os
from typing import Callable, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.header import is_hand_edited
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.project.save import resource_destination
from app.features.form_builder.engine.ui4.document import UiDocument

OpenBuffer = Callable[[str], Optional[Tuple[str, bool]]]
ReadDisk = Callable[[str], Optional[str]]


def watched_generated_paths(scope: Optional[FormScope], document: UiDocument) -> Tuple[str, ...]:
    """``ui_*.py`` and each ``*_rc.py`` this form would rewrite."""
    if scope is None:
        return ()
    paths = []
    if scope.generated_path:
        paths.append(scope.generated_path)
    if scope.project_root and scope.ui_path:
        for node in document.ui.children("resources"):
            location = node.field("location")
            if not isinstance(location, str) or not location.strip():
                continue
            module = os.path.splitext(os.path.basename(location))[0] + "_rc"
            paths.append(resource_destination(scope.project_root, scope.ui_path, location, module))
    return tuple(paths)


def first_hand_edited_output(
    paths: Sequence[str],
    *,
    open_buffer: OpenBuffer,
    read_disk: ReadDisk,
) -> Optional[str]:
    """The first output that has a dirty buffer or a hand-edited file on disk."""
    for path in paths:
        opened = open_buffer(path)
        if opened is not None:
            text, dirty = opened
            if dirty or is_hand_edited(text):
                return path
            continue
        disk = read_disk(path)
        if disk is not None and is_hand_edited(disk):
            return path
    return None


__all__ = ["first_hand_edited_output", "watched_generated_paths"]
