
from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.commands.catalog import Rename
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.qtside.inspector._services import Rejected, Services, rejection_text
from app.features.form_builder.qtside.inspector.model import Crumb, HeaderView, ManyHeader, OneHeader
from app.features.form_builder.qtside.theme.chrome import FormChrome
from app.features.form_builder.qtside.theme.metrics import (
    BREADCRUMB,
    ICON,
    INSPECTOR_ROW,
    PANE_PAD,
    R_CONTROL,
    S2,
    TYPE_BODY,
    TYPE_EMPHASIS,
    TYPE_FINE,
)
from app.qt.QtCore import QEvent, Qt
from app.qt.QtGui import QFont, QPainter, QPen, QResizeEvent
from app.qt.QtWidgets import QLabel, QLineEdit, QSizePolicy, QVBoxLayout, QWidget
from app.qt.qt_compat import enum_value


class _CrumbLabel(QLabel):
    """A link label that stays a tab stop without trapping Tab or Shift+Tab."""

    def event(self, event: QEvent) -> bool:  # noqa: N802
        kind = event.type()
        if kind != QEvent.KeyPress and kind != QEvent.ShortcutOverride:
            return bool(super().event(event))
        key = int(enum_value(getattr(event, "key")()))
        tab = int(enum_value(Qt.Key_Tab))
        back = int(enum_value(Qt.Key_Backtab))
        if key != tab and key != back:
            return bool(super().event(event))
        if kind == QEvent.KeyPress:
            shift = int(enum_value(getattr(event, "modifiers")())) & int(enum_value(Qt.ShiftModifier))
            QWidget.focusNextPrevChild(self, key == tab and not shift)
        event.accept()
        return True


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
        self._used_in: Optional[Tuple[Crumb, ...]] = None
        self._class_full = ""
        self._class_short = ""
        self._link_color = ""
        self._muted = ""
        self._faint = ""
        self._accent = ""
        self._hover_href = ""
        self._glyph = _ClassGlyph(self)
        self._name = QLineEdit(self)
        self._name.setObjectName("formBuilder.inspectorName")
        self._name.setAccessibleName("Name")
        self._name.setFont(_title_font())
        self._name.editingFinished.connect(self._on_name_entered)
        self._name.installEventFilter(self)
        # The class line and the crumbs change text on every select. Each sits
        # alone in a layout-less slot, so its updateGeometry stops at the slot
        # instead of re-laying out every parent up to the MainWindow.
        self._class_slot = _Slot(self, self._show_class, INSPECTOR_ROW)
        self._class = QLabel(self._class_slot)
        self._class_slot.hold(self._class)
        self._class.setObjectName("formBuilder.inspectorClass")
        self._class.setWordWrap(False)
        self._class.setTextFormat(Qt.PlainText)
        self._class.setAlignment(
            getattr(getattr(Qt, "AlignmentFlag", Qt), "AlignLeft")
            | getattr(getattr(Qt, "AlignmentFlag", Qt), "AlignVCenter")
        )
        self._crumbs_slot = _Slot(self, self._render_crumbs, BREADCRUMB)
        self._crumbs = _CrumbLabel(self._crumbs_slot)
        self._crumbs_slot.hold(self._crumbs)
        self._crumbs.setObjectName("formBuilder.inspectorCrumbs")
        self._crumbs.setAccessibleName("Selection path")
        self._crumbs.setTextFormat(Qt.RichText)
        selectable = getattr(Qt, "TextSelectableByMouse")
        links = getattr(Qt, "LinksAccessibleByMouse")
        self._crumbs.setTextInteractionFlags(selectable | links)
        self._crumbs.setOpenExternalLinks(False)
        self._crumbs.setFocusPolicy(Qt.StrongFocus)
        self._crumbs.setSizePolicy(_ignored(), _preferred())
        self._crumbs.setMinimumWidth(0)
        self._crumbs.linkActivated.connect(self._on_crumb)
        hovered = getattr(self._crumbs, "linkHovered", None)
        if hovered is not None:
            hovered.connect(self._on_crumb_hover)
        self._error = QLabel(self)
        self._error.setObjectName("formBuilder.inspectorNameError")
        self._error.setWordWrap(True)
        self._error.hide()
        self._crumbs_slot.hide()

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(PANE_PAD, 0, PANE_PAD, S2)
        self._layout.setSpacing(0)
        self._identity = _Identity(self._glyph, self._name, self._class_slot, self._class, self)
        self._layout.addWidget(self._identity)
        self._layout.addWidget(self._crumbs_slot)
        self._layout.addWidget(self._error)
        self.setFocusProxy(self._name)

    def apply_chrome(self, chrome: FormChrome) -> None:
        """Name border, class ink, and crumb colours. The sheet sits on each control."""
        self._muted = chrome.muted
        self._faint = chrome.faint
        self._accent = chrome.accent
        focus = chrome.focus_width if chrome.focus_width > 0 else 1
        # 1 px is the resting hover edge. Focus uses the chrome width.
        self._name.setStyleSheet(
            "QLineEdit#formBuilder\\.inspectorName {"
            " background: transparent; color: %s; border: 1px solid transparent;"
            " border-radius: %dpx; font-size: %dpx; font-weight: 600; padding: 0px; }"
            "QLineEdit#formBuilder\\.inspectorName:hover { border: 1px solid %s; }"
            "QLineEdit#formBuilder\\.inspectorName:focus { border: %dpx solid %s; }"
            % (chrome.text, R_CONTROL, TYPE_EMPHASIS, chrome.border, focus, chrome.accent)
        )
        class_font = self._class.font()
        class_font.setPixelSize(TYPE_BODY)
        self._class.setFont(class_font)
        self._class.setStyleSheet(
            "QLabel#formBuilder\\.inspectorClass { color: %s; background: transparent; font-size: %dpx; }"
            % (chrome.muted, TYPE_BODY)
        )
        crumb_font = self._crumbs.font()
        crumb_font.setPixelSize(TYPE_FINE)
        self._crumbs.setFont(crumb_font)
        self._crumbs.setStyleSheet(
            "QLabel#formBuilder\\.inspectorCrumbs { color: %s; background: transparent; font-size: %dpx; }"
            % (chrome.muted, TYPE_FINE)
        )
        self._render_crumbs()
        self._identity.place()

    def set_link_color(self, color: str) -> None:
        self._link_color = color
        if not self._muted:
            self._muted = color
        if not self._accent:
            self._accent = color
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

    def has_pending_name(self) -> bool:
        """The name field has focus and text that is not the document's name."""
        name = self._name
        if name.isReadOnly() or not name.hasFocus():
            return False
        return name.text() != self._saved_name

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
        self._fit_name()

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802
        if watched is self._name and event.type() == QEvent.FocusIn:
            if not self._invalid and self._name.text() != self._saved_name:
                self._name.blockSignals(True)
                self._name.setText(self._saved_name)
                self._name.blockSignals(False)
            self._name.setToolTip("")
        elif watched is self._name and event.type() == QEvent.FocusOut:
            self._fit_name()
        return super().eventFilter(watched, event)  # type: ignore[arg-type]

    def _paint_many(self, view: ManyHeader) -> None:
        self._node = None
        self._invalid = False
        self._saved_name = ""
        self._name.blockSignals(True)
        self._name.setReadOnly(True)
        self._name.setText("%d selected" % view.count)
        self._name.setToolTip("")
        self._name.blockSignals(False)
        self._glyph.set_kind("")
        self._set_class_text(view.kinds, view.kinds)
        self._crumbs_data = ()
        self._used_in = None
        self._crumbs_slot.hide()
        self._error.hide()
        self._identity.place()

    def _paint_one(self, view: OneHeader) -> None:
        if self._node != view.node:
            self._invalid = False
        self._node = view.node
        self._saved_name = view.name
        self._name.setReadOnly(False)
        self._glyph.set_kind(view.glyph)
        if view.class_line:
            self._set_class_text(view.class_line, view.qt_line or view.class_line)
        else:
            self._set_class_text(view.friendly, view.friendly, view.qt_class)
        if not self._invalid:
            if self._name.hasFocus():
                if self._name.text() != view.name:
                    self._name.blockSignals(True)
                    self._name.setText(view.name)
                    self._name.blockSignals(False)
            else:
                self._fit_name()
            self._error.hide()
        self._identity.place()
        self._crumbs_data = view.crumbs
        self._used_in = view.used_in
        self._render_crumbs()

    def _fit_name(self) -> None:
        """Show the start of the name; the full name is the tooltip when it does not fit.

        The field keeps the real name as its text. Writing an elided copy into
        it would hand "okButt…ctName" to screen readers, copy and anything
        that reads the field (UX-INSP-001, UX-INSP-003: the head stays visible).
        """
        if self._invalid or self._name.hasFocus() or self._name.isReadOnly() or not self._saved_name:
            return
        self._name.blockSignals(True)
        if self._name.text() != self._saved_name:
            self._name.setText(self._saved_name)
        self._name.setCursorPosition(0)
        self._name.blockSignals(False)
        width = int(self._name.contentsRect().width())
        fits = width < 8 or self._name.fontMetrics().horizontalAdvance(self._saved_name) <= width
        tip = "" if fits else self._saved_name
        if self._name.toolTip() != tip:
            self._name.setToolTip(tip)
        self._identity.place()

    def _apply_short(self, short: bool) -> None:
        """Short mode hides the path. The class stays on the name row."""
        if short == self._short:
            return
        self._short = short
        self._render_crumbs()

    def _set_class_text(self, text: str, short: str, tip: str = "") -> None:
        self._class_full = text
        self._class_short = short
        self._class_tip = tip
        self._show_class()

    def _show_class(self) -> None:
        """Elide the class line to its slot. The full text is the tooltip. O(1)."""
        full = self._class_full
        label = self._class
        width = label.width()
        shown = full
        if width > 0:
            # Too narrow for "Push button · QPushButton": keep the Qt class whole.
            # Eliding that class turns QPushButton into "QPushButt…".
            elide = getattr(getattr(Qt, "TextElideMode", Qt), "ElideRight")
            metrics = label.fontMetrics()
            shown = metrics.elidedText(full, elide, width)
            if shown != full and self._class_short:
                shown = self._class_short
        if label.text() != shown:
            label.setText(shown)
        tip = getattr(self, "_class_tip", "") or (full if shown != full else "")
        if label.toolTip() != tip:
            label.setToolTip(tip)

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

    def _on_crumb_hover(self, link: str) -> None:
        if link == self._hover_href:
            return
        self._hover_href = link
        self._render_crumbs()

    def _on_crumb(self, link: str) -> None:
        self._services.session.selection.set(
            (NodeId(int(link)),),
            source=SelectionSource.INSPECTOR,
        )

    def _render_used_in(self, hosts: Tuple[Crumb, ...]) -> None:
        """An action's header line: "Used in File menu and Main toolbar", each a link (UX-MAIN-012)."""
        style = ' style="color:%s"' % self._link_color if self._link_color else ""
        links = ['<a href="%d"%s>%s</a>' % (int(crumb.node), style, _escape(crumb.label)) for crumb in hosts]
        if not links:
            text = "Not used"
        elif len(links) == 1:
            text = "Used in %s" % links[0]
        else:
            text = "Used in %s and %s" % (", ".join(links[:-1]), links[-1])
        text = _ink(self._link_color, text)
        self._crumbs.setToolTip("Used in " + " and ".join(crumb.label for crumb in hosts) if hosts else "Not used")
        if self._crumbs.text() != text:
            self._crumbs.setText(text)
        self._crumbs_slot.show()

    def _render_crumbs(self) -> None:
        if self._short:
            self._crumbs_slot.hide()
            return
        if self._used_in is not None:
            self._render_used_in(self._used_in)
            return
        crumbs = self._crumbs_data
        if len(crumbs) <= 1:
            self._crumbs_slot.hide()
            return
        labels = [crumb.label for crumb in crumbs]
        self._crumbs.setToolTip(" \u203a ".join(labels))
        width = self._crumbs.width()
        if width < 40:
            width = self.width() - (PANE_PAD * 2) if self.width() > 40 else 240
        shown = list(crumbs)
        while len(shown) > 2 and _plain_width(self._crumbs, shown) > width:
            shown = shown[1:]
        parts = []
        if len(shown) < len(crumbs):
            parts.append(_crumb_span("\u2026", self._faint or self._muted, False))
        for crumb in shown[:-1]:
            hot = self._hover_href == str(int(crumb.node))
            parts.append(self._crumb_link(crumb, hot))
        parts.append(_crumb_span(_escape(shown[-1].label), self._muted or self._link_color, False))
        text = _join_crumbs(parts, self._faint or self._muted)
        if self._crumbs.text() != text:
            self._crumbs.setText(text)
        self._crumbs_slot.show()

    def _crumb_link(self, crumb: Crumb, hovered: bool) -> str:
        color = self._accent if hovered and self._accent else (self._muted or self._link_color)
        return (
            '<a href="%d" style="color:%s;text-decoration:%s">%s</a>'
            % (int(crumb.node), color, "underline" if hovered else "none", _escape(crumb.label))
        )

