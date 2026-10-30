"""The overlay banner (UX-OVL-002): glyph, name, one sentence, an extra action and Done · Esc.

It sits in the top margin of the canvas, above the viewport, so the page is
pushed down by its height and is never covered (UX-WB-006). The host tells it
colours as plain strings; this module imports nothing from the shell.
"""

from __future__ import annotations

from typing import Callable, Optional

from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.qt.QtCore import Qt
from app.qt.QtGui import QIcon, QKeyEvent
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

HEIGHT = 52


class EnterButton(QPushButton):
    """A push button that Enter presses as Space does, as the keyboard scripts need outside a dialog."""

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.isEnabled():
            self.click()
            return
        super().keyPressEvent(event)

DONE_LABEL = "Done · Esc"


class ModeBanner(QFrame):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._done_slot: Optional[Callable[[], None]] = None
        self.setObjectName("formBuilder.overlayBanner")
        self.setAccessibleName("Overlay")
        self.setFixedHeight(HEIGHT)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 6, 0)
        row.setSpacing(8)
        self._glyph = QLabel(self)
        self._glyph.setObjectName("formBuilder.overlayBannerGlyph")
        self._glyph.setFixedSize(16, 16)
        self._name = QLabel(self)
        self._name.setObjectName("formBuilder.overlayBannerName")
        self._sentence = QLabel(self)
        self._sentence.setObjectName("formBuilder.overlayBannerText")
        self._sentence.setAccessibleName("Overlay instruction")
        self._sentence.setWordWrap(True)
        self._sentence.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._extra = EnterButton(self)
        self._extra.setObjectName("formBuilder.overlayBannerExtra")
        self._extra.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._done = EnterButton(DONE_LABEL, self)
        self._done.setObjectName("formBuilder.overlayBannerDone")
        self._done.setAccessibleName("Done")
        self._done.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._done.clicked.connect(self._run_done)
        row.addWidget(self._glyph)
        row.addWidget(self._name)
        row.addWidget(self._sentence, 1)
        row.addWidget(self._extra)
        row.addWidget(self._done)
        self._glyph_name = ""
        self._ink = ""
        self._extra_slot: Optional[Callable[[], None]] = None
        self._extra.clicked.connect(self._run_extra)
        self.hide()

    def show_mode(
        self,
        glyph: str,
        name: str,
        sentence: str,
        extra: str,
        on_extra: Optional[Callable[[], None]],
        on_done: Callable[[], None],
    ) -> None:
        self._done_slot = on_done
        self._glyph_name = glyph
        self._name.setText(name)
        self._sentence.setText(sentence)
        self._extra.setText(extra)
        self._extra.setVisible(bool(extra))
        self._extra.setAccessibleName(extra)
        self._extra_slot = on_extra
        self._paint_glyph()
        self.show()

    def set_sentence(self, sentence: str) -> None:
        self._sentence.setText(sentence)

    def sentence(self) -> str:
        return self._sentence.text()

    def name(self) -> str:
        return self._name.text()

    def apply_colors(self, background: str, border: str, text: str, muted: str, button: str, accent: str, focus_width: int) -> None:
        self._ink = text
        self.setStyleSheet(
            "QFrame#formBuilder\\.overlayBanner { background: %s; border: none; border-bottom: 1px solid %s; }"
            "QLabel#formBuilder\\.overlayBannerName { color: %s; font-weight: 600; background: transparent; }"
            "QLabel#formBuilder\\.overlayBannerText { color: %s; background: transparent; }"
            "QPushButton { color: %s; background: %s; border: 1px solid %s; padding: 3px 10px; }"
            "QPushButton:focus { border: %dpx solid %s; }"
            % (background, border, text, muted, text, button, border, max(1, focus_width), accent)
        )
        self._paint_glyph()

    def _paint_glyph(self) -> None:
        if not self._glyph_name or not self._ink:
            return
        dpr = float(self.devicePixelRatioF()) if hasattr(self, "devicePixelRatioF") else 1.0
        icon = QIcon(paint_glyph(self._glyph_name, self._ink, 16, dpr))
        self._glyph.setPixmap(icon.pixmap(16, 16))

    def _run_done(self) -> None:
        if self._done_slot is not None:
            self._done_slot()

    def _run_extra(self) -> None:
        if self._extra_slot is not None:
            self._extra_slot()
