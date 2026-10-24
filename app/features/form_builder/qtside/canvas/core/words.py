"""Chip labels and the sentences the canvas speaks."""

from __future__ import annotations

from typing import Literal, Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.selection import SelectionState
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, SpacerNode, WidgetNode
from app.features.form_builder.qtside.canvas.core.structure import effective_class, effective_selection

SizingWord = Literal["Hug", "Fill", "Fixed"]

ELIDE_AT = 24

FIRST_FOCUS_HINT = (
    "Tab moves between widgets. Alt+4 goes to the inspector, Alt+1 to the outline."
)
RESIZE_IN_LAYOUT_LATER = "Size handles on widgets in a layout arrive with Hug, Fill and Fixed."

_FILL = frozenset({"Expanding", "MinimumExpanding", "Ignored"})
_HUG = frozenset({"Preferred", "Fixed"})
_LAYOUT = {
    "QHBoxLayout": ("Horizontal", "Horizontal layout"),
    "QVBoxLayout": ("Vertical", "Vertical layout"),
    "QGridLayout": ("Grid", "Grid layout"),
    "QFormLayout": ("Form", "Form layout"),
}
_CLASS_WORDS = {
    "QLabel": "Label",
    "QPushButton": "Push button",
    "QToolButton": "Tool button",
    "QRadioButton": "Radio button",
    "QCheckBox": "Check box",
    "QCommandLinkButton": "Command link button",
    "QLineEdit": "Line edit",
    "QGroupBox": "Group box",
    "QFrame": "Frame",
    "QWidget": "Widget",
    "QScrollArea": "Scroll area",
    "QTabWidget": "Tab widget",
    "QStackedWidget": "Stacked widget",
    "QToolBox": "Toolbox",
    "QSplitter": "Splitter",
    "QMainWindow": "Main window",
    "QDialog": "Dialog",
    "QComboBox": "Combo box",
    "QListWidget": "List",
    "QTextEdit": "Text edit",
    "QPlainTextEdit": "Plain text",
    "QSpinBox": "Spin box",
    "QSlider": "Slider",
    "QProgressBar": "Progress bar",
}


def sizing_word(policy: str, fixed_size: bool) -> Optional[SizingWord]:
    """Hug, Fill, or Fixed. None is a custom policy the chip does not name."""
    name = policy.split("::")[-1]
    if name == "Fixed" and fixed_size:
        return "Fixed"
    if name in _FILL:
        return "Fill"
    if name in _HUG:
        return "Hug"
    return None


def elide_middle(name: str, limit: int = ELIDE_AT) -> str:
    if len(name) <= limit:
        return name
    if limit < 2:
        return name[:limit]
    keep = limit - 1
    left = keep // 2
    right = keep - left
    return name[:left] + "…" + name[-right:]


def chip_text(
    document: UiDocument,
    state: SelectionState,
    sizing: Optional[Tuple[Optional[SizingWord], Optional[SizingWord]]],
) -> str:
    shown = effective_selection(document, state)
    current = document.get(shown.current) if shown.current is not None else None
    name = elide_middle(_name(current))
    if len(state.ids) > 1:
        return "%s + %d more" % (elide_middle(_name(document.get(state.current))), len(state.ids) - 1)
    if isinstance(current, LayoutNode):
        phrase = _layout_words(current.class_name)[1]
        count = sum(1 for item in current.items if item.content is not None)
        noun = "item" if count == 1 else "items"
        return "%s · %s · %d %s" % (name, phrase, count, noun)
    if isinstance(current, WidgetNode) and current.layout is not None:
        return "%s · %s" % (name, _layout_words(current.layout.class_name)[0])
    if sizing is not None:
        words = [word for word in sizing if word]
        if words:
            return "%s · %s" % (name, " × ".join(words))
    return name


def no_layout_text() -> str:
    return "No layout"


def page_chip_label(document: UiDocument, fallback_name: str) -> str:
    """``Name · Vertical layout`` above the page."""
    name = document.root.object_name or fallback_name or "Form"
    layout = document.root.layout
    if isinstance(layout, LayoutNode) and layout.class_name:
        phrase = _layout_words(layout.class_name)[1]
    else:
        phrase = no_layout_text()
    return "%s · %s" % (name, phrase)


def hover_sentence(document: UiDocument, node: NodeId, double_click_edits: bool) -> str:
    found = document.get(node)
    action = "double-click to edit text" if double_click_edits else "click to select"
    return "%s · %s · %s" % (_name(found), _friendly(document, found), action)


def describe_selection(document: UiDocument, state: SelectionState) -> str:
    shown = effective_selection(document, state)
    pieces = []
    for node_id in shown.ids:
        found = document.get(node_id)
        if found is None:
            continue
        place = _place(document, found)
        text = "%s, %s" % (_name(found), _friendly(document, found).lower())
        if place:
            text = "%s, %s" % (text, place)
        pieces.append(text)
    if not pieces:
        return "Selected: form"
    return "Selected: %s" % "; ".join(pieces)


def zoom_label(factor: float) -> str:
    return "%d%%" % int(round(factor * 100))


def _name(node: object) -> str:
    if isinstance(node, WidgetNode):
        return node.object_name or "widget"
    if isinstance(node, LayoutNode):
        return node.object_name or "layout"
    if isinstance(node, SpacerNode):
        return node.name or "spacer"
    return "item"


def _friendly(document: UiDocument, node: object) -> str:
    if isinstance(node, LayoutNode):
        return _layout_words(node.class_name)[1]
    if isinstance(node, SpacerNode):
        return "Spacer"
    if isinstance(node, WidgetNode):
        class_name = effective_class(document, node)
        known = _CLASS_WORDS.get(class_name)
        if known:
            return known
        return _split_class(class_name)
    return "Item"


def _layout_words(class_name: str) -> Tuple[str, str]:
    return _LAYOUT.get(class_name, (class_name or "Layout", class_name or "Layout"))


def _split_class(class_name: str) -> str:
    bare = class_name[1:] if class_name.startswith("Q") and len(class_name) > 1 else class_name
    chars = []
    for index, char in enumerate(bare):
        if char.isupper() and index and bare[index - 1].islower():
            chars.append(" ")
        chars.append(char)
    return "".join(chars)


def _place(document: UiDocument, node: object) -> str:
    if not isinstance(node, (WidgetNode, SpacerNode, LayoutNode)):
        return ""
    parent = document.parent(node.id)
    if not isinstance(parent, LayoutItemNode):
        return ""
    layout = document.parent(parent.id)
    if not isinstance(layout, LayoutNode):
        return ""
    contents = []
    for item in layout.items:
        content = item.content
        if content is not None:
            contents.append(content)
    index = next((pos for pos, content in enumerate(contents) if content.id == node.id), None)
    if index is None:
        return ""
    if layout.class_name == "QVBoxLayout":
        axis = "row"
    elif layout.class_name == "QHBoxLayout":
        axis = "column"
    else:
        axis = "item"
    return "%s %d of the %s" % (axis, index + 1, _spaced(layout.object_name or "layout"))


def _spaced(name: str) -> str:
    chars = []
    for index, char in enumerate(name):
        if char.isupper() and index and (name[index - 1].islower() or name[index - 1].isdigit()):
            chars.append(" ")
        chars.append(char.lower())
    return "".join(chars)
