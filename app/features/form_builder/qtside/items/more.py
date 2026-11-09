"""More properties uses the inspector editor registry (UX-ITEM-006).

Each row is the same editor the inspector would build for that value. The
host writes into the item draft, so the edit stays inside the one "Edit items
of {name}" step. A popover's session only remembers the value it opened on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Mapping, Optional, Sequence, Tuple, cast

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import (
    BrushValue,
    EnumValue,
    FontValue,
    SetValue,
    StringValue,
    Value,
)
from app.features.form_builder.qtside.inspector.api import (
    ALIGNMENT,
    EditorKey,
    EnumSpec,
    RowValue,
    Unset,
    ValueSpec,
    Written,
)
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.items.model import Item
from app.qt.QtCore import QEvent, QObject, Qt
from app.qt.QtWidgets import QApplication, QFormLayout, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from app.features.form_builder.qtside.items.editor import ItemEditor
    from app.features.form_builder.qtside.theme.chrome import FormChrome

_POPOVER_ROOM = 420

# Qt::ItemFlag, in the order codegen already spells (engine/codegen/qtmap.py).
_ITEM_FLAGS = (
    "NoItemFlags",
    "ItemIsSelectable",
    "ItemIsEditable",
    "ItemIsDragEnabled",
    "ItemIsDropEnabled",
    "ItemIsUserCheckable",
    "ItemIsEnabled",
    "ItemIsAutoTristate",
    "ItemNeverHasChildren",
    "ItemIsUserTristate",
)
_CHECK = EnumSpec("Qt", "CheckState", ("Unchecked", "PartiallyChecked", "Checked"), False)
_FLAGS = EnumSpec("Qt", "ItemFlag", _ITEM_FLAGS, True)

_Row = Tuple[str, str, EditorKey, Optional[EnumSpec]]
_ROWS: Tuple[_Row, ...] = (
    ("Text", "text", EditorKey(StringValue.ELEMENT), None),
    ("Tooltip", "toolTip", EditorKey(StringValue.ELEMENT), None),
    ("Status tip", "statusTip", EditorKey(StringValue.ELEMENT), None),
    ("What's this", "whatsThis", EditorKey(StringValue.ELEMENT), None),
    ("Font", "font", EditorKey(FontValue.ELEMENT), None),
    ("Background", "background", EditorKey(BrushValue.ELEMENT), None),
    ("Foreground", "foreground", EditorKey(BrushValue.ELEMENT), None),
    ("Text alignment", "textAlignment", ALIGNMENT, None),
    ("Check state", "checkState", EditorKey(EnumValue.ELEMENT), _CHECK),
    ("Flags", "flags", EditorKey(SetValue.ELEMENT), _FLAGS),
)

OnValue = Callable[[str, Optional[Value]], None]
OnClose = Callable[[], None]


def show_more(
    parent: QWidget,
    editor: "ItemEditor",
    current: Callable[[], Item],
    on_value: OnValue,
    on_close: OnClose,
) -> QWidget:
    existing = parent.findChild(QWidget, "formBuilder.itemMorePanel")
    if existing is not None:
        existing.show()
        return existing
    panel = QWidget(parent)
    panel.setObjectName("formBuilder.itemMorePanel")
    form = QFormLayout(panel)
    form.setContentsMargins(0, 4, 0, 0)
    catalog = default_catalog()
    item = current()
    for label, name, key, enum in _ROWS:
        factory = catalog.editor(key)
        if factory is None:
            raise RuntimeError("No inspector editor for %s" % label)
        spec = ValueSpec(str(key), enum=enum)
        host = _PropHost(editor, current, on_value, label, name)
        holder = QWidget(panel)
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        built = factory(spec, host, holder)
        column.addWidget(built.widget)
        caption = getattr(built, "caption_widget", None)
        if isinstance(caption, QWidget):
            # The string editor builds this with no parent. Parent it before
            # show(), or the disclosure opens as its own window. Qt's stubs
            # do not narrow under isinstance, so the cast is the type.
            disclosure = cast(QWidget, caption)
            disclosure.setParent(holder)
            column.addWidget(disclosure)
        host.bind(holder)
        form.addRow(label, holder)
        built.show(_row_value(item, name))
        if key == ALIGNMENT:
            # The item window is not inside the inspector sheet. The segment
            # rule stays on this row so the rest of the panel keeps native
            # checkbox indicators.
            _paint_segments(built.widget, editor.chrome)
    layout = parent.layout()
    if isinstance(layout, QFormLayout):
        layout.addRow(panel)
    elif isinstance(layout, QVBoxLayout):
        layout.addWidget(panel)
    else:
        panel.setParent(parent)
        panel.show()
    _AltLeft(panel, on_close)
    return panel


def _paint_segments(widget: QWidget, chrome: "FormChrome") -> None:
    widget.setStyleSheet(
        "QToolButton[fbSegment=\"true\"] {"
        " background: %s; color: %s; border: 1px solid %s; }"
        "QToolButton[fbSegment=\"true\"]:checked {"
        " background: %s; color: %s; border: 1px solid %s; }"
        % (chrome.input, chrome.text, chrome.border, chrome.accent, chrome.on_accent, chrome.accent)
    )


class _AltLeft(QObject):
    """Alt+Left closes the more-properties panel. A nested popover keeps the key."""

    def __init__(self, panel: QWidget, on_close: OnClose) -> None:
        super().__init__(panel)
        self._panel = panel
        self._on_close = on_close
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        panel.destroyed.connect(self._drop)

    def _drop(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        del watched
        press = getattr(getattr(QEvent, "Type", QEvent), "KeyPress", QEvent.KeyPress)
        if event.type() != press or not self._panel.isVisible():
            return False
        key = event.key()  # type: ignore[attr-defined]
        mods = event.modifiers()  # type: ignore[attr-defined]
        alt = bool(mods & getattr(Qt, "AltModifier"))
        ctrl = bool(mods & getattr(Qt, "ControlModifier"))
        if key != getattr(Qt, "Key_Left") or not alt or ctrl:
            return False
        focus = QApplication.focusWidget()
        if not isinstance(focus, QWidget):
            return False
        if focus is not self._panel and not self._panel.isAncestorOf(focus):
            return False
        if _inside_popover(focus):
            return False
        self._on_close()
        return True


def _inside_popover(widget: QWidget) -> bool:
    current: Optional[QWidget] = widget
    while current is not None:
        if current.objectName() == "formBuilder.rowPopover":
            return True
        current = current.parentWidget()
    return False


class _PropSession:
    """One popover's memory of the property it opened on. Writes stay on the item draft."""

    def __init__(self, host: "_PropHost", label: str) -> None:
        self._host = host
        self._label = label
        self._before = _stored(host.current(), host.qt_name)
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
        self._host.write(self._before)
        self._closed = True
        return True

    def close(self) -> None:
        self._closed = True

    def watch(self, on_change: Callable[[], None]) -> Callable[[], None]:
        del on_change
        return lambda: None


