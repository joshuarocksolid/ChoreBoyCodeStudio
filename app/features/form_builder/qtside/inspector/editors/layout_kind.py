"""Layout group: the layout's rows, then Kind, size constraint, and form policies.

Kind runs through ``perform`` like every other layout gesture. The rows are
the standard inspector rows, so their writes are plain property writes.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Sequence, Tuple

from app.features.form_builder.engine.commands.base import Command, CommandRejected
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.layout_actions import (
    FORM,
    GRID,
    HORIZONTAL,
    KINDS,
    SEGMENTS,
    VERTICAL,
    Execute,
    InspectedKind,
    Offer,
    Refused,
    gate,
    offers,
)
from app.features.form_builder.qtside.inspector.api import (
    Editor,
    GroupHost,
    GroupId,
    LayoutProp,
    LockedRow,
    OpenRow,
    Registrar,
    Row,
    RowSpec,
)
from app.features.form_builder.qtside.layout_gestures import ask, measure, perform
from app.qt.QtCore import QPoint, QRect, QSize, Qt
from app.qt.QtGui import QPainter, QPaintEvent, QPalette
from app.qt.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

_LAYOUT = GroupId.LAYOUT

_ROWS: Tuple[RowSpec, ...] = (
    RowSpec(
        "layout.sizeConstraint",
        _LAYOUT,
        "Size constraint",
        "Whether the layout sets the size of the widget that holds it.",
        LayoutProp("sizeConstraint"),
        after="layout.verticalSpacing",
    ),
    RowSpec(
        "layout.fieldGrowthPolicy",
        _LAYOUT,
        "Field growth",
        "Which fields widen when the form has room.",
        LayoutProp("fieldGrowthPolicy"),
        after="layout.sizeConstraint",
    ),
    RowSpec(
        "layout.rowWrapPolicy",
        _LAYOUT,
        "Row wrap",
        "When a field moves under its label.",
        LayoutProp("rowWrapPolicy"),
        after="layout.fieldGrowthPolicy",
    ),
    RowSpec(
        "layout.labelAlignment",
        _LAYOUT,
        "Label alignment",
        "Where each label sits in the label column.",
        LayoutProp("labelAlignment"),
        after="layout.rowWrapPolicy",
    ),
    RowSpec(
        "layout.formAlignment",
        _LAYOUT,
        "Form alignment",
        "Where the rows sit when the form has spare room.",
        LayoutProp("formAlignment"),
        after="layout.labelAlignment",
    ),
)
_AFTER_KIND = frozenset(spec.key for spec in _ROWS)

# The Kind row lines up with the standard rows around it: an 8 px changed-bar
# slot, then a 104 px label column.
_BAR_SLOT = 8
_LABEL = 104


def register(registrar: Registrar) -> None:
    for spec in _ROWS:
        registrar.row(spec, baseline=True)
    registrar.group_body(GroupId.LAYOUT, LayoutBody, baseline=True)


class LayoutBody:
    """The Layout group's whole body. ``show`` reads the current owners."""

    def __init__(self, host: GroupHost, parent: QWidget) -> None:
        self._host = host
        self._root = QWidget(parent)
        self._root.setObjectName("formBuilder.layoutBody")
        self._root.setAccessibleName("Layout")
        self._root.setMinimumWidth(0)
        self._column = QVBoxLayout(self._root)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(2)
        self._kind = _KindRow(self._root, self._pick)
        self._column.addWidget(self._kind.widget)
        self._editors: Dict[str, Tuple[tuple, Editor]] = {}
        self._shown_for: Tuple[NodeId, ...] = ()

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, rows: Tuple[Row, ...]) -> None:
        if self._host.owners != self._shown_for:
            self._shown_for = self._host.owners
            self._kind.show_error("")
        before = [self._editor(row) for row in rows if row.key not in _AFTER_KIND]
        after = [self._editor(row) for row in rows if row.key in _AFTER_KIND]
        keys = {row.key for row in rows}
        for key in [key for key in self._editors if key not in keys]:
            self._drop(self._editors.pop(key)[1].widget)
        self._order(before + [self._kind.widget] + after)
        self._paint_kind()

    def _editor(self, row: Row) -> QWidget:
        signature = _signature(row, self._host.qt_names)
        held = self._editors.get(row.key)
        if held is not None and held[0] == signature:
            held[1].show(row.value)
            return held[1].widget
        if held is not None:
            self._drop(held[1].widget)
        editor = self._host.editor_for(row, self._root)
        self._editors[row.key] = (signature, editor)
        return editor.widget

    def _order(self, widgets: Sequence[QWidget]) -> None:
        for index, widget in enumerate(widgets):
            if self._column.indexOf(widget) != index:
                self._column.removeWidget(widget)
                self._column.insertWidget(index, widget)
            widget.show()

    def _drop(self, widget: QWidget) -> None:
        widget.hide()
        self._column.removeWidget(widget)
        widget.deleteLater()

    def _paint_kind(self) -> None:
        host = self._host
        document = host.document
        requests = [InspectedKind(kind_id) for kind_id in SEGMENTS]
        sheet = offers(document, host.owners, measure(document, host.owners, host.live), only=requests)
        for kind_id, request in zip(SEGMENTS, requests):
            self._kind.paint(kind_id, gate(sheet, request), sheet.current_kind == kind_id)

    def _pick(self, kind_id: str) -> None:
        host = self._host
        outcome = perform(
            host.document,
            host.owners,
            host.live,
            _through(host),
            InspectedKind(kind_id),
            ask(self._root, None, self._place),
        )
        self._kind.show_error(outcome.reason if isinstance(outcome, Refused) else "")
        self._paint_kind()

    def _place(self) -> Tuple[QRect, QRect]:
        row = self._kind.widget
        window = row.window()
        subject = QRect(row.mapToGlobal(QPoint(0, 0)), row.size())
        return subject, QRect(window.mapToGlobal(QPoint(0, 0)), window.size())


