"""One-line tab info bar. Same job as the host disk-conflict bar.

Fill is the tree hover colour. A warning uses that fill plus a warning
edge, never a solid accent. The line elides. The full text stays in the tooltip.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.features.form_builder.qtside.theme.metrics import ICON, INFO_BAR, R_CONTROL, S2, S3, TYPE_BODY
from app.qt.QtCore import Qt
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget


class TabInfoBar(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.tabInfoBar")
        self.setFixedHeight(INFO_BAR)
        self._chrome: Optional[FormChrome] = None
        self._full = ""
        self._warning = False
        self._glyph = ""
        self._buttons: List[QPushButton] = []
        row = QHBoxLayout(self)
        row.setContentsMargins(S3, 0, S2, 0)
        row.setSpacing(S2)
        self._icon = QLabel(self)
        self._icon.setObjectName("formBuilder.tabInfoBarIcon")
        self._icon.setFixedSize(ICON, ICON)
        self._message = QLabel(self)
        self._message.setObjectName("formBuilder.tabInfoBarText")
        self._message.setWordWrap(False)
        row.addWidget(self._icon)
        row.addWidget(self._message, 1)
        self._row = row

    def set_text(self, text: str, *, warning: bool = False) -> None:
        self._full = text
        self._warning = warning
        self._message.setToolTip(text)
        self.setVisible(bool(text))
        self._elide()
        self._apply()

    def text(self) -> str:
        return self._full

    def set_glyph(self, name: str) -> None:
        self._glyph = name
        self._paint()

    def add_button(self, label: str, object_name: str) -> QPushButton:
        button = QPushButton(label, self)
        button.setObjectName(object_name)
        button.setAccessibleName(label)
        button.setAutoDefault(False)
        button.setCursor(getattr(getattr(Qt, "CursorShape", Qt), "PointingHandCursor"))
        self._buttons.append(button)
        self._row.addWidget(button)
        self._apply()
        return button

    def apply_chrome(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        self._apply()
        self._paint()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._elide()

    def showEvent(self, event: object) -> None:  # noqa: N802
        super().showEvent(event)  # type: ignore[arg-type]
        self._paint()

    def _elide(self) -> None:
        full = self._full
        if not full:
            self._message.setText("")
            return
        width = self._message.width()
        if width < 8:
            self._message.setText(full)
            return
        self._message.setText(self._message.fontMetrics().elidedText(full, self._elide_right(), width))

    def _apply(self) -> None:
        chrome = self._chrome
        if chrome is None:
            return
        focus = chrome.focus_width if chrome.focus_width > 0 else 1
        edge = chrome.warning if self._warning and chrome.warning else chrome.border
        left = 2 if self._warning else 0
        self.setStyleSheet(
            "QFrame#formBuilder\\.tabInfoBar { background: %s; color: %s;"
            " border: none; border-bottom: 1px solid %s; border-left: %dpx solid %s; }"
            "QLabel#formBuilder\\.tabInfoBarText { color: %s; background: transparent; border: none;"
            " font-size: %dpx; }"
            "QFrame#formBuilder\\.tabInfoBar QPushButton {"
            " color: %s; background: %s; border: 1px solid %s; border-radius: %dpx;"
            " padding: 2px 8px; font-size: %dpx; font-weight: 600; }"
            "QFrame#formBuilder\\.tabInfoBar QPushButton:focus { border: %dpx solid %s; }"
            % (
                chrome.row_hover,
                chrome.text,
                chrome.border,
                left,
                edge,
                chrome.text,
                TYPE_BODY,
                chrome.text,
                chrome.input,
                chrome.border,
                R_CONTROL,
                TYPE_BODY,
                focus,
                chrome.accent,
            )
        )

    def _paint(self) -> None:
        chrome = self._chrome
        if chrome is None or not self._glyph:
            return
        ink = chrome.warning if self._warning and chrome.warning else chrome.icon_muted
        dpr = float(self.devicePixelRatioF()) if hasattr(self, "devicePixelRatioF") else 1.0
        self._icon.setPixmap(paint_glyph(self._glyph, ink, ICON, dpr))

    @staticmethod
    def _elide_right() -> Qt.TextElideMode:
        return getattr(getattr(Qt, "TextElideMode", Qt), "ElideRight")


def secondary_button_qss(chrome: FormChrome, selector: str) -> str:
    """Host secondary button, for a bar that builds its own buttons."""
    focus = chrome.focus_width if chrome.focus_width > 0 else 1
    return (
        "%s { color: %s; background: %s; border: 1px solid %s; border-radius: %dpx;"
        " padding: 2px 8px; font-weight: 600; }"
        "%s:focus { border: %dpx solid %s; }"
        % (selector, chrome.text, chrome.input, chrome.border, R_CONTROL, selector, focus, chrome.accent)
    )


def bar_colors(chrome: FormChrome) -> Tuple[str, str, str]:
    """Hover fill, text, and border for a caller that paints its own bar."""
    return (chrome.row_hover, chrome.text, chrome.border)