def _plain_width(label: QLabel, crumbs: list) -> int:
    text = " \u203a ".join(crumb.label for crumb in crumbs)
    metrics = label.fontMetrics()
    advance = getattr(metrics, "horizontalAdvance", None)
    if callable(advance):
        return int(advance(text))
    return int(metrics.width(text))

def _join_crumbs(parts: list, faint: str) -> str:
    sep = _crumb_span(" \u203a ", faint, False)
    return sep.join(parts)


def _crumb_span(text: str, color: str, underline: bool) -> str:
    deco = "underline" if underline else "none"
    if not color:
        return '<span style="text-decoration:%s">%s</span>' % (deco, text)
    return '<span style="color:%s;text-decoration:%s">%s</span>' % (color, deco, text)


def _ink(color: str, text: str) -> str:
    """Rich text otherwise paints black, which disappears on a dark panel."""
    if not color:
        return text
    return '<span style="color:%s">%s</span>' % (color, text)


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


class _Slot(QWidget):
    """A one-line holder with no layout. Its label fills it.

    A child's updateGeometry posts a LayoutRequest to this widget, which has
    no layout to act on it, so the request goes no further. The slot's own
    size never follows the text: ignored width, one line of height.
    """

    def __init__(self, parent: QWidget, on_resize: "object", height: int = 0) -> None:
        super().__init__(parent)
        self._child: Optional[QWidget] = None
        self._on_resize = on_resize
        self._locked = height
        self.setSizePolicy(_ignored(), getattr(getattr(QSizePolicy, "Policy", QSizePolicy), "Fixed"))
        if height:
            self.setFixedHeight(height)

    def hold(self, child: QWidget) -> None:
        self._child = child
        self.fit()

    def fit(self) -> None:
        if self._locked:
            if self.maximumHeight() != self._locked:
                self.setFixedHeight(self._locked)
            return
        child = self._child
        if child is None:
            return
        height = max(1, child.fontMetrics().height() + 2 * getattr(child, "margin", lambda: 0)())
        if self.minimumHeight() != height or self.maximumHeight() != height:
            self.setFixedHeight(height)

    def changeEvent(self, event: object) -> None:  # noqa: N802
        super().changeEvent(event)  # type: ignore[arg-type]
        kind = getattr(event, "type", lambda: None)()
        if kind in (_FONT_CHANGE, _STYLE_CHANGE):
            self.fit()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        child = self._child
        if child is not None:
            child.setGeometry(self.rect())
        callback = self._on_resize
        if callable(callback):
            callback()


