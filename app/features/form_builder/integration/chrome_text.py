"""User-facing phrases for the form tab. No Qt."""

from __future__ import annotations

import re
from typing import Optional, Sequence

from app.features.form_builder.engine.query.selection import SelectionState
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, Node, SpacerNode, WidgetNode
from app.features.form_builder.engine.ui4.values import RectValue
from app.intelligence.diagnostics_models import CodeDiagnostic, DiagnosticSeverity

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


def problem_summary(rows: Sequence[CodeDiagnostic]) -> str:
    """``2 problems: 1 error, 1 warning``. Empty when there are none."""
    if not rows:
        return ""
    parts = []
    for severity, one, many in (
        (DiagnosticSeverity.ERROR, "error", "errors"),
        (DiagnosticSeverity.WARNING, "warning", "warnings"),
        (DiagnosticSeverity.INFO, "info", "info"),
    ):
        count = sum(1 for row in rows if row.severity == severity)
        if count:
            parts.append("%d %s" % (count, one if count == 1 else many))
    noun = "problem" if len(rows) == 1 else "problems"
    return "%d %s: %s" % (len(rows), noun, ", ".join(parts))


def problem_property_sentence(property_name: str) -> str:
    """``This problem is about Buddy.`` for ``buddy``; ``toolTip`` reads ``Tool tip``."""
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", property_name).lower()
    return "This problem is about %s." % (words[:1].upper() + words[1:])


def selection_sentence(document: UiDocument, selection: SelectionState) -> str:
    """``email · Line edit · row 2 of the form layout`` from names and class words, never a node id.

    Nothing selected, or the root, reads ``Invoice · the form · 640 × 480``.
    """
    if len(selection.ids) > 1:
        return "%d selected" % len(selection.ids)
    node = None if selection.current is None else document.get(selection.current)
    root = document.root
    if node is None or node.id == root.id:
        parts = [root.object_name or "Form", "the form", page_size_text(document) or ""]
    else:
        parts = [_node_name(node), _kind_word(node), _place(document, node)]
    return " · ".join(part for part in parts if part)


def _class_word(class_name: str) -> str:
    """``QLineEdit`` reads ``Line edit``. A class without the Qt prefix keeps its name."""
    if not re.match(r"Q[A-Z]", class_name):
        return class_name
    words = re.findall(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z][a-z0-9]*", class_name[1:])
    rest = [word if word.isupper() and len(word) > 1 else word.lower() for word in words[1:]]
    return " ".join([words[0]] + rest)


def _node_name(node: Node) -> str:
    if isinstance(node, (WidgetNode, LayoutNode)):
        return node.object_name
    if isinstance(node, SpacerNode):
        return node.name
    return ""


def _kind_word(node: Node) -> str:
    if isinstance(node, WidgetNode):
        return _class_word(node.class_name)
    if isinstance(node, LayoutNode):
        return _LAYOUT_PHRASE.get(node.class_name) or _class_word(node.class_name)
    if isinstance(node, SpacerNode):
        return "Spacer"
    return ""


def _place(document: UiDocument, node: Node) -> str:
    item = None if node.parent_id is None else document.get(node.parent_id)
    if not isinstance(item, LayoutItemNode) or item.parent_id is None:
        return ""
    layout = document.get(item.parent_id)
    if not isinstance(layout, LayoutNode):
        return ""
    known = _LAYOUT_PHRASE.get(layout.class_name)
    phrase = known[0].lower() + known[1:] if known else layout.class_name
    if layout.class_name == "QGridLayout":
        return "row %d, column %d of the %s" % ((item.row or 0) + 1, (item.column or 0) + 1, phrase)
    if layout.class_name == "QHBoxLayout":
        return "column %d of the %s" % (item.slot_index + 1, phrase)
    row = item.row if item.row is not None else item.slot_index
    return "row %d of the %s" % (row + 1, phrase)


__all__ = [
    "draft_clock",
    "external_change_sentence",
    "page_chip_label",
    "page_chip_text",
    "page_size_text",
    "problem_property_sentence",
    "problem_summary",
    "recovered_draft_sentence",
    "selection_sentence",
    "undo_menu_text",
]
