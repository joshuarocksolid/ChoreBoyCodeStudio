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
    ChangeTo,
    Outcome,
    _morph_targets,
    carry_out,
    measure_ids,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.values import RectValue, SizeValue
from app.features.form_builder.qtside.sizing_live import class_default_policies
from app.features.form_builder.qtside.theme.chrome import LAYOUT_CONFIRM_NAME, FormChrome, popover_style
from app.qt import QtWidgets
from app.qt.QtCore import QEventLoop, QPoint, QRect, QSize, Qt
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QLayout, QPushButton, QVBoxLayout, QWidget
from app.qt.qt_compat import delete_now, exec_qt

Live = Callable[[NodeId], Optional[QWidget]]
Layouts = Callable[[NodeId], Optional[QLayout]]
_PROPERTY_NAMES: Dict[str, Tuple[str, ...]] = {}
Confirm = Callable[[NeedsConfirm], bool]
# The subject a popover sits beside and the area it must stay inside, in global coordinates.
Place = Callable[[], Tuple[QRect, QRect]]

_GAP = 6


def measure(
    doc: UiDocument, ids: Sequence[NodeId], live: Live, layouts: Optional[Layouts] = None
) -> Measured:
    """Geometry in parent coordinates, size hint, and class default policies of each live widget.

    When ``layouts`` is set, each selected layout's rectangle is measured too.
    A nested layout has no widget of its own, and that rectangle is its box.
    """
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
    if layouts is not None:
        for node_id in _layout_ids(doc, ids):
            layout = layouts(node_id)
            if layout is None:
                continue
            rect = layout.geometry()
            measured[node_id] = Measure(
                RectValue(rect.x(), rect.y(), rect.width(), rect.height()),
                SizeValue(rect.width(), rect.height()),
            )
    return measured


def class_properties(class_name: str) -> Optional[Tuple[str, ...]]:
    """Property names from a fresh instance's meta object, including inherited ones.

    ``staticMetaObject`` is a temporary in PySide and is deleted before its
    properties can be read. The instance keeps the meta object alive.
    """
    bare = class_name.split("::")[-1]
    cached = _PROPERTY_NAMES.get(bare)
    if cached is not None:
        return cached
    widget_type = getattr(QtWidgets, bare, None)
    if not isinstance(widget_type, type):
        return None
    try:
        probe = widget_type()
    except (TypeError, RuntimeError):
        return None
    try:
        meta = probe.metaObject()
        names = []
        for index in range(meta.propertyCount()):
            raw = meta.property(index).name()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            names.append(str(raw))
    finally:
        delete_now(probe)
    found = tuple(names)
    _PROPERTY_NAMES[bare] = found
    return found


def _layout_ids(doc: UiDocument, ids: Sequence[NodeId]) -> Tuple[NodeId, ...]:
    """Selected layouts, or the layout on each selected widget. The root when nothing is selected."""
    found = []
    targets = list(ids) if ids else [doc.root.id]
    for node_id in targets:
        if not doc.contains(node_id):
            continue
        node = doc.node(node_id)
        if isinstance(node, LayoutNode):
            found.append(node.id)
        elif isinstance(node, WidgetNode) and node.layout is not None:
            found.append(node.layout.id)
    return tuple(found)


def properties_for(doc: UiDocument, ids: Sequence[NodeId]) -> Dict[str, Tuple[str, ...]]:
    """Target classes a Change to on ``ids`` could land on, and the names each accepts."""
    found: Dict[str, Tuple[str, ...]] = {}
    for target in _morph_targets(doc, ids):
        names = class_properties(target.class_name)
        if names is not None:
            found[target.class_name] = names
    return found


def perform(
    doc: UiDocument,
    ids: Sequence[NodeId],
    live: Live,
    execute: Execute,
    request: object,
    confirm: Confirm,
    layouts: Optional[Layouts] = None,
) -> Outcome:
    """Plan ``request`` for ``ids`` and run it as one undo step.

    A declined confirm returns its ``NeedsConfirm`` and writes nothing. After
    an accept the widgets are measured and planned again, because they can
    move while the question is open.
    """
    known = properties_for(doc, ids) if isinstance(request, ChangeTo) else None
    outcome = carry_out(doc, ids, request, measure(doc, ids, live, layouts), execute, accepted=known)
    if not isinstance(outcome, NeedsConfirm) or not confirm(outcome):
        return outcome
    return carry_out(
        doc,
        ids,
        request,
        measure(doc, ids, live, layouts),
        execute,
        confirmed=outcome.text,
        accepted=known,
    )


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


def ask(parent: QWidget, chrome: Optional[FormChrome], place: Place) -> Confirm:
    """A ``Confirm`` that asks in a popover beside the subject ``place`` names.

    Cancel has the focus. Esc or a click outside the popover is Cancel.
    Without ``chrome`` the popover takes its look from a style sheet above
    ``parent`` that styles ``LAYOUT_CONFIRM_NAME``.
    """

    def confirm(prompt: NeedsConfirm) -> bool:
        question = _Question(parent, prompt, chrome)
        try:
            return question.ask(*place())
        finally:
            question.deleteLater()

    return confirm


class _Question(QFrame):
    def __init__(self, parent: QWidget, prompt: NeedsConfirm, chrome: Optional[FormChrome]) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName(LAYOUT_CONFIRM_NAME)
        self.setAccessibleName("Confirm")
        if chrome is not None:
            self.setStyleSheet(popover_style(LAYOUT_CONFIRM_NAME, chrome))
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
