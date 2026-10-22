"""User-facing phrases for the form tab. No Qt."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode
from app.features.form_builder.engine.ui4.values import RectValue

_LAYOUT_PHRASE = {
    "QFormLayout": "Form layout",
    "QVBoxLayout": "Vertical layout",
    "QHBoxLayout": "Horizontal layout",
    "QGridLayout": "Grid layout",
}


def undo_menu_text(prefix: str, command_label: Optional[str]) -> str:
    """Edit menu label. ``Edit XML`` reads as ``Undo XML edits``."""
    if not command_label:
        return prefix
    if command_label == "Edit XML":
        return "%s XML edits" % prefix
    return "%s %s" % (prefix, command_label)


def page_chip_text(document: UiDocument, fallback_name: str) -> tuple[str, str]:
    """Object name and the layout phrase for the page chip."""
    root = document.root
    name = root.object_name or fallback_name or "Form"
    layout = root.layout
    if isinstance(layout, LayoutNode) and layout.class_name:
        phrase = _LAYOUT_PHRASE.get(layout.class_name, layout.class_name)
    else:
        phrase = "No layout"
    return name, phrase


def page_size_text(document: UiDocument) -> Optional[str]:
    """``640 × 480`` from the root geometry, or None when the form has none."""
    entry = document.root.prop("geometry")
    value = None if entry is None else entry.value
    if not isinstance(value, RectValue):
        return None
    if value.width <= 0 or value.height <= 0:
        return None
    return "%d × %d" % (value.width, value.height)


def draft_clock(saved_at: str) -> str:
    """``14:02`` from an ISO timestamp. Empty when the text has no clock."""
    text = saved_at.strip()
    if "T" in text:
        clock = text.split("T", 1)[1]
    else:
        clock = text
    clock = clock.replace("Z", " ").split("+", 1)[0].split("-", 1)[0].strip()
    parts = clock.split(":")
    if len(parts) < 2 or not parts[0].isdigit() or len(parts[1]) < 2:
        return ""
    return "%02d:%s" % (int(parts[0]), parts[1][:2])


def recovered_draft_sentence(saved_at: str) -> str:
    clock = draft_clock(saved_at)
    if clock:
        return "Recovered unsaved changes from %s." % clock
    return "Recovered unsaved changes."


def external_change_sentence(file_name: str) -> str:
    return "%s changed on disk." % file_name


__all__ = [
    "draft_clock",
    "external_change_sentence",
    "page_chip_text",
    "page_size_text",
    "recovered_draft_sentence",
    "undo_menu_text",
]
