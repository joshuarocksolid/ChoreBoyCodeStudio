"""What the Text colour and Background rows read and write (UX-STYLE-010, UX-STYLE-012). Qt-free.

* **Background** writes one palette role in the active, inactive and disabled
  groups, and ``autoFillBackground`` where Qt would otherwise paint nothing.
* **Text colour** writes a ``color`` declaration in the widget's own style
  sheet (FreeCAD's application style sheet overrides palette text roles on
  ChoreBoy, so a palette role would not show there). It *reads* the palette
  text role so a colour set in Designer still appears.
* The form's **accent colour** is the root palette's Highlight and Link roles;
  its **text size** is the point size of the root font.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.style.classes import effective_class, is_a, widget_chain
from app.features.form_builder.engine.style.colors import Rgb, hex_text
from app.features.form_builder.engine.style.edit import read_rgb, remove_color, set_color
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    BrushValue,
    ColorRole,
    ColorValue,
    FontValue,
    PaletteValue,
    StringValue,
)

#: The order roles are written in, the palette editor's order.
ROLE_ORDER: Tuple[str, ...] = (
    "Window",
    "WindowText",
    "Base",
    "AlternateBase",
    "Text",
    "PlaceholderText",
    "Button",
    "ButtonText",
    "BrightText",
    "Highlight",
    "HighlightedText",
    "Link",
    "LinkVisited",
    "ToolTipBase",
    "ToolTipText",
    "Light",
    "Midlight",
    "Mid",
    "Dark",
    "Shadow",
)
GROUPS: Tuple[str, ...] = ("active", "inactive", "disabled")

TEXT_SIZE_MIN = 8
TEXT_SIZE_MAX = 24

PALETTE_CAPTION = "Set by the palette. ChoreBoy shows its own text colour; pick a colour here to override it."
OVERRIDDEN_CAPTION = "The style sheet sets this colour, so this one has no effect."


@dataclass(frozen=True)
class Roles:
    """The palette roles a class uses. ``fill`` is True when Qt paints no background without ``autoFillBackground``."""

    text: str
    background: str
    fill: bool


_WINDOW = Roles("WindowText", "Window", True)
_BUTTON = Roles("ButtonText", "Button", False)
_BASE = Roles("Text", "Base", False)
#: Qt paints a check box and a radio button from the Button role, not Window, and
#: a command link only with the fill on (found by the pixel check under Fusion).
_CHECK = Roles("WindowText", "Button", True)
_LINK = Roles("ButtonText", "Button", True)


def roles_for(document: UiDocument, node: WidgetNode) -> Optional[Roles]:
    """The roles of ``node``, or None when its class has neither row (a progress bar, a tab bar ...)."""
    chain = widget_chain(document, node)
    is_form = node.id == document.root.id
    if is_a(chain, "QAbstractSpinBox", "QLineEdit", "QTextEdit", "QPlainTextEdit", "QAbstractItemView"):
        return _BASE
    if is_a(chain, "QComboBox"):
        return _BASE if _editable(node) else _BUTTON
    if is_a(chain, "QCommandLinkButton"):
        return _LINK
    if is_a(chain, "QPushButton", "QToolButton"):
        return _BUTTON
    if is_a(chain, "QCheckBox", "QRadioButton"):
        return _CHECK
    if is_form:
        return _WINDOW
    base = effective_class(chain)
    if base in ("QLabel", "QGroupBox", "QFrame", "QWidget"):
        return _WINDOW
    return None


def _editable(node: WidgetNode) -> bool:
    entry = node.prop("editable")
    return entry is not None and isinstance(entry.value, BoolValue) and entry.value.value


def _widget(document: UiDocument, owner: NodeId) -> WidgetNode:
    node = document.node(owner)
    if not isinstance(node, WidgetNode):
        raise ValueError("not a widget")
    return node


def shows_rows(document: UiDocument, owners: Tuple[NodeId, ...]) -> bool:
    """True when every owner is a widget that has the Text colour and Background rows."""
    if not owners:
        return False
    for owner in owners:
        node = document.get(owner)
        if not isinstance(node, WidgetNode) or roles_for(document, node) is None:
            return False
    return True


# palette ------------------------------------------------------------------


def _solid(rgb: Rgb) -> BrushValue:
    return BrushValue(brushstyle="SolidPattern", color=ColorValue(rgb[0], rgb[1], rgb[2]))


def _palette_of(node: WidgetNode) -> PaletteValue:
    entry = node.prop("palette")
    if entry is not None and isinstance(entry.value, PaletteValue):
        return entry.value
    return PaletteValue()


def role_color(node: WidgetNode, role: str) -> Optional[Rgb]:
    """The colour of ``role`` in the active group, when it is a plain colour."""
    for item in _palette_of(node).active:
        if item.role == role:
            color = item.brush.color
            if color is not None and item.brush.brushstyle in (None, "SolidPattern"):
                return (color.red, color.green, color.blue)
    return None


def with_roles(palette: PaletteValue, wanted: Dict[str, Optional[Rgb]]) -> PaletteValue:
    """``palette`` with each role in ``wanted`` set in all three groups (None removes it)."""
    groups = {}
    for group in GROUPS:
        kept = {item.role: item for item in getattr(palette, group) if item.role not in wanted}
        for role, rgb in wanted.items():
            if rgb is not None:
                kept[role] = ColorRole(role, _solid(rgb))
        ordered = [kept[role] for role in ROLE_ORDER if role in kept]
        ordered.extend(item for role, item in kept.items() if role not in ROLE_ORDER)
        groups[group] = tuple(ordered)
    return PaletteValue(active=groups["active"], inactive=groups["inactive"], disabled=groups["disabled"])


def _is_empty(palette: PaletteValue) -> bool:
    return not (palette.active or palette.inactive or palette.disabled)


def _palette_command(owner: NodeId, palette: PaletteValue, label: str) -> SetProperty:
    value = None if _is_empty(palette) else palette
    return SetProperty(owner, "palette", value, undo_label=label)


def background_color(document: UiDocument, owner: NodeId) -> Optional[Rgb]:
    node = _widget(document, owner)
    roles = roles_for(document, node)
    return role_color(node, roles.background) if roles is not None else None


def background_commands(document: UiDocument, owner: NodeId, rgb: Rgb, label: str) -> Tuple[Command, ...]:
    node = _widget(document, owner)
    roles = roles_for(document, node)
    if roles is None:
        return ()
    commands: List[Command] = [_palette_command(owner, with_roles(_palette_of(node), {roles.background: rgb}), label)]
    if roles.fill and not _auto_fill(node):
        commands.append(SetProperty(owner, "autoFillBackground", BoolValue(True), undo_label=label))
    return tuple(commands)


def clear_background_commands(document: UiDocument, owner: NodeId, label: str) -> Tuple[Command, ...]:
    node = _widget(document, owner)
    roles = roles_for(document, node)
    if roles is None or role_color(node, roles.background) is None:
        return ()
    cleared = with_roles(_palette_of(node), {roles.background: None})
    commands: List[Command] = [_palette_command(owner, cleared, label)]
    if roles.fill and _auto_fill(node) and not any(item.role in ("Window", "Button", "Base") for item in cleared.active):
        commands.append(SetProperty(owner, "autoFillBackground", None, undo_label=label))
    return tuple(commands)


def _auto_fill(node: WidgetNode) -> bool:
    entry = node.prop("autoFillBackground")
    return entry is not None and isinstance(entry.value, BoolValue) and entry.value.value


# text colour --------------------------------------------------------------


def _sheet_text(node: WidgetNode) -> str:
    entry = node.prop("styleSheet")
    if entry is not None and isinstance(entry.value, StringValue):
        return entry.value.text
    return ""


def own_text_color(document: UiDocument, owner: NodeId) -> Optional[Rgb]:
    """The ``color`` the widget's own sheet sets for it, when it reads as a colour."""
    node = _widget(document, owner)
    return read_rgb(_sheet_text(node), node.object_name)


