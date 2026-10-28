"""The colour picker (UX-PED-081) and the 16 px swatch (UX-PED-082). Not registered."""

from __future__ import annotations

from typing import Callable, Optional

from app.features.form_builder.engine.ui4.values import ColorValue
from app.features.form_builder.qtside.visual.recent import active_store
from app.features.form_builder.qtside.visual.common import (
    COLOUR_REFUSAL,
    alpha_percent,
    color_hex,
    parse_color_hex,
    part_name,
    percent_alpha,
    refit_widget,
    square_size,
    token_color,
)
from app.features.form_builder.qtside.theme.chrome import ChromeTokens, FormChrome
from app.qt.QtCore import QPoint, QRect, Qt
from app.qt.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPen
from app.qt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

OnColor = Callable[[ColorValue], None]
OnText = Callable[[str], None]


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _modifier(name: str) -> object:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _focus(name: str) -> object:
    return getattr(getattr(Qt, "FocusPolicy", Qt), name)


def _button(name: str) -> object:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


class Swatch(QWidget):
    """A 16 px swatch: checker under transparency, a 1 px border, hollow when unset."""

    def __init__(self, parent: Optional[QWidget] = None, side: int = 16) -> None:
        super().__init__(parent)
        self.setFixedSize(side, side)
        self._color: Optional[ColorValue] = None
        self._hollow = True
        self._mixed = False
        self._tokens: Optional[ChromeTokens] = None
        self._border = QColor(0, 0, 0)
        self._checker_a = QColor(255, 255, 255)
        self._checker_b = QColor(211, 216, 223)
        self._fill: Optional[QBrush] = None

    def set_tokens(self, chrome: FormChrome) -> None:
        tokens = chrome.fb
        self._tokens = tokens
        self._border = token_color(tokens.swatch_border)
        self._checker_a = token_color(tokens.checker_a)
        self._checker_b = token_color(tokens.checker_b)
        self.update()

    def set_color(self, color: Optional[ColorValue], *, hollow: bool = False, mixed: bool = False) -> None:
        self._color = color
        self._fill = None
        self._hollow = hollow
        self._mixed = mixed
        self.update()

    def set_fill(self, fill: Optional[QBrush]) -> None:
        """Paint a pattern or gradient brush instead of a flat colour (UX-PED-083)."""
        self._fill = fill
        self._hollow = fill is None
        self._mixed = False
        self.update()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = self.rect().adjusted(0, 0, -1, -1)
        if self._fill is not None:
            _paint_checker(painter, self.rect(), self._checker_a, self._checker_b)
            painter.fillRect(self.rect(), self._fill)
        if not self._hollow and self._color is not None and _has_alpha(self._color):
            _paint_checker(painter, self.rect(), self._checker_a, self._checker_b)
        if not self._hollow and self._color is not None:
            painter.fillRect(self.rect(), _qcolor(self._color))
        painter.setPen(QPen(self._border, 1))
        painter.drawRect(rect)
        if self._mixed:
            painter.drawLine(rect.topLeft(), rect.bottomRight())
        painter.end()


def _image_format(name: str) -> object:
    return getattr(getattr(QImage, "Format", QImage), name)


class _Plane(QWidget):
    """A painted plane that reports drags and arrow keys. The image is cached."""

    def __init__(self, parent: QWidget, name: str, on_point: Callable[[int, int, bool, bool], None]) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self.setFocusPolicy(_focus("StrongFocus"))  # type: ignore[arg-type]
        self._on_point = on_point
        self._image = QImage()
        self._dragging = False

    def set_image(self, image: QImage) -> None:
        self._image = image
        self.setFixedSize(image.width(), image.height())
        self.update()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        self._draw(painter)
        painter.end()

    def _draw(self, painter: QPainter) -> None:
        if not self._image.isNull():
            painter.drawImage(0, 0, self._image)

    def mousePressEvent(self, event: object) -> None:  # noqa: N802
        if getattr(event, "button", lambda: None)() != _button("LeftButton"):
            return
        self._dragging = True
        self.setFocus()
        self._emit(event, False, False)
        event.accept()  # type: ignore[attr-defined]

    def mouseMoveEvent(self, event: object) -> None:  # noqa: N802
        if not self._dragging:
            return
        self._emit(event, False, False)
        event.accept()  # type: ignore[attr-defined]

    def mouseReleaseEvent(self, event: object) -> None:  # noqa: N802
        if not self._dragging:
            return
        self._dragging = False
        self._emit(event, True, False)
        event.accept()  # type: ignore[attr-defined]

    def _emit(self, event: object, released: bool, from_keys: bool) -> None:
        pos = event.position() if hasattr(event, "position") else event.pos()  # type: ignore[attr-defined]
        x = int(pos.x()) if not isinstance(pos, QPoint) else pos.x()
        y = int(pos.y()) if not isinstance(pos, QPoint) else pos.y()
        self._on_point(
            max(0, min(self.width() - 1, x)),
            max(0, min(self.height() - 1, y)),
            released,
            from_keys,
        )


