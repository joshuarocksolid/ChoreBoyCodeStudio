"""Start-screen cards. The whole card is the click target."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import Qt, Signal
from app.qt.QtGui import QColor, QFont, QPainter, QPen
from app.qt.QtWidgets import QWidget
from app.qt.qt_compat import enum_value

from app.features.form_builder.qtside.theme.chrome import FormChrome

CARD_WIDTH = 200
CARD_HEIGHT = 156
THUMB_HEIGHT = 120

_Draw = Callable[[QPainter, FormChrome, int, int, int, int], None]


class StartCard(QWidget):
    """One 200 by 156 card. Arrow keys are handled by the panel."""

    activated = Signal(str)
    move_requested = Signal(str, int, int)

    def __init__(self, key: str, title: str, description: str, chrome: FormChrome, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.key = key
        self._title = title
        self._description = description
        self._chrome = chrome
        self._hover = False
        self.setObjectName("formBuilder.newForm.card." + key)
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(title)
        self.setCursor(Qt.PointingHandCursor)

    def set_chrome(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        self.update()

    def enterEvent(self, event: object) -> None:  # type: ignore[override]
        self._hover = True
        self.update()
        super().enterEvent(event)  # type: ignore[arg-type]

    def leaveEvent(self, event: object) -> None:  # type: ignore[override]
        self._hover = False
        self.update()
        super().leaveEvent(event)  # type: ignore[arg-type]

    def mouseReleaseEvent(self, event: object) -> None:  # type: ignore[override]
        if self.isEnabled() and enum_value(getattr(event, "button")()) == enum_value(Qt.LeftButton):
            self.activated.emit(self.key)
        super().mouseReleaseEvent(event)  # type: ignore[arg-type]

    def keyPressEvent(self, event: object) -> None:  # type: ignore[override]
        key = enum_value(getattr(event, "key")())
        if key in (enum_value(Qt.Key_Return), enum_value(Qt.Key_Enter), enum_value(Qt.Key_Space)):
            if self.isEnabled():
                self.activated.emit(self.key)
            getattr(event, "accept")()
            return
        step = {
            enum_value(Qt.Key_Left): (-1, 0),
            enum_value(Qt.Key_Right): (1, 0),
            enum_value(Qt.Key_Up): (0, -1),
            enum_value(Qt.Key_Down): (0, 1),
        }.get(key)
        if step is not None:
            self.move_requested.emit(self.key, step[0], step[1])
            getattr(event, "accept")()
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def paintEvent(self, event: object) -> None:  # type: ignore[override]
        del event
        chrome = self._chrome
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(chrome.panel))
        focused = self.hasFocus()
        if focused:
            width = chrome.focus_width
            color = chrome.accent
        elif self._hover and self.isEnabled():
            width = 1
            color = chrome.accent
        else:
            width = 1
            color = chrome.border
        pen = QPen(QColor(color))
        pen.setWidth(width)
        painter.setPen(pen)
        painter.drawRect(width // 2, width // 2, self.width() - width, self.height() - width)
        painter.fillRect(1, 1, self.width() - 2, THUMB_HEIGHT - 1, QColor(chrome.row_hover))
        drawer = _WIREFRAMES.get(self.key, _draw_blank)
        painter.setPen(QPen(QColor(chrome.faint)))
        drawer(painter, chrome, 12, 16, self.width() - 24, THUMB_HEIGHT - 28)
        painter.setPen(QColor(chrome.text if self.isEnabled() else chrome.faint))
        title_font = QFont(self.font())
        title_font.setBold(True)
        title_font.setPixelSize(12)
        painter.setFont(title_font)
        painter.drawText(8, THUMB_HEIGHT + 2, self.width() - 16, 16, int(Qt.AlignLeft | Qt.AlignVCenter), self._title)
        painter.setPen(QColor(chrome.muted if self.isEnabled() else chrome.faint))
        caption = QFont(self.font())
        caption.setBold(False)
        caption.setPixelSize(11)
        painter.setFont(caption)
        painter.drawText(8, THUMB_HEIGHT + 18, self.width() - 16, 16, int(Qt.AlignLeft | Qt.AlignVCenter), self._description)
        painter.end()


def _draw_fields(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int, accent_row: int) -> None:
    del height
    row_h = 16
    for index in range(3):
        top = y + index * (row_h + 6)
        painter.drawRect(x, top + 4, 36, 8)
        if index == accent_row:
            painter.fillRect(x + 44, top, width - 44, row_h, QColor(chrome.accent))
        else:
            painter.drawRect(x + 44, top, width - 44, row_h)


def _draw_data_entry(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    _draw_fields(painter, chrome, x, y, width, height, 1)


def _draw_list_detail(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    list_w = max(28, width // 3)
    painter.fillRect(x, y, list_w, height, QColor(chrome.accent))
    _draw_fields(painter, chrome, x + list_w + 8, y, width - list_w - 8, height, -1)


def _draw_table_search(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    painter.fillRect(x, y, width, 14, QColor(chrome.accent))
    top = y + 22
    cols = 3
    rows = 3
    col_w = width // cols
    row_h = max(8, (height - 22) // rows)
    for row in range(rows):
        for col in range(cols):
            painter.drawRect(x + col * col_w, top + row * row_h, col_w - 2, row_h - 2)


def _draw_dialog(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    _draw_fields(painter, chrome, x, y, width, height - 22, 0)
    button_y = y + height - 16
    painter.drawRect(x + width - 78, button_y, 34, 14)
    painter.fillRect(x + width - 38, button_y, 38, 14, QColor(chrome.accent))


def _draw_blank(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    del chrome
    painter.drawRect(x, y, width, height)


def _draw_main_window(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    painter.fillRect(x, y, width, 12, QColor(chrome.accent))
    painter.drawRect(x, y + 16, width, height - 16)


def _draw_from_table(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    painter.fillRect(x, y, width, 12, QColor(chrome.accent))
    row_h = max(8, (height - 12) // 4)
    for index in range(4):
        top = y + 12 + index * row_h
        painter.drawRect(x, top, width // 3, row_h - 2)
        painter.drawRect(x + width // 3 + 4, top, width - width // 3 - 4, row_h - 2)


def _draw_adopt(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    painter.drawRect(x + 8, y, width - 16, height)
    painter.fillRect(x + 16, y + 10, width // 2, 8, QColor(chrome.accent))
    painter.drawRect(x + 16, y + 24, width - 40, 8)
    painter.drawRect(x + 16, y + 38, width - 52, 8)


_WIREFRAMES = {
    "data_entry": _draw_data_entry,
    "list_detail": _draw_list_detail,
    "table_search": _draw_table_search,
    "dialog_ok_cancel": _draw_dialog,
    "widget": _draw_blank,
    "main_window": _draw_main_window,
    "dialog": _draw_blank,
    "from_table": _draw_from_table,
    "adopt": _draw_adopt,
}
