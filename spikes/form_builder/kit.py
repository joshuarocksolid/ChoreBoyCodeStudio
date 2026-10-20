"""Small chrome components built from the design tokens.

Custom painting where QSS cannot do the job: segmented controls, toasts,
thumbnails, empty states. Everything reads `theme.current()` at paint time,
so a theme switch only needs a repaint.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QColor, QFont, QFontMetrics, QIntValidator, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from spikes.form_builder.icons import icon, paint_glyph
from spikes.form_builder.theme import current


def qcolor(value: str, alpha: int = 255) -> QColor:
    color = QColor(value)
    color.setAlpha(alpha)
    return color


def overline(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("Overline")
    return label


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def hairline(vertical: bool = False) -> QFrame:
    line = QFrame()
    line.setObjectName("VHairline" if vertical else "Hairline")
    return line


def kbd(text: str) -> QLabel:
    key = QLabel(text)
    key.setObjectName("Kbd")
    return key


def paint_shadow(painter: QPainter, rect: QRectF, radius: float, strength: int = 18, spread: int = 6) -> None:
    """A soft painted shadow, drawn as stroked rings so a large page costs almost nothing."""
    painter.save()
    painter.setBrush(Qt.NoBrush)
    for step in range(1, spread + 1):
        alpha = max(1, int(strength * (1 - step / (spread + 1)) / 2))
        painter.setPen(QPen(QColor(15, 20, 35, alpha), 1.0))
        grown = rect.adjusted(-step + 0.5, -step + 2.5, step - 0.5, step + 1.5)
        painter.drawRoundedRect(grown, radius + step, radius + step)
    painter.restore()


class IconButton(QToolButton):
    """A flat tool button whose painted glyph follows the theme."""

    def __init__(self, glyph: str, tip: str = "", text: str = "", checkable: bool = False, parent=None):
        super().__init__(parent)
        self.glyph = glyph
        self.setToolTip(tip)
        self.setCheckable(checkable)
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(16, 16))
        self.setFocusPolicy(Qt.TabFocus)
        if text:
            self.setText(text)
            self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.setObjectName("TextTool")
        self.refresh()
        self.toggled.connect(lambda _on: self.refresh())

    def refresh(self) -> None:
        tokens = current()
        color = tokens.accent if self.isChecked() else tokens.muted
        self.setIcon(icon(self.glyph, color))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.PaletteChange:
            self.refresh()


class SegmentedControl(QWidget):
    """Equal-height segments on a track. Painted, so it looks the same everywhere."""

    changed = Signal(str)

    def __init__(self, options, current_key: str | None = None, compact: bool = False, parent=None):
        super().__init__(parent)
        self.options = list(options)  # (key, label, glyph or "", tooltip)
        self.current = current_key
        self.hover = None
        self.compact = compact
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        tips = [option[3] for option in self.options if len(option) > 3 and option[3]]
        if tips:
            self.setToolTip("\n".join(tips))
        self._rects: list[QRect] = []
        self._layout_segments()

    def _font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(12 if self.compact else 13)
        return font

    def _layout_segments(self) -> None:
        bold = self._font()
        bold.setWeight(QFont.DemiBold)
        metrics = QFontMetrics(bold)
        pad = 10 if self.compact else 12
        x = 2
        self._rects = []
        for option in self.options:
            text_width = metrics.horizontalAdvance(option[1]) if option[1] else 0
            glyph_width = 16 + (6 if option[1] else 0) if option[2] else 0
            width = max(text_width + glyph_width + pad * 2, 30)
            self._rects.append(QRect(x, 2, width, self._height() - 4))
            x += width
        self.setFixedSize(x + 2, self._height())

    def _height(self) -> int:
        return 26 if self.compact else 30

    def set_current(self, key, emit: bool = False) -> None:
        if key == self.current:
            return
        self.current = key
        self.update()
        if emit and key is not None:
            self.changed.emit(key)

    def paintEvent(self, _event):
        tokens = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(tokens.surface_alt))
        painter.drawRoundedRect(track, 8, 8)
        painter.setFont(self._font())
        for index, (option, rect) in enumerate(zip(self.options, self._rects)):
            key, text, glyph = option[0], option[1], option[2]
            selected = key == self.current
            if selected:
                pill = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
                painter.setPen(QPen(QColor(tokens.border_strong), 1))
                painter.setBrush(QColor(tokens.surface))
                painter.drawRoundedRect(pill, 6, 6)
            elif self.hover == index:
                painter.setPen(Qt.NoPen)
                painter.setBrush(qcolor(tokens.border, 160))
                painter.drawRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), 6, 6)
            color = QColor(tokens.text if selected or self.hover == index else tokens.muted)
            font = QFont(self._font())
            font.setWeight(QFont.DemiBold if selected else QFont.Normal)
            painter.setFont(font)
            metrics = QFontMetrics(font)
            text_width = metrics.horizontalAdvance(text) if text else 0
            glyph_width = (16 + (6 if text else 0)) if glyph else 0
            x = rect.left() + (rect.width() - text_width - glyph_width) / 2
            if glyph:
                glyph_color = tokens.accent if selected else color
                paint_glyph(painter, glyph, QRectF(x, rect.center().y() - 7.5, 16, 16), glyph_color)
                x += glyph_width
            if text:
                painter.setPen(color)
                painter.drawText(QRectF(x, rect.top(), text_width + 2, rect.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
        if self.hasFocus():
            painter.setPen(QPen(QColor(tokens.accent), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(track, 8, 8)
        painter.end()

    def _index_at(self, pos: QPoint):
        for index, rect in enumerate(self._rects):
            if rect.contains(pos):
                return index
        return None

    def mouseMoveEvent(self, event):
        index = self._index_at(event.position().toPoint())
        if index != self.hover:
            self.hover = index
            self.update()

    def leaveEvent(self, _event):
        self.hover = None
        self.update()

    def mousePressEvent(self, event):
        index = self._index_at(event.position().toPoint())
        if index is not None:
            key = self.options[index][0]
            self.current = key
            self.update()
            self.changed.emit(key)

    def keyPressEvent(self, event):
        keys = [option[0] for option in self.options]
        if event.key() in (Qt.Key_Left, Qt.Key_Right) and keys:
            index = keys.index(self.current) if self.current in keys else 0
            index = (index + (1 if event.key() == Qt.Key_Right else -1)) % len(keys)
            self.set_current(keys[index], emit=True)
            return
        super().keyPressEvent(event)


class Section(QWidget):
    """A collapsible inspector section: overline header, optional trailing control."""

    _collapsed: dict[str, bool] = {}

    def __init__(self, title: str, key: str = "", trailing: QWidget | None = None, parent=None):
        super().__init__(parent)
        self.key = key or title
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        header = QWidget()
        header.setCursor(Qt.PointingHandCursor)
        row = QHBoxLayout(header)
        row.setContentsMargins(14, 10, 10, 6)
        row.setSpacing(6)
        self.chevron = QLabel()
        self.title = overline(title)
        row.addWidget(self.chevron)
        row.addWidget(self.title)
        row.addStretch(1)
        if trailing is not None:
            row.addWidget(trailing)
        header.mousePressEvent = lambda _event: self.toggle()
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(14, 2, 14, 12)
        self.body_layout.setSpacing(8)
        outer.addWidget(header)
        outer.addWidget(self.body)
        outer.addWidget(hairline())
        self._apply(Section._collapsed.get(self.key, False))

    def toggle(self) -> None:
        self._apply(not self.body.isHidden())
        callback = getattr(self, "header_clicked", None)
        if callback is not None:
            callback()

    def _apply(self, collapsed: bool) -> None:
        Section._collapsed[self.key] = collapsed
        self.body.setVisible(not collapsed)
        glyph = "chevron-right" if collapsed else "chevron-down"
        self.chevron.setPixmap(_pix(glyph, current().faint, 12))

    def add(self, widget: QWidget) -> QWidget:
        self.body_layout.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self.body_layout.addLayout(layout)


def _pix(glyph: str, color, size: int = 16):
    from spikes.form_builder.icons import pixmap

    return pixmap(glyph, color, size)


class NumberField(QLineEdit):
    """An integer field that can be blank. Blank means "not set": Reset deletes the line.

    Up/Down step by 1, Shift by 10. Commits on Enter or focus out.
    """

    committed = Signal(object)

    def __init__(self, value=None, placeholder: str = "", minimum: int = -999999, maximum: int = 999999, parent=None):
        super().__init__(parent)
        self.minimum = minimum
        self.maximum = maximum
        self.setValidator(QIntValidator(minimum, maximum, self))
        self.setPlaceholderText(placeholder)
        self._last = value
        self.setText("" if value is None else str(value))
        self.setMinimumWidth(56)
        self.editingFinished.connect(self._commit)

    def value(self):
        text = self.text().strip()
        if text in ("", "-"):
            return None
        try:
            return max(self.minimum, min(self.maximum, int(text)))
        except ValueError:
            return None

    def set_value(self, value) -> None:
        self._last = value
        self.setText("" if value is None else str(value))

    def _commit(self) -> None:
        value = self.value()
        if value != self._last:
            self._last = value
            self.committed.emit(value)

    def step(self, delta: int, commit: bool = True) -> None:
        base = self.value()
        if base is None:
            try:
                base = int(self.placeholderText().split()[0])
            except (ValueError, IndexError):
                base = 0
        self.setText(str(max(self.minimum, min(self.maximum, base + delta))))
        if commit:
            self._commit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Up, Qt.Key_Down):
            amount = 10 if event.modifiers() & Qt.ShiftModifier else 1
            self.step(amount if event.key() == Qt.Key_Up else -amount)
            return
        super().keyPressEvent(event)


class ScrubLabel(QLabel):
    """Drag sideways on the label to change the linked number (Figma style).

    4 px of travel per step; Shift steps by 10, Alt by 1 regardless of speed.
    """

    def __init__(self, text: str, field: NumberField, parent=None):
        super().__init__(text, parent)
        self.field = field
        self.setObjectName("Small")
        self.setCursor(Qt.SizeHorCursor)
        self._origin = None
        self._start = 0

    def mousePressEvent(self, event):
        self._origin = event.position().x()
        value = self.field.value()
        self._start = 0 if value is None else value

    def mouseMoveEvent(self, event):
        if self._origin is None:
            return
        steps = int((event.position().x() - self._origin) / 4)
        scale = 10 if event.modifiers() & Qt.ShiftModifier else 1
        value = max(self.field.minimum, min(self.field.maximum, self._start + steps * scale))
        self.field.setText(str(value))

    def mouseReleaseEvent(self, _event):
        if self._origin is not None:
            self._origin = None
            self.field._commit()


class Card(QFrame):
    """A whole-surface click target with an optional painted thumbnail."""

    clicked = Signal()

    def __init__(self, title: str, body: str, thumb=None, glyph: str = "", height: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_Hover, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 14)
        layout.setSpacing(4)
        if thumb is not None:
            view = Thumbnail(thumb)
            view.setFixedHeight(height or 112)
            layout.addWidget(view)
            layout.addSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        if glyph:
            mark = QLabel()
            mark.setPixmap(_pix(glyph, current().accent, 16))
            row.addWidget(mark)
        heading = QLabel(title)
        heading.setObjectName("Title")
        heading.setStyleSheet("font-size: 14px;")
        row.addWidget(heading)
        row.addStretch(1)
        layout.addLayout(row)
        detail = QLabel(body)
        detail.setObjectName("Small")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        layout.addStretch(1)

    def _hover(self, on: bool) -> None:
        self.setProperty("hover", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def enterEvent(self, event):
        self._hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover(False)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class Thumbnail(QWidget):
    def __init__(self, painter_fn, parent=None):
        super().__init__(parent)
        self.painter_fn = painter_fn

    def paintEvent(self, _event):
        tokens = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(tokens.surface_alt))
        painter.drawRoundedRect(rect, 8, 8)
        self.painter_fn(painter, rect, tokens)
        painter.end()


class EmptyState(QWidget):
    def __init__(self, glyph: str, title: str, body: str, action: QWidget | None = None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 24, 20, 24)
        layout.setSpacing(6)
        mark = QLabel()
        mark.setPixmap(_pix(glyph, current().faint, 28))
        mark.setAlignment(Qt.AlignHCenter)
        heading = QLabel(title)
        heading.setObjectName("Title")
        heading.setAlignment(Qt.AlignHCenter)
        heading.setWordWrap(True)
        detail = QLabel(body)
        detail.setObjectName("Small")
        detail.setAlignment(Qt.AlignHCenter)
        detail.setWordWrap(True)
        layout.addWidget(mark)
        layout.addSpacing(4)
        layout.addWidget(heading)
        layout.addWidget(detail)
        if action is not None:
            layout.addSpacing(8)
            layout.addWidget(action, 0, Qt.AlignHCenter)


class Toast(QWidget):
    """A transient pill at the bottom of its host. Optional action, e.g. Undo."""

    def __init__(self, host: QWidget):
        super().__init__(host)
        self.host = host
        self.text = ""
        self.action_text = ""
        self.callback = None
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.hide()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._fade)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.anim = QPropertyAnimation(self.effect, b"opacity", self)
        self.anim.setDuration(220)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.finished.connect(self._done)

    def show_message(self, text: str, action_text: str = "", callback=None, ms: int = 2800) -> None:
        self.text = text
        self.action_text = action_text
        self.callback = callback
        font = QFont(self.font())
        font.setPixelSize(13)
        self.setFont(font)
        metrics = QFontMetrics(font)
        width = metrics.horizontalAdvance(text) + 32
        if action_text:
            width += metrics.horizontalAdvance(action_text) + 28
        self.resize(width, 36)
        self._place()
        self.anim.stop()
        self.effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self.update()
        self.timer.start(ms)

    def _place(self) -> None:
        x = (self.host.width() - self.width()) // 2
        y = self.host.height() - self.height() - 20
        self.move(max(8, x), max(8, y))

    def _fade(self) -> None:
        self.anim.stop()
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.start()

    def _done(self) -> None:
        if self.effect.opacity() < 0.05:
            self.hide()

    def paintEvent(self, _event):
        tokens = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(tokens.text))
        painter.drawRoundedRect(rect, 18, 18)
        painter.setPen(QColor(tokens.surface))
        metrics = QFontMetrics(self.font())
        painter.drawText(QRectF(16, 0, metrics.horizontalAdvance(self.text) + 2, self.height()), Qt.AlignVCenter, self.text)
        if self.action_text:
            x = 16 + metrics.horizontalAdvance(self.text) + 20
            accent = QColor("#9DB6FF") if not tokens.dark else QColor("#2F5BDB")
            font = QFont(self.font())
            font.setWeight(QFont.DemiBold)
            painter.setFont(font)
            painter.setPen(accent)
            painter.drawText(QRectF(x, 0, metrics.horizontalAdvance(self.action_text) + 8, self.height()), Qt.AlignVCenter, self.action_text)
        painter.end()

    def mousePressEvent(self, _event):
        if self.callback is not None:
            callback = self.callback
            self.callback = None
            callback()
        self._fade()


def rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def chip(painter: QPainter, anchor: QPointF, text: str, fill, ink, align: str = "left", glyph: str = "", pixel_size: int = 11, bold: bool = True) -> QRectF:
    """Paint a small rounded label. anchor is the bottom-left (or bottom-centre) corner."""
    font = QFont(QGuiApplication.font())
    font.setPixelSize(pixel_size)
    font.setWeight(QFont.DemiBold if bold else QFont.Normal)
    painter.save()
    painter.setFont(font)
    metrics = QFontMetrics(font)
    width = metrics.horizontalAdvance(text) + 12 + (14 if glyph else 0)
    height = pixel_size + 8
    if align == "center":
        rect = QRectF(anchor.x() - width / 2, anchor.y() - height, width, height)
    elif align == "right":
        rect = QRectF(anchor.x() - width, anchor.y() - height, width, height)
    else:
        rect = QRectF(anchor.x(), anchor.y() - height, width, height)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(fill))
    painter.drawRoundedRect(rect, 4, 4)
    x = rect.left() + 6
    if glyph:
        paint_glyph(painter, glyph, QRectF(x, rect.center().y() - 5.5, 11, 11), ink)
        x += 14
    painter.setPen(QColor(ink))
    painter.drawText(QRectF(x, rect.top(), width, height), Qt.AlignVCenter | Qt.AlignLeft, text)
    painter.restore()
    return rect
