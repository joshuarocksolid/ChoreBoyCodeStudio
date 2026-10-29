"""The small dialogs behind the drawer's Insert menu (UX-STYLE-006). Each returns text, or "" when cancelled."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.style.colors import hex_text, parse_color
from app.features.form_builder.engine.ui4.values import ColorValue
from app.features.form_builder.qtside.style import insert as insert_text
from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.features.form_builder.qtside.visual.color_picker import ColorPicker
from app.qt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFontDialog,
    QVBoxLayout,
    QWidget,
)


class _ColourDialog(QDialog):
    """A colour picker with OK and Cancel. ``chosen`` is the last colour the picker held."""

    def __init__(self, parent: Optional[QWidget], chrome: FormChrome, title: str, start: str) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.styleColourDialog")
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        rgb = parse_color(start) or (26, 127, 55)
        self.chosen = hex_text(*rgb)
        self._picker = ColorPicker(self, on_color=self._held, on_invalid=lambda _message: None, on_done=self.accept, row="Colour")
        self._picker.set_tokens(chrome)
        self._picker.set_color(ColorValue(*rgb))
        layout.addWidget(self._picker)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _held(self, color: ColorValue) -> None:
        self.chosen = hex_text(color.red, color.green, color.blue)


def ask_colour(parent: Optional[QWidget], chrome: FormChrome, start: str = "#1A7F37") -> str:
    dialog = _ColourDialog(parent, chrome, "Colour", start)
    return dialog.chosen if dialog.exec() else ""


def ask_gradient(parent: Optional[QWidget], chrome: FormChrome) -> str:
    """Two colours, top to bottom (or left to right)."""
    first = _ColourDialog(parent, chrome, "Gradient: first colour", "#FFFFFF")
    if not first.exec():
        return ""
    second = _ColourDialog(parent, chrome, "Gradient: second colour", "#1A7F37")
    if not second.exec():
        return ""
    return insert_text.gradient_text(first.chosen, second.chosen)


def ask_font(parent: Optional[QWidget]) -> str:
    ok, font = QFontDialog.getFont(parent)  # type: ignore[misc]
    if not ok:
        return ""
    points = font.pointSize() if font.pointSize() > 0 else 12
    return insert_text.font_text(font.family(), points, bold=font.bold(), italic=font.italic())


__all__ = ["ask_colour", "ask_font", "ask_gradient"]
