"""Ctrl+Shift+G: wrap the selection in one of nine containers (UX-WRAP-001)."""

from __future__ import annotations

from typing import Callable, List

from app.qt.QtCore import QEvent, QObject, QRect, Qt
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import QFrame, QGridLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.layout_actions import KINDS, POPOVER, OfferSheet, PickWrap, gate
from app.features.form_builder.qtside.layout_gestures import beside, popover_style
from app.features.form_builder.qtside.theme.chrome import FormChrome

_COLUMNS = 3
_DIGITS = {enum_value(getattr(Qt.Key, "Key_%d" % digit)): digit - 1 for digit in range(1, 10)}
_ARROWS = {
    enum_value(Qt.Key.Key_Left): (-1, 0),
    enum_value(Qt.Key.Key_Right): (1, 0),
    enum_value(Qt.Key.Key_Up): (0, -1),
    enum_value(Qt.Key.Key_Down): (0, 1),
}
_ENTER = frozenset({enum_value(Qt.Key.Key_Return), enum_value(Qt.Key.Key_Enter)})
_ESCAPE = enum_value(Qt.Key.Key_Escape)
_CHORDS = (
    enum_value(Qt.KeyboardModifier.ControlModifier)
    | enum_value(Qt.KeyboardModifier.AltModifier)
    | enum_value(Qt.KeyboardModifier.MetaModifier)
)


class WrapPopover(QFrame):
    """Nine tiles in ``POPOVER`` order. Digits 1 to 9 pick a tile.

    A tile that cannot apply stays visible, disabled, with the reason as its
    tooltip; its digit shows the reason under the grid. While the popover is
    open it claims every shortcut, so Ctrl+1 cannot also run on the canvas.
    """

    def __init__(
        self,
        parent: QWidget,
        sheet: OfferSheet,
        count: int,
        chrome: FormChrome,
        on_pick: Callable[[str], None],
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("formBuilder.wrapPopover")
        self.setAccessibleName("Wrap in")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(popover_style(self.objectName(), chrome))
        self._on_pick = on_pick
        column = QVBoxLayout(self)
        column.setContentsMargins(12, 10, 12, 12)
        column.setSpacing(8)
        header = QLabel("Wrap %d %s in\u2026" % (count, "widget" if count == 1 else "widgets"), self)
        header.setObjectName("formBuilder.wrapHeader")
        column.addWidget(header)
        grid = QGridLayout()
        grid.setSpacing(6)
        self.tiles: List[QToolButton] = []
        self._reasons: List[str] = []
        for index, kind_id in enumerate(POPOVER):
            offer = gate(sheet, PickWrap(kind_id))
            label = KINDS[kind_id].label
            tile = QToolButton(self)
            tile.setObjectName("formBuilder.wrapTile.%s" % kind_id)
            tile.setText("%d  %s" % (index + 1, label))
            tile.setAccessibleName(label)
            tile.setEnabled(offer.enabled)
            tile.setToolTip(offer.reason)
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            tile.clicked.connect(lambda _checked=False, kind_id=kind_id: self._pick(kind_id))
            tile.installEventFilter(self)
            grid.addWidget(tile, index // _COLUMNS, index % _COLUMNS)
            self.tiles.append(tile)
            self._reasons.append(offer.reason)
        column.addLayout(grid)
        self.note = QLabel("", self)
        self.note.setObjectName("formBuilder.wrapNote")
        self.note.setProperty("note", True)
        self.note.setWordWrap(True)
        self.note.hide()
        column.addWidget(self.note)

    def open_beside(self, subject: QRect, bounds: QRect) -> None:
        """Show under ``subject`` (global), inside ``bounds``, with the first open tile focused."""
        self.adjustSize()
        self.move(beside(subject, self.sizeHint(), bounds))
        self.show()
        first = next((tile for tile in self.tiles if tile.isEnabled()), None)
        if first is not None:
            first.setFocus()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        if event.type() != QEvent.Type.KeyPress or watched not in self.tiles:
            return super().eventFilter(watched, event)
        return self._key(self.tiles.index(watched), event)  # type: ignore[arg-type]

    def _key(self, at: int, event: QKeyEvent) -> bool:
        key = enum_value(event.key())
        digit = _DIGITS.get(key)
        if digit is not None:
            if not enum_value(event.modifiers()) & _CHORDS:
                self._digit(digit)
            return True
        step = _ARROWS.get(key)
        if step is not None:
            self._move(at, *step)
            return True
        if key in _ENTER:
            self.tiles[at].click()
            return True
        if key == _ESCAPE:
            self.close()
            return True
        return False

    def _digit(self, index: int) -> None:
        tile = self.tiles[index]
        if tile.isEnabled():
            tile.click()
            return
        self.note.setText(self._reasons[index])
        self.note.show()
        self.adjustSize()

    def _move(self, at: int, dx: int, dy: int) -> None:
        row, column = divmod(at, _COLUMNS)
        while True:
            row, column = row + dy, column + dx
            if not (0 <= row < len(self.tiles) // _COLUMNS and 0 <= column < _COLUMNS):
                return
            tile = self.tiles[row * _COLUMNS + column]
            if tile.isEnabled():
                tile.setFocus()
                return

    def _pick(self, kind_id: str) -> None:
        self.close()
        self._on_pick(kind_id)
