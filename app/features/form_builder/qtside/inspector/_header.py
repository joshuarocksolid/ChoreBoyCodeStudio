
from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.commands.catalog import Rename
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.qtside.inspector._services import Rejected, Services, rejection_text
from app.features.form_builder.qtside.inspector.model import Crumb, HeaderView, ManyHeader, OneHeader
from app.qt.QtCore import Qt
from app.qt.QtGui import QFont, QPainter, QPen, QResizeEvent
from app.qt.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QVBoxLayout, QWidget

class Header(QWidget):

    def __init__(self, services: Services, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.inspectorHeader")
        self._services = services
        self._node: Optional[NodeId] = None
        self._saved_name = ""
        self._invalid = False
        self._short = False
        self._crumbs_data: Tuple[Crumb, ...] = ()
        self._link_color = ""
        self._glyph = _ClassGlyph(self)
        self._name = QLineEdit(self)
        self._name.setObjectName("formBuilder.inspectorName")
        self._name.setAccessibleName("Name")
        self._name.setFont(_title_font())
        self._name.editingFinished.connect(self._on_name_entered)
        self._class = QLabel(self)
        self._class.setObjectName("formBuilder.inspectorClass")
        self._class.setWordWrap(False)
        self._class.setTextFormat(Qt.PlainText)
        self._crumbs = QLabel(self)
        self._crumbs.setObjectName("formBuilder.inspectorCrumbs")
        self._crumbs.setTextFormat(Qt.RichText)
        self._crumbs.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self._crumbs.setOpenExternalLinks(False)
        self._crumbs.setFocusPolicy(Qt.StrongFocus)
        self._crumbs.setSizePolicy(_ignored(), _preferred())
        self._crumbs.setMinimumWidth(0)
        self._crumbs.linkActivated.connect(self._on_crumb)
        self._error = QLabel(self)
        self._error.setObjectName("formBuilder.inspectorNameError")
        self._error.setWordWrap(True)
        self._error.hide()
        self._crumbs.hide()

        self._identity = QHBoxLayout()
        self._identity.setContentsMargins(8, 6, 8, 0)
        self._identity.setSpacing(6)
        self._identity.addWidget(self._glyph, 0)
        self._identity.addWidget(self._name, 1)
        self._class_line = QWidget(self)
        self._class_row = QHBoxLayout(self._class_line)
        self._class_row.setContentsMargins(8, 0, 8, 0)
        self._class_row.addWidget(self._class, 1)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 6)
        self._layout.setSpacing(2)
        self._layout.addLayout(self._identity)
        self._layout.addWidget(self._class_line)
        self._layout.addWidget(self._crumbs)
        self._layout.addWidget(self._error)
        self.setFocusProxy(self._name)

    def set_link_color(self, color: str) -> None:
        self._link_color = color
        self._render_crumbs()

    def paint(self, view: HeaderView, short: bool) -> None:
        with self._services.painting():
            self._apply_short(short)
            if isinstance(view, ManyHeader):
                self._paint_many(view)
                return
            self._paint_one(view)

    def begin_rename(self) -> None:
        if self._name.isReadOnly():
            return
        self._name.setFocus()
        self._name.selectAll()

    def has_invalid_name(self) -> bool:
        return self._invalid

    def revert_name(self) -> None:
        self._invalid = False
        self._name.blockSignals(True)
        self._name.setText(self._saved_name)
        self._name.blockSignals(False)
        self._error.hide()
        self._error.clear()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._render_crumbs()

    def _paint_many(self, view: ManyHeader) -> None:
        self._node = None
        self._invalid = False
        self._saved_name = ""
        self._name.blockSignals(True)
        self._name.setReadOnly(True)
        self._name.setText("%d selected" % view.count)
        self._name.blockSignals(False)
        self._glyph.set_kind("")
        self._class.setText(view.kinds)
        self._crumbs_data = ()
        self._crumbs.hide()
        self._error.hide()

    def _paint_one(self, view: OneHeader) -> None:
        if self._node != view.node:
            self._invalid = False
        self._node = view.node
        self._saved_name = view.name
        self._name.setReadOnly(False)
        self._glyph.set_kind(view.glyph)
        self._class.setText("%s \u00b7 %s" % (view.friendly, view.qt_class))
        if not self._invalid:
            self._name.blockSignals(True)
            self._name.setText(view.name)
            self._name.blockSignals(False)
            self._error.hide()
        self._crumbs_data = view.crumbs
        self._render_crumbs()

    def _apply_short(self, short: bool) -> None:
        if short == self._short:
            return
        self._short = short
        if short:
            self._class_line.hide()
            self._identity.addWidget(self._class, 0)
            return
        self._identity.removeWidget(self._class)
        self._class.setParent(self._class_line)
        self._class_row.addWidget(self._class, 1)
        self._class_line.show()

    def _on_name_entered(self) -> None:
        node = self._node
        if node is None or self._name.isReadOnly():
            return
        text = self._name.text()
        if text == self._saved_name and not self._invalid:
            return
        result = self._services.execute(Rename(node, text))
        if isinstance(result, Rejected):
            self._invalid = True
            self._error.setText(rejection_text(result))
            self._error.show()
            return
        self._invalid = False
        self._saved_name = text
        self._error.hide()
        self._error.clear()

    def _on_crumb(self, link: str) -> None:
        self._services.session.selection.set(
            (NodeId(int(link)),),
            source=SelectionSource.INSPECTOR,
        )

    def _render_crumbs(self) -> None:
        crumbs = self._crumbs_data
        if len(crumbs) <= 1:
            self._crumbs.hide()
            return
        labels = [crumb.label for crumb in crumbs]
        self._crumbs.setToolTip(" \u203a ".join(labels))
        width = self._crumbs.width()
        if width < 40:
            width = self.width() - 16 if self.width() > 40 else 240
        shown = list(crumbs)
        while len(shown) > 2 and _plain_width(self._crumbs, shown) > width:
            shown = shown[1:]
        parts = []
        if len(shown) < len(crumbs):
            parts.append("\u2026")
        for crumb in shown[:-1]:
            style = ""
            if self._link_color:
                style = ' style="color:%s"' % self._link_color
            parts.append(
                '<a href="%d"%s>%s</a>' % (int(crumb.node), style, _escape(crumb.label))
            )
        parts.append(_escape(shown[-1].label))
        self._crumbs.setText(" \u203a ".join(parts))
        self._crumbs.show()

