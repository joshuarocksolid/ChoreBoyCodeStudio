"""UX-CAT-002: Buttons."""

from __future__ import annotations

from typing import Callable, Tuple

from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.qtside.insert.catalog._build import (
    fragment,
    leaf_entry,
    standard_buttons,
    text,
    widget,
)
from app.features.form_builder.qtside.insert.catalog._model import WIDGET, Entry, Registry

CATEGORY = "Buttons"


def _button_box() -> Callable[[], Fragment]:
    def build() -> Fragment:
        return fragment(
            widget(
                "QDialogButtonBox",
                "buttonBox",
                properties=(
                    standard_buttons(
                        "QDialogButtonBox::StandardButton::Ok|QDialogButtonBox::StandardButton::Cancel"
                    ),
                ),
            )
        )

    return build


def entries() -> Tuple[Entry, ...]:
    button_box = Entry(
        "QDialogButtonBox", "Button box", "QDialogButtonBox", CATEGORY, "buttonBox",
        "OK, Cancel and other standard buttons, in the order the desktop expects.",
        ("ok cancel", "dialog buttons", "buttons"), "button_box", WIDGET, _button_box(),
    )
    return (
        leaf_entry("QPushButton", "Push button", "QPushButton", CATEGORY, "pushButton",
                   "Runs an action when clicked.", ("button", "btn", "command"), "pill",
                   (text("text", "Button"),)),
        leaf_entry("QToolButton", "Tool button", "QToolButton", CATEGORY, "toolButton",
                   "A small button, often with only an icon.", ("button", "btn"), "tool_button",
                   (text("text", "…"),)),
        leaf_entry("QCommandLinkButton", "Command link", "QCommandLinkButton", CATEGORY,
                   "commandLinkButton",
                   "A large button with a title and a description.",
                   ("button", "command", "command button"), "command_link",
                   (text("text", "Command link"),)),
        button_box,
    )


def register(registry: Registry) -> None:
    for entry in entries():
        registry.add(entry)

