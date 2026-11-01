"""The first-check question: show messages under the field, or not yet."""

from __future__ import annotations

from typing import Optional

from app.qt.QtCore import QEvent, Qt
from app.qt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget
from app.qt.qt_compat import enum_value

_ENTER = frozenset(
    {
        enum_value(Qt.Key.Key_Return),
        enum_value(Qt.Key.Key_Enter),
        enum_value(Qt.Key.Key_Space),
    }
)


def _wrap(label: QLabel) -> None:
    label.setWordWrap(True)
    label.setMinimumWidth(0)
    # setSizePolicy() clears the height-for-width bit setWordWrap turned on.
    # The column then keeps a one-line hint and the wrapped sentence draws
    # over the next rows. Ignored keeps that sentence from widening the section.
    names = getattr(QSizePolicy, "Policy", QSizePolicy)
    label.setSizePolicy(getattr(names, "Ignored"), getattr(names, "Minimum"))
    fitted = label.sizePolicy()
    fitted.setHeightForWidth(True)
    label.setSizePolicy(fitted)


class _EnterButton(QPushButton):
    """Enter activates the button. A plain widget is not a dialog, so Qt will not."""

    def __init__(self, text: str, parent: QWidget) -> None:
        super().__init__(text, parent)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAutoDefault(False)
        self.setDefault(False)

    def keyPressEvent(self, event: QEvent) -> None:  # noqa: N802
        if enum_value(event.key()) in _ENTER:  # type: ignore[attr-defined]
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


class CheckOffer(QWidget):
    """Shown when the first check is ready and the field has no error label."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.checks.offer")
        self.setMinimumWidth(0)
        self._on_add = None
        self._on_skip = None
        question = QLabel("Show messages under the field?", self)
        question.setObjectName("formBuilder.checks.offer.question")
        _wrap(question)
        self._add = _EnterButton("Add label", self)
        self._add.setObjectName("formBuilder.checks.addLabel")
        self._skip = _EnterButton("Not now", self)
        self._skip.setObjectName("formBuilder.checks.notNow")
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)
        buttons.addWidget(self._add)
        buttons.addWidget(self._skip)
        buttons.addStretch(1)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        column.addWidget(question)
        column.addLayout(buttons)
        self._add.clicked.connect(self._add_clicked)
        self._skip.clicked.connect(self._skip_clicked)

    def set_handlers(self, on_add: object, on_skip: object) -> None:
        self._on_add = on_add
        self._on_skip = on_skip

    def focus_add(self) -> None:
        self._add.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._skip.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._add.setFocus()

    def _add_clicked(self) -> None:
        if callable(self._on_add):
            self._on_add()

    def _skip_clicked(self) -> None:
        if callable(self._on_skip):
            self._on_skip()
