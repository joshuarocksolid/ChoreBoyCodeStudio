"""A 24 px segmented control. Text or 16 px glyphs. One selection."""

from __future__ import annotations

from typing import List, Optional, Sequence

from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.features.form_builder.qtside.theme.metrics import (
    CONTROL,
    ICON,
    R_CONTROL,
    R_SEGMENT,
    S1,
    SEGMENT_CELL,
    TYPE_BODY,
)
from app.qt.QtCore import QSize, Qt, Signal
from app.qt.QtGui import QIcon
from app.qt.QtWidgets import QHBoxLayout, QSizePolicy, QToolButton, QWidget


class SegmentedControl(QWidget):
    """Track in the hover colour. The chosen segment is a panel chip."""

    current_changed = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.segmented")
        self.setFixedHeight(CONTROL)
        self._chrome: Optional[FormChrome] = None
        self._index = 0
        self._buttons: List[QToolButton] = []
        self._glyphs: List[str] = []
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(2, 2, 2, 2)
        self._row.setSpacing(0)
        policy = getattr(QSizePolicy, "Policy", QSizePolicy)
        self.setSizePolicy(getattr(policy, "Maximum"), getattr(policy, "Fixed"))

    def set_items(
        self,
        labels: Sequence[str],
        *,
        tooltips: Sequence[str] = (),
        glyphs: Sequence[str] = (),
        names: Sequence[str] = (),
        object_names: Sequence[str] = (),
    ) -> None:
        while self._row.count():
            item = self._row.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._buttons = []
        self._glyphs = [glyph for glyph in glyphs]
        for index, label in enumerate(labels):
            button = QToolButton(self)
            named = object_names[index] if index < len(object_names) and object_names[index] else ""
            button.setObjectName(named or "formBuilder.segment")
            if named:
                button.setProperty("fbTrack", "true")
            button.setCheckable(True)
            button.setAutoRaise(True)
            tip = tooltips[index] if index < len(tooltips) and tooltips[index] else label
            button.setText(label or tip)
            button.setToolTip(tip)
            accessible = names[index] if index < len(names) and names[index] else tip
            button.setAccessibleName(accessible)
            button.setFocusPolicy(self._focus("StrongFocus"))
            button.setCursor(self._cursor())
            button.clicked.connect(lambda _checked=False, slot=index: self.set_current_index(slot))
            self._buttons.append(button)
            self._row.addWidget(button)
        if self._buttons:
            self.set_current_index(min(self._index, len(self._buttons) - 1))
        self._paint()

    def buttons(self) -> List[QToolButton]:
        return list(self._buttons)

    def current_index(self) -> int:
        return self._index

    def set_current_index(self, index: int) -> None:
        if not self._buttons:
            return
        index = max(0, min(index, len(self._buttons) - 1))
        changed = index != self._index
        self._index = index
        for slot, button in enumerate(self._buttons):
            button.setChecked(slot == index)
        self._paint()
        if changed:
            self.current_changed.emit(index)

    def apply_chrome(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        focus = chrome.focus_width if chrome.focus_width > 0 else 1
        plain = _segment_selector()
        checked = _segment_selector(":checked")
        hover = _segment_selector(":hover")
        focused = _segment_selector(":focus")
        self.setStyleSheet(
            "QWidget#formBuilder\\.segmented { background: %s; border: none; border-radius: %dpx; }"
            "%s {"
            " background: transparent; color: %s; border: none; border-radius: %dpx;"
            " padding: 0px %dpx; font-size: %dpx; font-weight: 400; }"
            "%s {"
            " background: %s; color: %s; border: 1px solid %s; font-weight: 600; }"
            "%s { color: %s; }"
            "%s { border: %dpx solid %s; }"
            % (
                chrome.row_hover,
                R_CONTROL,
                plain,
                chrome.muted,
                R_SEGMENT,
                S1,
                TYPE_BODY,
                checked,
                chrome.panel,
                chrome.text,
                chrome.border,
                hover,
                chrome.text,
                focused,
                focus,
                chrome.accent,
            )
        )
        self._paint()

    def showEvent(self, event: object) -> None:  # noqa: N802
        super().showEvent(event)  # type: ignore[arg-type]
        self._paint()

    def _paint(self) -> None:
        chrome = self._chrome
        if chrome is None:
            return
        dpr = float(self.devicePixelRatioF()) if hasattr(self, "devicePixelRatioF") else 1.0
        for index, button in enumerate(self._buttons):
            glyph = self._glyphs[index] if index < len(self._glyphs) else ""
            if not glyph:
                continue
            ink = chrome.text if button.isChecked() else chrome.muted
            button.setIcon(QIcon(paint_glyph(glyph, ink, ICON, dpr)))
            button.setIconSize(QSize(ICON, ICON))
            button.setFixedWidth(SEGMENT_CELL)

    def _cursor(self) -> Qt.CursorShape:
        shapes = getattr(Qt, "CursorShape", Qt)
        return getattr(shapes, "PointingHandCursor")

    @staticmethod
    def _focus(name: str) -> Qt.FocusPolicy:
        return getattr(getattr(Qt, "FocusPolicy", Qt), name)


def _segment_selector(pseudo: str = "") -> str:
    return (
        "QToolButton#formBuilder\\.segment%s, QToolButton[fbTrack=\"true\"]%s"
        % (pseudo, pseudo)
    )
