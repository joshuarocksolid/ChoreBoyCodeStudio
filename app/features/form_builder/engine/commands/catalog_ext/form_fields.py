"""Form settings: the form's own fields, and the free-placement grid (UX-FSET-001 ... 006).

``SetFormField`` (CONTRACTS section 1.4, the M5.5b row) writes one field of the ``<ui>`` element: the Code group
(``author``, ``layoutdefault``, ``layoutfunction``, ``pixmapfunction``,
``includes``, ``exportmacro``, ``comment``), the Translation group
(``idbasedtr``, ``language``, ``displayname``) and the older ``stdsetdef`` /
``stdSetDef`` attributes, which are only ever kept or removed. ``SetFormGrid``
writes one value of the free-placement grid into ``<designerdata>``, the way
Qt Designer stores it, and writes nothing for a value that equals its default.

The read helpers (``form_grid``, ``has_free_container``) are Qt-free and shared
with the canvas, which snaps to the same step.
"""

from __future__ import annotations

import keyword
from dataclasses import dataclass
from typing import ClassVar, Optional, Tuple, Union

from app.features.form_builder.engine.commands import planning
from app.features.form_builder.engine.commands.base import CommandRejected, PlanContext
from app.features.form_builder.engine.commands.catalog import _CommandBase
from app.features.form_builder.engine.commands.ops import RemoveNodeOp
from app.features.form_builder.engine.sizing import placed_freely
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.opaque import OpaqueElement
from app.features.form_builder.engine.ui4.schema import LayoutDefault, LayoutFunction
from app.features.form_builder.engine.ui4.spec import NodeSpec

#: Fields ``SetFormField`` writes. Anything else is refused.
TEXT_FIELDS = ("author", "comment", "exportmacro", "pixmapfunction", "language", "displayname")
FLAG_FIELDS = ("idbasedtr",)
LEGACY_FIELDS = ("stdsetdef", "stdSetDef")
FORM_FIELDS = TEXT_FIELDS + FLAG_FIELDS + LEGACY_FIELDS + ("layoutdefault", "layoutfunction", "includes")

NAME_REFUSAL = "Use a function name like margin_for."
CHANGE_PREFIX = "Change form setting: "
REMOVE_LEGACY = "Remove older file setting"

#: One line of the include list: ``(location, text)``. ``location`` is "local" or "global".
IncludeLine = Tuple[str, str]

GRID_STEP_DEFAULT = 8
GRID_STEP_MIN = 2
GRID_STEP_MAX = 100

GRID_PARTS = ("show", "across", "down", "snap")
_PROPERTY = {"show": ("gridVisible",), "across": ("gridDeltaX",), "down": ("gridDeltaY",), "snap": ("gridSnapX", "gridSnapY")}
#: The order Qt Designer writes the grid in. A new property goes before the first later one.
_ORDER = ("gridDeltaX", "gridDeltaY", "gridSnapX", "gridSnapY", "gridVisible")


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add(SetFormField)
    add(SetFormGrid)


def function_name_ok(text: str) -> bool:
    """A Python name, or dotted names (``tools.margin_for``), that is not a keyword."""
    parts = text.split(".")
    return all(part.isidentifier() and not keyword.iskeyword(part) for part in parts)


def lower_label(label: str) -> str:
    """"Translate by ID" -> "translate by id" (the undo names of UX-M5-008)."""
    return label.lower()


@dataclass(frozen=True)
class SetFormField(_CommandBase):
    """Set one field of the form. ``None`` (or an empty text) removes it.

    ``value`` by field: text for the text fields, ``"true"``/``"false"`` for
    ``idbasedtr``, ``LayoutDefault`` / ``LayoutFunction`` for the layout fields,
    a tuple of ``(location, text)`` for ``includes``. The legacy attributes
    accept only ``None``: the builder never writes them.
    """

    command_type: ClassVar[str] = "set_form_field"
    _label_text: ClassVar[str] = "Change form setting"
    field: str
    value: object = None
    undo_label: str = ""
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return self.undo_label or self._label_text

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        if self.field not in FORM_FIELDS:
            raise CommandRejected("That form setting is not one Code Studio edits.")
        if self.field == "includes":
            _set_includes(doc, ctx, _lines(self.value))
            return
        planning.set_field(doc, ctx, doc.ui.id, self.field, self._checked())

    def _checked(self) -> object:
        value = self.value
        if self.field in LEGACY_FIELDS:
            if value is not None:
                raise CommandRejected("Code Studio keeps this older setting as it is.")
            return None
        if self.field in FLAG_FIELDS:
            if value in (None, ""):
                return None
            if value not in ("true", "false"):
                raise CommandRejected("That is not a yes or no setting.")
            return value
        if self.field == "layoutdefault":
            return _layout_default(value)
        if self.field == "layoutfunction":
            return _layout_function(value)
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise CommandRejected("That setting takes text.")
        if self.field == "pixmapfunction" and not function_name_ok(value.strip()):
            raise CommandRejected(NAME_REFUSAL)
        return value.strip() if self.field == "pixmapfunction" else value


