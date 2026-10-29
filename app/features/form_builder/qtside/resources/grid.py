"""The resource editor's picture grid (UX-RES-004): one header per prefix, 72 x 80 px cells.

Cells are painted, not widgets, so a project with 500 pictures stays cheap to open.
Thumbnails come from the same size-and-mtime cache the picker uses.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from app.features.form_builder.engine.project.qrc_write import QrcLayout, entry_disk_path, resource_of
from app.features.form_builder.qtside.inspector.editors._picture_picker import (
    cached_thumbnail,
    cell_name,
    paint_checker,
)
from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.features.form_builder.qtside.visual.common import token_color
from app.qt.QtCore import QEvent, QRect, Qt
from app.qt.QtGui import QFont, QFontMetrics, QPainter, QPen
from app.qt.QtWidgets import QWidget

CELL_W = 72
CELL_H = 80
THUMB = 56
HEADER_H = 24
NO_PREFIX = "No prefix"

Cell = Tuple[int, int]


def prefix_title(prefix: str) -> str:
    """``/`` is shown as "No prefix"."""
    return NO_PREFIX if prefix.strip("/") == "" else prefix


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


@dataclass
class _Slot:
    kind: str
    x: int
    y: int
    w: int
    h: int
    cell: Cell = (-1, -1)


class QrcGrid(QWidget):
    """Arrows move, Enter renames, Delete removes. The owner supplies the actions."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.qrcGrid")
        self.setAccessibleName("Pictures")
        self.setFocusPolicy(getattr(getattr(Qt, "FocusPolicy", Qt), "StrongFocus"))  # type: ignore[arg-type]
        self.setMouseTracking(True)
        self._layout = QrcLayout()
        self._qrc_path = ""
        self._root = ""
        self._chrome: Optional[FormChrome] = None
        self._slots: List[_Slot] = []
        self._cells: List[_Slot] = []
        self._selected: Optional[Cell] = None
        self.on_rename: Callable[[], None] = lambda: None
        self.on_remove: Callable[[], None] = lambda: None
        self.on_selection: Callable[[], None] = lambda: None
        self.on_undo: Callable[[], object] = lambda: None
        self.on_redo: Callable[[], object] = lambda: None

    def set_tokens(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        self.update()

    def set_layout(self, layout: QrcLayout, qrc_path: str, project_root: str) -> None:
        self._layout = layout
        self._qrc_path = qrc_path
        self._root = project_root
        if self._selected is not None and not self._valid(self._selected):
            self._selected = None
        self._reflow()
        if self._selected is None and self._cells:
            self._selected = self._cells[0].cell
        self._describe()
        self.update()

    def selected(self) -> Optional[Cell]:
        return self._selected

    def select_resource(self, resource: str) -> None:
        """Select the picture that has this ``:/`` path, when the grid shows it."""
        for slot in self._cells:
            group = self._layout.groups[slot.cell[0]]
            if resource_of(group, group.entries[slot.cell[1]]) == resource:
                self.select(slot.cell)
                return

    def select(self, cell: Cell) -> None:
        if self._valid(cell):
            self._selected = cell
            self._describe()
            self._reveal()
            self.update()
            self.on_selection()

    def count(self) -> int:
        return len(self._cells)

    def selected_resource(self) -> str:
        cell = self._selected
        if cell is None or not self._valid(cell):
            return ""
        group = self._layout.groups[cell[0]]
        return resource_of(group, group.entries[cell[1]])

    def selected_name(self) -> str:
        cell = self._selected
        if cell is None or not self._valid(cell):
            return ""
        entry = self._layout.groups[cell[0]].entries[cell[1]]
        return os.path.basename(entry.alias or entry.path)

    def move_by(self, dx: int, dy: int) -> None:
        if not self._cells:
            return
        order = [slot.cell for slot in self._cells]
        here = self._selected if self._selected in order else order[0]
        index = order.index(here)
        if dx:
            index = max(0, min(len(order) - 1, index + dx))
        if dy:
            index = self._row_neighbour(index, dy)
        self.select(order[index])

    def _row_neighbour(self, index: int, dy: int) -> int:
        here = self._cells[index]
        rows = sorted({slot.y for slot in self._cells})
        at = rows.index(here.y) + (1 if dy > 0 else -1)
        if at < 0 or at >= len(rows):
            return index
        row = [slot for slot in self._cells if slot.y == rows[at]]
        best = min(row, key=lambda slot: abs(slot.x - here.x))
        return self._cells.index(best)

    def event(self, event: QEvent) -> bool:
        # Ctrl+Z belongs to the tab's undo, not the shell's; claim it while the grid has focus.
        if event.type() == getattr(QEvent.Type, "ShortcutOverride"):
            if self.hasFocus() and self._wants_shortcut(event):
                event.accept()  # type: ignore[attr-defined]
                return True
        return super().event(event)

    def _wants_shortcut(self, event: QEvent) -> bool:
        key = event.key()  # type: ignore[attr-defined]
        ctrl = getattr(getattr(Qt, "KeyboardModifier", Qt), "ControlModifier")
        mods = event.modifiers()  # type: ignore[attr-defined]
        return bool(mods & ctrl) and key in (_key("Key_Z"), _key("Key_Y"))

    def keyPressEvent(self, event: QEvent) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        mods = event.modifiers()  # type: ignore[attr-defined]
        ctrl = getattr(getattr(Qt, "KeyboardModifier", Qt), "ControlModifier")
        shift = getattr(getattr(Qt, "KeyboardModifier", Qt), "ShiftModifier")
        if mods & ctrl and key == _key("Key_Z"):
            (self.on_redo if mods & shift else self.on_undo)()
        elif mods & ctrl and key == _key("Key_Y"):
            self.on_redo()
        elif key == _key("Key_Left"):
            self.move_by(-1, 0)
        elif key == _key("Key_Right"):
            self.move_by(1, 0)
        elif key == _key("Key_Up"):
            self.move_by(0, -1)
        elif key == _key("Key_Down"):
            self.move_by(0, 1)
        elif key in (_key("Key_Return"), _key("Key_Enter")):
            self.on_rename()
        elif key in (_key("Key_Delete"), _key("Key_Backspace")):
            self.on_remove()
        else:
            super().keyPressEvent(event)  # type: ignore[arg-type]
            return
        event.accept()  # type: ignore[attr-defined]

    def mousePressEvent(self, event: QEvent) -> None:  # noqa: N802
        pos = event.position() if hasattr(event, "position") else event.pos()  # type: ignore[attr-defined]
        x, y = int(pos.x()), int(pos.y())
        for slot in self._cells:
            if QRect(slot.x, slot.y, slot.w, slot.h).contains(x, y):
                self.setFocus()
                self.select(slot.cell)
                event.accept()  # type: ignore[attr-defined]
                return
        super().mousePressEvent(event)  # type: ignore[arg-type]

    def mouseDoubleClickEvent(self, event: QEvent) -> None:  # noqa: N802
        self.mousePressEvent(event)
        if self._selected is not None:
            self.on_rename()

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._reflow()

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        chrome = self._chrome
        if chrome is None:
            return
        painter = QPainter(self)
        text = token_color(chrome.text)
        muted = token_color(chrome.muted)
        accent = token_color(chrome.accent)
        error = token_color(chrome.error)
        border = token_color(chrome.fb.swatch_border)
        checker_a = token_color(chrome.fb.checker_a)
        checker_b = token_color(chrome.fb.checker_b)
        clip = event.rect()  # type: ignore[attr-defined]
        metrics = QFontMetrics(self.font())
        for slot in self._slots:
            rect = QRect(slot.x, slot.y, slot.w, slot.h)
            if not rect.intersects(clip):
                continue
            if slot.kind == "header":
                bold = QFont(self.font())
                bold.setBold(True)
                painter.setFont(bold)
                painter.setPen(muted)
                painter.drawText(rect.adjusted(2, 0, -2, 0), _align("AlignVCenter", "AlignLeft"), slot.text_for(self))
                painter.setFont(self.font())
                continue
            group = self._layout.groups[slot.cell[0]]
            entry = group.entries[slot.cell[1]]
            disk = entry_disk_path(self._qrc_path, entry, self._root or os.path.dirname(self._qrc_path))
            missing = not disk or not os.path.isfile(disk)
            thumb = QRect(slot.x + (CELL_W - THUMB) // 2, slot.y + 2, THUMB, THUMB)
            paint_checker(painter, thumb, checker_a, checker_b)
            if not missing:
                pixmap = cached_thumbnail(disk, THUMB)
                if not pixmap.isNull():
                    painter.drawPixmap(
                        thumb.x() + (thumb.width() - pixmap.width()) // 2,
                        thumb.y() + (thumb.height() - pixmap.height()) // 2,
                        pixmap,
                    )
            painter.setPen(QPen(border))
            painter.drawRect(thumb.adjusted(0, 0, -1, -1))
            if slot.cell == self._selected:
                painter.setPen(QPen(accent, 2))
                painter.drawRect(rect.adjusted(1, 1, -2, -2))
            painter.setPen(error if missing else text)
            name = cell_name(metrics, os.path.basename(entry.alias or entry.path), CELL_W - 4)
            painter.drawText(QRect(slot.x, thumb.bottom() + 1, CELL_W, 14), _align("AlignHCenter", "AlignTop"), name)
            if missing:
                painter.setPen(error)
                painter.drawText(QRect(slot.x, thumb.bottom() + 14, CELL_W, 14), _align("AlignHCenter", "AlignTop"), "missing")
        painter.end()

    def _valid(self, cell: Cell) -> bool:
        group, entry = cell
        return 0 <= group < len(self._layout.groups) and 0 <= entry < len(self._layout.groups[group].entries)

    def _reflow(self) -> None:
        columns = max(1, max(self.width(), CELL_W) // CELL_W)
        slots: List[_Slot] = []
        cells: List[_Slot] = []
        y = 0
        for group_index, group in enumerate(self._layout.groups):
            header = _Header(group_index, prefix_title(group.prefix), 0, y, columns * CELL_W, HEADER_H)
            slots.append(header)
            y += HEADER_H
            column = 0
            for entry_index in range(len(group.entries)):
                slot = _Slot("cell", column * CELL_W, y, CELL_W, CELL_H, (group_index, entry_index))
                slots.append(slot)
                cells.append(slot)
                column += 1
                if column >= columns:
                    column = 0
                    y += CELL_H
            if column:
                y += CELL_H
        self._slots = slots
        self._cells = cells
        self.setMinimumHeight(max(y, CELL_H))
        self.updateGeometry()

    def _describe(self) -> None:
        cell = self._selected
        if cell is None or not self._valid(cell):
            self.setAccessibleName("Pictures")
            self.setAccessibleDescription("")
            return
        order = [slot.cell for slot in self._cells]
        position = order.index(cell) + 1 if cell in order else 0
        self.setAccessibleName("Picture: %s, %d of %d" % (self.selected_name(), position, len(order)))
        self.setAccessibleDescription(self.selected_resource())

    def _reveal(self) -> None:
        cell = self._selected
        if cell is None:
            return
        for slot in self._cells:
            if slot.cell == cell:
                parent = self.parentWidget()
                while parent is not None:
                    ensure = getattr(parent, "ensureVisible", None)
                    if callable(ensure):
                        ensure(slot.x, slot.y + slot.h // 2, 8, 8)
                        return
                    parent = parent.parentWidget()

    def tip_for(self, x: int, y: int) -> str:
        for slot in self._cells:
            if QRect(slot.x, slot.y, slot.w, slot.h).contains(x, y):
                group = self._layout.groups[slot.cell[0]]
                return resource_of(group, group.entries[slot.cell[1]])
        return ""

    def mouseMoveEvent(self, event: QEvent) -> None:  # noqa: N802
        pos = event.position() if hasattr(event, "position") else event.pos()  # type: ignore[attr-defined]
        self.setToolTip(self.tip_for(int(pos.x()), int(pos.y())))
        super().mouseMoveEvent(event)  # type: ignore[arg-type]


class _Header(_Slot):
    def __init__(self, group_index: int, text: str, x: int, y: int, w: int, h: int) -> None:
        super().__init__("header", x, y, w, h, (group_index, -1))
        self.text = text

    def text_for(self, grid: QrcGrid) -> str:
        del grid
        return self.text


def _align(*names: str) -> object:
    flag = getattr(Qt, "AlignmentFlag", Qt)
    combined: object = None
    for name in names:
        value = getattr(flag, name)
        combined = value if combined is None else combined | value
    return combined


__all__ = ["CELL_H", "CELL_W", "NO_PREFIX", "QrcGrid", "prefix_title"]