def _through(host: GroupHost) -> Execute:
    def execute(label: str, commands: Tuple[Command, ...]) -> Tuple[object, ...]:
        message = host.run(label, commands)
        if message is not None:
            raise CommandRejected(message)
        return ()

    return execute


def _signature(row: Row, qt_names: bool) -> tuple:
    """What a row widget is built from. A change in any of it means a new widget."""
    if isinstance(row, OpenRow):
        return (OpenRow, row.label, row.qt_name, row.help, row.editor, row.spec, row.write, qt_names)
    assert isinstance(row, LockedRow)
    return (LockedRow, row.label, row.qt_name, row.help, row.reason, qt_names)


class _KindRow:
    def __init__(self, parent: QWidget, on_pick: Callable[[str], None]) -> None:
        self.widget = QWidget(parent)
        self.widget.setObjectName("formBuilder.layout.kind")
        self.widget.setMinimumWidth(0)
        outer = QVBoxLayout(self.widget)
        outer.setContentsMargins(0, 2, 0, 2)
        outer.setSpacing(2)
        line = QHBoxLayout()
        line.setContentsMargins(_BAR_SLOT, 0, 0, 0)
        line.setSpacing(6)
        label = _Caption("Kind", self.widget)
        label.setMaximumWidth(_LABEL)
        label.setToolTip("How the layout arranges what is inside it.")
        line.addWidget(label, 0)
        strip = QHBoxLayout()
        strip.setContentsMargins(0, 0, 0, 0)
        strip.setSpacing(2)
        self._buttons: Dict[str, QToolButton] = {}
        for kind_id in SEGMENTS:
            button = _KindButton(kind_id, self.widget)
            button.setObjectName("formBuilder.layout.kind.%s" % kind_id)
            button.setAccessibleName("%s layout" % KINDS[kind_id].label)
            button.setCheckable(True)
            button.setProperty("fbSegment", "true")
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, chosen=kind_id: on_pick(chosen))
            self._buttons[kind_id] = button
            strip.addWidget(button, 1)
        line.addLayout(strip, 1)
        outer.addLayout(line)
        self._error = QLabel(self.widget)
        self._error.setObjectName("formBuilder.rowError")
        self._error.setWordWrap(True)
        self._error.setMinimumWidth(0)
        self._error.hide()
        outer.addWidget(self._error)

    def paint(self, kind_id: str, offer: Offer, current: bool) -> None:
        button = self._buttons[kind_id]
        label = "%s layout" % KINDS[kind_id].label
        button.blockSignals(True)
        button.setChecked(current)
        button.blockSignals(False)
        # The current kind stays enabled, so it reads as chosen rather than unavailable.
        button.setEnabled(offer.enabled or current)
        if current:
            button.setToolTip("%s (current)" % label)
        elif offer.enabled:
            button.setToolTip(label)
        else:
            button.setToolTip("%s: %s" % (label, offer.reason) if offer.reason else label)

    def show_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.setVisible(bool(message))


class _Caption(QLabel):
    """As wide as the standard rows' label column, and narrower only when the inspector is."""

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(_LABEL, super().sizeHint().height())


class _KindButton(QToolButton):
    """A segment that draws its layout as a small picture in the text color."""

    def __init__(self, kind_id: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._kind_id = kind_id

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(30, 22)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(18, 22)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        try:
            if not self.isEnabled():
                painter.setOpacity(0.4)
            color = self.palette().color(QPalette.ColorRole.ButtonText)
            for rect in _glyph(self._kind_id, self.rect().center()):
                painter.fillRect(rect, color)
        finally:
            painter.end()


_GLYPHS: Dict[str, Tuple[Tuple[int, int, int, int], ...]] = {
    VERTICAL: ((0, 0, 13, 3), (0, 4, 13, 3), (0, 8, 13, 3)),
    HORIZONTAL: ((0, 0, 3, 11), (5, 0, 3, 11), (10, 0, 3, 11)),
    GRID: ((0, 0, 6, 5), (7, 0, 6, 5), (0, 6, 6, 5), (7, 6, 6, 5)),
    FORM: ((0, 0, 4, 3), (6, 0, 7, 3), (0, 4, 4, 3), (6, 4, 7, 3), (0, 8, 4, 3), (6, 8, 7, 3)),
}


def _glyph(kind_id: str, center: QPoint) -> List[QRect]:
    """Bars of a 13 by 11 picture of ``kind_id`` centered on ``center``."""
    left = center.x() - 6
    top = center.y() - 5
    return [QRect(left + x, top + y, width, height) for x, y, width, height in _GLYPHS.get(kind_id, ())]