class _PropHost:
    def __init__(
        self,
        editor: "ItemEditor",
        current: Callable[[], Item],
        on_value: OnValue,
        label: str,
        name: str,
    ) -> None:
        self.editor = editor
        self.current = current
        self._on_value = on_value
        self._label = label
        self._name = name
        self._row: Optional[QWidget] = None

    def bind(self, row: QWidget) -> None:
        self._row = row

    def write(self, value: Optional[Value]) -> None:
        self._on_value(self._name, value)

    def commit(self, value: Value, session: object = None) -> None:
        del session
        self.write(value)

    def begin_session(self, label: str) -> _PropSession:
        # Translation commits are inline. Resizing here would close a popover
        # that is already open, and the disclosure is not one.
        if "translation" not in label.lower():
            self.editor.make_room(_POPOVER_ROOM)
        return _PropSession(self, label)

    @property
    def chrome(self) -> "FormChrome":
        return self.editor.chrome

    @property
    def label(self) -> str:
        return self._label

    @property
    def qt_name(self) -> str:
        return self._name

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
        style = self.document().enum_style()
        spelled = [_spell(enum, name, style) for name in names]
        if enum.is_flag or len(spelled) != 1:
            return SetValue("|".join(spelled))
        return EnumValue(spelled[0])


def _spell(enum: EnumSpec, name: str, style: str) -> str:
    if not name or "::" in name or not enum.scope:
        return name
    if style == "qualified" and enum.type_name and enum.type_name != enum.scope:
        return "%s::%s::%s" % (enum.scope, enum.type_name, name)
    return "%s::%s" % (enum.scope, name)


def _row_value(item: Item, name: str) -> RowValue:
    value = _stored(item, name)
    if value is None:
        return Unset()
    return Written(value)


def _stored(item: Item, name: str) -> Optional[Value]:
    if item.base is not None:
        for entry in item.base.properties:
            if entry.name == name:
                if name == "text" and isinstance(entry.value, StringValue):
                    return StringValue(
                        item.text_at(0),
                        entry.value.notr,
                        entry.value.comment,
                        entry.value.extracomment,
                        entry.value.id,
                    )
                return entry.value
    if name == "text":
        return StringValue(item.text_at(0))
    return None