def _layout_default(value: object) -> Optional[LayoutDefault]:
    if value is None:
        return None
    if not isinstance(value, LayoutDefault):
        raise CommandRejected("Gap and margin are numbers.")
    for number in (value.spacing, value.margin):
        if number is not None and (isinstance(number, bool) or not isinstance(number, int) or number < 0):
            raise CommandRejected("Gap and margin are whole numbers from 0.")
    if value.spacing is None and value.margin is None:
        return None
    return value


def _layout_function(value: object) -> Optional[LayoutFunction]:
    if value is None:
        return None
    if not isinstance(value, LayoutFunction):
        raise CommandRejected(NAME_REFUSAL)
    names = []
    for name in (value.spacing, value.margin):
        text = (name or "").strip()
        if text and not function_name_ok(text):
            raise CommandRejected(NAME_REFUSAL)
        names.append(text or None)
    if names[0] is None and names[1] is None:
        return None
    return LayoutFunction(spacing=names[0], margin=names[1])


def _lines(value: object) -> Tuple[IncludeLine, ...]:
    if not isinstance(value, tuple):
        raise CommandRejected("The include list is a list of lines.")
    lines = []
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2 or not all(isinstance(part, str) for part in item):
            raise CommandRejected("Each include line has a place and a name.")
        location, text = item
        if location not in ("local", "global"):
            raise CommandRejected("An include is Local or Global.")
        lines.append((location, text.strip()))
    return tuple(line for line in lines if line[1])


def _set_includes(doc: UiDocument, ctx: PlanContext, lines: Tuple[IncludeLine, ...]) -> None:
    """Edit the include list in place, so lines that did not change keep their bytes."""
    existing = list(doc.ui.children("includes"))
    for index, (location, text) in enumerate(lines):
        if index < len(existing):
            node = existing[index]
            if node.field("text") != text:
                # A different header: the old line's "in the declaration or the implementation" hint does not carry over.
                planning.set_field(doc, ctx, node.id, "impldecl", None)
            planning.set_field(doc, ctx, node.id, "location", location)
            planning.set_field(doc, ctx, node.id, "text", text)
            continue
        spec = NodeSpec("include", None, (("location", location), ("text", text)))
        planning._insert_spec(doc, ctx, doc.ui.id, "includes", spec)
    for node in existing[len(lines):]:
        ctx.do(RemoveNodeOp(node.id))


def include_lines(doc: UiDocument) -> Tuple[IncludeLine, ...]:
    """The form's include list as ``(location, text)``. A missing location reads as Global, as Qt does."""
    found = []
    for node in doc.ui.children("includes"):
        location = node.field("location")
        text = node.field("text")
        found.append((location if location in ("local", "global") else "global", text if isinstance(text, str) else ""))
    return tuple(found)


# --------------------------------------------------------------------------- grid


@dataclass(frozen=True)
class FormGrid:
    """The free-placement grid as the file stores it. Defaults: shown, 8 by 8, snapping."""

    show: bool = True
    across: int = GRID_STEP_DEFAULT
    down: int = GRID_STEP_DEFAULT
    snap: bool = True


def form_grid(doc: UiDocument) -> FormGrid:
    """The grid from ``<designerdata>``; a missing or odd property reads as its default."""
    data = doc.ui.field("designerdata")
    values = _grid_values(data)
    snap_x = values.get("gridSnapX", True)
    snap_y = values.get("gridSnapY", True)
    return FormGrid(
        show=bool(values.get("gridVisible", True)),
        across=_step(values.get("gridDeltaX")),
        down=_step(values.get("gridDeltaY")),
        snap=bool(snap_x) or bool(snap_y),
    )


def grid_is_default(doc: UiDocument, part: str) -> bool:
    """True when the file stores nothing for ``part``."""
    names = _PROPERTY[part]
    present = _grid_values(doc.ui.field("designerdata"))
    return not any(name in present for name in names)


