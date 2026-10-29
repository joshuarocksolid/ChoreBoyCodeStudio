"""Workbench panes and the tab toolbar (UX-WB-001..003, UX-RESP).

Widths come from a ``LayoutPlan``. This module does not decide breakpoints.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

from app.qt.QtCore import QEvent, QItemSelectionModel, QMimeData, QObject, QPoint, QRect, QSize, Qt, QTimer
from app.qt.QtGui import QBrush, QColor, QDrag, QIcon
from app.qt.QtWidgets import (
    QActionGroup,
    QApplication,
    QPlainTextEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value, event_pos

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog_ext.drop import InsertFormRow
from app.features.form_builder.engine.commands.drop_plan import auto_commands
from app.features.form_builder.engine.commands.participants import default_registry
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.outline import (
    ConfirmGesture,
    DropGesture,
    FilterGesture,
    InPageSlot,
    InsertGesture,
    KeyGesture,
    OutlineCursor,
    OutlineForest,
    OutlineWorld,
    RenameGesture,
    captions_touched,
    claims_key,
    filter_mask,
    layout_row,
    outline_mode,
    patch_captions,
    patch_structure,
    plan,
    project,
)
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
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
    tile_for,
)
from app.features.form_builder.engine.commands.drop_plan import auto_target
from app.features.form_builder.engine.query.drop_target import (
    CENTRAL_NOTE,
    AcceptedDrop,
    DropPayload,
    NoDrop,
    OutlineRow,
    RefusedDrop,
    blocked_ids,
    central_redirect,
    resolve_outline,
)
from app.features.form_builder.integration.insert_memory import LazyInsertMemory
from app.features.form_builder.qtside.insert.catalog import in_sentence, load_catalog
from app.features.form_builder.qtside.insert.delegate import ROW_ROLE, EntryDelegate
from app.features.form_builder.qtside.insert.header import PaneHeader
from app.features.form_builder.qtside.insert.pane import InsertPane
from app.features.form_builder.qtside.insert.rows import ENTRY, Row, quick_rows
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint
from app.features.form_builder.qtside.icons import paint_glyph
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.integration.canvas import FormCanvas, _drop_payload
from app.features.form_builder.integration.clipboard_actions import publish_xml
from app.features.form_builder.engine.query import actions as q_actions
from app.features.form_builder.integration.workbench_ext import LeftSection, WorkbenchSlots, default_slots
from app.features.form_builder.integration.pieces import (
    piece_for_ids,
    renamed_pieces,
    without_piece,
)
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
from app.features.form_builder.integration.outline_bind import key_gesture, perform
from app.features.form_builder.integration.toast import CommandToast, ToastNote, undo_matches
from app.features.form_builder.qtside.inspector import InspectorPane, TabId
from app.features.form_builder.qtside.outline.delegate import (
    CAPTION,
    EXTRA,
    FAINT,
    PROBLEM,
    TONE,
    OutlineRowDelegate,
)
from app.features.form_builder.qtside.outline.friendly import friendly_of
from app.features.form_builder.qtside.outline.methods import window_methods
from app.features.form_builder.qtside.inspector.api import GroupId
from app.features.form_builder.qtside.realize.api import Realizer
from app.shell.theme_tokens import ShellThemeTokens
from app.shell.toolbar_style import flat_tool_button_qss, mode_group_qss

logger = logging.getLogger(__name__)

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


_NAME_ROW_PX = 24

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
_SHORT_HEIGHT = 560
_UNDER_MIN = 160
_CANVAS_MIN = 200
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

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Body text on the panel, like the rest of the tab: 4.5:1, 7:1 in high contrast.

        The bar is the surface's child, not the workbench's, so the workbench sheet never reached it.
        """
        self.setStyleSheet(
            "QFrame#formBuilder\\.notice { background: %s; border: 1px solid %s; }"
            "QLabel#formBuilder\\.noticeText { color: %s; background: transparent; border: none; }"
            "QPushButton#formBuilder\\.noticeButton {"
            " color: %s; background: %s; border: 1px solid %s; padding: 2px 8px; }"
            "QPushButton#formBuilder\\.noticeButton:focus { border: %dpx solid %s; }"
            % (
                tokens.panel_bg,
                tokens.border,
                tokens.text_primary,
                tokens.text_primary,
                tokens.input_bg,
                tokens.border,
                tokens.focus_border_width,
                tokens.accent,
            )
        )


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

        self.tab_order = _tool("Tab order", "formBuilder.tabOrder", "Tab order (F8)", self)
        self.tab_order.setCheckable(True)
        self.buddies = _tool("Buddies", "formBuilder.buddies", "Buddies (F7)", self)
        self.buddies.setCheckable(True)
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

        self.preview = _tool("", "formBuilder.preview", "Run the form with F5.", self)
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
        self._text_menu_action = self._menu.addAction("Text size")
        self._text_menu_action.setEnabled(False)
        self._widths_menu_action = self._menu.addAction("Two widths")
        self._widths_menu_action.setEnabled(False)
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

    def attach_preview(self, preview: object) -> None:
        """Turn on text size and two widths. Both stay off the document."""
        self.text_size.setEnabled(True)
        self.text_size.setToolTip("Text size")
        self.text_size.setAccessibleName("Text size")
        self.two_widths.setEnabled(True)
        self.two_widths.setToolTip("Two widths")
        self.two_widths.setAccessibleName("Two widths")
        menu = QMenu(self.text_size)
        menu.setObjectName("formBuilder.textSizeMenu")
        menu.addSection("Text size")
        text_actions = []
        for label, factor in (("Smaller", 0.85), ("Normal", 1.0), ("Larger", 1.25), ("Largest", 1.5)):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, value=factor, target=preview: target.set_text_factor(value))
            text_actions.append((action, factor))
        menu.addSection("Screen scale")
        screen_actions = []
        for percent in (100, 125, 150, 200):
            action = menu.addAction("%d%%" % percent)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, value=percent, target=preview: target.set_screen(value))
            screen_actions.append((action, percent))

        def _mark_preview() -> None:
            choice = preview.preview_choice()
            factor, screen, absolute = choice
            for item, value in text_actions:
                item.setChecked(absolute is None and abs(float(factor) - float(value)) < 0.001)
            for item, value in screen_actions:
                item.setChecked(int(screen) == int(value))

        menu.aboutToShow.connect(_mark_preview)
        _mark_preview()
        self.text_size.setMenu(menu)
        popup = getattr(getattr(QToolButton, "ToolButtonPopupMode", QToolButton), "InstantPopup")
        self.text_size.setPopupMode(popup)
        self.two_widths.clicked.connect(preview.toggle_widths)
        wide = QMenu(self.two_widths)
        wide.setObjectName("formBuilder.wideMenu")
        for pixels in (1280, 1366, 1920):
            action = wide.addAction("Wide · %d px" % pixels)
            action.triggered.connect(lambda _checked=False, value=pixels, target=preview: target.set_wide(value))
        self._text_menu_action.setEnabled(True)
        self._text_menu_action.triggered.connect(self.text_size.showMenu)
        self._widths_menu_action.setEnabled(True)
        self._widths_menu_action.triggered.connect(preview.toggle_widths)
        self.two_widths.setMenu(wide)
        delayed = getattr(getattr(QToolButton, "ToolButtonPopupMode", QToolButton), "DelayedPopup")
        self.two_widths.setPopupMode(delayed)

    def attach_preview_options(self, control: object, on_preview: Callable[[], None]) -> None:
        """Style and Screen in the Aa menu (UX-PREV-001, R3 178 and 179), and the Preview button (UX-WB-003).

        Both submenus start with the caption that says the canvas never changes (D21). They are
        rebuilt each time the menu opens, so the styles the preview runtime reported and the
        user's screens are always current.
        """
        menu = self.text_size.menu()
        if menu is None:
            return
        self.preview.setEnabled(True)
        self.preview.setToolTip("Preview (Ctrl+Shift+R)")
        self.preview.setAccessibleName("Preview")
        self.preview.clicked.connect(lambda _checked=False: on_preview())
        menu.addMenu("Style").setObjectName("formBuilder.previewStyleMenu")
        menu.addMenu("Screen").setObjectName("formBuilder.previewScreenMenu")

        def rebuild() -> None:
            # Looked up each time: the menus belong to Qt, and a Python wrapper kept from addMenu can go stale.
            style_menu = menu.findChild(QMenu, "formBuilder.previewStyleMenu")
            screen_menu = menu.findChild(QMenu, "formBuilder.previewScreenMenu")
            if style_menu is not None:
                _fill_style_menu(style_menu, control)
            if screen_menu is not None:
                _fill_screen_menu(screen_menu, control)

        menu.aboutToShow.connect(rebuild)
        rebuild()

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


def _fill_style_menu(menu: QMenu, control: Any) -> None:
    """Fusion first (checked by default), then every style the preview runtime reports."""
    from app.features.form_builder.engine.preview_options import CAPTION, style_label

    menu.clear()
    menu.addSection(CAPTION)
    group = QActionGroup(menu)
    group.setExclusive(True)
    chosen = control.choices.style.lower()
    for name in control.styles():
        action = menu.addAction(style_label(name))
        action.setCheckable(True)
        action.setChecked(name.lower() == chosen)
        action.setObjectName("formBuilder.previewStyle.%s" % name)
        group.addAction(action)
        action.triggered.connect(lambda _checked=False, value=name: control.set_style(value))


