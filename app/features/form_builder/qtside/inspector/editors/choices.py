
from __future__ import annotations

from typing import List, Tuple

from app.features.form_builder.engine.ui4.values import (
    CursorShapeValue,
    CursorValue,
    EnumValue,
    SetValue,
    semantic_equal,
)
from app.features.form_builder.qtside.inspector.api import (
    ALIGNMENT,
    Choice,
    MIXED_TEXT,
    EditorHost,
    EditorKey,
    Mixed,
    Registrar,
    RowValue,
    Unset,
    ValueSpec,
    Written,
    mark,
)
from app.features.form_builder.qtside.inspector.editors._editor_kit import name_part, qt_key
from app.features.form_builder.qtside.inspector.editors._enum_words import friendly
from app.features.form_builder.qtside.inspector.editors._segments import ChoiceSegments
from app.features.form_builder.qtside.theme.metrics import ICON, S1
from app.qt.QtCore import QSize, Qt
from app.qt.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from app.qt.QtWidgets import (
    QComboBox,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value

_ALIGN_CELL = 24
_HORIZONTAL = ("AlignLeft", "AlignHCenter", "AlignRight", "AlignJustify")
_VERTICAL = ("AlignTop", "AlignVCenter", "AlignBottom")
_ALIGN_ALIASES = {"AlignLeading": "AlignLeft", "AlignTrailing": "AlignRight"}
_ALIGN_TAILS = {
    "AlignLeft": "Left",
    "AlignHCenter": "Center",
    "AlignRight": "Right",
    "AlignJustify": "Justify",
    "AlignTop": "Top",
    "AlignVCenter": "Middle",
    "AlignBottom": "Bottom",
}


def _row_label(host: EditorHost) -> str:
    label = getattr(host, "row_label", "")
    if isinstance(label, str) and label.strip():
        return label.strip()
    return "Alignment"


def _align_name(host: EditorHost, name: str, shown: str) -> str:
    """Row: Choice. The two center buttons stay distinct for a screen reader."""
    row = _row_label(host)
    if name == "AlignVCenter" and row == "Text alignment":
        return "Vertical alignment: Middle"
    if name == "AlignVCenter":
        return "%s: Middle" % row
    if name == "AlignHCenter":
        return "%s: Center" % row
    return "%s: %s" % (row, _ALIGN_TAILS.get(name, shown))
_CURSORS = (
    "ArrowCursor",
    "UpArrowCursor",
    "CrossCursor",
    "WaitCursor",
    "IBeamCursor",
    "SizeVerCursor",
    "SizeHorCursor",
    "SizeBDiagCursor",
    "SizeFDiagCursor",
    "SizeAllCursor",
    "BlankCursor",
    "SplitVCursor",
    "SplitHCursor",
    "PointingHandCursor",
    "ForbiddenCursor",
    "WhatsThisCursor",
    "BusyCursor",
    "OpenHandCursor",
    "ClosedHandCursor",
)


class _EnumBox(QComboBox):
    """Space opens the list. Up and Down on the closed list change the choice."""

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        mods = event.modifiers()  # type: ignore[attr-defined]
        alt = bool(mods & getattr(getattr(Qt, "KeyboardModifier", Qt), "AltModifier"))
        opens = key == qt_key("Key_Space") or (alt and key == qt_key("Key_Down"))
        if opens and not self.view().isVisible():
            self.showPopup()
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


class EnumEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._enum = spec.enum
        self._choices = spec.choices
        if spec.choices:
            combo = QComboBox(parent)
            for choice in spec.choices:
                combo.addItem(choice.label)
            combo.currentIndexChanged.connect(self._commit_choice)
            self._box: QWidget = combo
            return
        if spec.enum is None:
            self._box = QLabel(parent)
            return
        combo = _EnumBox(parent)
        type_name = spec.enum.type_name
        for name in spec.enum.names:
            label = friendly(type_name, host.qt_name, name)
            combo.addItem(label)
            index = combo.count() - 1
            combo.setItemData(index, name)
            combo.setItemData(index, name, Qt.ToolTipRole)  # type: ignore[attr-defined]
        combo.currentIndexChanged.connect(self._commit)
        self._box = combo

    @property
    def widget(self) -> QWidget:
        return self._box

    def wants_stacked(self, width: int) -> bool:
        del width
        return False

    def show(self, value: RowValue) -> None:
        if self._choices:
            combo = self._box
            assert isinstance(combo, QComboBox)
            mark(combo, value)
            # Written, or an Unset row's default (faint by ``mark``).
            current = _payload(value)
            index = -1
            if current is not None:
                for position, choice in enumerate(self._choices):
                    if semantic_equal(choice.value, current):
                        index = position
                        break
                if index < 0:
                    index = _covering_choice(self._choices, current)
            combo.blockSignals(True)
            combo.setCurrentIndex(index)
            combo.setPlaceholderText(
                MIXED_TEXT if isinstance(value, Mixed) else ""
            )
            combo.blockSignals(False)
            return
        text = _enum_text(value)
        if self._enum is None:
            label = self._box
            assert isinstance(label, QLabel)
            mark(label, value)
            if isinstance(value, Mixed):
                label.setText(MIXED_TEXT)
            elif text:
                label.setText(text)
            else:
                label.setText("")
            return
        combo = self._box
        assert isinstance(combo, QComboBox)
        mark(combo, value)
        name_part(combo, self._host, "choice")
        combo.blockSignals(True)
        self._drop_kept(combo)
        tail = text.split("::")[-1] if text else ""
        index = _index_of(combo, tail)
        if index < 0 and tail and not isinstance(value, Mixed):
            combo.insertItem(0, "%s (kept as is)" % tail)
            combo.setItemData(0, tail)
            combo.setItemData(0, tail, Qt.ToolTipRole)  # type: ignore[attr-defined]
            font = combo.font()
            font.setItalic(True)
            combo.setItemData(0, font, Qt.FontRole)  # type: ignore[attr-defined]
            combo.setProperty("fbKept", tail)
            index = 0
        combo.setCurrentIndex(index)
        if index < 0:
            combo.setPlaceholderText(MIXED_TEXT if isinstance(value, Mixed) else "")
        else:
            combo.setPlaceholderText("")
        combo.blockSignals(False)

    def _drop_kept(self, combo: QComboBox) -> None:
        kept = combo.property("fbKept")
        if not kept:
            return
        if combo.itemData(0) == kept:
            combo.removeItem(0)
        combo.setProperty("fbKept", "")

    def _commit(self, index: int) -> None:
        if self._enum is None or index < 0:
            return
        combo = self._box
        assert isinstance(combo, QComboBox)
        name = combo.itemData(index)
        if not isinstance(name, str) or not name:
            return
        self._host.commit(self._host.enum_value(self._enum, (name,)))

    def _commit_choice(self, index: int) -> None:
        if index < 0 or index >= len(self._choices):
            return
        self._host.commit(self._choices[index].value)


class AlignmentEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = QWidget(parent)
        layout = QVBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(S1)
        self._buttons: List[Tuple[str, QToolButton]] = []
        self._horizontal = self._segments(_HORIZONTAL)
        self._vertical = self._segments(_VERTICAL)
        layout.addWidget(self._horizontal, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._vertical, 0, Qt.AlignmentFlag.AlignLeft)
        self._paint_icons()

    @property
    def widget(self) -> QWidget:
        return self._root

    def wants_stacked(self, width: int) -> bool:
        del width
        return False

    def show(self, value: RowValue) -> None:
        mark(self._root, value)
        chosen = {_ALIGN_ALIASES.get(name, name) for name in _flag_tails(_set_text(value))}
        self._show_axis(self._horizontal, _HORIZONTAL, chosen)
        self._show_axis(self._vertical, _VERTICAL, chosen)
        self._paint_icons()

    def _segments(self, names: Tuple[str, ...]) -> ChoiceSegments:
        tips = [_ALIGN_TAILS.get(name, name) for name in names]
        access = [_align_name(self._host, name, tip) for name, tip in zip(names, tips)]
        row = ChoiceSegments(self._root)
        row.set_items([""] * len(names), tooltips=tips, names=access)
        row.name_buttons(["formBuilder.align.%s" % name for name in names])
        row.show_index(-1)
        box = row.layout()
        if box is not None:
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(0)
        row.setFixedSize(_ALIGN_CELL * len(names), _ALIGN_CELL)
        for button in row.buttons():
            button.setText("")
            button.setFixedSize(_ALIGN_CELL, _ALIGN_CELL)
        for name, button in zip(names, row.buttons()):
            button.clicked.connect(self._commit)
            self._buttons.append((name, button))
        return row

    def _show_axis(self, row: ChoiceSegments, names: Tuple[str, ...], chosen: set) -> None:
        index = -1
        for slot, name in enumerate(names):
            if name in chosen:
                index = slot
                break
        row.show_index(index)

    def _commit(self, _checked: bool = False) -> None:
        names = ["Qt::" + name for name, button in self._buttons if button.isChecked()]
        self._host.commit(SetValue("|".join(names)))

    def _paint_icons(self) -> None:
        color = self._root.palette().color(self._root.foregroundRole()).name()
        dpr = float(self._root.devicePixelRatioF()) if hasattr(self._root, "devicePixelRatioF") else 1.0
        self._horizontal.set_icons([_align_icon(name, color, dpr) for name in _HORIZONTAL])
        self._vertical.set_icons([_align_icon(name, color, dpr) for name in _VERTICAL])
        for row, names in ((self._horizontal, _HORIZONTAL), (self._vertical, _VERTICAL)):
            row.setFixedSize(_ALIGN_CELL * len(names), _ALIGN_CELL)
            for button in row.buttons():
                button.setText("")
                button.setFixedSize(_ALIGN_CELL, _ALIGN_CELL)
                button.setIconSize(QSize(ICON, ICON))


def _align_icon(name: str, color: str, dpr: float) -> QIcon:
    """A 16 px alignment mark. The glyph catalog has no align names."""
    ratio = round(float(dpr), 2) or 1.0
    device = max(1, int(round(ICON * ratio)))
    pixmap = QPixmap(device, device)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(getattr(getattr(QPainter, "RenderHint", QPainter), "Antialiasing"), True)
        pen = QPen(QColor(color))
        pen.setWidthF(max(1.0, ratio))
        painter.setPen(pen)
        scale = ratio
        bars = _ALIGN_BARS.get(name, ((2, 4, 12),))
        for top, left, width in bars:
            painter.drawLine(int(left * scale), int(top * scale), int((left + width) * scale), int(top * scale))
    finally:
        painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return QIcon(pixmap)


_ALIGN_BARS = {
    "AlignLeft": ((4, 2, 8), (8, 2, 12), (12, 2, 6)),
    "AlignHCenter": ((4, 4, 8), (8, 2, 12), (12, 5, 6)),
    "AlignRight": ((4, 6, 8), (8, 2, 12), (12, 8, 6)),
    "AlignJustify": ((4, 2, 12), (8, 2, 12), (12, 2, 12)),
    "AlignTop": ((3, 2, 12), (6, 4, 8), (9, 5, 6)),
    "AlignVCenter": ((4, 4, 8), (8, 2, 12), (12, 4, 8)),
    "AlignBottom": ((5, 5, 6), (8, 4, 8), (12, 2, 12)),
}


class CursorEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._combo = QComboBox(parent)
        self._combo.addItems(_CURSORS)
        self._combo.currentIndexChanged.connect(self._commit)

    @property
    def widget(self) -> QWidget:
        return self._combo

    def show(self, value: RowValue) -> None:
        mark(self._combo, value)
        name = _cursor_name(value)
        self._combo.blockSignals(True)
        index = self._combo.findText(name)
        if index < 0 and name:
            self._combo.addItem(name)
            index = self._combo.findText(name)
        self._combo.setCurrentIndex(index)
        self._combo.blockSignals(False)

    def _commit(self, index: int) -> None:
        if index < 0:
            return
        name = self._combo.itemText(index)
        if self._spec.element == CursorValue.ELEMENT:
            shape = getattr(Qt, name, 0)
            self._host.commit(CursorValue(enum_value(shape)))
            return
        self._host.commit(CursorShapeValue(name))

def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(EnumValue.ELEMENT), EnumEditor, baseline=True)
    registrar.editor(ALIGNMENT, AlignmentEditor, baseline=True)
    for element in (CursorShapeValue.ELEMENT, CursorValue.ELEMENT):
        registrar.editor(EditorKey(element), CursorEditor, baseline=True)

