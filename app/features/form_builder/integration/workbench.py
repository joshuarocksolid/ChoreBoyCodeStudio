"""Workbench panes and the tab toolbar (UX-WB-001..003, UX-RESP).

Widths come from a ``LayoutPlan``. This module does not decide breakpoints.
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from app.qt.QtCore import QEvent, QMimeData, QObject, QPoint, QSize, Qt, QTimer
from app.qt.QtGui import QBrush, QColor, QDrag, QIcon
from app.qt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import event_pos

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog_ext.drop import InsertFormRow
from app.features.form_builder.engine.commands.drop_plan import auto_commands
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.qtside.canvas.core.gesture import (
    EditTextAsked,
    HoverFrom,
    PlaceAsked,
    PlaceDrop,
    PlaceHover,
)
from app.features.form_builder.qtside.canvas.core.palette import (
    MIME_INSERT,
    MIME_NODE,
    fragment_for,
    matching_tiles,
    tile_for,
)
from app.features.form_builder.engine.query.drop_target import (
    AcceptedDrop,
    DropPayload,
    NoDrop,
    OutlineRow,
    blocked_ids,
    resolve_outline,
)
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint
from app.features.form_builder.qtside.icons import paint_glyph
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.integration.canvas import FormCanvas, _drop_payload
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.canvas.controller import CanvasHost
from app.features.form_builder.integration.layout import (
    INSPECTOR_MAX,
    INSPECTOR_MIN,
    LEFT_MAX,
    LEFT_MIN,
    LayoutPlan,
    RAIL_WIDTH,
)
from app.features.form_builder.integration.structure import structure_entries
from app.features.form_builder.qtside.inspector import InspectorPane, TabId
from app.features.form_builder.qtside.realize.api import Realizer
from app.shell.theme_tokens import ShellThemeTokens
from app.shell.toolbar_style import flat_tool_button_qss, mode_group_qss

Choice = Tuple[str, Callable[[], None]]


def _is_leave(event: QEvent) -> bool:
    return event.type() == getattr(getattr(QEvent, "Type", QEvent), "Leave")


def _event_kind(event: QEvent) -> str:
    kind = event.type()
    name = getattr(kind, "name", None)
    if isinstance(name, str) and name:
        return name
    return str(kind).rsplit(".", 1)[-1]


def _drag_mime(event: QEvent) -> bool:
    mime = getattr(event, "mimeData", lambda: None)()
    if mime is None:
        return False
    return bool(mime.hasFormat(MIME_INSERT) or mime.hasFormat(MIME_NODE))


def _strong() -> Qt.FocusPolicy:
    return getattr(getattr(Qt, "FocusPolicy", Qt), "StrongFocus")


def _transparent() -> Qt.WidgetAttribute:
    return getattr(getattr(Qt, "WidgetAttribute", Qt), "WA_TransparentForMouseEvents")


def _align(*names: str) -> Qt.Alignment:
    flag = getattr(Qt, "AlignmentFlag", Qt)
    value = getattr(flag, names[0])
    for name in names[1:]:
        value = value | getattr(flag, name)
    return value


def _top_left() -> Qt.Alignment:
    return _align("AlignLeft", "AlignTop")


def _center() -> Qt.Alignment:
    return _align("AlignHCenter", "AlignVCenter")


def _policy(name: str) -> QSizePolicy.Policy:
    return getattr(getattr(QSizePolicy, "Policy", QSizePolicy), name)


def _without_shortcut(tip: str) -> str:
    cut = tip.rfind(" (")
    if cut > 0 and tip.endswith(")"):
        return tip[:cut]
    return tip


def _control_name(text: str, tip: str) -> str:
    # A glyph has no letters. Its name is the tooltip, and the shortcut parenthesis is not part of that name.
    if any(ch.isalnum() for ch in text):
        return text
    return _without_shortcut(tip or text)


def _name_tabs(tabs: QTabWidget, name: str) -> None:
    tabs.setAccessibleName(name)
    tabs.tabBar().setAccessibleName(name)


def _button_style(name: str) -> Qt.ToolButtonStyle:
    return getattr(getattr(Qt, "ToolButtonStyle", Qt), name)


def _dpr(widget: QWidget) -> float:
    reader = getattr(widget, "devicePixelRatioF", None)
    if callable(reader):
        return float(reader())
    return float(widget.devicePixelRatio())


def _glyph_icon(glyph: str, color: str, faint: str, logical: int, dpr: float) -> QIcon:
    icon = QIcon()
    mode = getattr(QIcon, "Mode", QIcon)
    icon.addPixmap(paint_glyph(glyph, color, logical, dpr), getattr(mode, "Normal"))
    icon.addPixmap(paint_glyph(glyph, faint, logical, dpr), getattr(mode, "Disabled"))
    return icon


def _paint_glyph(button: QToolButton, glyph: str, tokens: ShellThemeTokens, logical: int) -> None:
    color = tokens.icon_primary or tokens.text_primary
    faint = tokens.gutter_text or color
    button.setIcon(_glyph_icon(glyph, color, faint, logical, _dpr(button)))
    button.setIconSize(QSize(logical, logical))


_TOOL_GLYPHS = (
    ("undo", "undo"),
    ("redo", "redo"),
    ("zoom_out", "minus"),
    ("zoom_in", "plus"),
    ("preview", "play"),
    ("overflow", "more"),
    ("tab_order", "tab_order"),
    ("buddies", "buddy"),
)
_RAIL_GLYPHS = {
    "formBuilder.leftRail.outline": "outline",
    "formBuilder.leftRail.insert": "insert",
    "formBuilder.rightRail.properties": "properties",
    "formBuilder.rightRail.behavior": "behavior",
    "formBuilder.pin": "pin",
}


def _button(text: str, name: str, tip: str, parent: QWidget) -> QPushButton:
    button = QPushButton(text, parent)
    button.setObjectName(name)
    button.setToolTip(tip)
    button.setAccessibleName(_control_name(text, tip))
    button.setFocusPolicy(_strong())
    return button


def _tool(text: str, name: str, tip: str, parent: QWidget) -> QToolButton:
    button = QToolButton(parent)
    button.setObjectName(name)
    button.setText(text)
    button.setToolTip(tip)
    button.setAccessibleName(_control_name(text, tip))
    button.setFocusPolicy(_strong())
    button.setAutoRaise(True)
    button.setToolButtonStyle(getattr(Qt, "ToolButtonTextOnly"))
    return button


def problems_link_color(tokens: ShellThemeTokens) -> str:
    """Body text colour: it clears 4.5:1 (7:1 in high contrast) on the panel in every theme."""
    return tokens.text_primary


class NoticeBar(QFrame):
    """One info bar for a recovered draft or a file that changed on disk."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.notice")
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(8, 4, 4, 4)
        self._row.setSpacing(6)
        self._label = QLabel(self)
        self._label.setObjectName("formBuilder.noticeText")
        self._label.setWordWrap(True)
        self._row.addWidget(self._label, 1)
        self._buttons: List[QPushButton] = []
        self.hide()

    def show_choices(self, text: str, choices: Sequence[Choice]) -> None:
        self._label.setText(text)
        self._label.setAccessibleName(text)
        for button in self._buttons:
            self._row.removeWidget(button)
            button.deleteLater()
        self._buttons = []
        for label, callback in choices:
            button = _button(label, "formBuilder.noticeButton", label, self)
            button.clicked.connect(callback)
            self._row.addWidget(button, 0)
            self._buttons.append(button)
        self.show()

    def dismiss(self) -> None:
        self.hide()


