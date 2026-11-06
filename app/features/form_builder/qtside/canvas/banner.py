"""A floating mode pill over the canvas (UX-WB-006).

Glyph, mode name, one sentence, an optional text action, and an Esc chip.
It does not take layout height, so the page stays where it is.
"""

from __future__ import annotations

from typing import Callable, Optional

from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.theme.chrome import apply_page_shadow
from app.features.form_builder.qtside.theme.metrics import BANNER, ICON, R_CONTROL, R_POPOVER, S2, S3, TYPE_BODY, TYPE_FINE
from app.qt.QtCore import QSize, Qt
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget


class EnterButton(QPushButton):
    """A push button that Enter presses as Space does, as the keyboard scripts need outside a dialog."""

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.isEnabled():
            self.click()
            return
        super().keyPressEvent(event)


DONE_LABEL = "Esc"
_PILL_CAP = 560
_PILL_INSET = 32


class ModeBanner(QFrame):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._done_slot: Optional[Callable[[], None]] = None
        self.setObjectName("formBuilder.overlayBanner")
        self.setAccessibleName("Overlay")
        self.setFixedHeight(BANNER)
        row = QHBoxLayout(self)
        row.setContentsMargins(S3, 0, S2, 0)
        row.setSpacing(S2)
        self._glyph = QLabel(self)
        self._glyph.setObjectName("formBuilder.overlayBannerGlyph")
        self._glyph.setFixedSize(ICON, ICON)
        self._name = QLabel(self)
        self._name.setObjectName("formBuilder.overlayBannerName")
        self._sentence = QLabel(self)
        self._sentence.setObjectName("formBuilder.overlayBannerText")
        self._sentence.setAccessibleName("Overlay instruction")
        self._sentence.setWordWrap(False)
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
        self._glyph_ink = ""
        self._ink = ""
        self._full = ""
        self._detail = ""
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
        detail: str = "",
    ) -> None:
        self._done_slot = on_done
        self._glyph_name = glyph
        self._name.setText(name)
        self._full = sentence
        self._detail = detail
        self._sentence.setToolTip(sentence if not detail else "%s %s" % (sentence, detail))
        self._extra.setText(extra)
        self._extra.setVisible(bool(extra))
        self._extra.setAccessibleName(extra)
        self._extra_slot = on_extra
        self._sentence.setText(self._full)
        self._paint_glyph()
        self.show()

    def set_glyph_ink(self, color: str) -> None:
        self._glyph_ink = color
        self._paint_glyph()

    def set_sentence(self, sentence: str) -> None:
        self._full = sentence
        self._sentence.setToolTip(sentence if not self._detail else "%s %s" % (sentence, self._detail))
        self._fit_sentence(self.width())

    def sentence(self) -> str:
        return self._full

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(min(self._content_width(self._text_px(self._full)), _PILL_CAP), BANNER)

    def preferred_width(self, viewport: int) -> int:
        """Content width, and no wider than 560 or the viewport minus 32."""
        cap = min(_PILL_CAP, max(0, int(viewport) - _PILL_INSET))
        hint = self.sizeHint().width()
        if cap < 1:
            return hint
        return min(hint, cap)

    def fitted_height(self, width: int) -> int:
        """The pill is one line. A long sentence elides. The tooltip keeps the rest."""
        self._fit_sentence(width)
        return BANNER

    def name(self) -> str:
        return self._name.text()

    def apply_colors(
        self,
        background: str,
        border: str,
        text: str,
        muted: str,
        button: str,
        accent: str,
        focus_width: int,
        *,
        high_contrast: bool = False,
        is_dark: bool = False,
    ) -> None:
        del button
        self._ink = text
        focus = max(1, focus_width)
        edge = 2 if high_contrast else 1
        self.setStyleSheet(
            "QFrame#formBuilder\\.overlayBanner { background: %s; border: %dpx solid %s;"
            " border-radius: %dpx; }"
            "QLabel#formBuilder\\.overlayBannerName { color: %s; background: transparent; border: none;"
            " font-size: %dpx; font-weight: 600; }"
            "QLabel#formBuilder\\.overlayBannerText { color: %s; background: transparent; border: none;"
            " font-size: %dpx; }"
            "QPushButton#formBuilder\\.overlayBannerExtra {"
            " color: %s; background: transparent; border: none; padding: 0px 4px; font-size: %dpx; }"
            "QPushButton#formBuilder\\.overlayBannerExtra:focus { border: %dpx solid %s; }"
            "QPushButton#formBuilder\\.overlayBannerDone {"
            " color: %s; background: transparent; border: 1px solid %s; border-radius: %dpx;"
            " padding: 0px 6px; font-size: %dpx; min-height: 18px; max-height: 18px; }"
            "QPushButton#formBuilder\\.overlayBannerDone:focus { border: %dpx solid %s; }"
            % (
                background,
                edge,
                border,
                R_POPOVER,
                text,
                TYPE_BODY,
                muted,
                TYPE_BODY,
                text,
                TYPE_BODY,
                focus,
                accent,
                text,
                border,
                R_CONTROL,
                TYPE_FINE,
                focus,
                accent,
            )
        )
        apply_page_shadow(self, is_dark=is_dark, is_high_contrast=high_contrast)
        self._paint_glyph()
        fit = getattr(self.parentWidget(), "_fit_banner", None)
        if callable(fit):
            fit()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._fit_sentence(self.width())

    def _text_px(self, text: str) -> int:
        if not text:
            return 0
        metrics = self._sentence.fontMetrics()
        advance = int(metrics.horizontalAdvance(text))
        bounds = int(metrics.boundingRect(text).width())
        return max(advance, bounds)

    def _content_width(self, sentence_px: int) -> int:
        layout = self.layout()
        margins = layout.contentsMargins()
        spacing = max(0, layout.spacing())
        pieces = [self._glyph.width() or ICON, max(self._name.sizeHint().width(), 0), max(0, sentence_px)]
        if not self._extra.isHidden():
            pieces.append(max(self._extra.sizeHint().width(), self._extra.minimumSizeHint().width(), 0))
        pieces.append(max(self._done.sizeHint().width(), self._done.minimumSizeHint().width(), 0))
        gaps = spacing * (len(pieces) - 1)
        return margins.left() + margins.right() + sum(pieces) + gaps + 8

    def _fit_sentence(self, width: int) -> None:
        full = self._full
        if not full:
            self._sentence.setText("")
            return
        if width < 8:
            self._sentence.setText(full)
            return
        taken = self.layout().contentsMargins().left() + self.layout().contentsMargins().right()
        taken += self._glyph.width()
        spacing = self.layout().spacing()
        for widget in (self._name, self._extra, self._done):
            if widget.isHidden():
                continue
            taken += spacing + max(widget.sizeHint().width(), 0)
        taken += spacing
        room = max(24, int(width) - taken)
        self._sentence.setText(self._sentence.fontMetrics().elidedText(full, self._elide_right(), room))

    def _paint_glyph(self) -> None:
        ink = self._glyph_ink or self._ink
        if not self._glyph_name or not ink:
            return
        dpr = float(self.devicePixelRatioF()) if hasattr(self, "devicePixelRatioF") else 1.0
        self._glyph.setPixmap(paint_glyph(self._glyph_name, ink, ICON, dpr))

    def _run_done(self) -> None:
        if self._done_slot is not None:
            self._done_slot()

    def _run_extra(self) -> None:
        if self._extra_slot is not None:
            self._extra_slot()

    @staticmethod
    def _elide_right() -> Qt.TextElideMode:
        return getattr(getattr(Qt, "TextElideMode", Qt), "ElideRight")
