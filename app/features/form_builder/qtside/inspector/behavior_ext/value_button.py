"""A 24 px value the person can open. Title case, 1 px border, 8 px chevron."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.features.form_builder.qtside.theme.metrics import (
    CHEVRON_SMALL,
    CONTROL,
    R_CONTROL,
    S2,
    TYPE_BODY,
)
from app.qt.QtCore import Qt
from app.qt.QtGui import QIcon, QPainter
from app.qt.QtWidgets import QPushButton, QWidget

_TITLES = {
    "always": "Always",
    "never": "Never",
    "typed by the person": "Typed by the person",
    "as designed": "As designed",
    "leaving the field": "Leaving the field",
}


def title_case_value(text: str) -> str:
    """The empty behaviour words. A formula the person wrote stays as written."""
    return _TITLES.get(text, text)


class ValueButton(QPushButton):
    """One behaviour value. The chevron is painted, not a menu glyph from the style."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._chrome: Optional[FormChrome] = None
        self._muted = True
        self._full = ""
        self.setFixedHeight(CONTROL)
        self.setCursor(getattr(getattr(Qt, "CursorShape", Qt), "PointingHandCursor"))
        self.setFocusPolicy(getattr(getattr(Qt, "FocusPolicy", Qt), "StrongFocus"))

    def set_value(self, text: str) -> None:
        self._full = text
        shown = title_case_value(text)
        self.setText(shown)
        tip = text if text and text != shown else text
        self.setToolTip(tip)

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        self._restyle()

    def apply_chrome(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        self._restyle()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        super().paintEvent(event)  # type: ignore[arg-type]
        chrome = self._chrome
        if chrome is None:
            return
        painter = QPainter(self)
        try:
            dpr = float(self.devicePixelRatioF()) if hasattr(self, "devicePixelRatioF") else 1.0
            pixmap = paint_glyph("chevron_down", chrome.icon_muted or chrome.muted, CHEVRON_SMALL, dpr)
            icon = QIcon(pixmap)
            side = CHEVRON_SMALL
            icon.paint(painter, self.width() - side - S2, (self.height() - side) // 2, side, side)
        finally:
            painter.end()

    def _restyle(self) -> None:
        chrome = self._chrome
        name = self.objectName()
        if chrome is None or not name:
            return
        ink = chrome.muted if self._muted else chrome.text
        focus = chrome.focus_width if chrome.focus_width > 0 else 1
        sel = name.replace(".", "\\.")
        self.setStyleSheet(
            "QPushButton#%s { color: %s; background: %s; border: 1px solid %s;"
            " border-radius: %dpx; padding: 0px %dpx 0px %dpx; text-align: left; font-size: %dpx; }"
            "QPushButton#%s:focus { border: %dpx solid %s; }"
            % (
                sel,
                ink,
                chrome.input,
                chrome.border,
                R_CONTROL,
                S2 + CHEVRON_SMALL,
                S2,
                TYPE_BODY,
                sel,
                focus,
                chrome.accent,
            )
        )
