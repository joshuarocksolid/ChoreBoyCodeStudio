"""Eject to code. The dialog lists the methods, the properties and the rewired steps."""

from __future__ import annotations

from typing import Any

from app.qt.QtCore import QSize, Qt
from app.qt.QtGui import QFont
from app.qt.QtWidgets import QDialog, QHBoxLayout, QLabel, QLayout, QPushButton, QSizePolicy, QVBoxLayout, QWidget
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.codegen.eject import EjectPlan
from app.features.form_builder.qtside.data_panel.chrome import apply_chrome


class _WrapLabel(QLabel):
    """A word-wrapped line whose height follows the dialog width."""

    def __init__(self, text: str, parent: QWidget) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return _text_height(self, width)

    def sizeHint(self) -> QSize:  # noqa: N802
        width = self.width() if self.width() > 40 else 488
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, self.heightForWidth(488))


def _text_height(label: QLabel, width: int) -> int:
    wrap = getattr(Qt, "TextWordWrap", None)
    if wrap is None:
        wrap = Qt.TextFlag.TextWordWrap
    align = getattr(Qt, "AlignLeft", None)
    if align is None:
        align = Qt.AlignmentFlag.AlignLeft
    flags = enum_value(wrap) | enum_value(align)
    rect = label.fontMetrics().boundingRect(0, 0, max(1, width), 10000, flags, label.text())
    return int(rect.height()) + 2


class EjectDialog(QDialog):
    def __init__(self, parent: QWidget, plan: EjectPlan, tokens: object = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.data.ejectDialog")
        self.setWindowTitle("Eject to code")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        constraint = getattr(QLayout, "SetMinimumSize", None)
        if constraint is None:
            constraint = QLayout.SizeConstraint.SetMinimumSize
        layout.setSizeConstraint(constraint)
        title = _WrapLabel("Eject %s to code?" % plan.ui_filename, self)
        title.setObjectName("formBuilder.data.ejectTitle")
        font = QFont(title.font())
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        index = 0
        for line in plan.summary:
            for part in line.split("\n"):
                label = _WrapLabel(part, self)
                label.setObjectName("formBuilder.data.ejectLine%d" % index)
                layout.addWidget(label)
                index += 1
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
        if tokens is not None:
            apply_chrome(self, tokens)
        self.fit_to_contents()

    def fit_to_contents(self) -> None:
        """Width stays 520. Height follows the wrapped labels, including button padding."""

        self.setFixedWidth(520)
        laid_out = self.layout()
        if laid_out is None:
            return
        laid_out.activate()
        self.resize(520, int(laid_out.totalHeightForWidth(520)))


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