def _plain_width(label: QLabel, crumbs: list) -> int:
    text = " \u203a ".join(crumb.label for crumb in crumbs)
    metrics = label.fontMetrics()
    advance = getattr(metrics, "horizontalAdvance", None)
    if callable(advance):
        return int(advance(text))
    return int(metrics.width(text))

def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

def _ignored() -> QSizePolicy.Policy:
    return getattr(getattr(QSizePolicy, "Policy", QSizePolicy), "Ignored")

def _preferred() -> QSizePolicy.Policy:
    return getattr(getattr(QSizePolicy, "Policy", QSizePolicy), "Preferred")

def _title_font() -> QFont:
    font = QFont()
    font.setPixelSize(13)
    font.setWeight(getattr(getattr(QFont, "Weight", QFont), "DemiBold"))
    return font

class _ClassGlyph(QWidget):

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.inspectorGlyph")
        self.setFixedSize(16, 16)
        self._kind = ""

    def set_kind(self, kind: str) -> None:
        self._kind = kind
        self.update()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        if not self._kind:
            return
        painter = QPainter(self)
        painter.setRenderHint(getattr(getattr(QPainter, "RenderHint", QPainter), "Antialiasing"), True)
        color = self.palette().color(self.foregroundRole())
        painter.setPen(QPen(color))
        painter.setBrush(getattr(getattr(Qt, "BrushStyle", Qt), "NoBrush"))
        _draw_glyph(painter, self._kind)
        painter.end()

def _draw_glyph(painter: QPainter, kind: str) -> None:
    left, top, right, bottom = 2, 2, 13, 13
    name = kind.lower()
    if name in ("button", "radio"):
        if name == "radio":
            painter.drawEllipse(left, top, 11, 11)
            return
        painter.drawRoundedRect(left, top, 12, 12, 2, 2)
        return
    if name == "checkbox":
        painter.drawRect(left + 2, top + 2, 8, 8)
        painter.drawLine(left + 4, top + 6, left + 6, top + 8)
        painter.drawLine(left + 6, top + 8, left + 10, top + 4)
        return
    if name in ("field", "textbox", "label"):
        painter.drawRect(left, top, 12, 12)
        painter.drawLine(left + 2, top + 6, right - 2, top + 6)
        if name != "field":
            painter.drawLine(left + 2, top + 9, right - 4, top + 9)
        return
    if name == "window":
        painter.drawRect(left, top, 12, 12)
        painter.drawLine(left, top + 3, right, top + 3)
        return
    if name == "layout":
        painter.drawRect(left, top, 12, 3)
        painter.drawRect(left, top + 5, 12, 3)
        painter.drawRect(left, top + 10, 8, 2)
        return
    painter.drawRoundedRect(left, top, 12, 12, 1, 1)
