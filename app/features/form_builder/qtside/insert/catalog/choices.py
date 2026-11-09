"""UX-CAT-002: Choices."""

from __future__ import annotations

from typing import Tuple

from app.features.form_builder.qtside.insert.catalog._build import leaf_entry, text
from app.features.form_builder.qtside.insert.catalog._model import Entry, Registry

CATEGORY = "Choices"


def entries() -> Tuple[Entry, ...]:
    return (
        leaf_entry("QComboBox", "Combo box", "QComboBox", CATEGORY, "comboBox",
                   "Pick one item from a drop-down list.",
                   ("dropdown", "select", "picklist", "choice", "combo"), "combo_box"),
        leaf_entry("QFontComboBox", "Font combo box", "QFontComboBox", CATEGORY, "fontComboBox",
                   "Pick one of the fonts on the computer.", ("font", "fonts"), "font_combo"),
        leaf_entry("QCheckBox", "Check box", "QCheckBox", CATEGORY, "checkBox",
                   "On or off, with a label.",
                   ("checkbox", "tick", "tickbox", "toggle", "yesno"), "check_box",
                   (text("text", "Check box"),)),
        leaf_entry("QRadioButton", "Radio button", "QRadioButton", CATEGORY, "radioButton",
                   "Pick one of several options.", ("radio", "option"), "radio_button",
                   (text("text", "Radio button"),)),
    )


def register(registry: Registry) -> None:
    for entry in entries():
        registry.add(entry)