_FONT_CHANGE = getattr(getattr(QEvent, "Type", QEvent), "FontChange")
_STYLE_CHANGE = getattr(getattr(QEvent, "Type", QEvent), "StyleChange")


class _Identity(QWidget):
    """Glyph, name, and class on one 28 px row. No layout, so a rename does not reflow the header."""

    def __init__(
        self,
        glyph: QWidget,
        name: QLineEdit,
        class_slot: QWidget,
        class_label: QLabel,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self._glyph = glyph
        self._name = name
        self._class_slot = class_slot
        self._class_label = class_label
        glyph.setParent(self)
        name.setParent(self)
        class_slot.setParent(self)
        self.setFixedHeight(INSPECTOR_ROW)
        policy = getattr(QSizePolicy, "Policy", QSizePolicy)
        self.setSizePolicy(getattr(policy, "Expanding"), getattr(policy, "Fixed"))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.place()

    def place(self) -> None:
        width = self.width()
        height = self.height() or INSPECTOR_ROW
        if width <= 0:
            return
        glyph = ICON
        self._glyph.setGeometry(0, max(0, (height - glyph) // 2), glyph, glyph)
        start = glyph + S2
        room = max(0, width - start)
        label = self._class_label
        class_w = label.fontMetrics().horizontalAdvance(label.text()) + S2
        class_w = min(class_w, max(0, room // 2))
        name_w = max(0, room - S2 - class_w)
        self._name.setGeometry(start, 0, name_w, height)
        self._class_slot.setGeometry(start + name_w + S2, 0, max(0, class_w), height)
