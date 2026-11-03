"""Eject to code. The dialog lists the methods, the properties and the rewired steps."""

from __future__ import annotations

from typing import Any

from app.qt.QtGui import QFont
from app.qt.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from app.features.form_builder.engine.codegen.eject import EjectPlan
from app.features.form_builder.qtside.data_panel.chrome import apply_chrome


class EjectDialog(QDialog):
    def __init__(self, parent: QWidget, plan: EjectPlan, tokens: object = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.data.ejectDialog")
        self.setWindowTitle("Eject to code")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        title = QLabel("Eject %s to code?" % plan.ui_filename, self)
        title.setObjectName("formBuilder.data.ejectTitle")
        font = QFont(title.font())
        font.setBold(True)
        title.setFont(font)
        title.setWordWrap(True)
        title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout.addWidget(title)
        for index, line in enumerate(plan.summary):
            label = QLabel(line, self)
            label.setObjectName("formBuilder.data.ejectLine%d" % index)
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            layout.addWidget(label)
        row = QHBoxLayout()
        row.setSpacing(8)
        layout.addLayout(row)
        row.addStretch(1)
        cancel = QPushButton("Cancel", self)
        cancel.setObjectName("formBuilder.data.ejectCancel")
        cancel.setAutoDefault(True)
        cancel.setDefault(True)
        eject = QPushButton("Eject", self)
        eject.setObjectName("formBuilder.data.ejectAccept")
        eject.setAutoDefault(False)
        eject.setDefault(False)
        for button in (cancel, eject):
            button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        cancel.clicked.connect(self.reject)
        eject.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(eject)
        self.setMinimumWidth(560)
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
