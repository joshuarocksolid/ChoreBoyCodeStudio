"""Run a layout request against the live widgets.

Qt geometry becomes engine values here, before any command runs, so the
engine never imports Qt.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Sequence, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.layout_actions import (
    Execute,
    Measure,
    Measured,
    NeedsConfirm,
    Outcome,
    carry_out,
    measure_ids,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import RectValue, SizeValue
from app.features.form_builder.qtside.sizing_live import class_default_policies
from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.qt.QtCore import QEventLoop, QPoint, QRect, QSize, Qt
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from app.qt.qt_compat import exec_qt

Live = Callable[[NodeId], Optional[QWidget]]
Confirm = Callable[[NeedsConfirm], bool]
# The subject a popover sits beside and the area it must stay inside, in global coordinates.
Place = Callable[[], Tuple[QRect, QRect]]

_GAP = 6


def measure(doc: UiDocument, ids: Sequence[NodeId], live: Live) -> Measured:
    """Geometry in parent coordinates, size hint, and class default policies of each live widget."""
    measured: Dict[NodeId, Measure] = {}
    for node_id in measure_ids(doc, ids):
        widget = live(node_id)
        if widget is None:
            continue
        rect = widget.geometry()
        hint = widget.sizeHint()
        measured[node_id] = Measure(
            RectValue(rect.x(), rect.y(), rect.width(), rect.height()),
            SizeValue(hint.width(), hint.height()),
            class_default_policies(widget),
        )
    return measured


def perform(
    doc: UiDocument,
    ids: Sequence[NodeId],
    live: Live,
    execute: Execute,
    request: object,
    confirm: Confirm,
) -> Outcome:
    """Plan ``request`` for ``ids`` and run it as one undo step.

    A declined confirm returns its ``NeedsConfirm`` and writes nothing. After
    an accept the widgets are measured and planned again, because they can
    move while the question is open.
    """
    outcome = carry_out(doc, ids, request, measure(doc, ids, live), execute)
    if not isinstance(outcome, NeedsConfirm) or not confirm(outcome):
        return outcome
    return carry_out(doc, ids, request, measure(doc, ids, live), execute, confirmed=outcome.text)


def beside(subject: QRect, size: QSize, bounds: QRect) -> QPoint:
    """Top-left for a popover of ``size`` next to ``subject``, kept inside ``bounds``.

    Below, then above, right, and left. The first spot that does not cover
    the subject wins. When every spot covers it, the popover goes below.
    """
    spots = (
        QPoint(subject.left(), subject.top() + subject.height() + _GAP),
        QPoint(subject.left(), subject.top() - _GAP - size.height()),
        QPoint(subject.left() + subject.width() + _GAP, subject.top()),
        QPoint(subject.left() - _GAP - size.width(), subject.top()),
    )
    kept = [_inside(spot, size, bounds) for spot in spots]
    for spot in kept:
        if not QRect(spot, size).intersects(subject):
            return spot
    return kept[0]


def popover_style(object_name: str, chrome: FormChrome) -> str:
    """Frame, text, and buttons of the builder popover named ``object_name``."""
    frame = "QFrame#%s" % object_name.replace(".", "\\.")
    return (
        "%(f)s { background: %(panel)s; color: %(text)s; border: 1px solid %(border)s; border-radius: 6px; }"
        "%(f)s QLabel { color: %(text)s; background: transparent; border: none; }"
        "%(f)s QLabel[note=\"true\"] { color: %(muted)s; }"
        "%(f)s QPushButton, %(f)s QToolButton {"
        " color: %(text)s; background: %(input)s; border: 1px solid %(border)s;"
        " border-radius: 4px; padding: 6px 10px; }"
        "%(f)s QPushButton:hover, %(f)s QToolButton:hover { background: %(hover)s; }"
        "%(f)s QPushButton:focus, %(f)s QToolButton:focus {"
        " border: %(focus)dpx solid %(accent)s; }"
        "%(f)s QPushButton:disabled, %(f)s QToolButton:disabled { color: %(muted)s; background: %(panel)s; }"
    ) % {
        "f": frame,
        "panel": chrome.panel,
        "text": chrome.text,
        "muted": chrome.muted,
        "border": chrome.border,
        "input": chrome.input,
        "hover": chrome.row_hover,
        "accent": chrome.accent,
        "focus": chrome.focus_width,
    }


def ask(parent: QWidget, chrome: FormChrome, place: Place) -> Confirm:
    """A ``Confirm`` that asks in a popover beside the subject ``place`` names.

    Cancel has the focus. Esc or a click outside the popover is Cancel.
    """

    def confirm(prompt: NeedsConfirm) -> bool:
        question = _Question(parent, prompt, chrome)
        try:
            return question.ask(*place())
        finally:
            question.deleteLater()

    return confirm


class _Question(QFrame):
    def __init__(self, parent: QWidget, prompt: NeedsConfirm, chrome: FormChrome) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("formBuilder.layoutConfirm")
        self.setAccessibleName("Confirm")
        self.setStyleSheet(popover_style(self.objectName(), chrome))
        column = QVBoxLayout(self)
        column.setContentsMargins(14, 12, 14, 12)
        column.setSpacing(12)
        text = QLabel(prompt.text, self)
        text.setObjectName("formBuilder.layoutConfirmText")
        text.setWordWrap(True)
        text.setMinimumWidth(280)
        text.setMaximumWidth(380)
        column.addWidget(text)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel = QPushButton(prompt.cancel, self)
        self.accept = QPushButton(prompt.accept, self)
        for button in (self.cancel, self.accept):
            # Enter presses the focused button; outside a QDialog that is off by default.
            button.setAutoDefault(True)
            row.addWidget(button)
        column.addLayout(row)
        self._accepted = False
        self._loop = QEventLoop(self)
        self.accept.clicked.connect(lambda: self._finish(True))
        self.cancel.clicked.connect(lambda: self._finish(False))

    def ask(self, subject: QRect, bounds: QRect) -> bool:
        self.adjustSize()
        self.move(beside(subject, self.sizeHint(), bounds))
        self.show()
        if not self.isVisible():
            return False
        self.cancel.setFocus()
        exec_qt(self._loop)
        return self._accepted

    def hideEvent(self, event: object) -> None:  # noqa: N802
        super().hideEvent(event)  # type: ignore[arg-type]
        self._loop.quit()

    def _finish(self, accepted: bool) -> None:
        self._accepted = accepted
        self.hide()


def _inside(spot: QPoint, size: QSize, bounds: QRect) -> QPoint:
    x = max(bounds.left(), min(spot.x(), bounds.left() + bounds.width() - size.width()))
    y = max(bounds.top(), min(spot.y(), bounds.top() + bounds.height() - size.height()))
    return QPoint(x, y)