class _Square(_Plane):
    """The saturation/value plane. The ring is drawn on top of a cached image."""

    def __init__(self, parent: QWidget, name: str, on_point: Callable[[int, int, bool, bool], None]) -> None:
        super().__init__(parent, name, on_point)
        self._handle_at: Optional[tuple] = None
        self._handle_color = QColor(255, 255, 255)
        self._handle_px = 1.5

    def set_handle(self, x: int, y: int, color: QColor, px: float) -> None:
        self._handle_at = (x, y)
        self._handle_color = color
        self._handle_px = px
        self.update()

    def _draw(self, painter: QPainter) -> None:
        super()._draw(painter)
        if self._handle_at is None:
            return
        pen = QPen(self._handle_color)
        pen.setWidthF(self._handle_px)
        painter.setPen(pen)
        painter.setBrush(QBrush())
        painter.drawEllipse(QPoint(self._handle_at[0], self._handle_at[1]), 6, 6)

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        step = 10 if event.modifiers() & _modifier("ShiftModifier") else 1  # type: ignore[attr-defined]
        dx = dy = 0
        if key == _key("Key_Left"):
            dx = -step
        elif key == _key("Key_Right"):
            dx = step
        elif key == _key("Key_Up"):
            dy = -step
        elif key == _key("Key_Down"):
            dy = step
        else:
            super().keyPressEvent(event)  # type: ignore[arg-type]
            return
        self._on_point(dx, dy, False, True)
        event.accept()  # type: ignore[attr-defined]


class _Strip(_Plane):
    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        step = 10 if event.modifiers() & _modifier("ShiftModifier") else 1  # type: ignore[attr-defined]
        if key == _key("Key_Left"):
            self._on_point(-step, 0, False, True)
        elif key == _key("Key_Right"):
            self._on_point(step, 0, False, True)
        else:
            super().keyPressEvent(event)  # type: ignore[arg-type]
            return
        event.accept()  # type: ignore[attr-defined]


