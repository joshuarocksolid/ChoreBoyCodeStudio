"""Workbench panes and the tab toolbar (UX-WB-001..003, UX-RESP).

Widths come from a ``LayoutPlan``. This module does not decide breakpoints.
"""

from __future__ import annotations

import os
from typing import Callable, Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

from app.qt.QtCore import QEvent, QItemSelectionModel, QMimeData, QObject, QPoint, QSize, Qt, QTimer
from app.qt.QtGui import QBrush, QColor, QDrag, QIcon, QKeyEvent
from app.qt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
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
from app.qt.qt_compat import event_pos

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
    MIME_DESIGNER_FRAGMENT,
    MIME_FRAGMENT,
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
from app.features.form_builder.integration.clipboard_actions import publish_xml
from app.features.form_builder.integration.pieces import (
    SavedPiece,
    SavedPieceStore,
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
        elide = getattr(getattr(Qt, "TextElideMode", Qt), "ElideMiddle")
        self.tree.setTextElideMode(elide)
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
        mode = outline_mode(change) if change is not None else "rebuild"  # type: ignore[arg-type]
        if mode == "structure" and self._forest is not None:
            self.patch_structure(document, selected, change)
        elif mode == "captions":
            self.patch_rows(document, selected, captions_touched(change))  # type: ignore[arg-type]
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
        self._blocked = True
        if item is None:
            self.tree.setCurrentItem(None)
            self.tree.clearSelection()
        else:
            command = getattr(QItemSelectionModel, "SelectionFlag", QItemSelectionModel)
            flags = getattr(command, "ClearAndSelect") | getattr(command, "Rows")
            self.tree.setCurrentItem(item, 0, flags)
            self.tree.scrollToItem(item)
        self._blocked = False

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
        self._on_pick(NodeId(int(raw)))

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
        buttons.addWidget(delete)
        buttons.addWidget(cancel)
        confirm_layout.addLayout(buttons)
        self._confirm.hide()
        self._insert_pop = QFrame(self)
        self._insert_pop.setObjectName("formBuilder.outlineInsert")
        insert_layout = QVBoxLayout(self._insert_pop)
        self._insert_list = QListWidget(self._insert_pop)
        self._insert_list.setObjectName("formBuilder.outlineInsertList")
        self._insert_list.itemActivated.connect(self._activate_insert)
        self._insert_list.currentItemChanged.connect(lambda *_args: self._preview_insert_row())
        self._insert_list.installEventFilter(self)
        insert_layout.addWidget(self._insert_list)
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

    def begin_rename(self, node: NodeId) -> None:
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

    def finish_rename(self) -> None:
        """Close the editor and clear the renaming state. Every way out of a rename ends here."""
        had_focus = self._editor.hasFocus()
        self._release_rename_row()
        self._renaming = None
        if had_focus:
            # Hiding a focused editor would hand focus to whatever Qt picks next.
            self.tree.setFocus()
        self._editor.hide()
        self._error.hide()

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
        extra = max(self._error.sizeHint().height(), self._error.fontMetrics().height())
        self.tree.setUniformRowHeights(False)
        item.setData(0, EXTRA, extra)
        self.tree.doItemsLayout()
        rect = self.tree.visualItemRect(item)
        self._place_editor(item)
        editor = self._editor.geometry()
        self._editor.setGeometry(editor.x(), rect.y(), editor.width(), _NAME_ROW_PX)
        self._error.setGeometry(rect.x(), rect.y() + _NAME_ROW_PX, max(rect.width(), 80), extra)
        self._error.show()
        self._error.raise_()

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

    def show_delete(self, prose: str, ids: Tuple[NodeId, ...]) -> None:
        self._ask_ids = ids
        self._confirm_text.setText(prose)
        margin = 8
        limit = max(self.width() - margin * 2, 64)
        self._confirm.setMaximumWidth(limit)
        self._confirm.setMinimumWidth(0)
        self._confirm_text.setMaximumWidth(max(limit - 16, 32))
        self._confirm.setMaximumHeight(max(self.height() - margin, 48))
        self._confirm.adjustSize()
        width = min(self._confirm.sizeHint().width(), limit)
        self._confirm.resize(width, min(self._confirm.sizeHint().height(), max(self.height() - margin, 48)))
        anchor = ids[0] if ids else self._current_node()
        item = None if anchor is None else self._rows.get(int(anchor))
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

    def show_insert(self) -> None:
        self._fill_insert(matching_tiles(""))
        self._insert_pop.setGeometry(0, self.header.height(), self.width(), min(220, max(self.height() - self.header.height(), 80)))
        self._insert_pop.show()
        self._insert_pop.raise_()
        self._insert_list.setFocus()
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
            "QPushButton { color: %s; background: %s; border: %dpx solid %s; }"
            "QPushButton:focus { border: %dpx solid %s; }"
            % (
                tokens.popup_bg or tokens.panel_bg,
                tokens.text_primary,
                width,
                tokens.border,
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
        boxes = layout_row(rect.width(), bool(caption), problem)
        left, _top, width, _height = boxes.name
        self._editor.setGeometry(rect.x() + left, rect.y(), max(width, 40), max(rect.height(), 24))

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
        if watched is self._insert_list and gesture.key in ("esc", "enter"):
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
        self._confirm.hide()
        self.consider(ConfirmGesture(ids, accept))
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

    def _fill_insert(self, tiles: Sequence[Tuple[str, str, str]]) -> None:
        self._insert_list.clear()
        role = int(getattr(Qt, "UserRole"))
        for tile in tiles:
            item = QListWidgetItem(tile[2])
            item.setData(role, tile[0])
            self._insert_list.addItem(item)
        if self._insert_list.count():
            self._insert_list.setCurrentRow(0)

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
        self._insert_pop.hide()
        if self._preview is not None:
            self._preview(None)
        if self._place is not None and raw is not None:
            self._place(str(raw))
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
        # UX-OUT-007: the page number and its title ("Page 2 \u00b7 Settings").
        slot = getattr(row, "slot", None)
        number = "Page %d" % (slot.index + 1) if isinstance(slot, InPageSlot) else "Page"
        title = str(getattr(row, "visible_text", "") or "")
        return "%s \u00b7 %s" % (number, title) if title else number
    bits = []
    friendly = row.friendly  # type: ignore[attr-defined]
    primary = row.primary  # type: ignore[attr-defined]
    if friendly and friendly != primary:
        bits.append(friendly)
    visible = row.visible_text  # type: ignore[attr-defined]
    if visible:
        bits.append("\u201c%s\u201d" % visible)
    return " ".join(bits)


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
        self._session: Optional[FormSession] = None
        self._piece_store: Optional[SavedPieceStore] = None
        self._pieces: Tuple[SavedPiece, ...] = ()
        self._piece_unsub: Optional[Callable[[], None]] = None
        self._notice: Optional[Callable[[str, Callable[[], None]], None]] = None
        self._paste: Optional[Callable[[], None]] = None
        self._piece_box = _PieceBox(self)
        self.destroyed.connect(lambda *_args: self._drop_piece_sub())
        layout.addWidget(self._piece_box)
        self._collapsed = False
        self._refill("")
        self._refresh_pieces()

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
        self._refresh_pieces()

    def bind_session(self, session: FormSession) -> None:
        self._session = session

    def set_paste(self, paste: Callable[[], None]) -> None:
        self._paste = paste

    def set_notice(self, notice: Callable[[str, Callable[[], None]], None]) -> None:
        self._notice = notice

    def bind_pieces(self, store: Optional[SavedPieceStore]) -> None:
        self._drop_piece_sub()
        self._piece_store = store
        if store is not None:
            self._pieces = store.load()
            self._piece_unsub = store.subscribe(self._on_pieces_changed)
        else:
            self._pieces = ()
        self._refresh_pieces()

    def _drop_piece_sub(self) -> None:
        unsub = self._piece_unsub
        self._piece_unsub = None
        if unsub is not None:
            unsub()

    def _on_pieces_changed(self) -> None:
        store = self._piece_store
        if store is None:
            return
        self._pieces = store.load()
        self._refresh_pieces()

    def save_selection(self, session: FormSession) -> None:
        self._session = session
        self._save_ids(session, session.selection.state.ids)

    def save_node(self, node_id: NodeId) -> None:
        session = self._session
        if session is None or not session.document.contains(node_id):
            return
        selected = session.selection.state.ids
        ids = selected if node_id in selected else (node_id,)
        self._save_ids(session, ids)

    def piece_at(self, index: int) -> Optional[SavedPiece]:
        if index < 0 or index >= len(self._pieces):
            return None
        return self._pieces[index]

    def rename_piece(self, index: int, name: str) -> None:
        updated = renamed_pieces(self._pieces, index, name)
        if updated == self._pieces:
            return
        self._pieces = updated
        self._store_pieces()
        self._refresh_pieces()

    def delete_piece(self, index: int) -> None:
        if index < 0 or index >= len(self._pieces):
            return
        removed = self._pieces[index]
        updated = without_piece(self._pieces, index)
        self._pieces = updated
        self._store_pieces()
        self._refresh_pieces()
        notice = self._notice
        if notice is None:
            return

        def undo(slot: int = index, piece: SavedPiece = removed) -> None:
            self._restore_piece(slot, piece)

        notice("Deleted %s." % removed.name, undo)

    def insert_piece(self, index: int) -> None:
        piece = self.piece_at(index)
        if piece is None:
            return
        publish_xml(piece.xml)
        paste = self._paste
        if paste is not None:
            paste()

    def _restore_piece(self, index: int, piece: SavedPiece) -> None:
        items = list(self._pieces)
        slot = index if 0 <= index <= len(items) else len(items)
        items.insert(slot, piece)
        self._pieces = tuple(items)
        self._store_pieces()
        self._refresh_pieces()

    def piece_menu(self, index: int) -> QMenu:
        menu = QMenu(self)
        rename = menu.addAction("Rename")
        delete = menu.addAction("Delete")
        rename.triggered.connect(lambda _checked=False, slot=index: self._prompt_rename(slot))
        delete.triggered.connect(lambda _checked=False, slot=index: self.delete_piece(slot))
        return menu

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._piece_box.apply_theme(tokens)

    def _save_ids(self, session: FormSession, ids: Sequence[NodeId]) -> None:
        piece = piece_for_ids(session.document, ids, tuple(item.name for item in self._pieces))
        if piece is None:
            return
        self._pieces = self._pieces + (piece,)
        self._store_pieces()
        self._refresh_pieces()

    def _store_pieces(self) -> None:
        store = self._piece_store
        if store is not None:
            store.replace(self._pieces)

    def _refresh_pieces(self) -> None:
        self._piece_box.fill(self._pieces)
        self._piece_box.setVisible(not self._collapsed)
        self._piece_box.list.setVisible(not self._collapsed and bool(self._pieces))

    def _prompt_rename(self, index: int) -> None:
        if index < 0 or index >= len(self._pieces):
            return
        text, ok = QInputDialog.getText(
            self,
            "Rename piece",
            "Name:",
            QLineEdit.Normal,
            self._pieces[index].name,
        )
        if not ok:
            return
        self.rename_piece(index, str(text))

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


class _PieceBox(QWidget):
    """Saved pieces under the insert list. The list stays hidden while empty."""

    def __init__(self, pane: InsertPane) -> None:
        super().__init__(pane)
        self._pane = pane
        self.setObjectName("formBuilder.savedPiecesBox")
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(0)
        self.title = QLabel("Saved pieces", self)
        self.title.setObjectName("formBuilder.sectionTitle")
        layout.addWidget(self.title)
        self.list = _PieceList(self)
        self.list.setObjectName("formBuilder.savedPieces")
        self.list.setAccessibleName("Saved pieces")
        self.list.setFocusPolicy(_strong())
        self.list.setAcceptDrops(True)
        policy = getattr(getattr(Qt, "ContextMenuPolicy", Qt), "CustomContextMenu")
        self.list.setContextMenuPolicy(policy)
        self.list.customContextMenuRequested.connect(self._menu)
        layout.addWidget(self.list)
        self.list.hide()

    def fill(self, pieces: Sequence[SavedPiece]) -> None:
        self.list.clear()
        role = getattr(Qt, "UserRole")
        for index, piece in enumerate(pieces):
            item = QListWidgetItem(piece.name)
            item.setData(role, index)
            item.setToolTip("Insert %s. Press Enter." % piece.name)
            self.list.addItem(item)
        self._fit()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        width = tokens.focus_border_width
        self.list.setStyleSheet(
            "QListWidget { background: %s; color: %s; border: 1px solid %s; }"
            "QListWidget::item:selected { background: %s; color: %s; }"
            "QListWidget:focus { border: %dpx solid %s; }"
            % (
                tokens.editor_bg,
                tokens.text_primary,
                tokens.border,
                tokens.tree_selected_bg,
                tokens.text_primary,
                width,
                tokens.accent,
            )
        )

    def showEvent(self, event: QEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._fit()

    def dragEnterEvent(self, event: object) -> None:  # noqa: N802
        _accept_node(event)

    def dragMoveEvent(self, event: object) -> None:  # noqa: N802
        _accept_node(event)

    def dropEvent(self, event: object) -> None:  # noqa: N802
        node_id = _accept_node(event)
        if node_id is not None:
            self._pane.save_node(node_id)

    def _fit(self) -> None:
        count = self.list.count()
        if count < 1:
            return
        row_h = self.list.sizeHintForRow(0)
        if row_h < 1:
            return
        shown = count if count < 8 else 8
        self.list.setFixedHeight(row_h * shown + self.list.frameWidth() * 2)

    def _menu(self, pos: QPoint) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        raw = item.data(getattr(Qt, "UserRole"))
        if raw is None:
            return
        self._pane.piece_menu(int(raw)).popup(self.list.mapToGlobal(pos))


class _PieceList(QListWidget):
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        enter = getattr(Qt, "Key_Return")
        keypad = getattr(Qt, "Key_Enter")
        if event.key() in (enter, keypad):
            item = self.currentItem()
            raw = None if item is None else item.data(getattr(Qt, "UserRole"))
            box = self.parent()
            if raw is not None and isinstance(box, _PieceBox):
                box._pane.insert_piece(int(raw))
                return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event: object) -> None:  # noqa: N802
        buttons = getattr(event, "buttons", lambda: 0)()
        left = getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")
        if not buttons & left:
            super().mouseMoveEvent(event)  # type: ignore[arg-type]
            return
        item = self.currentItem()
        if item is None:
            return
        raw = item.data(getattr(Qt, "UserRole"))
        if raw is None:
            return
        box = self.parent()
        if not isinstance(box, _PieceBox):
            return
        piece = box._pane.piece_at(int(raw))
        if piece is None:
            return
        drag = QDrag(self)
        mime = QMimeData()
        raw_xml = piece.xml.encode("utf-8")
        mime.setData(MIME_FRAGMENT, raw_xml)
        mime.setData(MIME_DESIGNER_FRAGMENT, raw_xml)
        drag.setMimeData(mime)
        action = getattr(getattr(Qt, "DropAction", Qt), "CopyAction")
        starter = getattr(drag, "exec", None) or getattr(drag, "exec_")
        starter(action)

    def dragEnterEvent(self, event: object) -> None:  # noqa: N802
        self.parent().dragEnterEvent(event)  # type: ignore[attr-defined]

    def dragMoveEvent(self, event: object) -> None:  # noqa: N802
        self.parent().dragMoveEvent(event)  # type: ignore[attr-defined]

    def dropEvent(self, event: object) -> None:  # noqa: N802
        self.parent().dropEvent(event)  # type: ignore[attr-defined]


def _accept_node(event: object) -> Optional[NodeId]:
    mime = getattr(event, "mimeData", lambda: None)()
    if mime is None or not mime.hasFormat(MIME_NODE):
        event.ignore()  # type: ignore[attr-defined]
        return None
    try:
        node_id = NodeId(int(bytes(mime.data(MIME_NODE)).decode("utf-8").strip()))
    except ValueError:
        event.ignore()  # type: ignore[attr-defined]
        return None
    event.acceptProposedAction()  # type: ignore[attr-defined]
    return node_id


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

        self.canvas = FormCanvas(session, realizer, host, self._splitter)
        self.outline.set_hover_target(self.canvas.send)
        self.outline.set_drop_bridge(self.canvas.send, self.canvas.place_payload)
        self.insert.set_place(self._place_tile)
        self.insert.set_preview(self._preview_insert)
        self.insert.set_drag_finished(self._cancel_place)
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
        self.outline.apply_colors(tokens)
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
        self.insert.apply_theme(tokens)
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

    def _place_from_outline(self, key: str) -> None:
        self._place_tile(key)
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