def has_free_container(doc: UiDocument) -> bool:
    """True when some widget sits in a container that has no layout (UX-FSET-006)."""
    for node in doc.iter_preorder():
        if isinstance(node, WidgetNode) and node.id != doc.root.id and placed_freely(doc, node.id):
            return True
    return False


def _step(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return GRID_STEP_DEFAULT


def _grid_values(data: object) -> dict:
    found: dict = {}
    if not isinstance(data, OpaqueElement):
        return found
    for child in data.children:
        if not isinstance(child, OpaqueElement) or child.tag != "property":
            continue
        name = dict(child.attrs).get("name", "")
        if name not in _ORDER:
            continue
        found[name] = _property_value(child)
    return found


def _property_value(prop: OpaqueElement) -> Union[int, bool, None]:
    for child in prop.children:
        if not isinstance(child, OpaqueElement):
            continue
        text = "".join(part for part in child.children if isinstance(part, str)).strip()
        if child.tag == "number":
            try:
                return int(text)
            except ValueError:
                return None
        if child.tag == "bool":
            return text == "true"
    return None


def _property_element(name: str, value: Union[int, bool]) -> OpaqueElement:
    if isinstance(value, bool):
        inner = OpaqueElement("bool", (), ("true" if value else "false",))
    else:
        inner = OpaqueElement("number", (), (str(value),))
    return OpaqueElement("property", (("name", name),), (inner,))


@dataclass(frozen=True)
class SetFormGrid(_CommandBase):
    """Set one part of the free-placement grid: ``show``, ``across``, ``down`` or ``snap``.

    A value equal to its default (shown, 8, 8, snapping) removes the stored
    property, so a form that never left the defaults has no ``<designerdata>``
    grid. ``None`` removes it as well. Other ``<designerdata>`` content stays.
    """

    command_type: ClassVar[str] = "set_form_grid"
    _label_text: ClassVar[str] = "Change form setting"
    part: str
    value: Union[int, bool, None] = None
    undo_label: str = ""
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return self.undo_label or self._label_text

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        if self.part not in GRID_PARTS:
            raise CommandRejected("That is not a grid setting.")
        value = self._checked()
        data = doc.ui.field("designerdata")
        if data is not None and not isinstance(data, OpaqueElement):
            raise CommandRejected("This form's grid settings are in a shape Code Studio keeps as it is.")
        changed = _with_grid(data, _PROPERTY[self.part], value)
        planning.set_field(doc, ctx, doc.ui.id, "designerdata", changed)

    def _checked(self) -> Union[int, bool, None]:
        value = self.value
        if value is None:
            return None
        if self.part in ("show", "snap"):
            if not isinstance(value, bool):
                raise CommandRejected("That is a yes or no setting.")
            return None if value else value
        if isinstance(value, bool) or not isinstance(value, int):
            raise CommandRejected("A step is a whole number of pixels.")
        if not GRID_STEP_MIN <= value <= GRID_STEP_MAX:
            raise CommandRejected("Use a step from %d to %d pixels." % (GRID_STEP_MIN, GRID_STEP_MAX))
        return None if value == GRID_STEP_DEFAULT else value


def _with_grid(data: Optional[OpaqueElement], names: Tuple[str, ...], value: Union[int, bool, None]) -> Optional[OpaqueElement]:
    """``data`` with the properties ``names`` set to ``value`` (removed when ``value`` is None)."""
    base = data if data is not None else OpaqueElement("designerdata")
    children = list(base.children)
    for name in names:
        children = _set_one(children, name, value)
    meaningful = [child for child in children if not (isinstance(child, str) and not child.strip())]
    if not meaningful and not base.attrs:
        return None
    return OpaqueElement(base.tag, base.attrs, tuple(children), base.line)


def _name_of(child: object) -> str:
    if isinstance(child, OpaqueElement) and child.tag == "property":
        return dict(child.attrs).get("name", "")
    return ""


def _set_one(children: list, name: str, value: Union[int, bool, None]) -> list:
    at = next((i for i, child in enumerate(children) if _name_of(child) == name), -1)
    if value is None:
        return children[:at] + children[at + 1:] if at >= 0 else children
    element = _property_element(name, value)
    if at >= 0:
        return children[:at] + [element] + children[at + 1:]
    rank = _ORDER.index(name)
    later = next((i for i, child in enumerate(children) if _name_of(child) in _ORDER and _ORDER.index(_name_of(child)) > rank), len(children))
    return children[:later] + [element] + children[later:]
