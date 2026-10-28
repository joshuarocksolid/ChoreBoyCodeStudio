"""Colour row (UX-PED-082). Font, brush, palette and cursor register from their own modules."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.ui4.values import ColorValue
from app.features.form_builder.qtside.inspector.api import (
    EditorHost,
    EditorKey,
    Mixed,
    Registrar,
    RowValue,
    ValueSpec,
    Written,
)
from app.features.form_builder.qtside.visual.color_picker import (
    ColorPicker,
    Swatch,
    colour_summary,
)
from app.features.form_builder.qtside.visual.common import (
    RowSummary,
    begin_popover,
    color_hex,
    refit,
)
from app.qt.QtWidgets import QHBoxLayout, QLabel, QWidget

_ROW = "Colour"


class ColorEditor:
    """Swatch plus hex. The popover holds the shared colour picker."""

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = QWidget(parent)
        layout = QHBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._swatch = Swatch(self._root, 16)
        self._swatch.set_tokens(host.chrome)
        self._summary = RowSummary(host.label or _ROW, self._root)
        self._summary.set_opener(self._open)
        self._summary.set_summary("Default")
        layout.addWidget(self._swatch)
        layout.addWidget(self._summary, 1)
        self._color: Optional[ColorValue] = None
        self._written = False
        self._mixed = False
        self._popover: Optional[object] = None
        self._picker: Optional[ColorPicker] = None
        self._error: Optional[QLabel] = None

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        self._mixed = isinstance(value, Mixed)
        self._written = isinstance(value, Written) and isinstance(value.value, ColorValue)
        self._color = value.value if self._written else None  # type: ignore[union-attr]
        text = colour_summary(self._color if isinstance(self._color, ColorValue) else None, mixed=self._mixed, unset=not self._written)
        self._summary.set_summary(text)
        faint = not self._written and not self._mixed
        self._summary.setStyleSheet("color: %s;" % (self._host.chrome.faint if faint else self._host.chrome.text))
        self._swatch.set_color(
            self._color if isinstance(self._color, ColorValue) else None,
            hollow=not self._written and not self._mixed,
            mixed=self._mixed,
        )
        if (
            self._picker is not None
            and isinstance(self._color, ColorValue)
            and color_hex(self._picker.color()) != color_hex(self._color)
        ):
            self._picker.set_color(self._color)

    def _open(self) -> None:
        popover = self._popover
        if popover is not None and not popover.closed:  # type: ignore[attr-defined]
            return
        label = "Change colour" if (self._host.label or "").lower() in ("", "color", "colour") else (
            "Change " + self._host.label[0].lower() + self._host.label[1:]
        )
        opened = begin_popover(self._host, self._summary, label)
        picker = ColorPicker(
            opened,
            on_color=self._live,
            on_invalid=self._invalid,
            on_done=opened.done,
            row=_ROW,
        )
        picker.set_tokens(self._host.chrome)
        if isinstance(self._color, ColorValue):
            picker.set_color(self._color)
        else:
            picker.set_color(ColorValue(0, 0, 0))
        opened.body().addWidget(picker)
        error = QLabel(opened)
        error.setObjectName("formBuilder.rowError")
        error.setStyleSheet("color: %s;" % self._host.chrome.error)
        error.hide()
        opened.body().addWidget(error)
        opened.set_reset(self._host.reset if self._written else None)
        self._popover = opened
        self._picker = picker
        self._error = error
        opened.open_popover()
        refit(opened)
        picker.fit_width(opened.width())

    def _live(self, color: ColorValue) -> None:
        popover = self._popover
        if popover is None:
            return
        self._color = color
        self._written = True
        self._host.commit(color, session=popover.session)  # type: ignore[attr-defined]
        self._summary.set_summary(colour_summary(color, mixed=False, unset=False))
        self._swatch.set_color(color)

    def _invalid(self, message: str) -> None:
        if not message:
            if self._error is not None:
                self._error.hide()
            return
        self._host.invalid(message)
        if self._error is not None:
            self._error.setText(message)
            self._error.show()


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(ColorValue.ELEMENT), ColorEditor, baseline=True)
