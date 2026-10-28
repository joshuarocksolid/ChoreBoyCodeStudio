"""Shared pieces for the visual property editors. Not registered."""

from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.ui4.values import ColorValue
from app.features.form_builder.qtside.inspector.api import EditorHost
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover, SummaryButton
from app.qt.QtCore import QEvent
from app.qt.QtGui import QColor, QFontMetrics
from app.qt.QtWidgets import QLineEdit, QWidget

_SAMPLE = "#" + "1A7F37"
COLOUR_REFUSAL = "Use a colour like %s." % _SAMPLE
GRADIENT_REFUSAL = "A gradient needs at least two colours."
NUMBER_REFUSAL = "Type a number, like 12."
_HEX = "0123456789abcdefABCDEF"


def part_name(row: str, part: str) -> str:
    """UX-PED-010. Parentheses are kept out of the accessible name."""
    return "%s: %s" % (row, part.split(" (", 1)[0])


def owner_name(host: EditorHost) -> str:
    window = host.row_widget.window()
    if window is None:
        return "widget"
    field = window.findChild(QLineEdit, "formBuilder.inspectorName")
    if field is not None:
        text = field.text().strip()
        if text:
            return text
    return "widget"


def token_color(text: str) -> QColor:
    raw = text[1:] if text.startswith("#") else text
    if len(raw) < 6:
        return QColor(0, 0, 0)
    return QColor(int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


def color_hex(color: ColorValue) -> str:
    body = "%02X%02X%02X" % (color.red, color.green, color.blue)
    if color.alpha is None:
        return "#" + body
    return "#" + body + ("%02X" % color.alpha)


def parse_color_hex(text: str) -> ColorValue:
    raw = text.strip()
    if raw.startswith("#"):
        raw = raw[1:]
    if len(raw) == 6 and _digits(raw):
        return ColorValue(int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
    if len(raw) == 8 and _digits(raw):
        return ColorValue(
            int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16), int(raw[6:8], 16)
        )
    raise ValueError(text)


def alpha_percent(color: ColorValue) -> Optional[int]:
    if color.alpha is None or color.alpha >= 255:
        return None
    return int(round(color.alpha * 100 / 255.0))


def percent_alpha(percent: int) -> int:
    return int(round(max(0, min(100, percent)) * 255 / 100.0))


def _digits(text: str) -> bool:
    return all(ch in _HEX for ch in text)


def square_size(popover_width: int) -> Tuple[int, int]:
    """UX-PED-081. At the 236 px popover the square is 212 × 120; otherwise 200 × 140."""
    if popover_width <= 236:
        return (212, 120)
    return (200, 140)


class RowSummary(SummaryButton):
    """Summary button whose reference text stays whole when it fits the editor column.

    The accessible name drops parentheses so a value like ``Default (13 pt)``
    is not read as a shortcut hint.
    """

    def set_summary(self, text: str) -> None:
        super().set_summary(text)
        self._fit()

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit()

    def _fit(self) -> None:
        full = self.summary
        width = self.width() if self.width() > 0 else 132
        if full:
            metrics = QFontMetrics(self.font())
            needed = metrics.horizontalAdvance(full + " \u25be")
            if needed <= width:
                self.setText(full + " \u25be")
        spoken = (full or "summary").replace(" (", ", ").replace(")", "")
        self.setAccessibleName("%s: %s" % (self._row_label, spoken))


def refit(popover: Optional[RowPopover]) -> None:
    """Grow the popover after a disclosure opens. ``place`` is the M4.0s seam."""
    if popover is not None and not popover.closed:
        popover.place()


def refit_widget(widget: QWidget) -> None:
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, RowPopover):
            refit(parent)
            return
        parent = parent.parentWidget()


def begin_popover(
    host: EditorHost,
    anchor: QWidget,
    session_label: str,
    *,
    large: bool = False,
) -> RowPopover:
    return RowPopover(
        host.row_widget,
        host,
        row_label=host.label,
        session_label=session_label,
        qt_name=host.qt_name,
        anchor=anchor,
        large=large,
    )