class FormToolbar(QWidget):
    """36 px bar. Design | XML replaces the single View XML toggle."""

    def __init__(
        self,
        parent: QWidget,
        *,
        on_design: Callable[[], None],
        on_xml: Callable[[bool], None],
        on_undo: Callable[[], None],
        on_redo: Callable[[], None],
        on_zoom_out: Optional[Callable[[], None]] = None,
        on_zoom_in: Optional[Callable[[], None]] = None,
        on_zoom_to: Optional[Callable[[float], None]] = None,
        on_zoom_fit: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.toolbar")
        self.setFixedHeight(36)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(4)

        self._mode = QWidget(self)
        self._mode.setObjectName("formBuilder.modeGroup")
        self._mode.setAccessibleName("Design or XML")
        mode_row = QHBoxLayout(self._mode)
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(0)
        self.design = _tool("Design", "formBuilder.design", "Design", self._mode)
        self.design.setCheckable(True)
        self.design.setChecked(True)
        self.design.clicked.connect(on_design)
        self.xml = _tool("XML", "formBuilder.viewXml", "View XML (Ctrl+Shift+V)", self._mode)
        self.xml.setCheckable(True)
        self.xml.toggled.connect(on_xml)
        mode_row.addWidget(self.design)
        mode_row.addWidget(self.xml)
        row.addWidget(self._mode, 0)
        self._divider = QFrame(self)
        self._divider.setObjectName("formBuilder.modeDivider")
        self._divider.setFixedWidth(1)
        self._divider.setFixedHeight(18)
        row.addWidget(self._divider)

        self.tab_order = _tool(
            "Tab order",
            "formBuilder.tabOrder",
            "Tab order is not available yet",
            self,
        )
        self.tab_order.setEnabled(False)
        self.buddies = _tool("Buddies", "formBuilder.buddies", "Buddies are not available yet", self)
        self.buddies.setEnabled(False)
        row.addWidget(self.tab_order)
        row.addWidget(self.buddies)

        self.undo = _tool("", "formBuilder.undo", "Undo (Ctrl+Z)", self)
        self.redo = _tool("", "formBuilder.redo", "Redo (Ctrl+Shift+Z)", self)
        self.undo.clicked.connect(on_undo)
        self.redo.clicked.connect(on_redo)
        row.addWidget(self.undo)
        row.addWidget(self.redo)

        zoom_ready = None not in (on_zoom_out, on_zoom_in, on_zoom_to, on_zoom_fit)
        self.zoom_out = _tool(
            "",
            "formBuilder.zoomOut",
            "Zoom out" if zoom_ready else "Zoom is not available yet",
            self,
        )
        self.zoom_label = _tool(
            "100%",
            "formBuilder.zoomLabel",
            "Choose a zoom" if zoom_ready else "Zoom is not available yet",
            self,
        )
        self.zoom_in = _tool(
            "",
            "formBuilder.zoomIn",
            "Zoom in" if zoom_ready else "Zoom is not available yet",
            self,
        )
        if zoom_ready:
            assert on_zoom_out is not None and on_zoom_in is not None
            assert on_zoom_to is not None and on_zoom_fit is not None
            self.zoom_out.clicked.connect(on_zoom_out)
            self.zoom_in.clicked.connect(on_zoom_in)
            self.zoom_label.setPopupMode(getattr(QToolButton, "ToolButtonPopupMode", QToolButton).InstantPopup)
            zoom_menu = QMenu(self.zoom_label)
            zoom_menu.setObjectName("formBuilder.zoomMenu")
            zoom_menu.addAction("Fit").triggered.connect(on_zoom_fit)
            for percent in (50, 75, 100, 150, 200):
                action = zoom_menu.addAction("%d%%" % percent)
                action.triggered.connect(lambda _checked=False, value=percent: on_zoom_to(value / 100.0))
            self.zoom_label.setMenu(zoom_menu)
        else:
            for button in (self.zoom_out, self.zoom_label, self.zoom_in):
                button.setEnabled(False)
        for button in (self.zoom_out, self.zoom_label, self.zoom_in):
            row.addWidget(button)
        self.text_size = _tool("Aa", "formBuilder.textSize", "Text size is not available yet", self)
        self.two_widths = _tool("Widths", "formBuilder.twoWidths", "Two widths is not available yet", self)
        self.text_size.setEnabled(False)
        self.two_widths.setEnabled(False)
        row.addWidget(self.text_size)
        row.addWidget(self.two_widths)

        self.preview = _tool("", "formBuilder.preview", "Preview is not available yet", self)
        self.preview.setEnabled(False)
        row.addWidget(self.preview)

        self.overflow = QToolButton(self)
        self.overflow.setObjectName("formBuilder.overflow")
        self.overflow.setText("")
        self.overflow.setToolTip("More")
        self.overflow.setAccessibleName("More")
        self.overflow.setAutoRaise(True)
        self.overflow.setToolButtonStyle(_button_style("ToolButtonIconOnly"))
        self.overflow.setFocusPolicy(_strong())
        self.overflow.setPopupMode(getattr(QToolButton, "ToolButtonPopupMode", QToolButton).InstantPopup)
        self._menu = QMenu(self.overflow)
        self._menu.addAction("Text size").setEnabled(False)
        self._menu.addAction("Two widths").setEnabled(False)
        self.overflow.setMenu(self._menu)
        self.overflow.hide()
        row.addWidget(self.overflow)

        row.addStretch(1)
        self.save_state = QLabel(self)
        self.save_state.setObjectName("formBuilder.saveState")
        self.save_state.setAccessibleName("Save state")
        row.addWidget(self.save_state, 0)
        self._tokens: Optional[ShellThemeTokens] = None
        icon_only = _button_style("ToolButtonIconOnly")
        for button in (self.undo, self.redo, self.zoom_out, self.zoom_in, self.preview):
            button.setToolButtonStyle(icon_only)
        beside = _button_style("ToolButtonTextBesideIcon")
        self.tab_order.setToolButtonStyle(beside)
        self.buddies.setToolButtonStyle(beside)

    def set_compact(self, compact: bool) -> None:
        self.tab_order.setText("" if compact else "Tab order")
        self.buddies.setText("" if compact else "Buddies")
        style = _button_style("ToolButtonIconOnly" if compact else "ToolButtonTextBesideIcon")
        self.tab_order.setToolButtonStyle(style)
        self.buddies.setToolButtonStyle(style)
        self.tab_order.setAccessibleName(_control_name(self.tab_order.text(), self.tab_order.toolTip()))
        self.buddies.setAccessibleName(_control_name(self.buddies.text(), self.buddies.toolTip()))
        self.text_size.setVisible(not compact)
        self.two_widths.setVisible(not compact)
        self.overflow.setVisible(compact)

    def set_undo(self, enabled: bool, tip: str) -> None:
        self.undo.setEnabled(enabled)
        self.undo.setToolTip(tip)
        self.undo.setAccessibleName(_control_name(self.undo.text(), tip))
        self._paint_glyphs()

    def set_redo(self, enabled: bool, tip: str) -> None:
        self.redo.setEnabled(enabled)
        self.redo.setToolTip(tip)
        self.redo.setAccessibleName(_control_name(self.redo.text(), tip))
        self._paint_glyphs()

    def set_save(self, text: str, *, error: bool, tokens: Optional[ShellThemeTokens]) -> None:
        self.save_state.setText(text)
        if tokens is None:
            return
        color = (tokens.diag_error_color or tokens.accent) if error else (tokens.gutter_text or tokens.text_primary)
        self.save_state.setStyleSheet(
            "QLabel#formBuilder\\.saveState { color: %s; background: transparent; border: none; }" % color
        )

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        self.setStyleSheet(_toolbar_qss(tokens))
        self._paint_glyphs()

    def _paint_glyphs(self) -> None:
        tokens = self._tokens
        if tokens is None:
            return
        for attr, glyph in _TOOL_GLYPHS:
            button = getattr(self, attr)
            _paint_glyph(button, glyph, tokens, 16)


def _splitter_qss(tokens: ShellThemeTokens) -> str:
    """A 1 px line. The 6 px handle is only the hit area."""
    return (
        "QSplitter#formBuilder\\.splitter::handle, QSplitter#formBuilder\\.leftSplitter::handle {"
        " background: transparent; image: none; }"
        "QSplitter#formBuilder\\.splitter::handle:horizontal {"
        " width: 6px; margin: 0; border: none; border-left: 1px solid %s; }"
        "QSplitter#formBuilder\\.leftSplitter::handle:vertical {"
        " height: 6px; margin: 0; border: none; border-top: 1px solid %s; }"
        % (tokens.border, tokens.border)
    )


def _toolbar_qss(tokens: ShellThemeTokens) -> str:
    names = (
        "tabOrder",
        "buddies",
        "undo",
        "redo",
        "zoomOut",
        "zoomLabel",
        "zoomIn",
        "textSize",
        "twoWidths",
        "preview",
        "overflow",
    )
    selectors = ["QToolButton#formBuilder\\.%s" % name for name in names]
    faint = tokens.gutter_text or tokens.text_primary
    return "".join(
        (
            "QWidget#formBuilder\\.toolbar { background: %s; color: %s; border-bottom: 1px solid %s; }"
            % (tokens.panel_bg, tokens.text_primary, tokens.border),
            mode_group_qss(tokens, "formBuilder\\.modeGroup"),
            "QWidget#formBuilder\\.modeGroup QToolButton#formBuilder\\.viewXml { border-right: none; }",
            "QFrame#formBuilder\\.modeDivider { background: %s; border: none; }" % tokens.border,
            flat_tool_button_qss(tokens, selectors),
            "QLabel#formBuilder\\.saveState { color: %s; background: transparent; border: none; }" % faint,
        )
    )


class _Header(QWidget):
    """Overline row. The row toggles the pane. The buttons on the right do not."""

    def __init__(self, title: str, parent: QWidget, on_toggle: Callable[[], None]) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.sectionHeader")
        self.setAccessibleName(title)
        self.setFocusPolicy(_strong())
        self._on_toggle = on_toggle
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(4)
        self.title = QLabel(title.upper(), self)
        self.title.setObjectName("formBuilder.sectionTitle")
        self.title.setAttribute(_transparent(), True)
        row.addWidget(self.title, 1)
        self.extra: List[QToolButton] = []

    def add_extra(self, text: str, tip: str) -> QToolButton:
        button = _tool(text, "formBuilder.sectionExtra", tip, self)
        button.setEnabled(False)
        button.setAccessibleName(tip)
        button.setMinimumSize(24, 24)
        layout = self.layout()
        assert layout is not None
        layout.addWidget(button)
        self.extra.append(button)
        return button

    def mousePressEvent(self, event: object) -> None:  # noqa: N802
        left = getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")
        if getattr(event, "button", lambda: None)() == left:
            pos = event_pos(event)
            for button in self.extra:
                if button.geometry().contains(pos):
                    super().mousePressEvent(event)  # type: ignore[arg-type]
                    return
            self._on_toggle()
            event.accept()  # type: ignore[attr-defined]
            return
        super().mousePressEvent(event)  # type: ignore[arg-type]

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = getattr(event, "key", lambda: None)()
        keys = getattr(Qt, "Key", Qt)
        if key in (getattr(keys, "Key_Return"), getattr(keys, "Key_Enter"), getattr(keys, "Key_Space")):
            self._on_toggle()
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


class OutlinePane(QWidget):
    """Read-only structure tree. Selection is written to the session."""

    def __init__(
        self,
        on_pick: Callable[[NodeId], None],
        on_collapsed: Callable[[bool], None],
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.outline")
        self._on_pick = on_pick
        self._on_collapsed = on_collapsed
        self._blocked = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = _Header("Outline", self, self._toggle)
        self.header.add_extra("+", "Not available yet")
        self.header.add_extra("⌕", "Not available yet")
        layout.addWidget(self.header)
        self.tree = QTreeWidget(self)
        self.tree.setObjectName("formBuilder.structure")
        self.tree.setAccessibleName("Form structure")
        self.tree.setHeaderHidden(True)
        self.tree.setFocusPolicy(_strong())
        triggers = getattr(self.tree, "EditTrigger", type(self.tree))
        self.tree.setEditTriggers(getattr(triggers, "NoEditTriggers", 0))
        mode = getattr(self.tree, "SelectionMode", type(self.tree))
        self.tree.setSelectionMode(getattr(mode, "SingleSelection"))
        self.tree.currentItemChanged.connect(self._current_changed)
        self.tree.setMouseTracking(True)
        self.tree.viewport().setMouseTracking(True)
        self.tree.itemEntered.connect(self._item_entered)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.viewport().setAcceptDrops(True)
        self.tree.viewport().installEventFilter(self)
        layout.addWidget(self.tree, 1)
        self._collapsed = False
        self._hover: Optional[NodeId] = None
        self._hover_fill = ""
        self._rows: Dict[int, QTreeWidgetItem] = {}
        self._send_hover: Optional[Callable[[HoverFrom], None]] = None
        self._post: Optional[Callable[[object], None]] = None
        self._payload: Optional[Callable[[], Optional[DropPayload]]] = None
        self._document: Optional[UiDocument] = None
        self._press: Optional[QPoint] = None
        self._drop_line = QFrame(self.tree.viewport())
        self._drop_line.setObjectName("formBuilder.outlineDrop")
        self._drop_line.setFixedHeight(2)
        self._drop_color = ""
        self._paint_drop_line()
        self._drop_line.hide()
        self._spring = QTimer(self)
        self._spring.setSingleShot(True)
        self._spring.setInterval(600)
        self._spring.timeout.connect(self._expand_hovered)
        self._spring_item: Optional[QTreeWidgetItem] = None

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.tree.setVisible(not collapsed)

    def set_drop_bridge(
        self,
        post: Callable[[object], None],
        payload: Callable[[], Optional[DropPayload]],
    ) -> None:
        self._post = post
        self._payload = payload

    def rebuild(self, document: UiDocument, selected: Optional[NodeId]) -> None:
        self._document = document
        self._blocked = True
        self.tree.clear()
        self._rows = {}
        parents: dict[int, QTreeWidgetItem] = {}
        role = getattr(Qt, "UserRole")
        for entry in structure_entries(document):
            item = QTreeWidgetItem([entry.label])
            item.setData(0, role, int(entry.node_id))
            parent = parents.get(entry.depth - 1)
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            parents[entry.depth] = item
            for deeper in [key for key in parents if key > entry.depth]:
                del parents[deeper]
            self._rows[int(entry.node_id)] = item
        self.tree.expandAll()
        self._blocked = False
        self.show_current(selected)
        self._paint_row(self._hover)

    def show_current(self, selected: Optional[NodeId]) -> None:
        """Move the current row. Does not rebuild the tree."""
        if selected is None:
            item = None
        else:
            item = self._rows.get(int(selected))
            if item is None:
                return
        self._blocked = True
        self.tree.setCurrentItem(item)
        if item is not None:
            self.tree.scrollToItem(item)
        self._blocked = False

    def patch_labels(self, document: UiDocument, selected: Optional[NodeId]) -> None:
        entries = tuple(structure_entries(document))
        if len(entries) != len(self._rows):
            self.rebuild(document, selected)
            return
        for entry in entries:
            item = self._rows.get(int(entry.node_id))
            if item is None:
                self.rebuild(document, selected)
                return
            item.setText(0, entry.label)
        self.show_current(selected)

    def set_hover_target(self, send: Callable[[HoverFrom], None]) -> None:
        self._send_hover = send

    def set_hover_fill(self, color: str) -> None:
        self._hover_fill = color
        self._paint_row(self._hover)

    def set_drop_color(self, color: str) -> None:
        self._drop_color = color
        self._paint_drop_line()

    def set_hover(self, node: Optional[NodeId]) -> None:
        previous = self._hover
        self._hover = node
        if previous != node:
            self._paint_row(previous)
            self._paint_row(node)

    def hover_node(self) -> Optional[NodeId]:
        return self._hover

    def _start_row_drag(self, pos: QPoint) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        raw = item.data(0, getattr(Qt, "UserRole"))
        if raw is None:
            return
        drag = QDrag(self.tree)
        mime = QMimeData()
        mime.setData(MIME_NODE, str(int(raw)).encode("utf-8"))
        drag.setMimeData(mime)
        action = getattr(getattr(Qt, "DropAction", Qt), "MoveAction")
        starter = getattr(drag, "exec", None) or getattr(drag, "exec_")
        starter(action)
        self._finish_drag()

    def _finish_drag(self) -> None:
        self._drop_line.hide()
        self._spring.stop()
        self._spring_item = None
        post = self._post
        if post is not None:
            post(PlaceDrop(CanvasPoint(0, 0), True, None, True))

    def _arm_row_spring(self, pos: QPoint) -> None:
        item = self.tree.itemAt(pos)
        if item is not None and not item.isExpanded() and item.childCount():
            if item is not self._spring_item:
                self._spring_item = item
                self._spring.start()
            return
        self._spring.stop()
        self._spring_item = None

    def _paint_drop_line(self) -> None:
        color = self._drop_color or self.tree.palette().highlight().color().name()
        self._drop_line.setStyleSheet(
            "QFrame#formBuilder\\.outlineDrop { background: %s; border: none; }" % color
        )

    def _show_line(self, target: object) -> None:
        if not isinstance(target, AcceptedDrop):
            self._drop_line.hide()
            return
        rect = target.indicator.rect
        height = max(rect.height, 2)
        self._paint_drop_line()
        self._drop_line.setFixedHeight(height)
        self._drop_line.setGeometry(rect.x, rect.y, max(rect.width, 1), height)
        self._drop_line.show()
        self._drop_line.raise_()

    def _expand_hovered(self) -> None:
        item = self._spring_item
        if item is not None:
            item.setExpanded(True)

    def _post_outside(self) -> None:
        post = self._post
        if post is not None:
            post(PlaceHover(CanvasPoint(0, 0), True, None, True))

    def _ensure_placing(self, event: QEvent, pos: QPoint) -> None:
        payload_of = self._payload
        if payload_of is not None and payload_of() is not None:
            return
        doc = self._document
        post = self._post
        if doc is None or post is None:
            return
        parsed = _drop_payload(event, doc)
        if parsed is None:
            return
        body, key = parsed
        post(PlaceAsked(CanvasPoint(pos.x(), pos.y()), body, key))

    def _post_target(self, pos: QPoint, drop: bool) -> None:
        post = self._post
        if post is None:
            return
        self._arm_row_spring(pos)
        target = self._outline_target(pos)
        point = CanvasPoint(pos.x(), pos.y())
        if drop:
            post(PlaceDrop(point, True, target, False, False))  # type: ignore[arg-type]
            self._drop_line.hide()
            return
        self._show_line(target)
        post(PlaceHover(point, True, target, False, False))

    def _outline_rows(self) -> Tuple[OutlineRow, ...]:
        rows = []
        for node_id, item in self._rows.items():
            if item.isHidden():
                continue
            visual = self.tree.visualItemRect(item)
            if visual.height() <= 0:
                continue
            rows.append(
                OutlineRow(
                    NodeId(int(node_id)),
                    visual.y(),
                    visual.height(),
                    max(visual.width(), 1),
                    visual.x(),
                )
            )
        return tuple(rows)

    def _outline_target(self, pos: QPoint) -> object:
        doc = self._document
        payload_of = self._payload
        if doc is None or payload_of is None:
            return NoDrop()
        payload = payload_of()
        if payload is None:
            return NoDrop()
        return resolve_outline(doc, self._outline_rows(), pos.y(), payload, blocked_ids(doc, payload.source_ids))

    def hit_global(self, global_pos: QPoint) -> Optional[object]:
        viewport = self.tree.viewport()
        if not viewport.isVisible():
            return None
        local = viewport.mapFromGlobal(global_pos)
        if not viewport.rect().contains(local):
            self._drop_line.hide()
            self._spring.stop()
            return None
        target = self._outline_target(local)
        self._show_line(target)
        return target

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is not self.tree.viewport():
            return super().eventFilter(watched, event)
        kind = _event_kind(event)
        if kind == "Leave":
            self._announce_hover(None)
            self._press = None
        elif kind == "MouseButtonPress":
            self._press = event_pos(event)
        elif kind == "MouseMove" and self._press is not None:
            pos = event_pos(event)
            if abs(pos.x() - self._press.x()) + abs(pos.y() - self._press.y()) >= 8:
                self._start_row_drag(self._press)
                self._press = None
                return True
        elif kind == "DragEnter" and _drag_mime(event):
            event.acceptProposedAction()  # type: ignore[attr-defined]
            pos = event_pos(event)
            self._ensure_placing(event, pos)
            self._post_target(pos, False)
            return True
        elif kind == "DragMove" and _drag_mime(event):
            event.acceptProposedAction()  # type: ignore[attr-defined]
            self._post_target(event_pos(event), False)
            return True
        elif kind == "Drop" and _drag_mime(event):
            event.acceptProposedAction()  # type: ignore[attr-defined]
            self._drop_line.hide()
            self._post_target(event_pos(event), True)
            return True
        elif kind == "DragLeave":
            self._drop_line.hide()
            self._spring.stop()
            self._post_outside()
        return super().eventFilter(watched, event)

    def show_for_design(self) -> None:
        self.tree.setVisible(not self._collapsed)

    def _toggle(self) -> None:
        self.set_collapsed(not self._collapsed)
        self._on_collapsed(self._collapsed)

    def _item_entered(self, item: QTreeWidgetItem, _column: int) -> None:
        raw = item.data(0, getattr(Qt, "UserRole"))
        if raw is None:
            return
        self._announce_hover(NodeId(int(raw)))

    def _announce_hover(self, node: Optional[NodeId]) -> None:
        send = self._send_hover
        if send is None:
            return
        send(HoverFrom(node))

    def _paint_row(self, node: Optional[NodeId]) -> None:
        if node is None:
            return
        item = self._rows.get(int(node))
        if item is None:
            return
        hovered = self._hover is not None and int(node) == int(self._hover) and bool(self._hover_fill)
        item.setBackground(0, QBrush(QColor(self._hover_fill)) if hovered else QBrush())

    def _current_changed(self, current: Optional[QTreeWidgetItem], _previous: object) -> None:
        if self._blocked or current is None:
            return
        raw = current.data(0, getattr(Qt, "UserRole"))
        if raw is None:
            return
        self._on_pick(NodeId(int(raw)))


class InsertPane(QWidget):
    def __init__(self, on_collapsed: Callable[[bool], None], parent: QWidget) -> None:
        super().__init__(parent)
        self._on_collapsed = on_collapsed
        self._place: Optional[Callable[[str], None]] = None
        self._preview: Optional[Callable[[Optional[str]], None]] = None
        self._on_drag_finished: Optional[Callable[[], None]] = None
        self.setObjectName("formBuilder.insert")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = _Header("Insert", self, self._toggle)
        search = self.header.add_extra("⌕", "Search widgets")
        search.setEnabled(True)
        search.clicked.connect(self._focus_filter)
        layout.addWidget(self.header)
        self.filter = QLineEdit(self)
        self.filter.setObjectName("formBuilder.insertFilter")
        self.filter.setAccessibleName("Search widgets")
        self.filter.setPlaceholderText("Search widgets")
        self.filter.textChanged.connect(self._refill)
        layout.addWidget(self.filter)
        self.caption = QLabel(self)
        self.caption.setObjectName("formBuilder.insertCaption")
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        self.body = _TileList(self, self._drag_finished)
        self.body.setObjectName("formBuilder.insertBody")
        self.body.setAccessibleName("Insert")
        self.body.setFocusPolicy(_strong())
        self.body.itemDoubleClicked.connect(self._activated)
        self.body.itemActivated.connect(self._activated)
        self.body.currentItemChanged.connect(lambda *_args: self._announce_preview())
        layout.addWidget(self.body, 1)
        self._collapsed = False
        self._refill("")

    def set_place(self, place: Callable[[str], None]) -> None:
        self._place = place

    def set_preview(self, preview: Callable[[Optional[str]], None]) -> None:
        self._preview = preview

    def set_caption(self, text: str) -> None:
        self.caption.setText(text)

    def set_drag_finished(self, done: Callable[[], None]) -> None:
        self._on_drag_finished = done

    def _drag_finished(self) -> None:
        done = self._on_drag_finished
        if done is not None:
            done()

    def _announce_preview(self) -> None:
        preview = self._preview
        if preview is None or not self.body.hasFocus():
            return
        item = self.body.currentItem()
        key = None if item is None else item.data(getattr(Qt, "UserRole"))
        preview(None if not key else str(key))

    def _clear_preview(self) -> None:
        preview = self._preview
        if preview is not None:
            preview(None)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.filter.setVisible(not collapsed)
        self.body.setVisible(not collapsed)

    def _toggle(self) -> None:
        self.set_collapsed(not self._collapsed)
        self._on_collapsed(self._collapsed)

    def _focus_filter(self) -> None:
        self.filter.setFocus()
        self.filter.selectAll()

    def _refill(self, text: str) -> None:
        self.body.clear()
        role = getattr(Qt, "UserRole")
        for key, _kind, label in matching_tiles(text):
            item = QListWidgetItem(label)
            item.setData(role, key)
            self.body.addItem(item)

    def _activated(self, item: QListWidgetItem) -> None:
        key = item.data(getattr(Qt, "UserRole"))
        if not key or self._place is None:
            return
        self._place(str(key))


class _TileList(QListWidget):
    def __init__(self, parent: QWidget, on_finished: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self._on_finished = on_finished

    def focusInEvent(self, event: QEvent) -> None:  # noqa: N802
        super().focusInEvent(event)
        announce = getattr(self.parent(), "_announce_preview", None)
        if announce is not None:
            announce()

    def focusOutEvent(self, event: QEvent) -> None:  # noqa: N802
        super().focusOutEvent(event)
        clear = getattr(self.parent(), "_clear_preview", None)
        if clear is not None:
            clear()

    def mouseMoveEvent(self, event: object) -> None:  # noqa: N802
        buttons = getattr(event, "buttons", lambda: 0)()
        left = getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")
        if not buttons & left:
            super().mouseMoveEvent(event)  # type: ignore[arg-type]
            return
        item = self.currentItem()
        if item is None:
            return
        key = item.data(getattr(Qt, "UserRole"))
        if not key:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_INSERT, str(key).encode("utf-8"))
        drag.setMimeData(mime)
        action = getattr(getattr(Qt, "DropAction", Qt), "CopyAction")
        starter = getattr(drag, "exec", None)
        if starter is None:
            starter = getattr(drag, "exec_")
        starter(action)
        done = self._on_finished
        if done is not None:
            done()


class _RailButton(QToolButton):
    """Keeps a 36 px rail from growing to the width of the button's words."""

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(32, 40)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(24, 32)


class _Rail(QWidget):
    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(2, 4, 2, 4)
        self._layout.setSpacing(2)
        self._layout.addStretch(1)

    def add_button(self, name: str, label: str, on_click: Callable[[], None]) -> QToolButton:
        button = _RailButton(self)
        button.setObjectName(name)
        button.setText("")
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.setFocusPolicy(_strong())
        button.setAutoRaise(True)
        button.setToolButtonStyle(_button_style("ToolButtonIconOnly"))
        button.setIconSize(QSize(20, 20))
        button.setSizePolicy(_policy("Ignored"), _policy("Fixed"))
        button.setFixedSize(32, 40)
        caption = QLabel(label, button)
        caption.setObjectName("formBuilder.railLabel")
        caption.hide()
        caption.setWordWrap(True)
        caption.setAlignment(_center())
        caption.setAttribute(_transparent(), True)
        caption.setGeometry(0, 2, 32, 36)
        button.clicked.connect(lambda _checked=False, call=on_click: call())
        self._layout.insertWidget(self._layout.count() - 1, button)
        return button


class FormWorkbench(QWidget):
    """Outline, insert, canvas, and inspector. Drawers reparent the same panes."""

    def __init__(
        self,
        session: FormSession,
        realizer: Realizer,
        on_pick: Callable[[NodeId], None],
        on_pin_left: Callable[[], None],
        on_pin_inspector: Callable[[], None],
        on_widths: Callable[[int, int], None],
        on_collapsed: Callable[[str, bool], None],
        host: CanvasHost,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.workbench")
        self._session = session
        self._on_pin_left = on_pin_left
        self._on_pin_inspector = on_pin_inspector
        self._on_widths = on_widths
        self._on_collapsed = on_collapsed
        self._plan: Optional[LayoutPlan] = None
        self._applying = False
        self._left_open = False
        self._right_open = False
        self._drawer_listener: Optional[Callable[[], None]] = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._splitter = QSplitter(self)
        self._splitter.setObjectName("formBuilder.splitter")
        self._splitter.setHandleWidth(6)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.splitterMoved.connect(self._remember_widths)
        orient = getattr(Qt, "Orientation", Qt)
        self._splitter.setOrientation(getattr(orient, "Horizontal"))
        outer.addWidget(self._splitter, 1)

        self._left_stack = QStackedWidget(self._splitter)
        self.outline = OutlinePane(on_pick, lambda collapsed: on_collapsed("outline", collapsed), self._left_stack)
        self.insert = InsertPane(lambda collapsed: on_collapsed("insert", collapsed), self._left_stack)
        self._left_body = QWidget(self._left_stack)
        self._left_split = QSplitter(self._left_body)
        self._left_split.setObjectName("formBuilder.leftSplitter")
        self._left_split.setHandleWidth(6)
        self._left_split.setChildrenCollapsible(False)
        self._left_split.setOrientation(getattr(orient, "Vertical"))
        self._left_body.setObjectName("formBuilder.leftBody")
        left_layout = QVBoxLayout(self._left_body)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self._left_split)
        self._left_tabs = QTabWidget(self._left_body)
        self._left_tabs.setObjectName("formBuilder.leftTabs")
        _name_tabs(self._left_tabs, "Outline and insert")
        self._left_tabs.hide()
        left_layout.addWidget(self._left_tabs)
        self._left_split.addWidget(self.outline)
        self._left_split.addWidget(self.insert)
        self._left_rail = _Rail("formBuilder.leftRail", self._left_stack)
        self._left_rail.add_button("formBuilder.leftRail.outline", "Outline", self.focus_outline)
        self._left_rail.add_button("formBuilder.leftRail.insert", "Insert", self.focus_insert)
        self._left_stack.addWidget(self._left_body)
        self._left_stack.addWidget(self._left_rail)

        self.canvas = FormCanvas(session, realizer, host, self._splitter)
        self.outline.set_hover_target(self.canvas.send)
        self.outline.set_drop_bridge(self.canvas.send, self.canvas.place_payload)
        self.insert.set_place(self._place_tile)
        self.insert.set_preview(self._preview_insert)
        self.insert.set_drag_finished(self._cancel_place)

        self._right_stack = QStackedWidget(self._splitter)
        self.inspector = InspectorPane(
            session,
            realizer,
            data_tab=os.environ.get("CBCS_FB_DEV") == "1",
            on_leave=self.canvas.setFocus,
            parent=self._right_stack,
        )
        self._right_rail = _Rail("formBuilder.rightRail", self._right_stack)
        self._right_rail.add_button(
            "formBuilder.rightRail.properties",
            "Properties",
            lambda: self._focus_inspector_tab(TabId.PROPERTIES),
        )
        self._right_rail.add_button(
            "formBuilder.rightRail.behavior",
            "Behavior",
            lambda: self._focus_inspector_tab(TabId.BEHAVIOR),
        )
        self._right_stack.addWidget(self.inspector)
        self._right_stack.addWidget(self._right_rail)
        self._splitter.addWidget(self._left_stack)
        self._splitter.addWidget(self.canvas)
        self._splitter.addWidget(self._right_stack)

        self._drawer = QFrame(self)
        self._drawer.setObjectName("formBuilder.drawer")
        drawer_layout = QVBoxLayout(self._drawer)
        drawer_layout.setContentsMargins(0, 0, 0, 0)
        pin_row = QHBoxLayout()
        self._pin = _tool("", "formBuilder.pin", "Keep this pane open", self._drawer)
        self._pin.setToolButtonStyle(_button_style("ToolButtonIconOnly"))
        self._pin.clicked.connect(self._pin_clicked)
        pin_row.addStretch(1)
        pin_row.addWidget(self._pin)
        drawer_layout.addLayout(pin_row)
        self._drawer_host = QWidget(self._drawer)
        self._drawer_host_layout = QVBoxLayout(self._drawer_host)
        self._drawer_host_layout.setContentsMargins(0, 0, 0, 0)
        drawer_layout.addWidget(self._drawer_host, 1)
        self._drawer.hide()
        self._drawer_side = ""

    def canvas_view(self) -> FormCanvas:
        return self.canvas

    def refresh(self, selected: Optional[NodeId], outline: str = "rebuild") -> None:
        document = self._session.document
        if outline == "patch":
            self.outline.patch_labels(document, selected)
        elif outline == "keep":
            self.outline.show_current(selected)
        else:
            self.outline.rebuild(document, selected)
        self.canvas.refresh_chip()

    def set_drawer_listener(self, callback: Callable[[], None]) -> None:
        self._drawer_listener = callback

    def apply_plan(self, plan: LayoutPlan) -> None:
        self._plan = plan
        self.inspector.set_short(plan.short)
        self.inspector.set_compact(plan.density == "compact")
        self._apply_padding(plan.padding)
        self._apply_short(plan.stack_left)
        if plan.left_docked:
            self._dock("left")
        else:
            self._show_rail("left")
        if plan.inspector_docked:
            self._dock("right")
        else:
            self._show_rail("right")
        self._size_panes(plan)
        self._place_drawer()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self.outline.set_hover_fill(tokens.tree_hover_bg)
        self.outline.set_drop_color(tokens.accent)
        for name, glyph in _RAIL_GLYPHS.items():
            button = self.findChild(QToolButton, name)
            if isinstance(button, QToolButton):
                _paint_glyph(button, glyph, tokens, 16 if name == "formBuilder.pin" else 20)
        width = tokens.focus_border_width
        self.setStyleSheet(
            "QWidget#formBuilder\\.workbench, QWidget#formBuilder\\.outline,"
            " QWidget#formBuilder\\.insert, QWidget#formBuilder\\.inspector,"
            " QWidget#formBuilder\\.leftBody, QWidget#formBuilder\\.leftRail,"
            " QWidget#formBuilder\\.rightRail { background: %s; color: %s; }"
            "QTreeWidget#formBuilder\\.structure { background: %s; color: %s; border: 1px solid %s; }"
            "QTreeWidget#formBuilder\\.structure::item:selected { background: %s; color: %s; }"
            "QTreeWidget#formBuilder\\.structure:focus { border: %dpx solid %s; }"
            "QLabel#formBuilder\\.noticeText { color: %s; background: transparent; }"
            "QLabel#formBuilder\\.insertBody { color: %s; background: transparent; border: none; }"
            "QWidget#formBuilder\\.sectionHeader { background: transparent; color: %s; border: none; }"
            "QWidget#formBuilder\\.sectionHeader:focus { border: %dpx solid %s; }"
            "QLabel#formBuilder\\.sectionTitle {"
            " color: %s; background: transparent; border: none;"
            " font-size: 10px; font-weight: 600; letter-spacing: 0.5px; }"
            "QToolButton#formBuilder\\.sectionExtra { font-size: 14px; min-width: 24px; min-height: 24px;"
            " border: none; background: transparent; padding: 0; }"
            "QToolButton#formBuilder\\.pin { border: none; background: transparent; padding: 2px 8px; }"
            "QLabel#formBuilder\\.railLabel {"
            " color: %s; background: transparent; border: none; font-size: 8px; }"
            "QFrame#formBuilder\\.notice, QFrame#formBuilder\\.drawer {"
            " background: %s; color: %s; border: 1px solid %s; }"
            "QTabWidget#formBuilder\\.inspectorTabs::pane, QTabWidget#formBuilder\\.leftTabs::pane {"
            " background: %s; color: %s; border: 1px solid %s; }"
            "QTabWidget#formBuilder\\.inspectorTabs QTabBar::tab,"
            " QTabWidget#formBuilder\\.leftTabs QTabBar::tab {"
            " background: %s; color: %s; border: 1px solid %s; padding: 4px 8px; }"
            "QTabWidget#formBuilder\\.inspectorTabs QTabBar::tab:selected,"
            " QTabWidget#formBuilder\\.leftTabs QTabBar::tab:selected {"
            " background: %s; color: %s; }"
            "%s"
            "%s"
            % (
                tokens.panel_bg,
                tokens.text_primary,
                tokens.editor_bg,
                tokens.text_primary,
                tokens.border,
                tokens.tree_selected_bg,
                tokens.text_primary,
                width,
                tokens.accent,
                tokens.text_primary,
                tokens.text_muted,
                tokens.text_primary,
                width,
                tokens.accent,
                tokens.text_muted,
                tokens.text_primary,
                tokens.panel_bg,
                tokens.text_primary,
                tokens.border,
                tokens.panel_bg,
                tokens.text_primary,
                tokens.border,
                tokens.panel_bg,
                tokens.text_primary,
                tokens.border,
                tokens.tree_selected_bg,
                tokens.text_primary,
                _splitter_qss(tokens),
                flat_tool_button_qss(
                    tokens,
                    (
                        "QToolButton#formBuilder\\.leftRail\\.outline",
                        "QToolButton#formBuilder\\.leftRail\\.insert",
                        "QToolButton#formBuilder\\.rightRail\\.properties",
                        "QToolButton#formBuilder\\.rightRail\\.behavior",
                        "QToolButton#formBuilder\\.sectionExtra",
                    ),
                ),
            )
        )
        self.canvas.apply_theme(tokens)
        self.inspector.apply_chrome(chrome_for(tokens))
        self.inspector.set_link_color(problems_link_color(tokens))

    def open_left(self) -> None:
        self._open_drawer("left")

    def open_right(self) -> None:
        self._open_drawer("right")

    def close_drawers(self) -> None:
        if not self._left_open and not self._right_open:
            return
        self._park_drawer_child()
        self._left_open = False
        self._right_open = False
        self._drawer.hide()
        plan = self._plan
        if plan is not None:
            self.apply_plan(plan)
        self._notify_drawer()

    def drawer_open(self) -> bool:
        return self._left_open or self._right_open

    def focus_outline(self) -> None:
        if self._plan is not None and not self._plan.left_docked:
            self.open_left()
        if self._plan is not None and self._plan.stack_left:
            self._left_tabs.setCurrentWidget(self.outline)
        self.outline.tree.setFocus()

    def focus_insert(self) -> None:
        if self._plan is not None and not self._plan.left_docked:
            self.open_left()
        if self._plan is not None and self._plan.stack_left:
            self._left_tabs.setCurrentWidget(self.insert)
        self.insert.body.setFocus()

    def _place_tile(self, key: str) -> None:
        tile = tile_for(key)
        fragment = fragment_for(key)
        if tile is None or fragment is None:
            return
        payload = DropPayload(tile[1])
        current = self._session.selection.state.current
        commands = auto_commands(self._session.document, current, payload, fragment)
        if not commands:
            return
        try:
            with self._session.log.transaction("Drop") as txn:
                for command in commands:
                    txn.execute(command)
        except CommandRejected:
            return
        self.canvas.setFocus()
        if any(isinstance(command, InsertFormRow) for command in commands):
            self.canvas.send(EditTextAsked())

    def _preview_insert(self, key: Optional[str]) -> None:
        self.canvas.set_insert_preview(key)
        self.insert.set_caption("" if key is None else self.canvas.preview_sentence())

    def _cancel_place(self) -> None:
        self.canvas.send(PlaceDrop(CanvasPoint(0, 0), True, None, True))

    def _focus_inspector_tab(self, tab: TabId) -> None:
        if self._plan is not None and not self._plan.inspector_docked:
            self.open_right()
        self.inspector.focus_tab(tab)

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        if self._plan is not None:
            self._size_panes(self._plan)
        self._place_drawer()

    def _apply_short(self, stacked: bool) -> None:
        if stacked:
            if self._left_tabs.count() == 0:
                self._left_tabs.addTab(self.outline, "Outline")
                self._left_tabs.addTab(self.insert, "Insert")
            self._left_split.hide()
            self._left_tabs.show()
            return
        if self._left_split.indexOf(self.outline) < 0:
            self._left_tabs.removeTab(self._left_tabs.indexOf(self.outline))
            self._left_tabs.removeTab(self._left_tabs.indexOf(self.insert))
            self._left_split.addWidget(self.outline)
            self._left_split.addWidget(self.insert)
        self.outline.show()
        self.insert.show()
        self._left_tabs.hide()
        self._left_split.show()
        height = max(self._left_split.height(), 240)
        top = height * 55 // 100
        self._left_split.setSizes([top, max(80, height - top)])

    def _show_rail(self, side: str) -> None:
        if side == "left" and not self._left_open:
            self._left_stack.setCurrentWidget(self._left_rail)
        if side == "right" and not self._right_open:
            self._right_stack.setCurrentWidget(self._right_rail)

    def _dock(self, side: str) -> None:
        if side == "left":
            self._left_open = False
            self._return_body("left")
            self._left_stack.setCurrentWidget(self._left_body)
        else:
            self._right_open = False
            self._return_body("right")
            self._right_stack.setCurrentWidget(self.inspector)
        if not self._left_open and not self._right_open:
            self._drawer.hide()
        self._notify_drawer()

    def _open_drawer(self, side: str) -> None:
        self._park_drawer_child()
        self._left_open = side == "left"
        self._right_open = side == "right"
        self._drawer_side = side
        body = self._left_body if side == "left" else self.inspector
        self._drawer_host_layout.addWidget(body)
        body.show()
        if side == "left":
            self._left_stack.setCurrentWidget(self._left_rail)
        else:
            self._right_stack.setCurrentWidget(self._right_rail)
        self._drawer.show()
        self._drawer.raise_()
        self._place_drawer()
        self._notify_drawer()

    def _notify_drawer(self) -> None:
        listener = self._drawer_listener
        if listener is not None:
            listener()

    def _apply_padding(self, padding: int) -> None:
        for pane in (self.outline, self.insert, self.inspector):
            layout = pane.layout()
            if layout is not None:
                layout.setContentsMargins(padding, padding, padding, padding)

    def _park_drawer_child(self) -> None:
        if self._drawer_host_layout.count() == 0:
            return
        self._return_body(self._drawer_side)

    def _return_body(self, side: str) -> None:
        if side == "left":
            if self._left_body.parent() is not self._left_stack:
                self._left_stack.insertWidget(0, self._left_body)
        elif side == "right":
            if self.inspector.parent() is not self._right_stack:
                self._right_stack.insertWidget(0, self.inspector)

    def _pin_clicked(self) -> None:
        if self._drawer_side == "left":
            self._on_pin_left()
        elif self._drawer_side == "right":
            self._on_pin_inspector()

    def _place_drawer(self) -> None:
        if self._drawer.isHidden() or self._plan is None:
            return
        width = self._plan.drawer_width if self._drawer_side == "left" else self._plan.inspector_drawer
        x = RAIL_WIDTH if self._drawer_side == "left" else max(0, self.width() - RAIL_WIDTH - width)
        self._drawer.setGeometry(x, 0, width, self.height())
        self._drawer.raise_()

    def _remember_widths(self, _pos: int, _index: int) -> None:
        if self._applying:
            return
        plan = self._plan
        if plan is None or plan.density != "wide" or not plan.left_docked or not plan.inspector_docked:
            return
        sizes = self._splitter.sizes()
        if len(sizes) < 3:
            return
        self._on_widths(sizes[0], sizes[2])

    def _size_panes(self, plan: LayoutPlan) -> None:
        left = self._left_stack
        right = self._right_stack
        if plan.density == "wide" and plan.left_docked:
            left.setMinimumWidth(LEFT_MIN)
            left.setMaximumWidth(LEFT_MAX)
        else:
            left.setMinimumWidth(plan.left_width)
            left.setMaximumWidth(plan.left_width)
        if plan.density == "wide" and plan.inspector_docked:
            right.setMinimumWidth(INSPECTOR_MIN)
            right.setMaximumWidth(INSPECTOR_MAX)
        else:
            right.setMinimumWidth(plan.inspector_width)
            right.setMaximumWidth(plan.inspector_width)
        handle = self._splitter.handleWidth()
        canvas = max(0, self.width() - plan.left_width - plan.inspector_width - handle * 2)
        self._applying = True
        try:
            self._splitter.setSizes([plan.left_width, canvas, plan.inspector_width])
        finally:
            self._applying = False


__all__ = ["FormToolbar", "FormWorkbench", "NoticeBar", "problems_link_color"]