def has_own_text_color(document: UiDocument, owner: NodeId) -> bool:
    node = _widget(document, owner)
    from app.features.form_builder.engine.style.edit import read_color

    return read_color(_sheet_text(node), node.object_name) is not None


def palette_text_color(document: UiDocument, owner: NodeId) -> Optional[Rgb]:
    node = _widget(document, owner)
    roles = roles_for(document, node)
    return role_color(node, roles.text) if roles is not None else None


def _sheet_command(owner: NodeId, node: WidgetNode, text: str, label: str) -> SetProperty:
    if not text.strip():
        return SetProperty(owner, "styleSheet", None, undo_label=label)
    entry = node.prop("styleSheet")
    base = entry.value if entry is not None and isinstance(entry.value, StringValue) else StringValue("")
    return SetProperty(owner, "styleSheet", replace(base, text=text), undo_label=label)


def text_color_commands(document: UiDocument, owner: NodeId, rgb: Rgb, label: str) -> Tuple[Command, ...]:
    """Raises ``StyleEditRefused`` when the widget's sheet has an error."""
    node = _widget(document, owner)
    text = set_color(_sheet_text(node), rgb, node.object_name)
    return (_sheet_command(owner, node, text, label),)


def clear_text_color_commands(document: UiDocument, owner: NodeId, label: str) -> Tuple[Command, ...]:
    node = _widget(document, owner)
    before = _sheet_text(node)
    after = remove_color(before, node.object_name)
    if after == before:
        return ()
    return (_sheet_command(owner, node, after, label),)


# the form's Look group ------------------------------------------------------

ACCENT_ROLES: Tuple[str, str] = ("Highlight", "Link")


def accent_color(document: UiDocument) -> Optional[Rgb]:
    return role_color(document.root, ACCENT_ROLES[0])


def accent_commands(document: UiDocument, rgb: Optional[Rgb], label: str) -> Tuple[Command, ...]:
    root = document.root
    palette = with_roles(_palette_of(root), {role: rgb for role in ACCENT_ROLES})
    if palette == _palette_of(root):
        return ()
    return (_palette_command(root.id, palette, label),)


def text_size(document: UiDocument) -> Optional[int]:
    entry = document.root.prop("font")
    if entry is not None and isinstance(entry.value, FontValue):
        return entry.value.pointsize
    return None


def text_size_commands(document: UiDocument, points: Optional[int], label: str) -> Tuple[Command, ...]:
    root = document.root
    entry = root.prop("font")
    font = entry.value if entry is not None and isinstance(entry.value, FontValue) else FontValue()
    if points is not None:
        points = max(TEXT_SIZE_MIN, min(TEXT_SIZE_MAX, int(points)))
    changed = replace(font, pointsize=points)
    if changed == font and entry is not None:
        return ()
    if changed == FontValue():
        return (SetProperty(root.id, "font", None, undo_label=label),) if entry is not None else ()
    return (SetProperty(root.id, "font", changed, undo_label=label),)


def swatch_text(rgb: Rgb) -> str:
    return hex_text(*rgb)
