"""Size group: Hug, Fill, Fixed, share, limits, and why.

Registered as a baseline so a later package can replace the body without
editing this file. The words and the writes live in the engine.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.catalog_ext.sizing import from_write, write_share
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.sizing import (
    FILL_TIP,
    FIXED_TIP,
    HUG_TIP,
    QWIDGET_SIZE_MAX,
    SHARE_CAPTION,
    WORD_FILL,
    WORD_FIXED,
    WORD_HUG,
    WORDS,
    AxisProjection,
    Share,
    SizingWrite,
    clear_property,
    encode_axis,
    project_axis,
    read_share,
    reset_words,
    share_slots,
)
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import SizePolicyValue, SizeValue
from app.features.form_builder.qtside.inspector.api import (
    GroupHost,
    GroupId,
    Registrar,
    set_style_flag,
)
from app.features.form_builder.qtside.sizing_live import (
    class_default_policies,
    class_phrase,
    why_text,
)
from app.qt.QtCore import QEvent, QObject, QTimer, Qt
from app.qt.qt_compat import wrapper_is_valid
from app.qt.QtGui import QIntValidator
from app.qt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_TIPS = {WORD_HUG: HUG_TIP, WORD_FILL: FILL_TIP, WORD_FIXED: FIXED_TIP}


class SizeBody:
    """The Size group's whole body. ``show`` reads the current owners."""

    def __init__(self, host: GroupHost, parent: QWidget) -> None:
        self._host = host
        self._painting = False
        self._root = QWidget(parent)
        self._root.setObjectName("formBuilder.sizeBody")
        self._root.setAccessibleName("Size")
        layout = QVBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._width = _AxisRow("h", "Width", self._root, self._pick, self._pixels)
        self._height = _AxisRow("v", "Height", self._root, self._pick, self._pixels)
        self._share_width = _ShareRow("h", self._root, self._share)
        self._share_height = _ShareRow("v", self._root, self._share)
        self._at_least = _LimitRow("minimumSize", "At least", self._root, self._limit, self._clear_limit)
        self._at_most = _LimitRow("maximumSize", "At most", self._root, self._limit, self._clear_limit)
        self._reset = _reset_button(self._root, "formBuilder.size.reset", "Reset size", self._reset_words)
        self._why = QLabel(self._root)
        self._why.setObjectName("formBuilder.sizeWhy")
        self._why.setAccessibleName("Why is it this size?")
        self._why.setWordWrap(True)
        self._why.setMinimumWidth(0)
        self._watched: Optional[QWidget] = None
        self._watch = _ResizeWatch(self._queue_why, self._root)
        self._why_timer = QTimer(self._root)
        self._why_timer.setSingleShot(True)
        self._why_timer.timeout.connect(self._refresh_why)
        layout.addWidget(self._width.widget)
        layout.addWidget(self._share_width.widget)
        layout.addWidget(self._height.widget)
        layout.addWidget(self._share_height.widget)
        layout.addWidget(self._at_least.widget)
        layout.addWidget(self._at_most.widget)
        layout.addWidget(self._reset)
        layout.addWidget(self._why)
        self._root.setMinimumWidth(0)

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, rows: Tuple[object, ...]) -> None:
        del rows
        self._painting = True
        try:
            self._paint()
        finally:
            self._painting = False

    def _paint(self) -> None:
        owners = [node for node in self._owners() if isinstance(node, WidgetNode)]
        projections = [_project(self._host, node) for node in owners]
        self._width.paint(_column(projections, 0))
        self._height.paint(_column(projections, 1))
        self._paint_share(owners)
        self._paint_limits(owners, projections)
        stored = any(node.prop("sizePolicy") is not None or _has_lock(node) for node in owners)
        self._reset.setVisible(stored)
        self._watch_live(owners)
        self._why.setText(self._why_text(owners))

    def _watch_live(self, owners: Sequence[WidgetNode]) -> None:
        widget = self._host.live(owners[0].id) if len(owners) == 1 else None
        watched = self._watched
        if watched is not None and not wrapper_is_valid(watched):
            watched = None
            self._watched = None
        if widget is not None and not wrapper_is_valid(widget):
            widget = None
        if widget is watched:
            return
        if watched is not None:
            watched.removeEventFilter(self._watch)
        self._watched = widget
        if widget is not None:
            widget.installEventFilter(self._watch)

    def _queue_why(self) -> None:
        if self._painting:
            return
        self._why_timer.start(0)

    def _refresh_why(self) -> None:
        if self._painting:
            return
        owners = [node for node in self._owners() if isinstance(node, WidgetNode)]
        self._why.setText(self._why_text(owners))

    def _owners(self) -> List[WidgetNode]:
        document = self._host.document
        found = []
        for owner in self._host.owners:
            node = document.get(owner)
            if isinstance(node, WidgetNode):
                found.append(node)
        return found

    def _paint_share(self, owners: Sequence[WidgetNode]) -> None:
        for row in (self._share_width, self._share_height):
            slots = [_slot_for(self._host, node, row.axis) for node in owners]
            if not owners or any(slot is None for slot in slots):
                row.hide()
                continue
            values = [int(slot[1]) for slot in slots if slot is not None]
            row.show_value(values)

    def _paint_limits(
        self, owners: Sequence[WidgetNode], projections: Sequence[Tuple[AxisProjection, AxisProjection]]
    ) -> None:
        width_fixed = bool(projections) and all(pair[0].word == WORD_FIXED and pair[0].filled for pair in projections)
        height_fixed = bool(projections) and all(pair[1].word == WORD_FIXED and pair[1].filled for pair in projections)
        self._at_least.paint(owners, "minimumSize", 0, hide_width=width_fixed, hide_height=height_fixed)
        self._at_most.paint(owners, "maximumSize", QWIDGET_SIZE_MAX, hide_width=width_fixed, hide_height=height_fixed)
        if width_fixed and height_fixed:
            self._at_least.widget.hide()
            self._at_most.widget.hide()

    def _why_text(self, owners: Sequence[WidgetNode]) -> str:
        if len(owners) != 1:
            return "Select one widget to see why it is this size."
        node = owners[0]
        widget = self._host.live(node.id)
        if widget is None:
            return "The canvas has not realized this widget yet."
        return why_text(self._host.document, node.id, widget, qt_names=self._host.qt_names)

    def _pick(self, axis: str, word: str) -> None:
        if self._painting:
            return
        commands = []
        for node in self._owners():
            widget = self._host.live(node.id)
            pixels = _live_pixels(widget, axis) if word == WORD_FIXED else None
            if word == WORD_FIXED and pixels is None:
                pixels = 40
            defaults = _defaults(widget, node)
            write = encode_axis(
                axis=axis,
                word=word,
                pixels=pixels,
                current_policy=_policy(node),
                current_minimum=_size(node, "minimumSize"),
                current_maximum=_size(node, "maximumSize"),
                class_default_h=defaults[0],
                class_default_v=defaults[1],
            )
            if _unchanged(node, write):
                continue
            commands.append(from_write(node.id, write))
        if commands:
            self._host.run("Size", commands)

    def _pixels(self, axis: str, pixels: int) -> None:
        if self._painting:
            return
        commands = []
        for node in self._owners():
            widget = self._host.live(node.id)
            defaults = _defaults(widget, node)
            commands.append(
                from_write(
                    node.id,
                    encode_axis(
                        axis=axis,
                        word=WORD_FIXED,
                        pixels=pixels,
                        current_policy=_policy(node),
                        current_minimum=_size(node, "minimumSize"),
                        current_maximum=_size(node, "maximumSize"),
                        class_default_h=defaults[0],
                        class_default_v=defaults[1],
                    ),
                )
            )
        if commands:
            self._host.run("Size", commands)

    def _share(self, axis: str, value: int) -> None:
        if self._painting:
            return
        commands = []
        for node in self._owners():
            found = _slot_for(self._host, node, axis)
            if found is None:
                continue
            slot, _current = found
            command = write_share(
                self._host.document, slot, node.id, value, _defaults(self._host.live(node.id), node)
            )
            if command is not None:
                commands.append(command)
        if commands:
            self._host.run("Size", commands)

    def _limit(self, name: str, axis: str, number: Optional[int]) -> None:
        if self._painting:
            return
        empty = 0 if name == "minimumSize" else QWIDGET_SIZE_MAX
        commands = []
        for node in self._owners():
            current = _size(node, name)
            width, height = _pair(current, empty)
            if axis == "h":
                width = empty if number is None else int(number)
            else:
                height = empty if number is None else int(number)
            written = _size_or_none(width, height, empty)
            touch_min = name == "minimumSize"
            commands.append(
                from_write(
                    node.id,
                    SizingWrite(None, written if touch_min else None, None if touch_min else written, False, touch_min, not touch_min),
                )
            )
        if commands:
            self._host.run("Size", commands)

    def _clear_limit(self, name: str) -> None:
        if self._painting:
            return
        commands = [from_write(node.id, clear_property(name)) for node in self._owners()]
        if commands:
            self._host.run("Reset", commands)

    def _reset_words(self) -> None:
        if self._painting:
            return
        commands = []
        for node in self._owners():
            commands.append(
                from_write(
                    node.id,
                    reset_words(
                        current_policy=_policy(node),
                        current_minimum=_size(node, "minimumSize"),
                        current_maximum=_size(node, "maximumSize"),
                    ),
                )
            )
        if commands:
            self._host.run("Reset", commands)


