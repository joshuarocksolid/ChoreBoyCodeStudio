"""The note under a text role in the palette editor (UX-STYLE-013)."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.qtside.inspector.editors._editor_kit import warning_color
from app.qt.QtWidgets import QLabel, QWidget

TEXT_ROLES = frozenset({"WindowText", "Text", "ButtonText", "BrightText", "PlaceholderText"})

PALETTE_NOTE = "ChoreBoy's theme sets text colours, so this has no effect when the app runs. Use Text colour in Appearance."


def text_role_note(parent: QWidget, role: str, written: bool, chrome: object) -> Optional[QLabel]:
    """A ``fb.warning`` label for a text role the user has set, else None. The value is still written."""
    if not written or role not in TEXT_ROLES:
        return None
    label = QLabel(PALETTE_NOTE, parent)
    label.setObjectName("formBuilder.paletteTextNote")
    label.setWordWrap(True)
    label.setContentsMargins(4, 0, 4, 2)
    label.setStyleSheet("color: %s; background: transparent;" % warning_color(chrome))
    label.setMinimumHeight(label.fontMetrics().lineSpacing() * 3 + 4)
    return label