def _enum_text(value: RowValue) -> str:
    found = _payload(value)
    if isinstance(found, EnumValue):
        return found.text
    if isinstance(found, SetValue):
        return found.text
    return ""

def _set_text(value: RowValue) -> str:
    found = _payload(value)
    if isinstance(found, SetValue):
        return found.text
    return ""

def _payload(value: RowValue) -> object:
    if isinstance(value, Written):
        return value.value
    if isinstance(value, Unset) and value.default is not None:
        return value.default
    return None

def _covering_choice(choices: Tuple[Choice, ...], current: object) -> int:
    """A set the choices do not spell exactly, such as an unscoped live default
    ``AlignLeft|AlignLeading``, shows the first choice whose names it holds."""
    if not isinstance(current, SetValue):
        return -1
    held = set(_flag_tails(current.text))
    for position, choice in enumerate(choices):
        if isinstance(choice.value, SetValue):
            names = set(_flag_tails(choice.value.text))
            if names and names <= held:
                return position
    return -1


def _flag_tails(text: str) -> Tuple[str, ...]:
    tails = []
    for piece in text.split("|"):
        name = piece.strip().split("::")[-1]
        if name and name != "0":
            tails.append(name)
    return tuple(tails)

def _cursor_name(value: RowValue) -> str:
    found = _payload(value)
    if isinstance(found, CursorShapeValue):
        return found.name
    if isinstance(found, CursorValue):
        return str(found.value)
    if isinstance(value, Mixed):
        return ""
    return ""

def _index_of(combo: QComboBox, tail: str) -> int:
    if not tail:
        return -1
    for index in range(combo.count()):
        if combo.itemData(index) == tail:
            return index
    return -1
