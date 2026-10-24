
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Literal, Mapping, NewType, Optional, Protocol, Sequence, Tuple, Union

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import CStringValue, SetValue, StringValue, Value

if TYPE_CHECKING:
    from app.qt.QtWidgets import QWidget

class GroupId(str, Enum):

    CONTENT = "content"
    INPUT = "input"
    APPEARANCE = "appearance"
    SIZE = "size"
    PLACEMENT = "placement"
    LAYOUT = "layout"
    ACCESSIBILITY = "accessibility"
    ALL = "all"

    @property
    def title(self) -> str:
        return "All properties" if self is GroupId.ALL else self.value.capitalize()


def _cover(order: Tuple["GroupId", ...]) -> Tuple["GroupId", ...]:
    if set(order) != set(GroupId) or len(order) != len(set(order)):
        raise RuntimeError("GROUP_ORDER must list each GroupId once")
    return order


GROUP_ORDER: Tuple["GroupId", ...] = _cover(
    (
        GroupId.CONTENT,
        GroupId.INPUT,
        GroupId.APPEARANCE,
        GroupId.SIZE,
        GroupId.PLACEMENT,
        GroupId.LAYOUT,
        GroupId.ACCESSIBILITY,
        GroupId.ALL,
    )
)

EditorKey = NewType("EditorKey", str)

KEY_SEQUENCE = EditorKey("keysequence")
ALIGNMENT = EditorKey("alignment")
STYLESHEET = EditorKey("stylesheet")

_KEY_BY_NAME: Mapping[Tuple[str, str], EditorKey] = {
    ("shortcut", StringValue.ELEMENT): KEY_SEQUENCE,
    ("shortcut", CStringValue.ELEMENT): KEY_SEQUENCE,
    ("keySequence", StringValue.ELEMENT): KEY_SEQUENCE,
    ("keySequence", CStringValue.ELEMENT): KEY_SEQUENCE,
    ("alignment", SetValue.ELEMENT): ALIGNMENT,
    ("styleSheet", StringValue.ELEMENT): STYLESHEET,
}

def editor_key(name: str, element: str) -> EditorKey:
    return _KEY_BY_NAME.get((name, element), EditorKey(element))

@dataclass(frozen=True)
class EnumSpec:
    scope: str
    type_name: str
    names: Tuple[str, ...]
    is_flag: bool

@dataclass(frozen=True)
class ValueSpec:
    """``enum`` is set only when ``element`` is "enum" or "set" and the choices are known."""

    element: str
    enum: Optional[EnumSpec] = None

@dataclass(frozen=True)
class Unset:
    """No owner has an entry. ``default`` is a non-volatile class-table default, or None."""

    default: Optional[Value] = None

@dataclass(frozen=True)
class Written:
    """Every owner has an entry, and the entries are equal."""

    value: Value

@dataclass(frozen=True)
class Mixed:
    """The owners disagree, and at least one has an entry."""

RowValue = Union[Unset, Written, Mixed]

MIXED_TEXT = "Mixed"
NOT_SET_TEXT = "\u2014"

MatchWhere = Literal["label", "qt_name", "value"]

@dataclass(frozen=True)
class Match:

    where: MatchWhere
    start: int
    end: int

class RowWrite(Protocol):
    def edit(self, value: Value, token: Optional[str]) -> Command: ...

    def reset(self) -> Command: ...

@dataclass(frozen=True)
class OpenRow:
    key: str
    label: str
    qt_name: str
    help: str
    value: RowValue
    spec: ValueSpec
    editor: EditorKey
    write: RowWrite
    match: Optional[Match] = None

    @property
    def changed(self) -> bool:
        return not isinstance(self.value, Unset)

@dataclass(frozen=True)
class LockedRow:
    key: str
    label: str
    qt_name: str
    help: str
    value: RowValue
    reason: str
    match: Optional[Match] = None

    @property
    def changed(self) -> bool:
        return not isinstance(self.value, Unset)

