"""Eject to code. The dialog lists the methods, the properties and the rewired steps."""

from __future__ import annotations

from typing import Any, Optional

from app.qt.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.features.form_builder.engine.codegen.eject import EjectPlan
from app.features.form_builder.qtside.data_panel.chrome import apply_chrome


class EjectDialog(QDialog):
    def __init__(self, parent: QWidget, plan: EjectPlan, tokens: object = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.data.ejectDialog")
        self.setWindowTitle("Eject to code")
        layout = QVBoxLayout(self)
        for index, line in enumerate(plan.summary):
            label = QLabel(line, self)
            label.setObjectName("formBuilder.data.ejectLine%d" % index)
            label.setWordWrap(True)
            layout.addWidget(label)
        buttons = QWidget(self)
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        eject = QPushButton("Eject", buttons)
        eject.setObjectName("formBuilder.data.ejectAccept")
        cancel = QPushButton("Cancel", buttons)
        cancel.setObjectName("formBuilder.data.ejectCancel")
        eject.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        row.addWidget(eject)
        row.addWidget(cancel)
        layout.addWidget(buttons)
        self.resize(520, 220)
        if tokens is not None:
            apply_chrome(self, tokens)


def open_eject_dialog(host: Any) -> None:
    from app.features.form_builder.qtside.data_panel.eject_cmd import commit_eject, plan_for
    from app.features.form_builder.qtside.data_panel.host import narrate
    from app.qt.qt_compat import exec_qt

    plan = plan_for(host)
    if isinstance(plan, str):
        narrate(host, plan)
        return
    tokens = getattr(host, "_tokens", None)
    dialog = EjectDialog(host, plan, tokens)
    if exec_qt(dialog):
        sentence = commit_eject(host, plan)
        if sentence:
            narrate(host, sentence)
