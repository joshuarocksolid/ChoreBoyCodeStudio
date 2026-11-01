"""The rule steer (UX E6). Esc closes without choosing."""

from __future__ import annotations

from typing import Optional

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from app.qt.qt_compat import exec_qt


def steer_sentence(slot: str, target: str, sender: str) -> str:
    """The question, with display names already filled in."""
    if slot.strip().startswith("setVisible"):
        kind = "visible"
    else:
        kind = "enabled"
    return (
        "Keep %s %s only while %s is checked? A rule also gets this right when the form opens."
        % (target, kind, sender)
    )


def ask_steer(parent: QWidget, sentence: str) -> Optional[str]:
    """``rule``, ``connect``, or None when Esc closes the dialog."""
    dialog = QDialog(parent)
    dialog.setObjectName("formBuilder.steer")
    dialog.setWindowModality(getattr(getattr(Qt, "WindowModality", Qt), "ApplicationModal"))
    dialog.setWindowTitle("Make it a rule")
    column = QVBoxLayout(dialog)
    label = QLabel(sentence, dialog)
    label.setObjectName("formBuilder.steer.sentence")
    label.setWordWrap(True)
    column.addWidget(label)
    buttons = QHBoxLayout()
    rule = QPushButton("Make it a rule", dialog)
    rule.setObjectName("formBuilder.steer.rule")
    rule.setDefault(True)
    rule.setAutoDefault(True)
    connect = QPushButton("Connect anyway", dialog)
    connect.setObjectName("formBuilder.steer.connect")
    connect.setAutoDefault(True)
    buttons.addWidget(rule)
    buttons.addWidget(connect)
    column.addLayout(buttons)
    choice = {"value": None}

    def pick_rule() -> None:
        choice["value"] = "rule"
        dialog.accept()

    def pick_connect() -> None:
        choice["value"] = "connect"
        dialog.accept()

    rule.clicked.connect(pick_rule)
    connect.clicked.connect(pick_connect)
    rule.setFocus()
    exec_qt(dialog)
    found = choice["value"]
    return found if isinstance(found, str) else None
