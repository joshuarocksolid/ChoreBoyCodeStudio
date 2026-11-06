"""Start-screen cards. The whole card is the click target."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from app.qt.QtCore import QRectF, Qt, Signal
from app.qt.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from app.qt.QtWidgets import QWidget
from app.qt.qt_compat import enum_value

from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.features.form_builder.qtside.theme.metrics import CARD_H, CARD_W, R_CARD, THUMB_H, TYPE_BODY

CARD_WIDTH = CARD_W
CARD_HEIGHT = CARD_H
THUMB_HEIGHT = THUMB_H
_CORNER_RADIUS = float(R_CARD)
_ACCENT_W = 24
_ACCENT_H = 8

_Draw = Callable[[QPainter, FormChrome, int, int, int, int], None]


class StartCard(QWidget):
    """One 200 by 156 card. Arrow keys are handled by the panel."""

    activated = Signal(str)
    move_requested = Signal(str, int, int)
    #: Ctrl+Down (1) and Ctrl+Up (-1): go to the next or previous group (UX-TMPL-004).
    group_requested = Signal(str, int)
    #: Shift+F10, the menu key or a right click on a saved template: the key and a global point.
    menu_requested = Signal(str, object)

    def __init__(
        self,
        key: str,
        title: str,
        description: str,
        chrome: FormChrome,
        parent: Optional[QWidget] = None,
        *,
        thumbnail: Optional[QPixmap] = None,
        tag: str = "",
        tooltip: str = "",
        has_menu: bool = False,
        widgets: Sequence[str] = (),
    ) -> None:
        super().__init__(parent)
        self.key = key
        self._title = title
        self._description = description
        self._chrome = chrome
        self._hover = False
        self._thumbnail = thumbnail
        self._tag = tag
        self._has_menu = has_menu
        self._widgets = tuple(widgets)
        self.setObjectName("formBuilder.newForm.card." + key.replace(":", "."))
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)
        tip = tooltip or description or title
        self.setToolTip(tip)
        self.setCursor(Qt.PointingHandCursor)

    def title(self) -> str:
        return self._title

    def description(self) -> str:
        return self._description

    def tag(self) -> str:
        return self._tag

    def has_menu(self) -> bool:
        return self._has_menu

    def contextMenuEvent(self, event: object) -> None:  # type: ignore[override]  # noqa: N802
        if not self._has_menu:
            super().contextMenuEvent(event)  # type: ignore[arg-type]
            return
        self.setFocus()
        self.menu_requested.emit(self.key, getattr(event, "globalPos")())
        getattr(event, "accept")()

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
        modifiers = enum_value(getattr(event, "modifiers")())
        control = bool(modifiers & enum_value(Qt.ControlModifier))
        shift = bool(modifiers & enum_value(Qt.ShiftModifier))
        if self._has_menu and (key == enum_value(Qt.Key_Menu) or (shift and key == enum_value(Qt.Key_F10))):
            self.menu_requested.emit(self.key, self.mapToGlobal(self.rect().center()))
            getattr(event, "accept")()
            return
        if control and key in (enum_value(Qt.Key_Down), enum_value(Qt.Key_Up)):
            self.group_requested.emit(self.key, 1 if key == enum_value(Qt.Key_Down) else -1)
            getattr(event, "accept")()
            return
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
        focused = self.hasFocus()
        if focused:
            ring = max(2, chrome.focus_width)
            color = chrome.accent
        elif self._hover and self.isEnabled():
            ring = 1
            color = chrome.accent
        else:
            ring = 1
            color = chrome.border
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        outer = QRectF(
            ring / 2.0,
            ring / 2.0,
            max(0.0, self.width() - ring),
            max(0.0, self.height() - ring),
        )
        clip = QPainterPath()
        clip.addRoundedRect(outer, _CORNER_RADIUS, _CORNER_RADIUS)
        painter.save()
        painter.setClipPath(clip)
        painter.fillRect(self.rect(), QColor(chrome.panel))
        painter.fillRect(0, 0, self.width(), THUMB_HEIGHT, QColor(chrome.row_hover))
        content = _paint_mini_window(painter, chrome, self.width())
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(_faint_pen(chrome))
        painter.setBrush(Qt.NoBrush)
        if self._widgets:
            _draw_saved(painter, chrome, content[0], content[1], content[2], content[3], self._widgets)
        else:
            drawer = _WIREFRAMES.get(self.key, _draw_blank)
            drawer(painter, chrome, content[0], content[1], content[2], content[3])
        text_width = max(0, self.width() - 16)
        band_h = max(0, self.height() - THUMB_HEIGHT)
        title_h = 16
        title_y = THUMB_HEIGHT + max(0, (band_h - title_h) // 2)
        tag_width = 0
        if self._tag:
            tag_font = QFont(self.font())
            tag_font.setBold(False)
            tag_font.setPixelSize(10)
            tag_width = QFontMetrics(tag_font).horizontalAdvance(self._tag) + 4
            painter.setFont(tag_font)
            painter.setPen(QColor(chrome.faint))
            painter.drawText(
                8 + text_width - tag_width,
                title_y,
                tag_width,
                title_h,
                int(Qt.AlignRight | Qt.AlignVCenter),
                self._tag,
            )
        painter.setPen(QColor(chrome.text if self.isEnabled() else chrome.faint))
        title_font = QFont(self.font())
        title_font.setBold(False)
        title_font.setWeight(QFont.DemiBold)
        title_font.setPixelSize(TYPE_BODY)
        painter.setFont(title_font)
        title = QFontMetrics(title_font).elidedText(self._title, Qt.ElideRight, max(0, text_width - tag_width))
        painter.drawText(8, title_y, text_width, title_h, int(Qt.AlignLeft | Qt.AlignVCenter), title)
        painter.restore()
        pen = QPen(QColor(color))
        pen.setWidth(ring)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(outer, _CORNER_RADIUS, _CORNER_RADIUS)
        painter.end()


def _faint_pen(chrome: FormChrome) -> QPen:
    color = QColor(chrome.faint)
    color.setAlpha(153)
    pen = QPen(color)
    pen.setWidth(1)
    pen.setCosmetic(True)
    return pen


def _paint_mini_window(painter: QPainter, chrome: FormChrome, card_width: int) -> tuple:
    """A 6 px title strip and three 2 px dots. Returns the content box under the strip."""
    x, y = 16, 14
    width = max(8, card_width - 32)
    height = max(16, THUMB_HEIGHT - 28)
    faint = QColor(chrome.faint)
    faint.setAlpha(153)
    painter.setPen(QPen(faint))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(x, y, width, height)
    strip = QColor(chrome.faint)
    strip.setAlpha(70)
    painter.fillRect(x + 1, y + 1, max(0, width - 1), 6, strip)
    painter.setPen(Qt.NoPen)
    painter.setBrush(faint)
    for index in range(3):
        painter.drawEllipse(x + 4 + index * 4, y + 2, 2, 2)
    return (x + 6, y + 10, max(8, width - 12), max(8, height - 14))


def _accent(painter: QPainter, chrome: FormChrome, x: int, y: int) -> None:
    painter.fillRect(x, y, _ACCENT_W, _ACCENT_H, QColor(chrome.accent))


def _field(painter: QPainter, x: int, y: int, width: int) -> None:
    painter.drawLine(x, y + 4, x + 20, y + 4)
    painter.drawRect(x + 28, y, min(72, max(8, width - 28)), _ACCENT_H)


def _draw_fields(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int, accent_row: int) -> None:
    del height
    for index in range(3):
        top = y + index * 14
        if index == accent_row:
            painter.drawLine(x, top + 4, x + 20, top + 4)
            _accent(painter, chrome, x + 28, top)
        else:
            _field(painter, x, top, width)


def _draw_data_entry(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    _draw_fields(painter, chrome, x, y, width, height, 1)


def _draw_list_detail(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    painter.drawRect(x, y, 22, max(8, height - 2))
    _accent(painter, chrome, x + 2, y + 4)
    _draw_fields(painter, chrome, x + 28, y, width - 28, height, -1)


def _draw_table_search(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    _accent(painter, chrome, x, y)
    top = y + 14
    col_w = max(8, width // 3)
    row_h = 10
    rows = max(1, min(3, (height - 14) // row_h))
    for row in range(rows):
        for col in range(3):
            painter.drawRect(x + col * col_w, top + row * row_h, col_w - 2, row_h - 2)


def _draw_dialog(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    _draw_fields(painter, chrome, x, y, width, height - 16, -1)
    button_y = y + max(16, height - 12)
    painter.drawRect(x + width - 56, button_y, 22, _ACCENT_H)
    _accent(painter, chrome, x + width - _ACCENT_W, button_y)


def _draw_dialog_right(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    _draw_fields(painter, chrome, x, y, width - 32, height, -1)
    _accent(painter, chrome, x + width - _ACCENT_W, y)
    painter.drawRect(x + width - _ACCENT_W, y + 14, _ACCENT_W, _ACCENT_H)


def _draw_blank(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    _draw_fields(painter, chrome, x, y, width, height, 0)


def _draw_main_window(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    painter.drawLine(x, y + 4, x + min(40, width), y + 4)
    _accent(painter, chrome, x, y + 10)
    painter.drawRect(x, y + 22, max(8, width), max(8, height - 24))


def _draw_from_table(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    _accent(painter, chrome, x, y)
    row_h = 12
    rows = max(1, min(4, (height - 12) // row_h))
    for index in range(rows):
        top = y + 12 + index * row_h
        painter.drawRect(x, top, max(8, width // 3), _ACCENT_H)
        painter.drawRect(x + width // 3 + 4, top, max(8, width - width // 3 - 4), _ACCENT_H)


def _draw_wizard(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    painter.drawRect(x, y, max(8, width), max(8, height - 16))
    button_y = y + max(16, height - 12)
    painter.drawRect(x, button_y, 22, _ACCENT_H)
    _accent(painter, chrome, x + max(0, width - _ACCENT_W), button_y)


def _draw_adopt(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    del height
    painter.drawRect(x, y, max(8, width), 36)
    _accent(painter, chrome, x + 6, y + 6)
    painter.drawRect(x + 6, y + 18, max(8, width - 20), _ACCENT_H)


_CONTAINERS = {"QWidget", "QDialog", "QMainWindow", "QFrame", "QGroupBox", "QScrollArea", "QTabWidget", "QWizard"}
_ACCENT_CLASSES = {"QPushButton", "QToolButton", "QCommandLinkButton"}


def _draw_saved(
    painter: QPainter,
    chrome: FormChrome,
    x: int,
    y: int,
    width: int,
    height: int,
    classes: Sequence[str],
) -> None:
    rows = [name for name in classes if name not in _CONTAINERS][:4]
    if not rows:
        rows = ["QLineEdit"]
    accent_at = 0
    for index, name in enumerate(rows):
        if name in _ACCENT_CLASSES:
            accent_at = index
            break
    for index, _name in enumerate(rows):
        top = y + index * 14
        if top + _ACCENT_H > y + height:
            break
        if index == accent_at:
            painter.drawLine(x, top + 4, x + 20, top + 4)
            _accent(painter, chrome, x + 28, top)
        else:
            _field(painter, x, top, width)


_WIREFRAMES = {
    "data_entry": _draw_data_entry,
    "list_detail": _draw_list_detail,
    "table_search": _draw_table_search,
    "dialog_ok_cancel": _draw_dialog,
    "dialog_buttons_right": _draw_dialog_right,
    "widget": _draw_blank,
    "main_window": _draw_main_window,
    "dialog": _draw_blank,
    "wizard": _draw_wizard,
    "from_table": _draw_from_table,
    "adopt": _draw_adopt,
}
