"""Compact field-level action buttons (Browse, Edit) for run dialogs."""

from __future__ import annotations

from PySide2.QtWidgets import QPushButton, QWidget

_FIELD_ACTION_OBJECT_NAME = "shell.fieldAction.button"


def make_field_action_button(label: str, parent: QWidget | None = None) -> QPushButton:
    """Return a themed compact button for inline form rows."""

    button = QPushButton(label, parent)
    button.setObjectName(_FIELD_ACTION_OBJECT_NAME)
    button.setProperty("fieldAction", True)
    return button
