"""A dialog body for callers that have not been handed the host chrome.

The host helpers live in ``app.shell.dialog_chrome``. This package cannot
import that module. The workbench stores those helpers on itself, and
``parts_from`` walks up to them. A dialog built in a unit test uses the
local body below.
"""

from __future__ import annotations

from typing import Optional, Tuple

from app.qt.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

PRIMARY = "primary"
SECONDARY = "secondary"

_NAMES = {
    PRIMARY: "shell.dialogChrome.button.primary",
    SECONDARY: "shell.dialogChrome.button.secondary",
}


class DialogBody:
    def __init__(self, body: QWidget, footer: QWidget, footer_layout: QHBoxLayout) -> None:
        self.body = body
        self.footer = footer
        self.footer_layout = footer_layout


def install(
    dialog: QDialog,
    *,
    title: str,
    object_name: str,
    body_margins: bool = True,
    subtitle: str = "",
    icon: object = None,
) -> DialogBody:
    del subtitle, icon
    dialog.setObjectName(object_name)
    dialog.setWindowTitle(title)
    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    body = QWidget(dialog)
    body.setObjectName("shell.dialogChrome.body")
    body_layout = QVBoxLayout(body)
    if body_margins:
        body_layout.setContentsMargins(20, 14, 20, 12)
    else:
        body_layout.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(body, 1)
    footer = QWidget(dialog)
    footer.setObjectName("shell.dialogChrome.footer")
    footer_layout = QHBoxLayout(footer)
    footer_layout.setContentsMargins(20, 12, 20, 14)
    footer_layout.setSpacing(8)
    outer.addWidget(footer)
    return DialogBody(body, footer, footer_layout)


def footer_button(chrome: DialogBody, label: str, *, role: str, default: bool = False) -> QPushButton:
    button = QPushButton(label, chrome.footer)
    button.setObjectName(_NAMES.get(role, "shell.dialogChrome.button.secondary"))
    button.setProperty("buttonRole", role)
    button.setDefault(default)
    button.setAutoDefault(default)
    chrome.footer_layout.addWidget(button)
    return button


def footer_stretch(chrome: DialogBody) -> None:
    chrome.footer_layout.addStretch(1)


def local_parts() -> Tuple[object, object, object, str, str]:
    return (install, footer_button, footer_stretch, PRIMARY, SECONDARY)


def parts_from(host: object) -> Tuple[object, object, object, str, str]:
    current: Optional[object] = host
    while current is not None:
        found = getattr(current, "dialog_chrome", None)
        if isinstance(found, tuple) and len(found) == 5:
            return found
        parent = getattr(current, "parentWidget", None)
        current = parent() if callable(parent) else None
    return local_parts()