def register(registrar: Registrar) -> None:
    registrar.group_body(GroupId.SIZE, SizeBody, baseline=True)


class _AxisRow:
    def __init__(
        self,
        axis: str,
        title: str,
        parent: QWidget,
        on_word: object,
        on_pixels: object,
    ) -> None:
        self.axis = axis
        self._on_word = on_word
        self._on_pixels = on_pixels
        self.widget = QWidget(parent)
        self.widget.setObjectName("formBuilder.size.%s" % axis)
        outer = QVBoxLayout(self.widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        self._bar = QFrame(self.widget)
        self._bar.setObjectName("formBuilder.rowChanged")
        self._bar.setFixedWidth(2)
        self._bar.setMinimumHeight(18)
        line.addWidget(self._bar)
        self._label = QLabel(title, self.widget)
        self._label.setMinimumWidth(0)
        self._label.setMaximumWidth(52)
        line.addWidget(self._label)
        self._buttons: Dict[str, QToolButton] = {}
        for word in WORDS:
            button = QToolButton(self.widget)
            button.setObjectName("formBuilder.size.%s.%s" % (title.lower(), word))
            button.setText(word)
            button.setCheckable(True)
            button.setProperty("fbSegment", "true")
            button.setToolTip(_TIPS[word])
            button.setAccessibleName("%s %s" % (title, word))
            button.setFocusPolicy(_strong())
            button.clicked.connect(lambda _checked=False, chosen=word: on_word(axis, chosen))
            self._buttons[word] = button
            line.addWidget(button)
        self._pixels = QSpinBox(self.widget)
        self._pixels.setObjectName("formBuilder.size.%s.pixels" % title.lower())
        self._pixels.setRange(1, QWIDGET_SIZE_MAX - 1)
        self._pixels.setSuffix(" px")
        self._pixels.setAccessibleName("%s in pixels" % title)
        self._pixels.setFocusPolicy(_strong())
        editor = self._pixels.lineEdit()
        if editor is not None:
            editor.setAccessibleName("%s in pixels" % title)
        self._pixels.editingFinished.connect(lambda: on_pixels(axis, self._pixels.value()))
        self._pixels.hide()
        line.addStretch(1)
        outer.addLayout(line)
        # Fixed pixels sit under the segments; one line cannot hold both at 236 px.
        pixel_line = QHBoxLayout()
        pixel_line.setContentsMargins(8, 0, 0, 0)
        pixel_line.addWidget(self._pixels)
        pixel_line.addStretch(1)
        outer.addLayout(pixel_line)
        self._caption = QLabel(self.widget)
        self._caption.setObjectName("formBuilder.rowNote")
        self._caption.setWordWrap(True)
        outer.addWidget(self._caption)

    def paint(self, projections: Sequence[AxisProjection]) -> None:
        if not projections:
            self._caption.setText("")
            return
        first = projections[0]
        mixed = any(item.word != first.word or item.filled != first.filled or item.custom != first.custom for item in projections)
        changed = any(item.filled or item.custom for item in projections)
        set_style_flag(self._label, "fbChanged", "true" if changed else "false")
        set_style_flag(self._bar, "fbChanged", "true" if changed else "false")
        for word, button in self._buttons.items():
            button.blockSignals(True)
            button.setChecked(not mixed and first.filled and first.word == word)
            outlined = not mixed and not first.filled and not first.custom and first.word == word
            set_style_flag(button, "fbOutline", "true" if outlined else "false")
            button.blockSignals(False)
        show_pixels = not mixed and first.filled and first.word == WORD_FIXED
        self._pixels.setVisible(show_pixels)
        if show_pixels and first.pixels is not None:
            self._pixels.blockSignals(True)
            self._pixels.setValue(int(first.pixels))
            self._pixels.blockSignals(False)
        if mixed:
            self._caption.setText("Mixed")
        elif first.caption:
            self._caption.setText(first.caption)
        else:
            self._caption.setText("")


class _ShareRow:
    def __init__(self, axis: str, parent: QWidget, on_share: object) -> None:
        self.axis = axis
        self.widget = QWidget(parent)
        self.widget.setObjectName("formBuilder.size.share.%s" % axis)
        outer = QVBoxLayout(self.widget)
        outer.setContentsMargins(8, 0, 0, 0)
        outer.setSpacing(2)
        line = QHBoxLayout()
        line.setSpacing(6)
        label = QLabel("Share of spare room", self.widget)
        label.setWordWrap(True)
        line.addWidget(label, 1)
        self._box = QSpinBox(self.widget)
        self._box.setObjectName("formBuilder.size.share.%s.value" % axis)
        self._box.setRange(0, 999)
        self._box.setAccessibleName("Share of spare room")
        self._box.setMinimumWidth(40)
        self._box.setFocusPolicy(_strong())
        editor = self._box.lineEdit()
        if editor is not None:
            editor.setAccessibleName("Share of spare room")
        self._box.editingFinished.connect(lambda: on_share(axis, self._box.value()))
        line.addWidget(self._box)
        outer.addLayout(line)
        self._caption = QLabel(SHARE_CAPTION, self.widget)
        self._caption.setObjectName("formBuilder.rowNote")
        self._caption.setWordWrap(True)
        outer.addWidget(self._caption)
        self.widget.hide()

    def hide(self) -> None:
        self.widget.hide()

    def show_value(self, values: Sequence[int]) -> None:
        self.widget.show()
        mixed = any(item != values[0] for item in values)
        self._box.blockSignals(True)
        if not mixed:
            self._box.setValue(int(values[0]))
            self._box.setSpecialValueText("")
        else:
            self._box.setSpecialValueText("Mixed")
            self._box.setValue(0)
        self._box.blockSignals(False)


class _LimitRow:
    def __init__(self, name: str, title: str, parent: QWidget, on_limit: object, on_reset: object) -> None:
        self.name = name
        self.widget = QWidget(parent)
        self.widget.setObjectName("formBuilder.size.%s" % name)
        outer = QVBoxLayout(self.widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        line = QHBoxLayout()
        line.setSpacing(4)
        self._bar = QFrame(self.widget)
        self._bar.setObjectName("formBuilder.rowChanged")
        self._bar.setFixedWidth(2)
        line.addWidget(self._bar)
        self._label = QLabel(title, self.widget)
        self._label.setMinimumWidth(0)
        self._label.setMaximumWidth(52)
        line.addWidget(self._label)
        self._width = _blank_edit(self.widget, "%s width in pixels" % title, "formBuilder.size.%s.width" % name)
        self._height = _blank_edit(self.widget, "%s height in pixels" % title, "formBuilder.size.%s.height" % name)
        self._width.editingFinished.connect(lambda: _commit_limit(self._width, name, "h", on_limit))
        self._height.editingFinished.connect(lambda: _commit_limit(self._height, name, "v", on_limit))
        # The fields share the free width; a trailing stretch would starve them.
        line.addWidget(self._width, 1)
        line.addWidget(QLabel("×", self.widget))
        line.addWidget(self._height, 1)
        self._reset = _reset_button(self.widget, "formBuilder.size.%s.reset" % name, "Reset %s" % title.lower(), lambda: on_reset(name))
        line.addWidget(self._reset)
        outer.addLayout(line)

    def paint(
        self,
        owners: Sequence[WidgetNode],
        name: str,
        empty: int,
        *,
        hide_width: bool,
        hide_height: bool,
    ) -> None:
        self.widget.setVisible(not (hide_width and hide_height))
        self._width.setVisible(not hide_width)
        self._height.setVisible(not hide_height)
        stored = [node.prop(name) is not None for node in owners]
        set_style_flag(self._label, "fbChanged", "true" if any(stored) else "false")
        set_style_flag(self._bar, "fbChanged", "true" if any(stored) else "false")
        self._reset.setVisible(any(stored))
        widths = [_component(node, name, True, empty) for node in owners]
        heights = [_component(node, name, False, empty) for node in owners]
        _show_blank(self._width, widths, empty)
        _show_blank(self._height, heights, empty)


def _project(host: GroupHost, node: WidgetNode) -> Tuple[AxisProjection, AxisProjection]:
    widget = host.live(node.id)
    defaults = _defaults(widget, node)
    phrase = class_phrase(node.class_name)
    policy = _policy(node)
    minimum = _size(node, "minimumSize")
    maximum = _size(node, "maximumSize")
    horizontal = project_axis(
        stored_policy=None if policy is None else policy.hsizetype,
        minimum=None if minimum is None else minimum.width,
        maximum=None if maximum is None else maximum.width,
        class_default_policy=defaults[0],
        class_phrase=phrase,
    )
    vertical = project_axis(
        stored_policy=None if policy is None else policy.vsizetype,
        minimum=None if minimum is None else minimum.height,
        maximum=None if maximum is None else maximum.height,
        class_default_policy=defaults[1],
        class_phrase=phrase,
    )
    return horizontal, vertical


def _defaults(widget: Optional[QWidget], node: WidgetNode) -> Tuple[str, str]:
    if widget is not None:
        return class_default_policies(widget)
    del node
    return ("Preferred", "Preferred")


def _policy(node: WidgetNode) -> Optional[SizePolicyValue]:
    entry = node.prop("sizePolicy")
    if entry is None or not isinstance(entry.value, SizePolicyValue):
        return None
    return entry.value


def _size(node: WidgetNode, name: str) -> Optional[SizeValue]:
    entry = node.prop(name)
    if entry is None or not isinstance(entry.value, SizeValue):
        return None
    return entry.value


def _column(
    projections: Sequence[Tuple[AxisProjection, AxisProjection]], index: int
) -> Tuple[AxisProjection, ...]:
    return tuple(pair[index] for pair in projections)


def _slot_for(host: GroupHost, node: WidgetNode, axis: str) -> Optional[Tuple[Share, int]]:
    for slot in share_slots(host.document, node.id):
        if slot.axis == axis:
            return slot, read_share(host.document, slot).value
    return None


def _live_pixels(widget: Optional[QWidget], axis: str) -> Optional[int]:
    if widget is None:
        return None
    size = int(widget.width() if axis == "h" else widget.height())
    if size > 0:
        return size
    hint = widget.sizeHint()
    fallback = int(hint.width() if axis == "h" else hint.height())
    return fallback if fallback > 0 else None


def _has_lock(node: WidgetNode) -> bool:
    minimum = _size(node, "minimumSize")
    maximum = _size(node, "maximumSize")
    if minimum is None or maximum is None:
        return False
    return minimum.width == maximum.width or minimum.height == maximum.height


def _pair(size: Optional[SizeValue], empty: int) -> Tuple[int, int]:
    if size is None:
        return empty, empty
    return int(size.width), int(size.height)


def _unchanged(node: WidgetNode, write: SizingWrite) -> bool:
    return (
        write.policy == _policy(node)
        and write.minimum == _size(node, "minimumSize")
        and write.maximum == _size(node, "maximumSize")
    )


def _size_or_none(width: int, height: int, empty: int) -> Optional[SizeValue]:
    if width == empty and height == empty:
        return None
    return SizeValue(int(width), int(height))


def _component(node: WidgetNode, name: str, horizontal: bool, empty: int) -> Optional[int]:
    size = _size(node, name)
    if size is None:
        return None
    value = int(size.width if horizontal else size.height)
    if value == empty:
        return None
    return value


def _blank_edit(parent: QWidget, accessible: str, object_name: str) -> QLineEdit:
    edit = QLineEdit(parent)
    edit.setObjectName(object_name)
    edit.setPlaceholderText("—")
    edit.setValidator(QIntValidator(0, QWIDGET_SIZE_MAX, edit))
    edit.setAccessibleName(accessible)
    edit.setFocusPolicy(_strong())
    edit.setToolTip(accessible)
    edit.setMinimumWidth(34)
    edit.setMaximumWidth(72)
    policy = edit.sizePolicy()
    policy.setHorizontalPolicy(getattr(getattr(QSizePolicy, "Policy", QSizePolicy), "Preferred"))
    edit.setSizePolicy(policy)
    return edit


def _commit_limit(edit: QLineEdit, name: str, axis: str, on_limit: object) -> None:
    if edit.text().strip() == "Mixed":
        return
    on_limit(name, axis, _blank_number(edit))


def _blank_number(edit: QLineEdit) -> Optional[int]:
    text = edit.text().strip()
    if not text or text == "—" or text == "Mixed":
        return None
    if not text.isdigit():
        return None
    return int(text)


def _show_blank(edit: QLineEdit, values: Sequence[Optional[int]], _empty: int) -> None:
    edit.blockSignals(True)
    if not values:
        edit.clear()
    elif any(item != values[0] for item in values):
        edit.setText("Mixed")
    elif values[0] is None:
        edit.clear()
    else:
        edit.setText(str(values[0]))
    edit.blockSignals(False)


def _reset_button(parent: QWidget, object_name: str, accessible: str, on_click: object) -> QToolButton:
    button = QToolButton(parent)
    button.setObjectName(object_name)
    button.setProperty("fbFlat", "true")
    button.setText("↺")
    button.setFixedSize(16, 16)
    button.setAccessibleName(accessible)
    button.setToolTip(accessible)
    button.setFocusPolicy(_strong())
    button.clicked.connect(on_click)
    button.hide()
    return button


class _ResizeWatch(QObject):
    def __init__(self, refresh: object, parent: QWidget) -> None:
        super().__init__(parent)
        self._refresh = refresh

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        resize = getattr(getattr(QEvent, "Type", QEvent), "Resize")
        if event.type() == resize:
            self._refresh()
        return False


def _strong() -> Qt.FocusPolicy:
    policy = getattr(Qt, "FocusPolicy", Qt)
    return getattr(policy, "StrongFocus")