class ColorPicker(QWidget):
    """Saturation square, hue strip, optional alpha strip, hex, more, and recents.

    ``on_color`` fires for a live change. ``on_done`` fires when Enter in the hex
    field should close the popover (the colour row). Embedded pickers leave it empty.
    """

    def __init__(
        self,
        parent: QWidget,
        *,
        on_color: OnColor,
        on_invalid: OnText,
        on_done: Optional[Callable[[], None]] = None,
        row: str = "Colour",
    ) -> None:
        super().__init__(parent)
        self._on_color = on_color
        self._on_invalid = on_invalid
        self._on_done = on_done
        self._row = row
        self._hue = 140
        self._sat = 200
        self._val = 160
        self._alpha: Optional[int] = None
        self._show_alpha = False
        self._square_w = 200
        self._square_h = 140
        self._chrome: Optional[FormChrome] = None
        self._checker_a = QColor(255, 255, 255)
        self._checker_b = QColor(211, 216, 223)
        self._handle = QColor(255, 255, 255)
        self._handle_px = 1.5
        self._pushing = False
        self._base_key: Optional[tuple] = None
        self._hue_key: Optional[int] = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._square = _Square(self, "formBuilder.colorSquare", self._square_point)
        self._square.setAccessibleName(part_name(self._row, "square"))
        self._hue_strip = _Strip(self, "formBuilder.colorHue", self._hue_point)
        self._hue_strip.setAccessibleName(part_name(self._row, "hue"))
        self._alpha_strip = _Strip(self, "formBuilder.colorAlpha", self._alpha_point)
        self._alpha_strip.setAccessibleName(part_name(self._row, "alpha"))
        layout.addWidget(self._square)
        layout.addWidget(self._hue_strip)
        layout.addWidget(self._alpha_strip)
        hex_row = QWidget(self)
        hex_layout = QHBoxLayout(hex_row)
        hex_layout.setContentsMargins(0, 0, 0, 0)
        hex_label = QLabel("Hex", hex_row)
        self._hex = QLineEdit(hex_row)
        self._hex.setObjectName("formBuilder.colorHex")
        self._hex.setAccessibleName(part_name(self._row, "hex"))
        self._hex.setProperty("fbEnterStays", True)
        self._hex.returnPressed.connect(self._commit_hex)
        hex_layout.addWidget(hex_label)
        hex_layout.addWidget(self._hex, 1)
        layout.addWidget(hex_row)
        self._more = QToolButton(self)
        self._more.setText("More \u25b8")
        self._more.setCheckable(True)
        self._more.setAccessibleName(part_name(self._row, "more"))
        self._more.toggled.connect(self._toggle_more)
        layout.addWidget(self._more, 0)
        self._more_box = QWidget(self)
        more_layout = QHBoxLayout(self._more_box)
        more_layout.setContentsMargins(0, 0, 0, 0)
        self._red = self._channel("red", 255)
        self._green = self._channel("green", 255)
        self._blue = self._channel("blue", 255)
        self._alpha_spin = self._channel("alpha percent", 100)
        for label, spin in (
            ("Red", self._red),
            ("Green", self._green),
            ("Blue", self._blue),
            ("Alpha", self._alpha_spin),
        ):
            more_layout.addWidget(QLabel(label, self._more_box))
            more_layout.addWidget(spin)
        self._more_box.hide()
        layout.addWidget(self._more_box)
        self._recent_row = QWidget(self)
        self._recent_row.setObjectName("formBuilder.colorRecent")
        self._recent_layout = QHBoxLayout(self._recent_row)
        self._recent_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_layout.setSpacing(4)
        layout.addWidget(self._recent_row)
        self._paint_planes()
        self._sync_fields()
        self._reload_recent()

    def _channel(self, part: str, upper: int) -> QSpinBox:
        spin = QSpinBox(self)
        spin.setRange(0, upper)
        spin.setAccessibleName(part_name(self._row, part))
        spin.setProperty("fbEnterStays", True)
        spin.valueChanged.connect(self._channels_edited)
        return spin

    def set_tokens(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        tokens = chrome.fb
        self._checker_a = token_color(tokens.checker_a)
        self._checker_b = token_color(tokens.checker_b)
        self._handle = token_color(tokens.handle_border)
        self._handle_px = tokens.handle_border_px
        self._paint_planes()

    def set_square(self, width: int, height: int) -> None:
        if (width, height) == (self._square_w, self._square_h):
            return
        self._square_w = width
        self._square_h = height
        self._paint_planes()

    def fit_width(self, popover_width: int) -> None:
        width, height = square_size(popover_width)
        self.set_square(width, height)

    def set_color(self, color: Optional[ColorValue]) -> None:
        if color is None:
            color = ColorValue(0, 0, 0)
        qcolor = _qcolor(color)
        hue = qcolor.hue()
        if hue >= 0:
            self._hue = hue
        self._sat = qcolor.saturation()
        self._val = qcolor.value()
        self._alpha = color.alpha
        self._show_alpha = color.alpha is not None
        self._alpha_strip.setVisible(self._show_alpha)
        self._paint_planes()
        self._sync_fields()

    def color(self) -> ColorValue:
        qcolor = QColor.fromHsv(self._hue % 360, self._sat, self._val)
        return ColorValue(qcolor.red(), qcolor.green(), qcolor.blue(), self._alpha)

    def _toggle_more(self, open_: bool) -> None:
        self._more_box.setVisible(open_)
        refit_widget(self)

    def _square_point(self, x: int, y: int, released: bool, from_keys: bool) -> None:
        if from_keys:
            self._sat = max(0, min(255, self._sat + x))
            self._val = max(0, min(255, self._val - y))
        else:
            self._sat = int(round(x * 255 / max(1, self._square_w - 1)))
            self._val = int(round((self._square_h - 1 - y) * 255 / max(1, self._square_h - 1)))
        self._paint_handle_only()
        self._emit(released)

    def _hue_point(self, x: int, _y: int, released: bool, from_keys: bool) -> None:
        if from_keys:
            self._hue = (self._hue + x) % 360
        else:
            width = max(1, self._hue_strip.width() - 1)
            self._hue = int(round(max(0, x) * 359 / width))
        self._paint_planes()
        self._emit(released)

    def _alpha_point(self, x: int, _y: int, released: bool, from_keys: bool) -> None:
        width = max(1, self._alpha_strip.width() - 1)
        if from_keys:
            current = 255 if self._alpha is None else self._alpha
            self._alpha = max(0, min(255, current + x))
        else:
            self._alpha = int(round(max(0, x) * 255 / width))
        self._show_alpha = True
        self._alpha_strip.setVisible(True)
        self._paint_alpha()
        self._emit(released)

    def _emit(self, released: bool) -> None:
        self._sync_fields()
        self._on_invalid("")
        self._on_color(self.color())
        if released:
            active_store().note(color_hex(self.color()))
            self._reload_recent()

    def _commit_hex(self) -> None:
        try:
            color = parse_color_hex(self._hex.text())
        except ValueError:
            self._on_invalid(COLOUR_REFUSAL)
            return
        self._on_invalid("")
        self.set_color(color)
        self._on_color(self.color())
        active_store().note(color_hex(self.color()))
        self._reload_recent()
        if self._on_done is not None:
            self._on_done()

    def _channels_edited(self, _value: int) -> None:
        if self._pushing:
            return
        self._alpha = percent_alpha(self._alpha_spin.value())
        self._show_alpha = True
        self._alpha_strip.setVisible(True)
        qcolor = QColor(self._red.value(), self._green.value(), self._blue.value())
        hue = qcolor.hue()
        if hue >= 0:
            self._hue = hue
        self._sat = qcolor.saturation()
        self._val = qcolor.value()
        self._paint_planes()
        self._hex.setText(color_hex(self.color()))
        self._on_invalid("")
        self._on_color(self.color())

    def _sync_fields(self) -> None:
        color = self.color()
        self._pushing = True
        self._hex.setText(color_hex(color))
        self._red.setValue(color.red)
        self._green.setValue(color.green)
        self._blue.setValue(color.blue)
        shown = alpha_percent(color)
        self._alpha_spin.setValue(100 if shown is None else shown)
        self._pushing = False

    def _reload_recent(self) -> None:
        while self._recent_layout.count():
            item = self._recent_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        recent = active_store().recent()
        for index, text in enumerate(recent):
            try:
                color = parse_color_hex(text)
            except ValueError:
                continue
            swatch = _Recent(self._recent_row, color, lambda colour=color: self._pick_recent(colour))
            swatch.setObjectName("formBuilder.colorRecentSwatch")
            swatch.setAccessibleName(part_name(self._row, "recent %d" % (index + 1)))
            swatch.setToolTip(text)
            if self._chrome is not None:
                swatch.set_tokens(self._chrome)
            self._recent_layout.addWidget(swatch)
        self._recent_layout.addStretch(1)

    def _pick_recent(self, color: ColorValue) -> None:
        self.set_color(color)
        self._on_color(self.color())
        active_store().note(color_hex(self.color()))
        self._reload_recent()

    def _paint_planes(self) -> None:
        self._paint_square()
        self._paint_hue()
        self._paint_alpha()

    def _paint_handle_only(self) -> None:
        self._place_handle()

    def _place_handle(self) -> None:
        width, height = self._square_w, self._square_h
        handle_x = int(round(self._sat * (width - 1) / 255))
        handle_y = int(round((255 - self._val) * (height - 1) / 255))
        self._square.set_handle(handle_x, handle_y, self._handle, self._handle_px)

    def _paint_square(self) -> None:
        key = (self._square_w, self._square_h, self._hue % 360)
        if key != self._base_key:
            self._base_key = key
            self._square.set_image(_sv_image(self._square_w, self._square_h, self._hue % 360))
        self._place_handle()

    def _paint_hue(self) -> None:
        if self._hue_key == self._square_w:
            return
        self._hue_key = self._square_w
        self._hue_strip.set_image(_hue_image(self._square_w))

    def _paint_alpha(self) -> None:
        if not self._show_alpha:
            return
        width = self._square_w
        image = QImage(width, 12, _image_format("Format_ARGB32"))  # type: ignore[arg-type]
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        _paint_checker(painter, QRect(0, 0, width, 12), self._checker_a, self._checker_b)
        qcolor = QColor.fromHsv(self._hue % 360, self._sat, self._val)
        for x in range(width):
            alpha = int(round(x * 255 / max(1, width - 1)))
            column = QColor(qcolor)
            column.setAlpha(alpha)
            painter.fillRect(x, 0, 1, 12, column)
        painter.end()
        self._alpha_strip.set_image(image)


def _sv_image(width: int, height: int, hue: int) -> QImage:
    """Saturation across, value down. One hue fill plus two gradients, not a pixel loop."""
    image = QImage(width, height, _image_format("Format_RGB32"))  # type: ignore[arg-type]
    painter = QPainter(image)
    painter.fillRect(0, 0, width, height, QColor.fromHsv(hue % 360, 255, 255))
    fade = QLinearGradient(0, 0, width, 0)
    fade.setColorAt(0.0, QColor(255, 255, 255))
    fade.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillRect(0, 0, width, height, fade)
    shade = QLinearGradient(0, 0, 0, height)
    shade.setColorAt(0.0, QColor(0, 0, 0, 0))
    shade.setColorAt(1.0, QColor(0, 0, 0))
    painter.fillRect(0, 0, width, height, shade)
    painter.end()
    return image


def _hue_image(width: int) -> QImage:
    image = QImage(width, 12, _image_format("Format_RGB32"))  # type: ignore[arg-type]
    painter = QPainter(image)
    strip = QLinearGradient(0, 0, width, 0)
    stops = (0, 60, 120, 180, 240, 300, 359)
    for hue in stops:
        strip.setColorAt(hue / 359.0, QColor.fromHsv(hue, 255, 255))
    painter.fillRect(0, 0, width, 12, strip)
    painter.end()
    return image


def colour_summary(color: Optional[ColorValue], *, mixed: bool, unset: bool) -> str:
    if mixed:
        return "Mixed"
    if unset or color is None:
        return "Default"
    percent = alpha_percent(color)
    text = color_hex(color)
    if percent is None:
        return text
    return "%s %d %%" % (text, percent)


def _has_alpha(color: ColorValue) -> bool:
    return color.alpha is not None and color.alpha < 255


def _qcolor(color: ColorValue) -> QColor:
    if color.alpha is None:
        return QColor(color.red, color.green, color.blue)
    return QColor(color.red, color.green, color.blue, color.alpha)


def _paint_checker(painter: QPainter, rect: QRect, first: QColor, second: QColor) -> None:
    painter.fillRect(rect, first)
    cell = 4
    y = rect.top()
    row = 0
    while y < rect.bottom():
        x = rect.left()
        column = 0
        while x < rect.right():
            if (row + column) % 2 == 1:
                painter.fillRect(x, y, cell, cell, second)
            x += cell
            column += 1
        y += cell
        row += 1


class _Recent(Swatch):
    """One recent-colour cell. Enter and a click both pick it."""

    def __init__(self, parent: QWidget, color: ColorValue, on_click: Callable[[], None]) -> None:
        super().__init__(parent, 16)
        self.set_color(color)
        self._on_click = on_click
        self.setFocusPolicy(_focus("StrongFocus"))  # type: ignore[arg-type]

    def mousePressEvent(self, event: object) -> None:  # noqa: N802
        self._on_click()
        event.accept()  # type: ignore[attr-defined]

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        if event.key() in (_key("Key_Return"), _key("Key_Enter"), _key("Key_Space")):  # type: ignore[attr-defined]
            self._on_click()
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]
