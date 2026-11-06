"""One search field for the builder chrome.

24 px, radius ``R_CONTROL``, ``input_bg``, a leading 16 px search glyph,
and a placeholder. No helper sentence.
"""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.features.form_builder.qtside.theme.metrics import CONTROL, ICON, R_CONTROL
from app.qt.QtGui import QIcon
from app.qt.QtWidgets import QLineEdit, QWidget


def search_line(parent: QWidget, placeholder: str, object_name: str) -> QLineEdit:
    """A search field. Call :func:`paint_search_glyph` when the theme is known."""
    edit = QLineEdit(parent)
    edit.setObjectName(object_name)
    edit.setPlaceholderText(placeholder)
    edit.setAccessibleName(placeholder)
    edit.setFixedHeight(CONTROL)
    edit.setClearButtonEnabled(False)
    return edit


def paint_search_glyph(edit: QLineEdit, color: str, chrome: Optional[FormChrome] = None) -> None:
    """Replace any leading action with the search glyph, and paint the field."""
    for action in list(edit.actions()):
        edit.removeAction(action)
    ratio = getattr(edit, "devicePixelRatioF", None)
    dpr = float(ratio()) if callable(ratio) else 1.0
    pixmap = paint_glyph("search", color, ICON, dpr)
    leading = getattr(getattr(QLineEdit, "ActionPosition", QLineEdit), "LeadingPosition")
    edit.addAction(QIcon(pixmap), leading)
    if chrome is None:
        return
    edit.setStyleSheet(
        "QLineEdit { background: %s; color: %s; border: 1px solid %s;"
        " border-radius: %dpx; padding-left: 4px; }"
        "QLineEdit:focus { border: %dpx solid %s; }"
        % (
            chrome.input,
            chrome.text,
            chrome.border,
            R_CONTROL,
            chrome.focus_width or 1,
            chrome.accent,
        )
    )