Row = Union[OpenRow, LockedRow]

PropKind = Literal["property", "attribute"]

@dataclass(frozen=True)
class Prop:

    name: str
    kind: PropKind = "property"

@dataclass(frozen=True)
class LayoutProp:

    name: str

@dataclass(frozen=True)
class CellAlignment:
    pass


RowSource = Union[Prop, LayoutProp, CellAlignment]

@dataclass(frozen=True)
class RowSpec:
    """A curated row. With ``classes`` set, every owner's chain must include one of them.

    ``order`` is a sort key inside the group. ``after`` names the row key this
    one sits immediately after. ``after`` is applied after ``order``.
    """

    key: str
    group: GroupId
    label: str
    help: str
    source: RowSource
    classes: Tuple[str, ...] = ()
    order: Optional[int] = None
    after: str = ""

class EditorHost(Protocol):
    def commit(self, value: Value) -> None:
        """Run the row's write. A rejection is shown under the field."""
        ...

    def invalid(self, message: str) -> None:
        """Text the editor cannot turn into a Value. Shown under the field. Nothing is written."""
        ...

    def enum_value(self, enum: EnumSpec, names: Sequence[str]) -> Value:
        """An EnumValue for one of ``enum``'s names, or a SetValue of flags, spelled in the document's style."""
        ...

class Editor(Protocol):
    @property
    def widget(self) -> QWidget: ...

    def show(self, value: RowValue) -> None:
        """Paint ``value``. The pane drops any write that this call triggers."""
        ...

class EditorFactory(Protocol):
    def __call__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> Editor: ...

class GroupHost(Protocol):
    @property
    def document(self) -> UiDocument: ...

    @property
    def owners(self) -> Tuple[NodeId, ...]: ...

    def run(self, label: str, commands: Sequence[Command]) -> Optional[str]:
        """One undo step named ``label``. Returns the rejection message, or None."""
        ...

    def editor_for(self, row: Row, parent: QWidget) -> Editor:
        """The standard row widget for ``row``, wired to its write, with its caption line."""
        ...

class GroupBody(Protocol):
    @property
    def widget(self) -> QWidget: ...

    def show(self, rows: Tuple[Row, ...]) -> None:
        """The group's projected rows. Called once per flush while the group is expanded."""
        ...

class GroupBodyFactory(Protocol):
    def __call__(self, host: GroupHost, parent: QWidget) -> GroupBody: ...

class Registrar(Protocol):
    def editor(self, key: EditorKey, factory: EditorFactory, *, baseline: bool = False) -> None: ...

    def row(self, spec: RowSpec, *, baseline: bool = False) -> None: ...

    def group_body(self, group: GroupId, factory: GroupBodyFactory, *, baseline: bool = False) -> None: ...

def mark(widget: QWidget, value: RowValue) -> None:
    if isinstance(value, Mixed):
        state = "mixed"
    elif isinstance(value, Unset):
        state = "unset"
    else:
        state = "set"
    # The inspector style sheet owns the look of each state, italic included.
    set_style_flag(widget, "fbState", state)


def set_style_flag(widget: QWidget, name: str, value: str) -> None:
    """Set a dynamic property that a style sheet rule reads, repolishing on change."""
    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)

__all__ = [
    "ALIGNMENT",
    "CellAlignment",
    "Editor",
    "EditorFactory",
    "EditorHost",
    "EditorKey",
    "EnumSpec",
    "GroupBody",
    "GroupBodyFactory",
    "GroupHost",
    "GroupId",
    "KEY_SEQUENCE",
    "LayoutProp",
    "LockedRow",
    "MIXED_TEXT",
    "Match",
    "Mixed",
    "NOT_SET_TEXT",
    "OpenRow",
    "Prop",
    "Registrar",
    "Row",
    "RowSpec",
    "RowValue",
    "RowWrite",
    "STYLESHEET",
    "Unset",
    "ValueSpec",
    "Written",
    "editor_key",
    "mark",
]
