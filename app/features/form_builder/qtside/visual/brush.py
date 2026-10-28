"""Brush popover, pattern list and gradient bar (UX-PED-083, UX-PED-084).

Picture (UX-PED-103) is a style segment plus ``set_brush_picture_page``. The
page itself lives with the picture editors.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from app.features.form_builder.engine.ui4.numfmt import parse_real
from app.features.form_builder.engine.ui4.values import (
    BrushValue,
    ColorValue,
    GradientStop,
    GradientValue,
    ResourcePixmap,
)
from app.features.form_builder.qtside.inspector.api import (
    EditorHost,
    EditorKey,
    Mixed,
    Registrar,
    RowValue,
    ValueSpec,
    Written,
)
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover
from app.features.form_builder.qtside.visual.color_picker import ColorPicker, Swatch
from app.features.form_builder.qtside.visual.common import (
    GRADIENT_REFUSAL,
    NUMBER_REFUSAL,
    RowSummary,
    begin_popover,
    color_hex,
    part_name,
    refit,
    refit_widget,
    token_color,
)
from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.qt.QtCore import QRect, QSize, Qt
from app.qt.QtGui import QBrush, QColor, QIcon, QImage, QPainter, QPen, QPixmap
from app.qt.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

OnBrush = Callable[[BrushValue], None]

_PATTERNS = (
    ("Dense 1 (darkest)", "Dense1Pattern"),
    ("Dense 2", "Dense2Pattern"),
    ("Dense 3", "Dense3Pattern"),
    ("Dense 4", "Dense4Pattern"),
    ("Dense 5", "Dense5Pattern"),
    ("Dense 6", "Dense6Pattern"),
    ("Dense 7 (lightest)", "Dense7Pattern"),
    ("Horizontal lines", "HorPattern"),
    ("Vertical lines", "VerPattern"),
    ("Cross", "CrossPattern"),
    ("Diagonal lines /", "FDiagPattern"),
    ("Diagonal lines \\", "BDiagPattern"),
    ("Diagonal cross", "DiagCrossPattern"),
)
_TYPES = (("Linear", "LinearGradient"), ("Radial", "RadialGradient"), ("Conical", "ConicalGradient"))
_SPREADS = (("Pad", "PadSpread"), ("Repeat", "RepeatSpread"), ("Reflect", "ReflectSpread"))
_FILLS = (
    ("Stretch to the widget", "ObjectBoundingMode"),
    ("Use pixel positions", "LogicalMode"),
    ("Stretch to the screen", "StretchToDeviceMode"),
)
_CORE_STYLES = (("none", "None"), ("solid", "Solid"), ("pattern", "Pattern"), ("gradient", "Gradient"))
_EXTRA_STYLES: List[Tuple[str, str]] = []
_LINEAR_FIELDS = (("startx", "Start X"), ("starty", "Start Y"), ("endx", "End X"), ("endy", "End Y"))
_RADIAL_FIELDS = (
    ("centralx", "Centre X"),
    ("centraly", "Centre Y"),
    ("radius", "Radius"),
    ("focalx", "Focal X"),
    ("focaly", "Focal Y"),
)
_CONICAL_FIELDS = (("centralx", "Centre X"), ("centraly", "Centre Y"), ("angle", "Angle"))
_GEOMETRY_DEFAULTS = {
    "LinearGradient": {"startx": 0.0, "starty": 0.0, "endx": 1.0, "endy": 0.0},
    "RadialGradient": {"centralx": 0.5, "centraly": 0.5, "radius": 0.5, "focalx": 0.5, "focaly": 0.5},
    "ConicalGradient": {"centralx": 0.5, "centraly": 0.5, "angle": 0.0},
}


def add_brush_style(key: str, label: str) -> None:
    """Register another Style segment. M4.3c uses this for Picture (UX-PED-103)."""
    if any(item[0] == key for item in _EXTRA_STYLES):
        return
    _EXTRA_STYLES.append((key, label))


# (parent, host, on_texture) -> widget with ``show_stored(ResourcePixmap | None)``.
_PICTURE_PAGE: Optional[Callable[..., QWidget]] = None


def set_brush_picture_page(factory: Callable[..., QWidget]) -> None:
    """Install the Picture page. The style segment alone has nowhere to put the picker."""
    global _PICTURE_PAGE
    _PICTURE_PAGE = factory


def brush_style_keys() -> Tuple[str, ...]:
    return tuple(key for key, _label in _CORE_STYLES + tuple(_EXTRA_STYLES))


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _modifier(name: str) -> object:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _focus(name: str) -> object:
    return getattr(getattr(Qt, "FocusPolicy", Qt), name)


def _brush_style(name: str) -> object:
    return getattr(getattr(Qt, "BrushStyle", Qt), name)


def _image_format(name: str) -> object:
    return getattr(getattr(QImage, "Format", QImage), name)


def _pattern_label(stored: str) -> str:
    for label, name in _PATTERNS:
        if name == stored:
            return label.split(" (", 1)[0]
    return stored


def brush_summary(brush: Optional[BrushValue], *, mixed: bool) -> str:
    if mixed:
        return "Mixed"
    if brush is None or _is_none(brush):
        return "No brush"
    if brush.gradient is not None:
        kind = {"RadialGradient": "Radial", "ConicalGradient": "Conical"}.get(brush.gradient.type or "", "Linear")
        count = len(brush.gradient.stops)
        return "%s gradient, %d colours" % (kind, count)
    if brush.texture is not None or brush.brushstyle == "TexturePattern":
        return "Picture"
    style = brush.brushstyle or ""
    if style and style not in ("NoBrush", "SolidPattern"):
        colour = color_hex(brush.color) if brush.color is not None else ""
        return "Pattern: %s, %s" % (_pattern_label(style), colour)
    colour = color_hex(brush.color) if brush.color is not None else color_hex(ColorValue(0, 0, 0))
    return "Solid %s" % colour


def _is_none(brush: BrushValue) -> bool:
    if brush.gradient is not None or brush.texture is not None or brush.color is not None:
        return False
    return brush.brushstyle in (None, "", "NoBrush")


def _style_of(brush: BrushValue) -> str:
    if brush.gradient is not None or (brush.brushstyle or "").endswith("GradientPattern"):
        return "gradient"
    if brush.texture is not None or brush.brushstyle == "TexturePattern":
        return "picture"
    style = brush.brushstyle or ""
    if style and style not in ("NoBrush", "SolidPattern"):
        return "pattern"
    if brush.color is not None or style == "SolidPattern":
        return "solid"
    return "none"


def _default_gradient() -> GradientValue:
    return GradientValue(
        type="LinearGradient",
        spread="PadSpread",
        coordinatemode="ObjectBoundingMode",
        startx=0.0,
        starty=0.0,
        endx=1.0,
        endy=0.0,
        stops=(GradientStop(0.0, ColorValue(0, 0, 0)), GradientStop(1.0, ColorValue(255, 255, 255))),
    )


def _mix(left: ColorValue, right: ColorValue, amount: float) -> ColorValue:
    def channel(a: int, b: int) -> int:
        return int(round(a + (b - a) * amount))

    alpha: Optional[int] = None
    if left.alpha is not None or right.alpha is not None:
        alpha = channel(255 if left.alpha is None else left.alpha, 255 if right.alpha is None else right.alpha)
    return ColorValue(channel(left.red, right.red), channel(left.green, right.green), channel(left.blue, right.blue), alpha)


def color_at(stops: Tuple[GradientStop, ...], position: float) -> ColorValue:
    if not stops:
        return ColorValue(0, 0, 0)
    ordered = tuple(sorted(stops, key=lambda stop: stop.position))
    if position <= ordered[0].position:
        return ordered[0].color
    if position >= ordered[-1].position:
        return ordered[-1].color
    for left, right in zip(ordered, ordered[1:]):
        span = right.position - left.position
        if left.position <= position <= right.position and span > 0:
            return _mix(left.color, right.color, (position - left.position) / span)
    return ordered[-1].color


def _show_number(value: Optional[float]) -> str:
    if value is None:
        return ""
    text = format(float(value), ".6f").rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


class GradientBar(QWidget):
    """The 24 px stop bar. Keys and drags edit the stops; the owner commits."""

    def __init__(
        self,
        parent: QWidget,
        on_change: Callable[[], None],
        on_refuse: Callable[[str], None],
        on_current: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.gradientBar")
        self.setAccessibleName(part_name("Gradient", "bar"))
        self.setFocusPolicy(_focus("StrongFocus"))  # type: ignore[arg-type]
        self.setFixedHeight(24)
        self.setMinimumWidth(0)
        self._on_change = on_change
        self._on_refuse = on_refuse
        self._on_current = on_current or (lambda: None)
        self._stops: List[GradientStop] = list(_default_gradient().stops)
        self._current = 0
        self._drag: Optional[int] = None
        self._press_y = 0
        self._moved = False
        self._chrome: Optional[FormChrome] = None

    def set_tokens(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        self.update()

    def set_stops(self, stops: Tuple[GradientStop, ...]) -> None:
        self._stops = list(stops) if stops else list(_default_gradient().stops)
        self._current = max(0, min(self._current, len(self._stops) - 1))
        self.update()

    def stops(self) -> Tuple[GradientStop, ...]:
        return tuple(self._stops)

    def current_color(self) -> ColorValue:
        return self._stops[self._current].color

    def set_current_color(self, color: ColorValue) -> None:
        stop = self._stops[self._current]
        self._stops[self._current] = GradientStop(stop.position, color)
        self.update()
        self._on_change()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = self.rect()
        gradient = self._qt_gradient(rect.width())
        painter.fillRect(rect, QBrush(gradient))
        chrome = self._chrome
        handle = token_color(chrome.fb.handle_border) if chrome is not None else QColor(0, 0, 0)
        current = token_color(chrome.fb.handle_current_border) if chrome is not None else QColor(0, 96, 192)
        width = chrome.fb.handle_border_px if chrome is not None else 1.5
        for index, stop in enumerate(self._stops):
            x = self._x_at(stop.position)
            pen = QPen(current if index == self._current else handle)
            pen.setWidthF(chrome.fb.handle_current_px if index == self._current and chrome is not None else width)
            painter.setPen(pen)
            painter.setBrush(QBrush(_qcolor(stop.color)))
            painter.drawEllipse(x - 6, rect.center().y() - 6, 12, 12)
        painter.end()

    def _qt_gradient(self, width: int) -> object:
        from app.qt.QtGui import QLinearGradient

        gradient = QLinearGradient(0, 0, max(1, width), 0)
        for stop in self._stops:
            gradient.setColorAt(max(0.0, min(1.0, stop.position)), _qcolor(stop.color))
        return gradient

    def mousePressEvent(self, event: object) -> None:  # noqa: N802
        self.setFocus()
        x, y = _event_pos(event)
        self._press_y = y
        self._moved = False
        hit = self._hit(x)
        self._drag = hit if hit >= 0 else None
        if hit >= 0:
            self._current = hit
            self.update()
            self._on_current()
        event.accept()  # type: ignore[attr-defined]

    def mouseMoveEvent(self, event: object) -> None:  # noqa: N802
        if self._drag is None:
            return
        self._moved = True
        x, _y = _event_pos(event)
        self._move_to(x)
        event.accept()  # type: ignore[attr-defined]

    def mouseReleaseEvent(self, event: object) -> None:  # noqa: N802
        x, y = _event_pos(event)
        if self._drag is not None and self._moved and (y < -24 or y > self.height() + 24):
            self._delete(refused_ok=True)
        elif self._drag is None:
            self._add_at(x)
        self._drag = None
        event.accept()  # type: ignore[attr-defined]

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        mods = event.modifiers()  # type: ignore[attr-defined]
        alt = bool(mods & _modifier("AltModifier"))
        shift = bool(mods & _modifier("ShiftModifier"))
        if key in (_key("Key_Left"), _key("Key_Right")) and not alt:
            self._select( -1 if key == _key("Key_Left") else 1)
        elif key in (_key("Key_Left"), _key("Key_Right")) and alt:
            step = 0.10 if shift else 0.01
            if key == _key("Key_Left"):
                step = -step
            self._nudge(step)
        elif key == _key("Key_Insert"):
            self._insert()
        elif key == _key("Key_Delete"):
            self._delete(refused_ok=False)
        else:
            super().keyPressEvent(event)  # type: ignore[arg-type]
            return
        event.accept()  # type: ignore[attr-defined]

    def _ordered(self) -> List[int]:
        return sorted(range(len(self._stops)), key=lambda index: (self._stops[index].position, index))

    def _select(self, delta: int) -> None:
        order = self._ordered()
        place = order.index(self._current)
        self._current = order[max(0, min(len(order) - 1, place + delta))]
        self.update()
        self._on_current()

    def _nudge(self, delta: float) -> None:
        stop = self._stops[self._current]
        position = max(0.0, min(1.0, stop.position + delta))
        self._stops[self._current] = GradientStop(position, stop.color)
        self.update()
        self._on_change()

    def _insert(self) -> None:
        order = self._ordered()
        place = order.index(self._current)
        current = self._stops[self._current]
        if place + 1 < len(order):
            other = self._stops[order[place + 1]].position
        else:
            other = 1.0
        if abs(other - current.position) < 0.001:
            return
        position = (current.position + other) / 2.0
        self._stops.append(GradientStop(position, color_at(tuple(self._stops), position)))
        self._current = len(self._stops) - 1
        self._on_refuse("")
        self.update()
        self._on_current()
        self._on_change()

    def _delete(self, *, refused_ok: bool) -> None:
        if len(self._stops) <= 2:
            self._on_refuse(GRADIENT_REFUSAL)
            return
        del self._stops[self._current]
        self._current = min(self._current, len(self._stops) - 1)
        self._on_refuse("")
        self.update()
        self._on_current()
        self._on_change()
        del refused_ok

    def _add_at(self, x: int) -> None:
        position = self._position_at(x)
        self._stops.append(GradientStop(position, color_at(tuple(self._stops), position)))
        self._current = len(self._stops) - 1
        self.update()
        self._on_current()
        self._on_change()

    def _move_to(self, x: int) -> None:
        if self._drag is None:
            return
        position = self._position_at(x)
        stop = self._stops[self._drag]
        self._stops[self._drag] = GradientStop(position, stop.color)
        self._current = self._drag
        self.update()
        self._on_change()

    def _x_at(self, position: float) -> int:
        inset = 8
        span = max(1, self.width() - 1 - 2 * inset)
        return inset + int(round(max(0.0, min(1.0, position)) * span))

    def _position_at(self, x: int) -> float:
        inset = 8
        span = max(1, self.width() - 1 - 2 * inset)
        return max(0.0, min(1.0, (x - inset) / float(span)))

    def _hit(self, x: int) -> int:
        found = -1
        best = 9
        for index, stop in enumerate(self._stops):
            sx = self._x_at(stop.position)
            distance = abs(sx - x)
            if distance <= 8 and distance < best:
                best = distance
                found = index
        return found


class BrushForm(QWidget):
    """Style, colour, pattern and gradient. Embedded by the brush row and by palettes."""

    def __init__(self, parent: QWidget, host: EditorHost, on_change: OnBrush) -> None:
        super().__init__(parent)
        self._host = host
        self._on_change = on_change
        self._brush = BrushValue(brushstyle="NoBrush")
        self._pushing = False
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(QLabel("Style", self))
        styles = QWidget(self)
        style_row = QHBoxLayout(styles)
        style_row.setContentsMargins(0, 0, 0, 0)
        self._group = QButtonGroup(styles)
        self._group.setExclusive(True)
        self._style_buttons: Dict[str, QToolButton] = {}
        for key, label in _CORE_STYLES + tuple(_EXTRA_STYLES):
            button = QToolButton(styles)
            button.setText(label)
            button.setCheckable(True)
            button.setProperty("fbSegment", "true")
            button.setAccessibleName(part_name("Brush", label.lower()))
            button.clicked.connect(lambda _checked=False, name=key: self._set_style(name))
            self._group.addButton(button)
            style_row.addWidget(button)
            self._style_buttons[key] = button
        layout.addWidget(styles)
        self._pattern = QComboBox(self)
        self._pattern.setObjectName("formBuilder.brushPattern")
        self._pattern.setAccessibleName(part_name("Brush", "pattern"))
        self._pattern.setIconSize(QSize(32, 16))
        self._pattern.activated.connect(self._pattern_changed)
        layout.addWidget(self._pattern)
        self._gradient_box = QWidget(self)
        gradient = QVBoxLayout(self._gradient_box)
        gradient.setContentsMargins(0, 0, 0, 0)
        self._type = self._combo("type", "Gradient", _TYPES)
        self._bar = GradientBar(self._gradient_box, self._gradient_changed, self._refuse, self._show_stop)
        self._spread = self._combo("spread", "Gradient", _SPREADS)
        self._fill = self._combo("fill", "Gradient", _FILLS)
        gradient.addWidget(self._labeled_combo("Type", self._type))
        gradient.addWidget(self._bar)
        self._refusal = QLabel(self._gradient_box)
        self._refusal.setObjectName("formBuilder.rowError")
        self._refusal.setStyleSheet("color: %s;" % self._host.chrome.error)
        self._refusal.hide()
        gradient.addWidget(self._refusal)
        gradient.addWidget(self._labeled_combo("Spread", self._spread))
        gradient.addWidget(self._labeled_combo("Fill", self._fill))
        more = QToolButton(self._gradient_box)
        more.setText("More \u25b8")
        more.setCheckable(True)
        more.setAccessibleName(part_name("Gradient", "more"))
        self._geometry = QWidget(self._gradient_box)
        self._geometry_layout = QVBoxLayout(self._geometry)
        self._geometry_layout.setContentsMargins(0, 0, 0, 0)
        self._fields: Dict[str, QLineEdit] = {}
        self._geometry.hide()
        more.toggled.connect(self._geometry.setVisible)
        more.toggled.connect(lambda _open: refit_widget(self))
        gradient.addWidget(more)
        gradient.addWidget(self._geometry)
        layout.addWidget(self._gradient_box)
        self._extra = QLabel(self)
        self._extra.setWordWrap(True)
        self._extra.hide()
        layout.addWidget(self._extra)
        self._picture: Optional[QWidget] = None
        if _PICTURE_PAGE is not None:
            self._picture = _PICTURE_PAGE(self, self._host, self._picture_chosen)
            layout.addWidget(self._picture)
        self._picker = ColorPicker(
            self,
            on_color=self._color_changed,
            on_invalid=self._host.invalid,
            row="Colour",
        )
        self._picker.set_tokens(self._host.chrome)
        layout.addWidget(self._picker)
        self._bar.set_tokens(self._host.chrome)
        self._apply_style_widgets()

    def _combo(self, part: str, row: str, options: Tuple[Tuple[str, str], ...]) -> QComboBox:
        combo = QComboBox(self)
        combo.setAccessibleName(part_name(row, part))
        combo.setObjectName("formBuilder.gradient" + part.capitalize())
        for label, stored in options:
            combo.addItem(label, stored)
        combo.activated.connect(lambda _index: self._gradient_changed())
        return combo

    def _labeled_combo(self, title: str, combo: QComboBox) -> QWidget:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(title, row))
        layout.addWidget(combo, 1)
        return row

    def set_brush(self, brush: BrushValue) -> None:
        self._brush = brush
        self._pushing = True
        style = _style_of(brush)
        for key, button in self._style_buttons.items():
            button.setChecked(key == style)
        if brush.brushstyle in dict((name, label) for label, name in _PATTERNS):
            self._ensure_patterns()
            index = self._pattern.findData(brush.brushstyle)
            if index >= 0:
                self._pattern.setCurrentIndex(index)
        gradient = brush.gradient if brush.gradient is not None else _default_gradient()
        self._select(self._type, gradient.type or "LinearGradient")
        self._select(self._spread, gradient.spread or "PadSpread")
        self._select(self._fill, gradient.coordinatemode or "ObjectBoundingMode")
        self._bar.set_stops(gradient.stops or _default_gradient().stops)
        self._ensure_geometry(gradient)
        color = brush.color
        if style == "gradient":
            color = self._bar.current_color()
        self._picker.set_color(color or ColorValue(0, 0, 0))
        if self._picture is not None and hasattr(self._picture, "show_stored"):
            self._picture.show_stored(brush.texture)  # type: ignore[attr-defined]
        self._apply_style_widgets()
        self._pushing = False

    def brush(self) -> BrushValue:
        return self._brush

    def _set_style(self, key: str) -> None:
        if self._pushing:
            return
        if key == "none":
            self._brush = BrushValue(brushstyle="NoBrush")
        elif key == "solid":
            color = self._brush.color or ColorValue(0, 0, 0)
            self._brush = BrushValue(brushstyle="SolidPattern", color=color)
        elif key == "pattern":
            self._ensure_patterns()
            color = self._brush.color or ColorValue(0, 0, 0)
            stored = self._pattern.currentData() or "Dense4Pattern"
            self._brush = BrushValue(brushstyle=str(stored), color=color)
        elif key == "gradient":
            gradient = self._brush.gradient or _default_gradient()
            self._brush = BrushValue(brushstyle=_gradient_brushstyle(gradient), gradient=gradient)
        elif key == "picture":
            self._brush = BrushValue(brushstyle="TexturePattern", texture=self._brush.texture)
        else:
            self._extra.setText("Picture uses the picture picker.")
            self._apply_style_widgets()
            refit_widget(self)
            return
        self._apply_style_widgets()
        # Another style shows other parts; the popover fits them again.
        refit_widget(self)
        self._emit()

    def _apply_style_widgets(self) -> None:
        style = _style_of(self._brush)
        self._pattern.setVisible(style == "pattern")
        self._gradient_box.setVisible(style == "gradient")
        self._picker.setVisible(style != "picture")
        if self._picture is not None:
            self._picture.setVisible(style == "picture")
        self._extra.setVisible(style == "picture" and self._picture is None)

    def _ensure_patterns(self) -> None:
        if self._pattern.count():
            return
        for label, stored in _PATTERNS:
            self._pattern.addItem(QIcon(_pattern_icon(stored)), label, stored)

    def _pattern_changed(self, _index: int) -> None:
        if self._pushing:
            return
        self._ensure_patterns()
        color = self._brush.color or ColorValue(0, 0, 0)
        self._brush = BrushValue(brushstyle=str(self._pattern.currentData()), color=color)
        self._emit()

    def _show_stop(self) -> None:
        self._pushing = True
        self._picker.set_color(self._bar.current_color())
        self._pushing = False

    def _color_changed(self, color: ColorValue) -> None:
        if self._pushing:
            return
        style = _style_of(self._brush)
        if style == "gradient":
            self._bar.set_current_color(color)
            return
        if style == "pattern":
            self._brush = BrushValue(brushstyle=str(self._pattern.currentData() or self._brush.brushstyle), color=color)
        else:
            self._brush = BrushValue(brushstyle="SolidPattern", color=color)
        self._emit()

    def _gradient_changed(self) -> None:
        if self._pushing:
            return
        previous = self._brush.gradient or _default_gradient()
        gradient = self._read_gradient(previous)
        self._brush = BrushValue(brushstyle=_gradient_brushstyle(gradient), gradient=gradient)
        self._ensure_geometry(gradient)
        self._emit()

    def _read_gradient(self, previous: GradientValue) -> GradientValue:
        values = {name: getattr(previous, name) for name in (
            "startx", "starty", "endx", "endy", "centralx", "centraly", "focalx", "focaly", "radius", "angle"
        )}
        for name, field in self._fields.items():
            text = field.text().strip()
            if not text:
                values[name] = None
                continue
            try:
                values[name] = parse_real(text)
            except ValueError:
                self._refuse(NUMBER_REFUSAL)
                values[name] = getattr(previous, name)
        kind = str(self._type.currentData() or "LinearGradient")
        # Qt writes only the geometry of the gradient's type. A new type keeps
        # the fields it shares with the old one (a centre) and starts the rest
        # from its own defaults.
        own = _GEOMETRY_DEFAULTS.get(kind, _GEOMETRY_DEFAULTS["LinearGradient"])
        before = _GEOMETRY_DEFAULTS.get(previous.type or "LinearGradient", _GEOMETRY_DEFAULTS["LinearGradient"])
        if kind != (previous.type or "LinearGradient"):
            values = {name: (value if name in before else None) for name, value in values.items()}
        for name in values:
            if name not in own:
                values[name] = None
            elif values[name] is None:
                values[name] = own[name]
        # Stops are written in position order, as Qt keeps them, so the same
        # stops are the same bytes whatever order they were added in.
        stops = tuple(sorted(self._bar.stops(), key=lambda stop: stop.position))
        return GradientValue(
            type=kind,
            spread=str(self._spread.currentData() or "PadSpread"),
            coordinatemode=str(self._fill.currentData() or "ObjectBoundingMode"),
            stops=stops,
            **values,
        )

    def _ensure_geometry(self, gradient: GradientValue) -> None:
        kind = gradient.type or "LinearGradient"
        fields = {"RadialGradient": _RADIAL_FIELDS, "ConicalGradient": _CONICAL_FIELDS}.get(kind, _LINEAR_FIELDS)
        if tuple(self._fields) == tuple(name for name, _label in fields):
            return
        self._rebuild_geometry(gradient)

    def _rebuild_geometry(self, gradient: GradientValue) -> None:
        kind = gradient.type or "LinearGradient"
        fields = {"RadialGradient": _RADIAL_FIELDS, "ConicalGradient": _CONICAL_FIELDS}.get(kind, _LINEAR_FIELDS)
        existing = {name: field.text() for name, field in self._fields.items()}
        while self._geometry_layout.count():
            item = self._geometry_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._fields = {}
        for name, label in fields:
            row = QWidget(self._geometry)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            field = QLineEdit(row)
            field.setAccessibleName(part_name("Gradient", label.lower()))
            field.setProperty("fbEnterStays", True)
            shown = existing.get(name)
            field.setText(shown if shown is not None else _show_number(getattr(gradient, name)))
            field.editingFinished.connect(self._gradient_changed)
            layout.addWidget(QLabel(label, row))
            layout.addWidget(field, 1)
            self._geometry_layout.addWidget(row)
            self._fields[name] = field

    def _refuse(self, message: str) -> None:
        if not message:
            self._refusal.hide()
            return
        self._refusal.setText(message)
        self._refusal.show()
        self._host.invalid(message)

    def _picture_chosen(self, texture: Optional[ResourcePixmap]) -> None:
        if self._pushing:
            return
        self._brush = BrushValue(brushstyle="TexturePattern", texture=texture)
        self._apply_style_widgets()
        self._emit()

    def _emit(self) -> None:
        if not self._pushing:
            self._on_change(self._brush)

    def _select(self, combo: QComboBox, stored: str) -> None:
        index = combo.findData(stored)
        combo.setCurrentIndex(0 if index < 0 else index)


class BrushEditor:
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = QWidget(parent)
        layout = QHBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._preview = Swatch(self._root, 16)
        self._preview.set_tokens(host.chrome)
        self._summary = RowSummary(host.label or "Brush", self._root)
        self._summary.set_opener(self._open)
        layout.addWidget(self._preview)
        layout.addWidget(self._summary, 1)
        self._brush = BrushValue(brushstyle="NoBrush")
        self._written = False
        self._popover: Optional[RowPopover] = None
        self._form: Optional[BrushForm] = None

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        mixed = isinstance(value, Mixed)
        self._written = isinstance(value, Written) and isinstance(value.value, BrushValue)
        self._brush = value.value if self._written else BrushValue(brushstyle="NoBrush")  # type: ignore[assignment]
        self._summary.set_summary(brush_summary(self._brush if self._written else None, mixed=mixed))
        self._summary.show_state(value, self._host.chrome.faint)
        self._paint_preview(self._brush if self._written else None, mixed=mixed)
        if (
            self._form is not None
            and self._popover is not None
            and not self._popover.closed
            and self._form.brush() != self._brush
        ):
            self._form.set_brush(self._brush)

    def _open(self) -> None:
        if self._popover is not None and not self._popover.closed:
            return
        label = self._host.label or "brush"
        popover = begin_popover(
            self._host,
            self._summary,
            "Change " + label[0].lower() + label[1:],
            large=True,
        )
        form = BrushForm(popover, self._host, self._live)
        form.set_brush(self._brush if self._written else BrushValue(brushstyle="NoBrush"))
        popover.body().addWidget(form)
        popover.set_reset(self._host.reset if self._written else None)
        self._popover = popover
        self._form = form
        popover.open_popover()
        refit(popover)

    def _live(self, brush: BrushValue) -> None:
        popover = self._popover
        if popover is None:
            return
        self._brush = brush
        self._written = True
        self._host.commit(brush, session=popover.session)
        self._summary.set_summary(brush_summary(brush, mixed=False))
        self._paint_preview(brush, mixed=False)
        popover.set_reset(self._host.reset)

    def _paint_preview(self, brush: Optional[BrushValue], *, mixed: bool) -> None:
        if brush is None or mixed or _is_none(brush):
            self._preview.set_color(None, hollow=not mixed, mixed=mixed)
            return
        fill = preview_brush(brush, 16)
        if fill is None:
            self._preview.set_color(brush.color or ColorValue(0, 0, 0))
            return
        self._preview.set_fill(fill)


def preview_brush(brush: BrushValue, side: int) -> Optional[QBrush]:
    """A QBrush that draws a pattern or gradient in a ``side`` px square, or None for solid."""
    style = _style_of(brush)
    if style == "picture":
        path = brush.texture.path if brush.texture is not None else ""
        pixmap = QPixmap(path) if path else QPixmap()
        if pixmap.isNull():
            return QBrush()
        return QBrush(pixmap)
    if style == "pattern":
        color = _qcolor(brush.color or ColorValue(0, 0, 0))
        return QBrush(color, _brush_style(brush.brushstyle or "Dense4Pattern"))  # type: ignore[arg-type]
    if style == "gradient" and brush.gradient is not None:
        from app.qt.QtGui import QConicalGradient, QLinearGradient, QRadialGradient

        gradient = brush.gradient
        kind = gradient.type or "LinearGradient"
        if kind == "RadialGradient":
            qt_gradient: object = QRadialGradient(side / 2.0, side / 2.0, side / 2.0)
        elif kind == "ConicalGradient":
            qt_gradient = QConicalGradient(side / 2.0, side / 2.0, gradient.angle or 0.0)
        else:
            qt_gradient = QLinearGradient(0, 0, side, 0)
        for stop in gradient.stops:
            qt_gradient.setColorAt(max(0.0, min(1.0, stop.position)), _qcolor(stop.color))  # type: ignore[attr-defined]
        return QBrush(qt_gradient)  # type: ignore[arg-type]
    return None


def _gradient_brushstyle(gradient: GradientValue) -> str:
    return {"RadialGradient": "RadialGradientPattern", "ConicalGradient": "ConicalGradientPattern"}.get(
        gradient.type or "", "LinearGradientPattern"
    )


def _pattern_icon(stored: str) -> QPixmap:
    image = QImage(32, 16, _image_format("Format_ARGB32"))  # type: ignore[arg-type]
    image.fill(QColor(255, 255, 255))
    painter = QPainter(image)
    painter.fillRect(QRect(0, 0, 32, 16), QBrush(QColor(0, 0, 0), _brush_style(stored)))  # type: ignore[arg-type]
    painter.end()
    return QPixmap.fromImage(image)


def _qcolor(color: ColorValue) -> QColor:
    if color.alpha is None:
        return QColor(color.red, color.green, color.blue)
    return QColor(color.red, color.green, color.blue, color.alpha)


def _event_pos(event: object) -> Tuple[int, int]:
    pos = event.position() if hasattr(event, "position") else event.pos()  # type: ignore[attr-defined]
    return int(pos.x()), int(pos.y())


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(BrushValue.ELEMENT), BrushEditor, baseline=False)
