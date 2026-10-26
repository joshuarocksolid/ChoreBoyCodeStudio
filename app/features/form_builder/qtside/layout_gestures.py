"""Run a layout request against the live widgets.

Qt geometry becomes engine values here, before any command runs, so the
engine never imports Qt.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Sequence

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.layout_actions import (
    Measure,
    Measured,
    NeedsConfirm,
    Outcome,
    carry_out,
    measure_ids,
    transact,
)
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import RectValue, SizeValue
from app.features.form_builder.qtside.sizing_live import class_default_policies
from app.qt.QtWidgets import QMessageBox, QWidget
from app.qt.qt_compat import exec_qt

Live = Callable[[NodeId], Optional[QWidget]]
Confirm = Callable[[NeedsConfirm], bool]


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


def perform(session: FormSession, live: Live, request: object, confirm: Confirm) -> Outcome:
    """Plan ``request`` for the current selection and run it as one undo step.

    A declined confirm returns its ``NeedsConfirm`` and writes nothing. After
    an accept the widgets are measured and planned again, because they can
    move while the question is open.
    """
    doc = session.document
    ids = session.selection.state.ids
    execute = transact(session.log)
    outcome = carry_out(doc, ids, request, measure(doc, ids, live), execute)
    if not isinstance(outcome, NeedsConfirm) or not confirm(outcome):
        return outcome
    return carry_out(doc, ids, request, measure(doc, ids, live), execute, confirmed=outcome.text)


def ask(parent: QWidget) -> Confirm:
    """A ``Confirm`` that asks in a message box over ``parent``. Cancel is the default."""

    def confirm(prompt: NeedsConfirm) -> bool:
        box = QMessageBox(parent)
        box.setObjectName("formBuilder.layoutConfirm")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(prompt.text)
        accept = box.addButton(prompt.accept, QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton(prompt.cancel, QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        exec_qt(box)
        accepted = box.clickedButton() is accept
        box.deleteLater()
        return accepted

    return confirm