def _fill_screen_menu(menu: QMenu, control: Any) -> None:
    """The built-in and the user's screens, then Add a screen\u2026."""
    from app.features.form_builder.engine.preview_options import ADD_SCREEN, CAPTION

    menu.clear()
    menu.addSection(CAPTION)
    group = QActionGroup(menu)
    group.setExclusive(True)
    chosen = control.current_profile().name
    for profile in control.profiles:
        action = menu.addAction(profile.label)
        action.setCheckable(True)
        action.setChecked(profile.name == chosen)
        action.setObjectName("formBuilder.previewScreen.%s" % profile.name)
        group.addAction(action)
        action.triggered.connect(lambda _checked=False, value=profile.name: control.set_screen(value))
    menu.addSeparator()
    add = menu.addAction(ADD_SCREEN)
    add.setObjectName("formBuilder.previewScreenAdd")
    add.triggered.connect(lambda _checked=False: control.add_screen_dialog())


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
        self.header = PaneHeader("Outline", self, self._toggle)
        self._add_button = self.header.add_extra("+", "Insert a widget")
        self._add_button.setEnabled(True)
        self._add_button.clicked.connect(self._open_insert)
        self._find_button = self.header.add_extra("\u2315", "Find a widget")
        self._find_button.setEnabled(True)
        self._find_button.clicked.connect(self._open_filter)
        layout.addWidget(self.header)
        self._filter = QLineEdit(self)
        self._filter.setObjectName("formBuilder.outlineFilter")
        self._filter.setAccessibleName("Find a widget")
        self._filter.setPlaceholderText("Find a widget")
        self._filter.textChanged.connect(self._filter_edited)
        self._filter.hide()
        layout.addWidget(self._filter)
        self._empty = QWidget(self)
        self._empty.setObjectName("formBuilder.outlineEmptyRow")
        empty_row = QHBoxLayout(self._empty)
        empty_row.setContentsMargins(8, 4, 8, 4)
        self._empty_label = QLabel(self._empty)
        self._empty_label.setObjectName("formBuilder.outlineEmpty")
        self._empty_label.setWordWrap(True)
        empty_row.addWidget(self._empty_label, 1)
        clear = QPushButton("Clear", self._empty)
        clear.setObjectName("formBuilder.outlineClear")
        clear.clicked.connect(self._clear_filter)
        empty_row.addWidget(clear)
        self._empty.hide()
        layout.addWidget(self._empty)
        self.tree = QTreeWidget(self)
        self.tree.setObjectName("formBuilder.structure")
        self.tree.setAccessibleName("Form structure")
        self.tree.setHeaderHidden(True)
        self.tree.header().setStretchLastSection(True)
        scroll_off = getattr(getattr(Qt, "ScrollBarPolicy", Qt), "ScrollBarAlwaysOff")
        self.tree.setHorizontalScrollBarPolicy(scroll_off)
        # Rows share one height. Qt then skips a per-item height walk on scroll and reorder.
        self.tree.setUniformRowHeights(True)
        self.tree.setFocusPolicy(_strong())
        elide = getattr(getattr(Qt, "TextElideMode", Qt), "ElideRight")
        self.tree.setTextElideMode(elide)
        self.tree.setIndentation(12)
        self._delegate = OutlineRowDelegate(self.tree)
        self.tree.setItemDelegate(self._delegate)
        triggers = getattr(self.tree, "EditTrigger", type(self.tree))
        self.tree.setEditTriggers(getattr(triggers, "NoEditTriggers", 0))
        mode = getattr(self.tree, "SelectionMode", type(self.tree))
        self.tree.setSelectionMode(getattr(mode, "ExtendedSelection"))
        self.tree.currentItemChanged.connect(self._current_changed)
        self.tree.itemExpanded.connect(lambda item: self._note_expanded(item, True))
        self.tree.itemCollapsed.connect(lambda item: self._note_expanded(item, False))
        self.tree.itemDoubleClicked.connect(self._rename_item)
        self.tree.setMouseTracking(True)
        self.tree.viewport().setMouseTracking(True)
        self.tree.itemEntered.connect(self._item_entered)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.viewport().setAcceptDrops(True)
        self.tree.viewport().installEventFilter(self)
        self.tree.installEventFilter(self)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu_requested)
        layout.addWidget(self.tree, 1)
        self._collapsed = False
        self._hover: Optional[NodeId] = None
        self._hover_fill = ""
        self._rows: Dict[int, QTreeWidgetItem] = {}
        self._current_item: Optional[QTreeWidgetItem] = None
        self._send_hover: Optional[Callable[[HoverFrom], None]] = None
        self._open_menu: Optional[Callable[[NodeId, QPoint], None]] = None
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
        self._mount_outline_tools()

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
        # New items: an open editor would sit over a row that is gone.
        self.finish_rename()
        self._document = document
        previous = self._forest
        self._forest = project(document, self._problem_ids(), friendly_of)
        self._revision = document.revision
        self._install(self._forest, previous)
        self.show_current(selected)
        self._paint_row(self._hover)

    def patch_rows(
        self,
        document: UiDocument,
        selected: Optional[NodeId],
        touched: Sequence[NodeId],
    ) -> None:
        """Update caption fields on ``touched`` rows. Other items stay the same objects."""
        self._document = document
        forest = self._forest
        if forest is None:
            self.rebuild(document, selected)
            return
        nodes = tuple(touched)
        if not nodes:
            self._revision = document.revision
            self.show_current(selected)
            return
        patch_captions(forest, document, nodes, self._problem_ids(), friendly_of)
        self._revision = document.revision
        states = self._filter_states(forest)
        for node in nodes:
            row = forest.row(node)
            item = self._rows.get(int(node))
            if row is None or item is None:
                if document.contains(node) and row is not None:
                    self.rebuild(document, selected)
                    return
                continue
            self._write_item(item, row, states)
        self.show_current(selected)

    def apply_change(self, document: UiDocument, selected: Optional[NodeId], change: object) -> None:
        """Patch rows for one ChangeSet. Only open and replace rebuild (CONTRACTS 12)."""
        mode = outline_mode(change, document) if change is not None else "rebuild"  # type: ignore[arg-type]
        if mode == "structure" and self._forest is not None:
            self.patch_structure(document, selected, change)
        elif mode == "captions":
            self.patch_rows(document, selected, captions_touched(change, document))  # type: ignore[arg-type]
        elif mode == "keep" and self._forest is not None:
            self._document = document
            self._revision = document.revision
            self.show_current(selected)
        else:
            self.rebuild(document, selected)

    def patch_structure(self, document: UiDocument, selected: Optional[NodeId], change: object) -> None:
        """Insert, take and move only the rows ``change`` touched. Untouched items stay put."""
        forest = self._forest
        if forest is None:
            self.rebuild(document, selected)
            return
        patch = patch_structure(forest, document, change, self._problem_ids(), friendly_of)  # type: ignore[arg-type]
        if patch is None:
            self.rebuild(document, selected)
            return
        # Rows shift under an open editor: end the rename like a rebuild does.
        self.finish_rename()
        self._document = document
        self._revision = document.revision
        self._blocked = True
        try:
            for node in patch.taken:
                item = self._rows.get(int(node))
                if item is not None:
                    self._take(item)
            for node in patch.dropped:
                self._rows.pop(int(node), None)
                self._closed.discard(node)
            states = self._filter_states(forest)
            role = int(getattr(Qt, "UserRole"))
            for node in patch.created:
                item = QTreeWidgetItem()
                item.setData(0, role, int(node))
                self._rows[int(node)] = item
                row = forest.row(node)
                if row is not None:
                    self._write_item(item, row, states)
            for node in patch.rewritten:
                item = self._rows.get(int(node))
                row = forest.row(node)
                if item is not None and row is not None:
                    self._write_item(item, row, states)
            root = self.tree.invisibleRootItem()
            for parent, node, index in patch.placed:
                holder = root if parent is None else self._rows.get(int(parent))
                item = self._rows.get(int(node))
                if holder is None or item is None:
                    raise LookupError(node)
                # Qt ignores insertChild for an item that still has a parent.
                holder.insertChild(min(index, holder.childCount()), item)
            for _parent, node, _index in patch.placed:
                self._restore_expansion(forest, node)
        except LookupError:
            self._blocked = False
            self.rebuild(document, selected)
            return
        self._blocked = False
        if self._filter_text:
            self._apply_empty(filter_mask(forest, self._filter_text))
        self.show_current(selected)
        self._reselect()

    def _filter_states(self, forest: OutlineForest) -> Dict[NodeId, str]:
        """Row filter states. Empty means every row matches, which costs nothing to know."""
        if not self._filter_text:
            return {}
        return dict(filter_mask(forest, self._filter_text).state)

    def _restore_expansion(self, forest: OutlineForest, node: NodeId) -> None:
        """A taken item forgets that it and its children were open. O(subtree)."""
        for each in forest.subtree(node):
            item = self._rows.get(int(each))
            if item is None or item.childCount() == 0:
                continue
            opened = each not in self._closed
            if item.isExpanded() != opened:
                item.setExpanded(opened)

    def _reselect(self) -> None:
        """Re-mark selected rows a take/insert unselected. O(selection)."""
        session = self._session
        if session is None:
            return
        self._blocked = True
        for node in session.selection.state.ids:
            item = self._rows.get(int(node))
            if item is not None and not item.isSelected():
                item.setSelected(True)
        self._blocked = False

    def show_current(self, selected: Optional[NodeId]) -> None:
        """Move the current row. Does not rebuild the tree."""
        if selected is None:
            item = None
        else:
            item = self._rows.get(int(selected))
            if item is None:
                return
        previous = self._current_item
        if item is previous and (item is None or item.isSelected()) and self._highlight_matches(item):
            return
        self._blocked = True
        scrolling = self.tree.hasAutoScroll()
        self.tree.setAutoScroll(False)
        try:
            if item is None:
                self.tree.setCurrentItem(None)
                self.tree.clearSelection()
            else:
                command = getattr(QItemSelectionModel, "SelectionFlag", QItemSelectionModel)
                ids = () if self._session is None else self._session.selection.state.ids
                if len(ids) > 1:
                    flags = getattr(command, "Current") | getattr(command, "Rows")
                    self.tree.setCurrentItem(item, 0, flags)
                    for node in ids:
                        row = self._rows.get(int(node))
                        if row is not None and not row.isSelected():
                            row.setSelected(True)
                else:
                    flags = getattr(command, "ClearAndSelect") | getattr(command, "Rows")
                    self.tree.setCurrentItem(item, 0, flags)
            self._current_item = item
        finally:
            self.tree.setAutoScroll(scrolling)
            self._blocked = False
        self.tree.viewport().update()
        if item is not None:
            # Reveal after the frame: the row test runs the tree's pending
            # layout, which must not sit inside the select itself.
            self._reveal_item = item
            QTimer.singleShot(0, self._reveal_current)

    def _highlight_matches(self, item: object) -> bool:
        """True when the tree lights exactly the selected rows, so no stale row stays lit."""
        if item is None:
            return True
        ids = () if self._session is None else self._session.selection.state.ids
        lit = self.tree.selectedItems()
        return len(lit) == max(len(ids), 1)

    def _reveal_current(self) -> None:
        """Scroll the current row into view only when it is off screen."""
        item = getattr(self, "_reveal_item", None)
        self._reveal_item = None
        if item is None or item is not self._current_item:
            return
        try:
            row = self.tree.visualItemRect(item)
        except RuntimeError:
            return
        if row.isValid() and self.tree.viewport().rect().contains(row):
            return
        self.tree.scrollToItem(item)

    def patch_labels(self, document: UiDocument, selected: Optional[NodeId]) -> None:
        forest = self._forest
        nodes = () if forest is None else tuple(row.node for row in forest.rows)
        self.patch_rows(document, selected, nodes)

    def set_hover_target(self, send: Callable[[HoverFrom], None]) -> None:
        self._send_hover = send

    def set_menu_target(self, open_menu: Callable[[NodeId, QPoint], None]) -> None:
        """``open_menu(node, at)`` runs for a right click or a menu key on a row. ``at`` is global."""
        self._open_menu = open_menu

    def request_menu(self) -> None:
        """The context menu of the current row, beside that row."""
        item = self.tree.currentItem()
        if item is not None:
            self._menu_requested(self.tree.visualItemRect(item).center())

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

    def _paint_drop_line(self, into: bool = False) -> None:
        color = self._drop_color or self.tree.palette().highlight().color().name()
        if into:
            self._drop_line.setStyleSheet(
                "QFrame#formBuilder\\.outlineDrop { background: transparent; border: 2px solid %s; }" % color
            )
            return
        self._drop_line.setStyleSheet(
            "QFrame#formBuilder\\.outlineDrop { background: %s; border: none; }" % color
        )

    def _show_line(self, target: object) -> None:
        if not isinstance(target, AcceptedDrop):
            self._drop_line.hide()
            return
        rect = target.indicator.rect
        into = bool(target.indicator.dashed)
        height = max(rect.height, 2)
        self._paint_drop_line(into)
        self._drop_line.setFixedHeight(height)
        self._drop_line.setGeometry(rect.x, rect.y, max(rect.width, 1), height)
        self._drop_line.show()
        self._drop_line.raise_()
        if target.sentence:
            self.report(target.sentence)

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
        body, key, fragment = parsed
        post(PlaceAsked(CanvasPoint(pos.x(), pos.y()), body, key, fragment))

    def _post_target(self, pos: QPoint, drop: bool) -> None:
        post = self._post
        if post is None:
            return
        self._arm_row_spring(pos)
        if drop and self._deliver_page_drop(pos):
            self._drop_line.hide()
            return
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
            depth = 0
            forest = self._forest
            if forest is not None:
                found = forest.row(NodeId(int(node_id)))
                if found is not None:
                    depth = found.depth
            rows.append(
                OutlineRow(
                    NodeId(int(node_id)),
                    visual.y(),
                    visual.height(),
                    max(visual.width(), 1),
                    visual.x(),
                    depth,
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
        return resolve_outline(
            doc,
            self._outline_rows(),
            pos.y(),
            payload,
            blocked_ids(doc, payload.source_ids),
            x=pos.x(),
        )

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
        kind = _event_kind(event)
        if kind == "FocusOut" and watched is getattr(self, "_editor", None) and _leaves_for_good(event):
            self.end_rename()
            return False
        if kind == "ShortcutOverride" and self._claim_override(watched, event):
            event.accept()
            return True
        if kind == "KeyPress":
            confirm = getattr(self, "_confirm", None)
            if (
                confirm is not None
                and watched in (confirm, getattr(self, "_delete_button", None), getattr(self, "_cancel_button", None))
                and self._on_confirm_key(event)
            ):
                return True
            if watched is self.tree and self._on_tree_key(event):
                return True
            if watched is self._editor and self._on_editor_key(event):
                return True
            if watched is self._filter and self._on_filter_key(event):
                return True
            if watched is self._insert_list and self._on_insert_key(event):
                return True
            if watched is self._insert_filter and self._on_quick_filter_key(event):
                return True
        if watched is not self.tree.viewport():
            return super().eventFilter(watched, event)
        kind = _event_kind(event)
        if kind == "Resize" and self._renaming is not None:
            # A scrollbar that appears (the error row grew) narrows the viewport: refit.
            self._refit_rename()
        if kind == "Leave":
            self._announce_hover(None)
            self._press = None
        elif kind == "MouseButtonPress":
            self._press = event_pos(event)
            self._remember_click_mods(event)
        elif kind == "MouseButtonRelease":
            self._remember_click_mods(event)
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

    def _menu_requested(self, pos: QPoint) -> None:
        item = self.tree.itemAt(pos)
        raw = None if item is None else item.data(0, getattr(Qt, "UserRole"))
        if raw is None or self._open_menu is None:
            return
        self._open_menu(NodeId(int(raw)), self.tree.viewport().mapToGlobal(pos))

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
        if self._renaming is not None and int(raw) != int(self._renaming):
            self.end_rename()
        if self._mod_down("ShiftModifier"):
            self._select_span(_previous, current)
            return
        if self._mod_down("ControlModifier") or self._mod_down("MetaModifier"):
            self._toggle_row(current)
            return
        self._on_pick(NodeId(int(raw)))

    def _remember_click_mods(self, event: object) -> None:
        mods = getattr(event, "modifiers", None)
        self._click_mods = int(enum_value(mods())) if callable(mods) else 0

    def _mod_down(self, name: str) -> bool:
        mods = int(enum_value(QApplication.keyboardModifiers())) | int(self._click_mods)
        return bool(mods & int(enum_value(getattr(Qt, name))))

    def _select_span(self, previous: object, current: QTreeWidgetItem) -> None:
        items = self._visible_items()
        try:
            start = items.index(previous) if isinstance(previous, QTreeWidgetItem) else 0
            end = items.index(current)
        except ValueError:
            self._publish_tree_selection()
            return
        low, high = (start, end) if start <= end else (end, start)
        chosen = items[low : high + 1]
        self._blocked = True
        try:
            self.tree.clearSelection()
            for item in chosen:
                item.setSelected(True)
            command = getattr(QItemSelectionModel, "SelectionFlag", QItemSelectionModel)
            flags = getattr(command, "Current") | getattr(command, "Rows")
            self.tree.setCurrentItem(current, 0, flags)
            self._current_item = current
        finally:
            self._blocked = False
        self._publish_tree_selection()

    def _toggle_row(self, current: QTreeWidgetItem) -> None:
        session = self._session
        if session is None:
            return
        role = int(getattr(Qt, "UserRole"))
        raw = current.data(0, role)
        if raw is None:
            return
        node = NodeId(int(raw))
        ids = [item for item in session.selection.state.ids if int(item) != int(node)]
        if len(ids) == len(session.selection.state.ids):
            ids.append(node)
        self._blocked = True
        try:
            self.tree.clearSelection()
            for each in ids:
                row = self._rows.get(int(each))
                if row is not None:
                    row.setSelected(True)
            command = getattr(QItemSelectionModel, "SelectionFlag", QItemSelectionModel)
            flags = getattr(command, "Current") | getattr(command, "Rows")
            self.tree.setCurrentItem(current, 0, flags)
            self._current_item = current
        finally:
            self._blocked = False
        if ids:
            session.selection.set(tuple(ids), current=node if node in ids else ids[-1], source=SelectionSource.OUTLINE)
        else:
            session.selection.set((), source=SelectionSource.OUTLINE)

    def _visible_items(self) -> List[QTreeWidgetItem]:
        found: List[QTreeWidgetItem] = []

        def walk(item: QTreeWidgetItem) -> None:
            if item.isHidden():
                return
            found.append(item)
            if not item.isExpanded():
                return
            for index in range(item.childCount()):
                child = item.child(index)
                if child is not None:
                    walk(child)

        for index in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(index)
            if top is not None:
                walk(top)
        return found

    def _publish_tree_selection(self) -> None:
        session = self._session
        if session is None:
            return
        role = int(getattr(Qt, "UserRole"))
        ids = []
        for item in self.tree.selectedItems():
            raw = item.data(0, role)
            if raw is not None:
                ids.append(NodeId(int(raw)))
        if not ids:
            return
        current_item = self.tree.currentItem()
        current = ids[-1]
        if current_item is not None:
            raw = current_item.data(0, role)
            if raw is not None:
                current = NodeId(int(raw))
        session.selection.set(tuple(ids), current=current, source=SelectionSource.OUTLINE)

    def _mount_outline_tools(self) -> None:
        self._session: Optional[FormSession] = None
        self._place: Optional[Callable[[str], None]] = None
        self._preview: Optional[Callable[[Optional[str]], None]] = None
        self._status: Optional[Callable[[str], None]] = None
        self._forest: Optional[OutlineForest] = None
        self._revision = -1
        self._closed: Set[NodeId] = set()
        self._filter_text = ""
        self._anchor: Optional[NodeId] = None
        self._renaming: Optional[NodeId] = None
        self._return_focus: Optional[QWidget] = None
        self._insert_return: Optional[QWidget] = None
        self._click_mods = 0
        self._ask_ids: Tuple[NodeId, ...] = ()
        self._last_change: object = None
        self._log_sub: object = None
        self.run_command: Optional[Callable[[str], None]] = None
        self._name_color = ""
        self._faint_color = ""
        self._error_color = ""
        self._layout_color = ""
        self._toast_box: Optional[CommandToast] = None
        self._editor = QLineEdit(self.tree.viewport())
        self._editor.setObjectName("formBuilder.outlineRename")
        self._editor.setAccessibleName("Object name")
        self._editor.hide()
        self._editor.installEventFilter(self)
        self._error = QLabel(self.tree.viewport())
        self._error.setObjectName("formBuilder.outlineNameError")
        self._error.setWordWrap(True)
        self._error.hide()
        self._confirm = QFrame(self)
        self._confirm.setObjectName("formBuilder.outlineConfirm")
        confirm_layout = QVBoxLayout(self._confirm)
        self._confirm_text = QLabel(self._confirm)
        self._confirm_text.setObjectName("formBuilder.outlineDeleteText")
        self._confirm_text.setWordWrap(True)
        confirm_layout.addWidget(self._confirm_text)
        buttons = QHBoxLayout()
        delete = QPushButton("Delete", self._confirm)
        delete.setObjectName("formBuilder.outlineDelete")
        delete.clicked.connect(lambda: self._answer_delete(True))
        delete.installEventFilter(self)
        cancel = QPushButton("Cancel", self._confirm)
        cancel.setObjectName("formBuilder.outlineCancel")
        cancel.clicked.connect(lambda: self._answer_delete(False))
        cancel.installEventFilter(self)
        self._delete_button = delete
        self._cancel_button = cancel
        self._confirm.installEventFilter(self)
        self._after_confirm = None
        buttons.addWidget(delete)
        buttons.addWidget(cancel)
        confirm_layout.addLayout(buttons)
        self._confirm.hide()
        self._insert_pop = QFrame(self)
        self._insert_pop.setObjectName("formBuilder.outlineInsert")
        insert_layout = QVBoxLayout(self._insert_pop)
        insert_layout.setContentsMargins(0, 0, 0, 0)
        self._insert_filter = QLineEdit(self._insert_pop)
        self._insert_filter.setObjectName("formBuilder.outlineInsertFilter")
        self._insert_filter.setAccessibleName("Search widgets")
        self._insert_filter.setPlaceholderText("Search widgets")
        self._insert_filter.textChanged.connect(self._quick_filter_changed)
        self._insert_filter.installEventFilter(self)
        insert_layout.addWidget(self._insert_filter)
        self._insert_list = QListWidget(self._insert_pop)
        self._insert_list.setObjectName("formBuilder.outlineInsertList")
        self._quick_delegate = EntryDelegate(self._insert_list)
        self._quick_delegate.set_icons(False)
        self._quick_delegate.set_width(200)
        self._insert_list.setItemDelegate(self._quick_delegate)
        # Rows are sized to the viewport and elide. A sideways bar clips the name.
        scroll_off = getattr(getattr(Qt, "ScrollBarPolicy", Qt), "ScrollBarAlwaysOff")
        self._insert_list.setHorizontalScrollBarPolicy(scroll_off)
        self._insert_list.setResizeMode(QListView.ResizeMode.Adjust)
        self._insert_list.itemActivated.connect(self._activate_insert)
        self._insert_list.currentItemChanged.connect(lambda *_args: self._preview_insert_row())
        self._insert_list.installEventFilter(self)
        insert_layout.addWidget(self._insert_list)
        self._quick_recent: Callable[[], Tuple[str, ...]] = lambda: ()
        self._insert_pop.hide()
        self._filter.installEventFilter(self)

    def attach(
        self,
        session: FormSession,
        place: Callable[[str], None],
        preview: Optional[Callable[[Optional[str]], None]] = None,
    ) -> None:
        self._session = session
        self._place = place
        self._preview = preview
        previous = self._log_sub
        if previous is not None:
            previous.close()  # type: ignore[attr-defined]
        self._log_sub = session.log.subscribe(self._remember_change, priority=1)
        root = session.document.root
        class_name = root.class_name if isinstance(root, WidgetNode) else ""
        session.set_base_methods(window_methods(class_name))
        self.rebuild(session.document, session.selection.state.current)

    def set_status(self, report: Callable[[str], None]) -> None:
        self._status = report

    def session(self) -> FormSession:
        assert self._session is not None
        return self._session

    def focus_tree(self) -> None:
        self.tree.setFocus()

    def focus_editor(self) -> None:
        self._editor.setFocus()

    def consider(self, gesture: object) -> bool:
        session = self._session
        forest = self._forest
        if session is None or forest is None:
            return False
        effect = plan(session.document, forest, self._cursor(), gesture, self._world())
        return perform(self, effect)

    def note_edited(self) -> None:
        session = self._session
        forest = self._forest
        if session is None or forest is None:
            return
        document = session.document
        current = session.selection.state.current
        if self._revision == document.revision:
            self.show_current(current)
            return
        change = self._last_change
        if change is not None and getattr(change, "revision", None) == document.revision:
            self.apply_change(document, current, change)
            return
        self.rebuild(document, current)

    def _remember_change(self, change_set: object) -> None:
        self._last_change = change_set

    def show_selection(self, ids: Tuple[NodeId, ...], current: NodeId, anchor: NodeId) -> None:
        self._anchor = anchor
        session = self._session
        if session is not None:
            session.selection.set(ids, current=current, source=SelectionSource.OUTLINE)
        self._blocked = True
        self.tree.clearSelection()
        for node in ids:
            item = self._rows.get(int(node))
            if item is not None:
                item.setSelected(True)
        current_item = self._rows.get(int(current))
        self.tree.setCurrentItem(current_item)
        if current_item is not None:
            self.tree.scrollToItem(current_item)
        self._blocked = False

    def apply_expand(self, effect: object) -> None:
        node = effect.node  # type: ignore[attr-defined]
        expanded = bool(effect.expanded)  # type: ignore[attr-defined]
        if expanded:
            self._closed.discard(node)
        else:
            self._closed.add(node)
        item = self._rows.get(int(node))
        if item is not None:
            self._blocked = True
            item.setExpanded(expanded)
            self._blocked = False
        if not effect.select_child or self._forest is None or self._session is None:  # type: ignore[attr-defined]
            self.focus_tree()
            return
        for child in self._forest.children(node):
            child_item = self._rows.get(int(child.node))
            if child_item is not None and not child_item.isHidden():
                self.show_selection((child.node,), child.node, child.node)
                break
        self.focus_tree()

    def begin_rename(self, node: NodeId, *, return_to: Optional[QWidget] = None) -> None:
        forest = self._forest
        if forest is None:
            return
        row = forest.row(node)
        item = self._rows.get(int(node))
        if row is None or item is None:
            return
        self._confirm.hide()
        self._insert_pop.hide()
        self._release_rename_row()
        if return_to is not None:
            self._return_focus = return_to
        self._renaming = node
        session = self._session
        if session is not None:
            session.selection.set((node,), current=node, source=SelectionSource.OUTLINE)
        self.show_current(node)
        self._editor.setText(row.name)
        self._place_editor(item)
        self._error.hide()
        self._editor.show()
        self._editor.raise_()
        self._editor.setFocus()
        self._editor.selectAll()

    def finish_rename(self) -> Optional[QWidget]:
        """Close the editor and clear the renaming state. Every way out of a rename ends here."""
        had_focus = self._editor.hasFocus()
        target = self._return_focus
        self._return_focus = None
        self._release_rename_row()
        self._renaming = None
        if had_focus:
            # Hiding a focused editor would hand focus to whatever Qt picks next.
            if target is not None:
                target.setFocus()
            else:
                self.tree.setFocus()
        self._editor.hide()
        self._error.hide()
        return target

    def end_rename(self) -> None:
        """Focus left the editor or the row changed: keep a valid name, drop an invalid one."""
        node = self._renaming
        if node is None:
            return
        if not self.consider(RenameGesture(node, self._editor.text(), "blur")) and self._renaming is not None:
            self.finish_rename()

    def show_name_error(self, prose: str) -> None:
        self._error.setText(prose)
        item = None if self._renaming is None else self._rows.get(int(self._renaming))
        if item is None:
            self._error.show()
            self._error.raise_()
            return
        rect = self.tree.visualItemRect(item)
        width = max(self._visible_width(rect), 80)
        # The error wraps inside the visible part of the row, under the editor.
        wrapped = self._error.heightForWidth(width)
        extra = max(wrapped, self._error.sizeHint().height(), self._error.fontMetrics().height())
        self.tree.setUniformRowHeights(False)
        item.setData(0, EXTRA, extra)
        self.tree.doItemsLayout()
        rect = self.tree.visualItemRect(item)
        self._place_editor(item)
        editor = self._editor.geometry()
        self._editor.setGeometry(editor.x(), rect.y(), editor.width(), _NAME_ROW_PX)
        self._error.setGeometry(rect.x(), rect.y() + _NAME_ROW_PX, max(self._visible_width(rect), 80), extra)
        self._error.show()
        self._error.raise_()

    def _refit_rename(self) -> None:
        item = None if self._renaming is None else self._rows.get(int(self._renaming))
        if item is None:
            return
        if self._error.isVisible():
            self.show_name_error(self._error.text())
        else:
            self._place_editor(item)

    def _release_rename_row(self) -> None:
        item = None if self._renaming is None else self._rows.get(int(self._renaming))
        if item is not None:
            item.setData(0, EXTRA, 0)
        self.tree.setUniformRowHeights(True)

    def apply_filter(self, text: str, focus_tree: bool, select: Optional[NodeId]) -> None:
        self._filter_text = text
        self._filter.blockSignals(True)
        self._filter.setText(text)
        self._filter.blockSignals(False)
        forest = self._forest
        if forest is None:
            return
        mask = filter_mask(forest, text)
        states = dict(mask.state)
        for row in forest.rows:
            item = self._rows.get(int(row.node))
            if item is not None:
                self._write_item(item, row, states)
        self._apply_empty(mask)
        if select is not None and self._session is not None:
            self._anchor = select
            self._session.selection.set((select,), current=select, source=SelectionSource.OUTLINE)
            self.show_current(select)
        if focus_tree and not text:
            self._filter.hide()
            self.focus_tree()
            return
        self._filter.show()
        if focus_tree:
            self.focus_tree()
        else:
            self._filter.setFocus()

    def show_delete(
        self,
        prose: str,
        ids: Tuple[NodeId, ...],
        anchor: Optional[QRect] = None,
        on_done: Optional[Callable[[], None]] = None,
        avoid: Tuple[QRect, ...] = (),
    ) -> None:
        self._ask_ids = ids
        self._after_confirm = on_done
        self._confirm_text.setText(prose)
        # UX-CONT-004: a page ask confirms with "Delete page"; every other ask with "Delete".
        self._delete_button.setText("Delete page" if prose.startswith("Delete page") else "Delete")
        host = self._confirm_host(anchor)
        if self._confirm.parentWidget() is not host:
            self._confirm.setParent(host)
        margin = 8
        limit = max(host.width() - margin * 2, 64)
        self._confirm.setMaximumWidth(limit)
        self._confirm.setMinimumWidth(0)
        self._confirm_text.setMaximumWidth(max(limit - 16, 32))
        self._confirm.setMaximumHeight(max(host.height() - margin, 48))
        self._confirm.adjustSize()
        width = min(self._confirm.sizeHint().width(), limit)
        self._confirm.resize(width, min(self._confirm.sizeHint().height(), max(host.height() - margin, 48)))
        if anchor is not None:
            self._place_confirm_global(anchor, host, avoid)
        else:
            row = ids[0] if ids else self._current_node()
            item = None if row is None else self._rows.get(int(row))
            x = margin
            y = self.header.height()
            if item is not None:
                rect = self.tree.visualItemRect(item)
                origin = self.tree.viewport().mapTo(self, rect.topLeft())
                x = origin.x()
                y = origin.y() + rect.height()
            self._place_confirm(x, y)
        self._confirm.show()
        self._confirm.raise_()
        self._delete_button.setFocus()

    def set_quick_recent(self, recent: Callable[[], Tuple[str, ...]]) -> None:
        """The per-user recent list the quick insert shows first (UX-CAT-013)."""
        self._quick_recent = recent

    def show_insert(self, *, return_to: Optional[QWidget] = None) -> None:
        self._insert_return = return_to
        self._insert_filter.clear()
        self._fill_insert(self._quick_rows(""))
        rows = min(self._insert_list.count(), 8)
        height = min(max(rows * 24 + 12, 80), max(self.height() - self.header.height(), 80))
        self._insert_pop.setGeometry(0, self.header.height(), self.width(), height)
        self._insert_pop.show()
        self._insert_pop.raise_()
        self._insert_filter.setFocus()
        self._preview_insert_row()

    def show_cue(self, effect: object) -> None:
        into = bool(effect.into)  # type: ignore[attr-defined]
        self._paint_drop_line(into)
        self._drop_line.setFixedHeight(max(int(effect.height), 2))  # type: ignore[attr-defined]
        self._drop_line.setGeometry(int(effect.x), int(effect.y), max(int(effect.width), 1), max(int(effect.height), 2))  # type: ignore[attr-defined]
        self._drop_line.show()
        self._drop_line.raise_()

    def flash_row(self, node: NodeId) -> None:
        item = self._rows.get(int(node))
        if item is None:
            return
        color = self._error_color or self.tree.palette().highlight().color().name()
        item.setBackground(0, QBrush(QColor(color)))
        QTimer.singleShot(120, lambda item=item: item.setBackground(0, QBrush()))

    def report(self, text: str) -> None:
        status = self._status
        if status is not None:
            status(text)

    def toast(self, text: str) -> None:
        session = self._session
        if session is None:
            return
        host = self.window() or self
        found = host.findChild(QFrame, "formBuilder.commandToast")
        toast = found if isinstance(found, CommandToast) else self._own_toast()
        entries = session.log.entries()
        entry = entries[-1] if entries else None
        note = ToastNote(text, "Undo", "Delete", len(entries), entry)
        toast.show_note(note, self._undo_toast)

    def apply_colors(self, tokens: ShellThemeTokens) -> None:
        self._quick_delegate.set_chrome(chrome_for(tokens))
        self._name_color = tokens.text_primary
        self._faint_color = tokens.text_muted
        self._error_color = tokens.diag_error_color
        self._layout_color = tokens.accent
        self._delegate.update_colors(
            tokens.text_primary,
            tokens.text_muted,
            tokens.diag_error_color,
            tokens.accent,
        )
        width = tokens.focus_border_width
        self._editor.setStyleSheet(
            "QLineEdit#formBuilder\\.outlineRename { color: %s; background: %s; border: %dpx solid %s; }"
            % (tokens.text_primary, tokens.editor_bg, width, tokens.accent)
        )
        self._error.setStyleSheet(
            "color: %s; background: %s;" % (tokens.diag_error_color, tokens.editor_bg)
        )
        self._confirm.setStyleSheet(
            "QFrame#formBuilder\\.outlineConfirm { background: %s; color: %s; border: %dpx solid %s; }"
            # The canvas confirm is reparented to the form surface, so the
            # sentence cannot inherit the outline pane's text colour.
            "QLabel#formBuilder\\.outlineDeleteText { color: %s; background: transparent; }"
            "QPushButton { color: %s; background: %s; border: %dpx solid %s; }"
            "QPushButton:focus { border: %dpx solid %s; }"
            % (
                tokens.popup_bg or tokens.panel_bg,
                tokens.text_primary,
                width,
                tokens.border,
                tokens.text_primary,
                tokens.text_primary,
                tokens.panel_bg,
                width,
                tokens.border,
                width,
                tokens.accent,
            )
        )
        self._empty_label.setStyleSheet("color: %s; background: transparent;" % tokens.text_primary)
        self._filter.setStyleSheet(
            "QLineEdit#formBuilder\\.outlineFilter { color: %s; background: %s; border: %dpx solid %s; }"
            "QLineEdit#formBuilder\\.outlineFilter:focus { border: %dpx solid %s; }"
            % (
                tokens.text_primary,
                tokens.editor_bg,
                width,
                tokens.border,
                width,
                tokens.accent,
            )
        )
        # The delegate paints theme text. An unstyled list stays white, so dark and
        # high-contrast text disappears on it.
        self._insert_pop.setStyleSheet(
            "QFrame#formBuilder\\.outlineInsert { background: %s; color: %s; border: 1px solid %s; }"
            "QLineEdit#formBuilder\\.outlineInsertFilter { background: %s; color: %s; border: 1px solid %s; }"
            "QLineEdit#formBuilder\\.outlineInsertFilter:focus { border: %dpx solid %s; }"
            "QListWidget#formBuilder\\.outlineInsertList { background: %s; color: %s; border: none; }"
            "QListWidget#formBuilder\\.outlineInsertList::item:selected { background: %s; color: %s; }"
            % (
                tokens.panel_bg,
                tokens.text_primary,
                tokens.border,
                tokens.input_bg,
                tokens.text_primary,
                tokens.border,
                width,
                tokens.accent,
                tokens.panel_bg,
                tokens.text_primary,
                tokens.tree_selected_bg,
                tokens.text_primary,
            )
        )
        self.tree.viewport().update()

    def receive_drop(self, pos: QPoint) -> None:
        self._post_target(pos, True)

    def _own_toast(self) -> CommandToast:
        toast = self._toast_box
        if toast is None:
            toast = CommandToast(self)
            self._toast_box = toast
        return toast

    def _undo_toast(self, note: ToastNote) -> None:
        session = self._session
        if session is None:
            return
        entries = session.log.entries()
        top = entries[-1] if entries else None
        if not undo_matches(note, top):
            return
        session.log.undo()

    def _install(self, forest: OutlineForest, previous: Optional[OutlineForest] = None) -> None:
        self._current_item = None
        self._blocked = True
        mask = filter_mask(forest, self._filter_text)
        states = dict(mask.state)
        alive = set()
        role = int(getattr(Qt, "UserRole"))
        filtered = bool(self._filter_text)
        for row in forest.rows:
            alive.add(int(row.node))
            item = self._rows.get(int(row.node))
            if item is None:
                item = QTreeWidgetItem()
                item.setData(0, role, int(row.node))
                self._rows[int(row.node)] = item
                self._write_item(item, row, states)
                continue
            before = None if previous is None else previous.row(row.node)
            if filtered or before != row:
                self._write_item(item, row, states)
        for node_id, item in list(self._rows.items()):
            if node_id not in alive:
                self._take(item)
                del self._rows[node_id]
        self._place_children(None, self.tree.invisibleRootItem(), forest)
        for row in forest.rows:  # type: ignore[attr-defined]
            item = self._rows.get(int(row.node))
            if item is None:
                continue
            opened = row.node not in self._closed
            if item.isExpanded() != opened:
                item.setExpanded(opened)
        self._blocked = False
        self._apply_empty(mask)

    def _place_children(self, parent_id: Optional[NodeId], holder: QTreeWidgetItem, forest: object) -> None:
        for index, row in enumerate(forest.children(parent_id)):  # type: ignore[attr-defined]
            item = self._rows.get(int(row.node))
            if item is None:
                continue
            self._move_item(holder, item, index)
            self._place_children(row.node, item, forest)

    def _move_item(self, holder: QTreeWidgetItem, item: QTreeWidgetItem, index: int) -> None:
        if item.treeWidget() is None:
            parent = item.parent()
            if parent is not None:
                row = parent.indexOfChild(item)
                if row >= 0:
                    item = parent.takeChild(row)
            holder.insertChild(min(index, holder.childCount()), item)
            return
        current = item.parent() if item.parent() is not None else self.tree.invisibleRootItem()
        if current is holder and current.indexOfChild(item) == index:
            return
        row = current.indexOfChild(item)
        if row < 0:
            holder.insertChild(index, item)
            return
        taken = current.takeChild(row)
        holder.insertChild(min(index, holder.childCount()), taken)

    def _take(self, item: QTreeWidgetItem) -> None:
        current = item.parent() if item.parent() is not None else self.tree.invisibleRootItem()
        row = current.indexOfChild(item)
        if row >= 0:
            current.takeChild(row)

    def _write_item(self, item: QTreeWidgetItem, row: object, states: Dict[NodeId, str]) -> None:
        item.setText(0, row.primary)  # type: ignore[attr-defined]
        caption = _row_caption(row)
        item.setData(0, CAPTION, caption)
        item.setData(0, PROBLEM, bool(row.problem))  # type: ignore[attr-defined]
        item.setData(0, TONE, row.tone)  # type: ignore[attr-defined]
        kind = states.get(row.node, "match")  # type: ignore[attr-defined]
        faint = kind == "ancestor" or bool(row.hidden)  # type: ignore[attr-defined]
        item.setData(0, FAINT, faint)
        item.setHidden(kind == "hidden")
        item.setToolTip(0, row.primary if not caption else "%s  %s" % (row.primary, caption))  # type: ignore[attr-defined]
        color = self._faint_color if faint else self._name_color
        if row.tone == "layout" and not faint and self._layout_color:
            color = self._layout_color
        if color:
            item.setForeground(0, QBrush(QColor(color)))
        else:
            item.setForeground(0, QBrush())

    def _apply_empty(self, mask: object) -> None:
        if mask.empty and mask.query:  # type: ignore[attr-defined]
            self._empty_label.setText("No widget matches \u201c%s\u201d." % mask.query)  # type: ignore[attr-defined]
            self._empty.show()
            return
        self._empty.hide()

    def _place_editor(self, item: QTreeWidgetItem) -> None:
        rect = self.tree.visualItemRect(item)
        caption = str(item.data(0, CAPTION) or "")
        problem = bool(item.data(0, PROBLEM))
        boxes = layout_row(self._visible_width(rect), bool(caption), problem)
        left, _top, width, _height = boxes.name
        self._editor.setGeometry(rect.x() + left, rect.y(), max(width, 40), max(rect.height(), 24))

    def _visible_width(self, rect: QRect) -> int:
        """Width of ``rect`` that is inside the viewport, so nothing sits under the scrollbar."""
        return max(min(rect.right() + 1, self.tree.viewport().width()) - max(rect.x(), 0), 0)

    def _cursor(self) -> object:
        focus = self._current_node()
        selected: Tuple[NodeId, ...] = ()
        if self._session is not None:
            selected = self._session.selection.state.ids
        if not selected and focus is not None:
            selected = (focus,)
        anchor = self._anchor or focus
        return OutlineCursor(
            anchor=anchor,
            focus=focus,
            expanded=frozenset(self._closed),
            filter_text=self._filter_text,
            renaming=self._renaming,
            selected=selected,
        )

    def _world(self) -> OutlineWorld:
        session = self.session()
        return OutlineWorld(
            session.refs,
            session.base_methods,
            self._problem_ids(),
            default_registry().all(),
            friendly_of,
        )

    def _problem_ids(self) -> FrozenSet[NodeId]:
        session = self._session
        if session is None:
            return frozenset()
        found = []
        for item in session.diagnostics.all():
            node_id = item.location.node_id
            if node_id is not None:
                found.append(node_id)
        return frozenset(found)

    def _current_node(self) -> Optional[NodeId]:
        item = self.tree.currentItem()
        if item is None:
            return None
        raw = item.data(0, int(getattr(Qt, "UserRole")))
        if raw is None:
            return None
        return NodeId(int(raw))

    def _on_tree_key(self, event: object) -> bool:
        if self._session is None:
            return False
        if self._renaming is not None:
            if self._editor.hasFocus() or _modifier_only(event):
                # A key the editor let through (a bare Shift, Ctrl+D): it is still the
                # editor's key. Swallow it so the tree does not type-ahead or act.
                return True
            # The tree really has focus, so the editor lost it without telling us.
            self.end_rename()
        return self.consider(key_gesture(event))

    def _on_editor_key(self, event: object) -> bool:
        node = self._renaming
        if node is None:
            return False
        gesture = key_gesture(event)
        if gesture.key == "esc":
            self.consider(RenameGesture(node, self._editor.text(), "cancel"))
            return True
        if gesture.key == "enter":
            self.consider(RenameGesture(node, self._editor.text(), "commit"))
            return True
        if gesture.key in ("tab", "backtab"):
            how = "prev" if gesture.shift or gesture.key == "backtab" else "next"
            self.consider(RenameGesture(node, self._editor.text(), how))
            return True
        return False

    def _on_filter_key(self, event: object) -> bool:
        gesture = key_gesture(event)
        if gesture.key == "esc":
            self.consider(FilterGesture(self._filter.text(), "clear"))
            return True
        if gesture.key == "enter":
            self.consider(FilterGesture(self._filter.text(), "enter"))
            return True
        return False

    def _on_insert_key(self, event: object) -> bool:
        gesture = key_gesture(event)
        if gesture.key == "enter":
            item = self._insert_list.currentItem()
            if item is not None:
                self._activate_insert(item)
            return True
        if gesture.key != "esc":
            return False
        self._insert_pop.hide()
        if self._preview is not None:
            self._preview(None)
        target = self._insert_return
        self._insert_return = None
        if target is not None:
            target.setFocus()
        else:
            self.focus_tree()
        return True

    def _claim_override(self, watched: QObject, event: QEvent) -> bool:
        gesture = key_gesture(event)
        if watched is self.tree and self.tree.hasFocus():
            return claims_key(gesture)
        if watched is self._editor and self._renaming is not None and gesture.command_id.startswith("form.action."):
            # A name is being typed: form commands (Ctrl+D, Ctrl+C, ...) belong to the text, or to nothing.
            return True
        if watched is self._filter and (gesture.command_id == "form.action.find" or gesture.key == "esc"):
            return True
        if watched in (self._insert_list, self._insert_filter) and gesture.key in ("esc", "enter"):
            return True
        confirm = getattr(self, "_confirm", None)
        buttons = (confirm, getattr(self, "_delete_button", None), getattr(self, "_cancel_button", None))
        if confirm is not None and watched in buttons and gesture.key in ("esc", "enter"):
            return True
        return False

    def _on_confirm_key(self, event: object) -> bool:
        if not self._confirm.isVisible():
            return False
        gesture = key_gesture(event)
        if gesture.key == "esc":
            self._answer_delete(False)
            return True
        if gesture.key == "enter":
            self._answer_delete(False if self._cancel_button.hasFocus() else True)
            return True
        return False

    def _place_confirm(self, x: int, y: int) -> None:
        width = self._confirm.width()
        height = self._confirm.height()
        x = min(max(x, 0), max(self.width() - width, 0))
        y = min(max(y, 0), max(self.height() - height, 0))
        window = self.window()
        if isinstance(window, QWidget) and window is not self:
            origin = self.mapTo(window, QPoint(x, y))
            limit = window.rect()
            origin.setX(min(max(origin.x(), limit.left()), max(limit.right() - width, limit.left())))
            origin.setY(min(max(origin.y(), limit.top()), max(limit.bottom() - height, limit.top())))
            back = self.mapFrom(window, origin)
            x, y = back.x(), back.y()
            x = min(max(x, 0), max(self.width() - width, 0))
            y = min(max(y, 0), max(self.height() - height, 0))
        self._confirm.move(x, y)

    def _confirm_host(self, anchor: Optional[QRect]) -> QWidget:
        """The form surface, so a canvas confirm is not clipped to the outline."""
        if anchor is None:
            return self
        widget = self.parentWidget()
        while isinstance(widget, QWidget):
            if hasattr(widget, "ask_delete"):
                return widget
            widget = widget.parentWidget()
        window = self.window()
        return window if isinstance(window, QWidget) else self

    def _place_confirm_global(self, anchor: QRect, host: QWidget, avoid: Tuple[QRect, ...] = ()) -> None:
        """Put the confirm under the tab, clear of the selection chip."""
        local = QRect(host.mapFromGlobal(anchor.topLeft()), anchor.size())
        width = self._confirm.width()
        height = self._confirm.height()
        below = local.y() + local.height() + 4
        above = local.y() - height - 4
        if below + height <= host.height() - 8:
            y = below
        elif above >= 8:
            y = above
        else:
            y = max(8, min(below, host.height() - height - 8))
        x = min(max(local.x(), 8), max(host.width() - width - 8, 8))
        y = min(max(y, 8), max(host.height() - height - 8, 8))
        rect = QRect(x, y, width, height)
        blocked = [QRect(host.mapFromGlobal(item.topLeft()), item.size()) for item in avoid]
        for _step in range(6):
            hit = next((block for block in blocked if rect.intersects(block)), None)
            if hit is None:
                break
            dropped = hit.bottom() + 6
            if dropped + rect.height() <= host.height() - 8 and dropped != rect.top():
                rect.moveTop(dropped)
                continue
            shifted = hit.left() - rect.width() - 6
            if shifted >= 8:
                rect.moveLeft(shifted)
                continue
            rect.moveTop(max(8, hit.top() - rect.height() - 6))
            break
        rect.moveLeft(min(max(rect.left(), 8), max(host.width() - rect.width() - 8, 8)))
        rect.moveTop(min(max(rect.top(), 8), max(host.height() - rect.height() - 8, 8)))
        self._confirm.move(rect.topLeft())

    def _filter_edited(self, text: str) -> None:
        if self._filter.signalsBlocked():
            return
        self.consider(FilterGesture(text, "edit"))

    def _clear_filter(self) -> None:
        self.consider(FilterGesture(self._filter.text(), "clear"))

    def _open_filter(self) -> None:
        self.consider(KeyGesture(command_id="form.action.find"))

    def _open_insert(self) -> None:
        self.consider(InsertGesture(self._current_node()))

    def _rename_item(self, item: QTreeWidgetItem, _column: int) -> None:
        if self._session is None:
            return
        self.tree.setCurrentItem(item)
        self.consider(KeyGesture(command_id="form.action.rename"))

    def _answer_delete(self, accept: bool) -> None:
        ids = self._ask_ids
        done = self._after_confirm
        self._after_confirm = None
        self._confirm.hide()
        if self._confirm.parentWidget() is not self:
            self._confirm.setParent(self)
        self.consider(ConfirmGesture(ids, accept))
        if done is not None:
            done()
        else:
            self.focus_tree()

    def _note_expanded(self, item: QTreeWidgetItem, expanded: bool) -> None:
        if self._blocked:
            return
        raw = item.data(0, int(getattr(Qt, "UserRole")))
        if raw is None:
            return
        node = NodeId(int(raw))
        if expanded:
            self._closed.discard(node)
        else:
            self._closed.add(node)

    def _quick_rows(self, query: str) -> Tuple[Row, ...]:
        return quick_rows(load_catalog().entries, self._quick_recent(), query)

    def _quick_filter_changed(self, text: str) -> None:
        self._fill_insert(self._quick_rows(text.strip()))
        self._preview_insert_row()

    def _on_quick_filter_key(self, event: object) -> bool:
        gesture = key_gesture(event)
        if gesture.key == "down":
            self._insert_list.setFocus()
            return True
        if gesture.key in ("enter", "esc"):
            return self._on_insert_key(event)
        return False

    def _fill_insert(self, rows: Sequence[Row]) -> None:
        self._insert_list.clear()
        role = int(getattr(Qt, "UserRole"))
        first = -1
        for row in rows:
            item = QListWidgetItem("" if row.kind != ENTRY else row.title)
            item.setData(int(ROW_ROLE), row)
            if row.kind == ENTRY:
                item.setData(role, row.key)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                if first < 0:
                    first = self._insert_list.count()
            else:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._insert_list.addItem(item)
        if first >= 0:
            self._insert_list.setCurrentRow(first)

    def _preview_insert_row(self) -> None:
        preview = self._preview
        if preview is None:
            return
        item = self._insert_list.currentItem()
        if item is None:
            preview(None)
            return
        raw = item.data(int(getattr(Qt, "UserRole")))
        preview(None if raw is None else str(raw))

    def _activate_insert(self, item: QListWidgetItem) -> None:
        raw = item.data(int(getattr(Qt, "UserRole")))
        if not raw:
            return
        self._insert_pop.hide()
        if self._preview is not None:
            self._preview(None)
        if self._place is not None and raw is not None:
            self._place(str(raw))
        target = self._insert_return
        self._insert_return = None
        focus = QApplication.focusWidget()
        if target is not None and focus is not None and target.isAncestorOf(focus) and focus is not target:
            return
        if target is not None:
            target.setFocus()
            return
        self.focus_tree()

    def _deliver_page_drop(self, pos: QPoint) -> bool:
        session = self._session
        forest = self._forest
        payload_of = self._payload
        document = self._document
        if session is None or forest is None or payload_of is None or document is None:
            return False
        payload = payload_of()
        if payload is None or not payload.source_ids:
            return False
        row = forest.row(payload.source_ids[0])
        if row is None or not isinstance(row.slot, InPageSlot):
            return False
        self.consider(
            DropGesture(
                pos.x(),
                pos.y(),
                True,
                payload,
                self._outline_rows(),
                blocked=blocked_ids(document, payload.source_ids),
            )
        )
        return True


_MODIFIER_KEYS = ("Key_Shift", "Key_Control", "Key_Alt", "Key_Meta", "Key_AltGr", "Key_CapsLock")


def _modifier_only(event: object) -> bool:
    key = int(getattr(event, "key")())
    keys = getattr(Qt, "Key", Qt)
    return any(key == int(getattr(keys, name)) for name in _MODIFIER_KEYS if hasattr(keys, name))


def _leaves_for_good(event: object) -> bool:
    """A focus change that ends a rename. Switching windows or opening a menu does not."""
    reason = getattr(event, "reason", None)
    if not callable(reason):
        return True
    reasons = getattr(Qt, "FocusReason", Qt)
    passing = (getattr(reasons, "ActiveWindowFocusReason"), getattr(reasons, "PopupFocusReason"))
    return reason() not in passing


def _row_caption(row: object) -> str:
    if getattr(row, "kind", "") == "page":
        # UX-CONT-001: "Tab 3 · Printing", "Step 2 · Payment", "Window 2 · Notes".
        slot = getattr(row, "slot", None)
        if isinstance(slot, InPageSlot):
            number = "%s %d" % (slot.word or "Tab", slot.index + 1)
        else:
            number = "Tab"
        title = str(getattr(row, "visible_text", "") or "")
        if not title:
            title = str(getattr(row, "primary", "") or "")
        if title and title != number:
            return "%s \u00b7 %s" % (number, title)
        return number
    bits = []
    friendly = row.friendly  # type: ignore[attr-defined]
    primary = row.primary  # type: ignore[attr-defined]
    if row.qt_class in ("QComboBox", "QListWidget", "QTreeWidget", "QTableWidget") and row.visible_text:  # type: ignore[attr-defined]
        # UX-ITEM-009: a narrow outline drops a caption that does not fit whole, so the items
        # come first and the class word (the inspector and tooltip carry it) is left out.
        return "\u201c%s\u201d" % row.visible_text  # type: ignore[attr-defined]
    if friendly and friendly != primary:
        bits.append(friendly)
    visible = row.visible_text  # type: ignore[attr-defined]
    if visible:
        bits.append("\u201c%s\u201d" % visible)
    return " ".join(bits)


class _PieceOps:
    """Saved-piece operations for the Insert pane: the settings store and the clipboard stay here."""

    def renamed(self, pieces: Sequence[object], index: int, name: str) -> Tuple[object, ...]:
        return renamed_pieces(pieces, index, name)  # type: ignore[arg-type,return-value]

    def without(self, pieces: Sequence[object], index: int) -> Tuple[object, ...]:
        return without_piece(pieces, index)  # type: ignore[arg-type,return-value]

    def for_ids(self, document: object, ids: Sequence[NodeId], taken: Sequence[str]) -> Optional[object]:
        return piece_for_ids(document, ids, taken)  # type: ignore[arg-type]

    def publish(self, xml: str) -> None:
        publish_xml(xml)


def _state_root_of(widget: QWidget) -> Optional[str]:
    root = getattr(widget.window(), "_state_root", None)
    return str(root) if root else None


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
        slots: Optional[WorkbenchSlots] = None,
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
        self._slots = slots if slots is not None else default_slots()
        self._stacked = False
        self._sections: List[Tuple[LeftSection, QWidget]] = []
        self._section_shown: Tuple[str, ...] = ()
        self._under_key = ""
        self._under_widget: Optional[QWidget] = None
        self._under_height = 0
        self._under_listener: Optional[Callable[[int], None]] = None
        self._beside_key = ""
        self._beside_widget: Optional[QWidget] = None
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
        self._insert_memory = LazyInsertMemory(lambda: _state_root_of(self))
        self._return_to_insert = False
        self._field_after_label: Optional[NodeId] = None
        self.insert = InsertPane(
            lambda collapsed: on_collapsed("insert", collapsed),
            self._left_stack,
            memory=self._insert_memory,
            pieces=_PieceOps(),
        )
        self.insert.bind_session(session)
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

        # The canvas column: the canvas with an optional split beside it (a
        # horizontal row), and an optional drawer under both.
        self._canvas_col = QSplitter(self._splitter)
        self._canvas_col.setObjectName("formBuilder.canvasColumn")
        self._canvas_col.setOrientation(getattr(orient, "Vertical"))
        self._canvas_col.setHandleWidth(6)
        self._canvas_col.setChildrenCollapsible(False)
        self._canvas_col.splitterMoved.connect(self._under_moved)
        self._canvas_row = QSplitter(self._canvas_col)
        self._canvas_row.setObjectName("formBuilder.canvasRow")
        self._canvas_row.setOrientation(getattr(orient, "Horizontal"))
        self._canvas_row.setHandleWidth(6)
        self._canvas_row.setChildrenCollapsible(False)
        self._canvas_col.addWidget(self._canvas_row)
        self.canvas = FormCanvas(session, realizer, host, self._canvas_row)
        self._canvas_row.addWidget(self.canvas)
        self._under = QFrame(self._canvas_col)
        self._under.setObjectName("formBuilder.underCanvas")
        under_layout = QVBoxLayout(self._under)
        under_layout.setContentsMargins(0, 0, 0, 0)
        self._under_layout = under_layout
        self._under.hide()
        self.outline.set_hover_target(self.canvas.send)
        self.outline.set_drop_bridge(self.canvas.send, self.canvas.place_payload)
        self.insert.set_place(self._place_tile)
        self.insert.set_preview(self._preview_insert)
        self.insert.set_drag_finished(self._cancel_place)
        self.insert.set_leave(self.canvas.setFocus)
        application = QApplication.instance()
        self._focus_hooked = False
        if application is not None:
            application.focusChanged.connect(self._on_focus_changed)
            self._focus_hooked = True
            self.destroyed.connect(self.dispose)
        self.insert.set_report(self.outline.report)
        self.insert.set_open_window(self._open_window_kind)
        self.outline.set_quick_recent(self._insert_memory.recent)
        self.outline.attach(session, self._place_from_outline, self._preview_insert)

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
        self._splitter.addWidget(self._canvas_col)
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
        self._build_sections()
        self._slots.attach(self)

    def canvas_view(self) -> FormCanvas:
        return self.canvas

    def refresh(
        self,
        selected: Optional[NodeId],
        outline: str = "rebuild",
        touched: Sequence[NodeId] = (),
        change: object = None,
    ) -> None:
        document = self._session.document
        if change is not None:
            self.outline.apply_change(document, selected, change)
        elif outline == "patch":
            self.outline.patch_rows(document, selected, touched)
        elif outline == "keep":
            self.outline.show_current(selected)
        else:
            self.outline.rebuild(document, selected)
        self.canvas.refresh_chip()
        self.insert.refresh_custom()
        self._sync_sections()

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
        self._place_under()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        code_view = getattr(self, "code_view", None)
        if code_view is not None:
            code_view.apply_theme(tokens)
        self.outline.set_hover_fill(tokens.tree_hover_bg)
        self.outline.set_drop_color(tokens.accent)
        self.outline.apply_colors(tokens)
        for name, glyph in _RAIL_GLYPHS.items():
            button = self.findChild(QToolButton, name)
            if isinstance(button, QToolButton):
                _paint_glyph(button, glyph, tokens, 16 if name == "formBuilder.pin" else 20)
        for spec, _widget in self._sections:
            button = self.findChild(QToolButton, "formBuilder.leftRail.%s" % spec.key)
            if isinstance(button, QToolButton) and spec.glyph:
                _paint_glyph(button, spec.glyph, tokens, 20)
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
            "QListWidget#formBuilder\\.insertBody { background: %s; color: %s; border: 1px solid %s; }"
            "QListWidget#formBuilder\\.insertBody::item:selected { background: %s; color: %s; }"
            "QListWidget#formBuilder\\.insertBody:focus { border: %dpx solid %s; }"
            "QLineEdit#formBuilder\\.insertFilter { background: %s; color: %s; border: 1px solid %s; }"
            "QLineEdit#formBuilder\\.insertFilter:focus { border: %dpx solid %s; }"
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
                tokens.editor_bg,
                tokens.text_primary,
                tokens.border,
                tokens.tree_selected_bg,
                tokens.text_primary,
                width,
                tokens.accent,
                tokens.editor_bg,
                tokens.text_primary,
                tokens.border,
                width,
                tokens.accent,
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
        self.insert.apply_chrome(chrome_for(tokens))
        self.canvas.apply_theme(tokens)
        self.inspector.apply_chrome(chrome_for(tokens))
        self.inspector.set_link_color(problems_link_color(tokens))

    def dispose(self, *_args: object) -> None:
        """Drop the focus watch. A closed form must not keep the application signal."""
        if not self._focus_hooked:
            return
        self._focus_hooked = False
        application = QApplication.instance()
        if application is None:
            return
        try:
            application.focusChanged.disconnect(self._on_focus_changed)
        except (RuntimeError, TypeError):
            return

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
        entry = load_catalog().get(key)
        name = in_sentence(entry.friendly if entry is not None else tile[2])
        payload = DropPayload(tile[1], dock=key == "QDockWidget", wizard_page=key == "QWizardPage")
        current = self._session.selection.state.current
        redirected = central_redirect(self._session.document, current) is not None
        commands = auto_commands(self._session.document, current, payload, fragment)
        if not commands:
            self._report_refusal(payload, current)
            return
        try:
            with self._session.log.transaction("Insert %s" % name) as txn:
                for command in commands:
                    txn.execute(command)
        except CommandRejected:
            self._report_refusal(payload, current)
            return
        self._insert_memory.note_used(key)
        self.insert.refresh_recent()
        if redirected:
            self.outline.report(CENTRAL_NOTE)
        if any(isinstance(command, InsertFormRow) for command in commands):
            # UX-CAT-011: a keyboard insert's label editor hands focus back to the Insert tile when it closes.
            self._return_to_insert = self._insert_has_focus()
            state = self._session.selection.state
            others = [node for node in state.ids if node != state.current]
            self._field_after_label = others[0] if len(others) == 1 and state.current is not None else None
            self.canvas.setFocus()
            self.canvas.send(EditTextAsked())
            return
        if not self._insert_has_focus():
            self.canvas.setFocus()

    def _on_focus_changed(self, old: object, now: object) -> None:
        """The label editor (a line or text box on the canvas) closed: return to the Insert tile once."""
        if not self._return_to_insert and self._field_after_label is None:
            return
        if not isinstance(old, (QLineEdit, QPlainTextEdit)) or not self.canvas.isAncestorOf(old):
            return
        if now is not None and now is not self.canvas and not self.canvas.isAncestorOf(now):
            return
        field = self._field_after_label
        self._field_after_label = None
        if field is not None and self._session.document.contains(field):
            # The new row's label editor closed: the field is the selection, not the label and field pair,
            # so the inspector shows the field's own rows.
            self._session.selection.set((field,), current=field, source=SelectionSource.CANVAS)
        if not self._return_to_insert:
            return
        self._return_to_insert = False
        self.insert.focus_list()

    def _insert_has_focus(self) -> bool:
        focus = QApplication.focusWidget()
        if focus is None:
            return False
        return focus is self.insert.body or focus is self.insert.filter or self.insert.isAncestorOf(focus)

    def _report_refusal(self, payload: DropPayload, anchor: Optional[NodeId]) -> None:
        """UX-CAT-011 and UX-CAT-014: a keyboard insert that cannot go here says why, and inserts nothing."""
        target = auto_target(self._session.document, anchor, payload)
        if isinstance(target, RefusedDrop):
            self.outline.report(target.sentence)
            return
        if payload.kind == "spacer":
            self.outline.report("A spacer can't go in a form row. Use a gap instead.")
            return
        self.outline.report("Nothing to insert here. Select a place first.")

    def _open_window_kind(self, key: str) -> None:
        if key.startswith("part:"):
            self._add_main_window_part(key[len("part:"):])
            return
        opener = getattr(self.window(), "_open_new_form_card", None)
        if callable(opener):
            opener(key)

    def _add_main_window_part(self, part: str) -> None:
        """Insert search rows "Menu bar · add to this window" ... (UX-MAIN-002): this form, not New form."""
        from app.features.form_builder.engine.commands.base import CommandRejected
        from app.features.form_builder.engine.commands.catalog_ext.main_window import AddMainWindowPart

        try:
            self._session.log.execute(AddMainWindowPart(part))
        except CommandRejected as refusal:
            sentence = str(refusal)
            doc = self._session.document
            if not q_actions.is_main_window(doc):
                friendly = load_catalog().friendly_for_class(q_actions.root_class(doc)) or "widget"
                sentence = "%s This form is a %s." % (sentence, friendly.lower())
            self.outline.report(sentence)

    def _place_from_outline(self, key: str) -> None:
        self._place_tile(key)
        if self.outline._insert_return is not None:
            return
        focus = QApplication.focusWidget()
        if focus is not None and focus is not self.canvas and self.canvas.isAncestorOf(focus):
            return
        self.outline.focus_tree()

    def _preview_insert(self, key: Optional[str]) -> None:
        self.canvas.set_insert_preview(key)
        self.insert.set_caption("" if key is None else self.canvas.preview_sentence())

    def _cancel_place(self) -> None:
        self.canvas.send(PlaceDrop(CanvasPoint(0, 0), True, None, True))

    def _focus_inspector_tab(self, tab: TabId) -> None:
        if self._plan is not None and not self._plan.inspector_docked:
            self.open_right()
        self.inspector.focus_tab(tab)

    def focus_inspector_tab(self, tab: TabId) -> None:
        """Open the inspector (a closed side panel opens) on ``tab``, as Alt+4 and Alt+5 do."""
        self._focus_inspector_tab(tab)

    def focus_share(self, axis: str) -> None:
        """Open the Size group on the current selection and focus its share spin for ``axis``."""
        self._focus_inspector_tab(TabId.PROPERTIES)
        self.inspector.set_group_expanded(GroupId.SIZE, True)
        self.inspector.flush()
        spin = self.inspector.findChild(QSpinBox, "formBuilder.size.share.%s.value" % axis)
        if spin is not None and spin.isVisibleTo(self.inspector):
            spin.setFocus()
            spin.selectAll()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        if self._plan is not None:
            self._size_panes(self._plan)
        self._place_drawer()
        self._place_under()

    def _apply_short(self, stacked: bool) -> None:
        self._stacked = stacked
        self._arrange_left()

    def _arrange_left(self) -> None:
        """Outline, Insert and the shown sections: split panes, or tabs at short heights."""
        shown = [(spec, widget) for spec, widget in self._sections if spec.key in self._section_shown]
        for spec, widget in self._sections:
            if spec.key not in self._section_shown:
                self._park_section(widget)
            self._rail_button(spec.key).setVisible(spec.key in self._section_shown)
        if self._stacked:
            if self._left_tabs.count() == 0:
                self._left_tabs.addTab(self.outline, "Outline")
                self._left_tabs.addTab(self.insert, "Insert")
            for position, (spec, widget) in enumerate(shown):
                if self._left_tabs.indexOf(widget) < 0:
                    self._left_tabs.insertTab(2 + position, widget, spec.title)
            self._left_split.hide()
            self._left_tabs.show()
            return
        if self._left_split.indexOf(self.outline) < 0:
            for spec, widget in shown:
                self._left_tabs.removeTab(self._left_tabs.indexOf(widget))
            self._left_tabs.removeTab(self._left_tabs.indexOf(self.outline))
            self._left_tabs.removeTab(self._left_tabs.indexOf(self.insert))
            self._left_split.addWidget(self.outline)
            self._left_split.addWidget(self.insert)
        for position, (spec, widget) in enumerate(shown):
            if self._left_split.indexOf(widget) < 0:
                self._left_tabs.removeTab(self._left_tabs.indexOf(widget))
                self._left_split.insertWidget(2 + position, widget)
            widget.show()
        self.outline.show()
        self.insert.show()
        self._left_tabs.hide()
        self._left_split.show()
        height = max(self._left_split.height(), 240)
        extra = sum(spec.weight for spec, _widget in shown)
        if extra:
            rest = 100 - extra
            top = height * rest * 40 // (75 * 100)
            middle = height * rest * 35 // (75 * 100)
            sizes = [top, middle] + [height * spec.weight // 100 for spec, _widget in shown]
        else:
            top = height * 55 // 100
            sizes = [top, max(80, height - top)]
        self._left_split.setSizes(sizes)

    def _park_section(self, widget: QWidget) -> None:
        index = self._left_tabs.indexOf(widget)
        if index >= 0:
            self._left_tabs.removeTab(index)
        if self._left_split.indexOf(widget) >= 0:
            widget.setParent(self._left_body)
        widget.hide()

    def _build_sections(self) -> None:
        for spec in self._slots.sections():
            try:
                widget = spec.build(self)
            except Exception:
                logger.exception("left section %s could not be built", spec.key)
                continue
            widget.setParent(self._left_body)
            widget.hide()
            self._sections.append((spec, widget))
            button = self._left_rail.add_button(
                "formBuilder.leftRail.%s" % spec.key,
                spec.title,
                lambda key=spec.key: self.focus_section(key),
            )
            if not spec.glyph:
                button.setToolButtonStyle(_button_style("ToolButtonTextOnly"))
                button.setText(spec.title[:1])
            button.hide()
            # ``spec.keys`` becomes a keys_ext row; the form tab binds it, so
            # Settings can rebind it and the collision test sees it.
        self._sync_sections()

    def _rail_button(self, key: str) -> QToolButton:
        button = self._left_rail.findChild(QToolButton, "formBuilder.leftRail.%s" % key)
        assert isinstance(button, QToolButton)
        return button

    def _sync_sections(self) -> None:
        """Ask each section if it shows for this form. Rearranges only when the answer changed."""
        if not self._sections:
            return
        shown = []
        for spec, _widget in self._sections:
            try:
                if spec.shown(self._session):
                    shown.append(spec.key)
            except Exception:
                logger.exception("left section %s could not say if it shows", spec.key)
        wanted = tuple(shown)
        if wanted == self._section_shown:
            return
        self._section_shown = wanted
        self._arrange_left()

    def section_widget(self, key: str) -> Optional[QWidget]:
        """The widget of a registered left section, shown or not."""
        for spec, widget in self._sections:
            if spec.key == key:
                return widget
        return None

    def focus_section(self, key: str) -> bool:
        """Alt+N for a lane section. False when the section is absent for this form."""
        if key not in self._section_shown:
            return False
        found = [(spec, widget) for spec, widget in self._sections if spec.key == key]
        spec, widget = found[0]
        if self._plan is not None and not self._plan.left_docked:
            self.open_left()
        if self._stacked:
            self._left_tabs.setCurrentWidget(widget)
        if spec.focus is not None:
            spec.focus(widget)
        else:
            widget.setFocus()
        return True

    def open_under_canvas(self, key: str, widget: QWidget, *, height: int = 240) -> bool:
        """The drawer under the canvas (UX-STYLE-002). One at a time; ``key`` names its owner.

        The height is clamped to 160 px through 60% of the workbench. The
        canvas keeps 200 px: when it could not, or at heights under 560 (the
        short layout), the drawer covers the canvas instead of pushing it.
        Returns False when the workbench has no room to show it at all.
        """
        if self.height() < _UNDER_MIN * 2 and self.height() > 0:
            return False
        self.close_under_canvas()
        self._under_key = key
        self._under_widget = widget
        self._under_height = max(_UNDER_MIN, min(height, self.height() * 6 // 10 or height))
        self._under_layout.addWidget(widget)
        widget.show()
        self._under.show()
        self._place_under()
        return True

    def close_under_canvas(self) -> None:
        widget = self._under_widget
        if widget is None:
            return
        self._under.hide()
        self._under_layout.removeWidget(widget)
        widget.hide()
        widget.setParent(self)
        self._under_widget = None
        self._under_key = ""

    def under_canvas_key(self) -> str:
        return self._under_key

    def under_canvas_height(self) -> int:
        return self._under_height

    def set_under_canvas_listener(self, callback: Optional[Callable[[int], None]]) -> None:
        """Called with the new height after the user drags the drawer's top edge."""
        self._under_listener = callback

    def _under_covers(self) -> bool:
        column = self._canvas_col.height()
        return self.height() < _SHORT_HEIGHT or column - self._under_height - self._canvas_col.handleWidth() < _CANVAS_MIN

    def _place_under(self) -> None:
        if self._under_widget is None:
            return
        column = self._canvas_col
        if self._under_covers():
            if self._under.parentWidget() is not self:
                self._under.setParent(self)
            height = min(self._under_height, column.height())
            origin = column.mapTo(self, QPoint(0, 0))
            self._under.setMinimumHeight(0)
            self._under.setMaximumHeight(16777215)
            self._under.setGeometry(origin.x(), origin.y() + column.height() - height, column.width(), height)
            self._under.show()
            self._under.raise_()
            return
        if column.indexOf(self._under) < 0:
            column.addWidget(self._under)
        self._under.setMinimumHeight(_UNDER_MIN)
        self._under.setMaximumHeight(max(_UNDER_MIN, column.height() * 6 // 10))
        self._under.show()
        total = max(column.height(), self._under_height + _CANVAS_MIN)
        column.setSizes([total - self._under_height, self._under_height])

    def _under_moved(self, _pos: int, _index: int) -> None:
        if self._under_widget is None or self._under_covers():
            return
        sizes = self._canvas_col.sizes()
        if len(sizes) < 2:
            return
        self._under_height = max(_UNDER_MIN, sizes[1])
        if self._under_listener is not None:
            self._under_listener(self._under_height)

    def open_beside_canvas(
        self, key: str, widget: QWidget, *, share: float = 0.45, min_canvas: int = 360
    ) -> bool:
        """The split at the right of the canvas (UX-PREV-004). One at a time.

        Returns False, and opens nothing, when the canvas would be left with
        fewer than ``min_canvas`` px. The caller says why in its own words.
        """
        row = self._canvas_row
        width = row.width()
        beside = int(width * share)
        if width - beside - row.handleWidth() < min_canvas:
            return False
        self.close_beside_canvas()
        self._beside_key = key
        self._beside_widget = widget
        row.addWidget(widget)
        widget.show()
        row.setSizes([width - beside, beside])
        return True

    def close_beside_canvas(self) -> None:
        widget = self._beside_widget
        if widget is None:
            return
        widget.hide()
        widget.setParent(self)
        self._beside_widget = None
        self._beside_key = ""

    def beside_canvas_key(self) -> str:
        return self._beside_key

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
