"""Start-screen cards. The whole card is the click target."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import QRectF, Qt, Signal
from app.qt.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from app.qt.QtWidgets import QWidget
from app.qt.qt_compat import enum_value

from app.features.form_builder.qtside.theme.chrome import FormChrome

CARD_WIDTH = 200
CARD_HEIGHT = 156
THUMB_HEIGHT = 120
_CORNER_RADIUS = 8.0

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
        self.setObjectName("formBuilder.newForm.card." + key.replace(":", "."))
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)
        self.setToolTip(tooltip or (title + "\n" + description))
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

    def _paint_thumbnail(self, painter: QPainter) -> None:
        """The saved canvas picture, centred in the 120 px thumbnail band at its own size or smaller."""
        picture = self._thumbnail
        if picture is None:
            return
        ratio = max(1.0, picture.devicePixelRatio())
        width = picture.width() / ratio
        height = picture.height() / ratio
        scale = min(1.0, self.width() / width, THUMB_HEIGHT / height)
        draw_w, draw_h = width * scale, height * scale
        painter.drawPixmap(
            QRectF((self.width() - draw_w) / 2.0, (THUMB_HEIGHT - draw_h) / 2.0, draw_w, draw_h),
            picture,
            QRectF(0, 0, picture.width(), picture.height()),
        )

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
        if self._thumbnail is not None and not self._thumbnail.isNull():
            self._paint_thumbnail(painter)
        else:
            drawer = _WIREFRAMES.get(self.key, _draw_blank)
            painter.setPen(QPen(QColor(chrome.faint)))
            drawer(painter, chrome, 12, 16, self.width() - 24, THUMB_HEIGHT - 28)
        text_width = max(0, self.width() - 16)
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
                THUMB_HEIGHT + 2,
                tag_width,
                16,
                int(Qt.AlignRight | Qt.AlignVCenter),
                self._tag,
            )
        painter.setPen(QColor(chrome.text if self.isEnabled() else chrome.faint))
        title_font = QFont(self.font())
        title_font.setBold(True)
        title_font.setPixelSize(12)
        painter.setFont(title_font)
        title = QFontMetrics(title_font).elidedText(self._title, Qt.ElideRight, max(0, text_width - tag_width))
        painter.drawText(8, THUMB_HEIGHT + 2, text_width, 16, int(Qt.AlignLeft | Qt.AlignVCenter), title)
        painter.setPen(QColor(chrome.muted if self.isEnabled() else chrome.faint))
        caption = QFont(self.font())
        caption.setBold(False)
        caption.setPixelSize(11)
        painter.setFont(caption)
        description = QFontMetrics(caption).elidedText(self._description, Qt.ElideRight, text_width)
        painter.drawText(
            8,
            THUMB_HEIGHT + 18,
            text_width,
            16,
            int(Qt.AlignLeft | Qt.AlignVCenter),
            description,
        )
        painter.restore()
        pen = QPen(QColor(color))
        pen.setWidth(ring)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(outer, _CORNER_RADIUS, _CORNER_RADIUS)
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


def _draw_dialog_right(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    side = 34
    _draw_fields(painter, chrome, x, y, width - side - 8, height, 0)
    painter.fillRect(x + width - side, y, side, 14, QColor(chrome.accent))
    painter.drawRect(x + width - side, y + 20, side, 14)


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


def _draw_wizard(painter: QPainter, chrome: FormChrome, x: int, y: int, width: int, height: int) -> None:
    del chrome
    painter.drawRect(x, y, width, height - 22)
    button_y = y + height - 16
    painter.drawRect(x + 8, button_y, 34, 14)
    painter.drawRect(x + width - 42, button_y, 34, 14)


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
    "dialog_buttons_right": _draw_dialog_right,
    "widget": _draw_blank,
    "main_window": _draw_main_window,
    "dialog": _draw_blank,
    "wizard": _draw_wizard,
    "from_table": _draw_from_table,
    "adopt": _draw_adopt,
}
