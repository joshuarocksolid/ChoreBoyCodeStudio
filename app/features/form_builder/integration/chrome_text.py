"""User-facing phrases for the form tab. No Qt."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.values import RectValue, StringValue

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


def page_title_text(document: UiDocument) -> str:
    """Window title, or the object name when the form has none."""
    entry = document.root.prop("windowTitle")
    value = None if entry is None else entry.value
    if isinstance(value, StringValue) and value.text:
        return value.text
    return document.root.object_name or "Form"


def page_chip_label(document: UiDocument, fallback_name: str) -> str:
    """``Name · Vertical layout`` for the single chip above the page."""
    name, phrase = page_chip_text(document, fallback_name)
    return "%s · %s" % (name, phrase)


def page_size_text(document: UiDocument) -> Optional[str]:
    """``640 × 480`` from the root geometry, or None when the form has none."""
    entry = document.root.prop("geometry")
    value = None if entry is None else entry.value
    if not isinstance(value, RectValue):
        return None
    if value.width <= 0 or value.height <= 0:
        return None
    return "%d × %d" % (value.width, value.height)


def widget_class_phrase(class_name: str) -> str:
    """``QLineEdit`` reads as ``Line edit``."""
    text = class_name[1:] if class_name.startswith("Q") and len(class_name) > 1 else class_name
    parts: list[str] = []
    current = ""
    for char in text:
        if char.isupper() and current:
            parts.append(current)
            current = char
        else:
            current += char
    if current:
        parts.append(current)
    if not parts:
        return class_name or "Widget"
    return parts[0] + "".join(" " + part.lower() for part in parts[1:])


def selection_sentence(document: UiDocument, current: Optional[NodeId], count: int) -> str:
    """Status-bar sentence. Object names only. Never a session id."""
    if count > 1:
        return "%d widgets selected" % count
    if current is None or current == document.root.id:
        name, phrase = page_chip_text(document, "Form")
        return "%s · %s" % (name, phrase)
    node = document.get(current)
    if not isinstance(node, WidgetNode):
        name, phrase = page_chip_text(document, "Form")
        return "%s · %s" % (name, phrase)
    name = node.object_name or "Widget"
    kind = widget_class_phrase(node.class_name)
    place = _place_phrase(document, node)
    if place:
        return "%s · %s · %s" % (name, kind, place)
    return "%s · %s" % (name, kind)


def _place_phrase(document: UiDocument, node: WidgetNode) -> str:
    parent = document.parent(node.id)
    if not isinstance(parent, LayoutItemNode):
        return ""
    layout = document.parent(parent.id)
    if not isinstance(layout, LayoutNode):
        return ""
    index = parent.index_in_parent() + 1
    row = parent.row
    column = parent.column
    if layout.class_name == "QFormLayout":
        number = row + 1 if isinstance(row, int) else index
        return "row %d of the form layout" % number
    if layout.class_name == "QGridLayout":
        row_number = row + 1 if isinstance(row, int) else index
        column_number = column + 1 if isinstance(column, int) else 1
        return "row %d, column %d of the grid" % (row_number, column_number)
    if layout.class_name == "QHBoxLayout":
        return "column %d of the horizontal layout" % index
    if layout.class_name == "QVBoxLayout":
        return "row %d of the vertical layout" % index
    return "item %d of the layout" % index


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
    "page_chip_label",
    "page_chip_text",
    "page_size_text",
    "page_title_text",
    "recovered_draft_sentence",
    "selection_sentence",
    "undo_menu_text",
    "widget_class_phrase",
]
