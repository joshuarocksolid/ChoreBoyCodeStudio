"""The Icon row of an item's details (UX-ITEM-003), on the inspector's icon editor.

``IconEditor`` (M4.3c, UX-PED-102) takes any ``EditorHost``. This host writes
the picked ``IconSetValue`` into the item draft, so every pick, state and
theme name lands in the item-editor session's one undo step ("Edit items of
{name}"). The popover's own session only remembers the value it opened on, so
its Esc puts that value back without touching the rest of the session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import EnumValue, IconSetValue, Value
from app.features.form_builder.qtside.inspector.api import EnumSpec, RowValue, Unset, ValueSpec, Written
from app.features.form_builder.qtside.inspector.editors.images import IconEditor
from app.features.form_builder.qtside.items.model import Item
from app.qt.QtWidgets import QWidget

if TYPE_CHECKING:
    from app.features.form_builder.qtside.items.editor import ItemEditor
    from app.features.form_builder.qtside.theme.chrome import FormChrome

_POPOVER_ROOM = 420

OnValue = Callable[[str, Optional[Value]], None]


def build_icon_row(editor: "ItemEditor", current: Callable[[], Item], on_value: OnValue, parent: QWidget) -> QWidget:
    host = _IconHost(editor, current, on_value)
    icon = IconEditor(ValueSpec(IconSetValue.ELEMENT), host, parent)
    host.bind(icon.widget)
    icon.show(_row_value(current()))
    icon.widget.setObjectName("formBuilder.itemIcon")
    return icon.widget


def _row_value(item: Item) -> RowValue:
    base = item.base
    if base is not None:
        for entry in base.properties:
            if entry.name == "icon" and isinstance(entry.value, IconSetValue):
                return Written(entry.value)
    return Unset()


class _IconSession:
    """The icon popover's session. Writes go through the item draft."""

    def __init__(self, host: "_IconHost", label: str) -> None:
        self._host = host
        self._label = label
        self._before = _row_value(host.current())
        self._closed = False

    @property
    def token(self) -> str:
        return self._host.editor.token

    @property
    def label(self) -> str:
        return self._label

    @property
    def closed(self) -> bool:
        return self._closed

    def set_label(self, label: str) -> None:
        self._label = label

    def run(self, commands: Sequence[object]) -> object:
        del commands
        return ()

    def has_step(self) -> bool:
        return False

    def undo(self) -> bool:
        return False

    def revert(self) -> bool:
        before = self._before
        self._host.write(before.value if isinstance(before, Written) else None)
        self._closed = True
        return True

    def close(self) -> None:
        self._closed = True

    def watch(self, on_change: Callable[[], None]) -> Callable[[], None]:
        # The item editor watches the log and closes, with its children, on a
        # foreign step; the popover needs no second watcher.
        del on_change
        return lambda: None


class _IconHost:
    def __init__(self, editor: "ItemEditor", current: Callable[[], Item], on_value: OnValue) -> None:
        self.editor = editor
        self.current = current
        self._on_value = on_value
        self._row: Optional[QWidget] = None

    def bind(self, row: QWidget) -> None:
        self._row = row

    def write(self, value: Optional[Value]) -> None:
        self._on_value("icon", value)

    def commit(self, value: Value, session: object = None) -> None:
        del session
        self.write(value)

    def begin_session(self, label: str) -> _IconSession:
        # The popover lives in the item editor's window: picker, theme field
        # and footer need about this much height.
        self.editor.make_room(_POPOVER_ROOM)
        return _IconSession(self, label)

    @property
    def chrome(self) -> "FormChrome":
        return self.editor.chrome

    @property
    def label(self) -> str:
        return "Icon"

    @property
    def qt_name(self) -> str:
        return "icon"

    def document(self) -> UiDocument:
        return self.editor.session.document

    def owner_ids(self) -> Tuple[NodeId, ...]:
        return ()

    def qt_names(self) -> bool:
        return False

    def form_shortcuts(self) -> Mapping[str, str]:
        return {}

    @property
    def row_widget(self) -> QWidget:
        assert self._row is not None
        return self._row

    def reset(self) -> None:
        self.write(None)

    def invalid(self, message: str) -> None:
        del message

    def enum_value(self, enum: EnumSpec, names: Sequence[str]) -> Value:
        return EnumValue("::".join((enum.scope, names[0])) if names else "")
