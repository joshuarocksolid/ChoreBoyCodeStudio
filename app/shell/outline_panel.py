"""Outline panel widget showing hierarchical Python symbols for the active file.

VS Code-inspired layout: a clickable section header (chevron + title + dim
file name + hover-revealed action buttons), an optional filter row, and a
`QTreeWidget` body that swaps with an empty-state label via a
`QStackedLayout`. The whole panel can be collapsed to header-only height
for embedding in the Explorer sidebar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional

from PySide2.QtCore import QEvent, QSize, Qt, Signal
from PySide2.QtGui import QColor, QFont, QIcon, QKeyEvent, QPainter, QPalette, QPixmap, QPolygon
from PySide2.QtCore import QPoint
from PySide2.QtWidgets import (
    QAbstractItemView,
    QAction,
    QActionGroup,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QStackedLayout,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.intelligence.outline_service import OutlineSymbol, find_innermost_symbol

ROLE_LINE_NUMBER = 410
ROLE_END_LINE_NUMBER = 411
ROLE_QUALIFIED_NAME = 412
ROLE_KIND = 413
ROLE_NAME_LOWER = 414

SORT_POSITION = "position"
SORT_NAME = "name"
SORT_CATEGORY = "category"
_VALID_SORT_MODES = frozenset({SORT_POSITION, SORT_NAME, SORT_CATEGORY})

# Order used for "category" sort. Matches VS Code's outline category grouping.
_CATEGORY_ORDER: dict[str, int] = {
    "class": 0,
    "constant": 1,
    "field": 2,
    "property": 3,
    "method": 4,
    "async_method": 4,
    "function": 5,
    "async_function": 5,
}

_KIND_GLYPHS: dict[str, str] = {
    "class": "C",
    "function": "f",
    "async_function": "f",
    "method": "m",
    "async_method": "m",
    "property": "p",
    "constant": "K",
    "field": "v",
}

# Per-kind accent colors. Kept as light/dark pairs so the icons remain
# legible across themes. VS Code uses similar hue families.
_KIND_COLORS_DARK: dict[str, str] = {
    "class": "#EE9D28",
    "function": "#B180D7",
    "async_function": "#B180D7",
    "method": "#B180D7",
    "async_method": "#B180D7",
    "property": "#75BEFF",
    "field": "#75BEFF",
    "constant": "#4FC1FF",
}
_KIND_COLORS_LIGHT: dict[str, str] = {
    "class": "#D67E00",
    "function": "#8052BD",
    "async_function": "#8052BD",
    "method": "#8052BD",
    "async_method": "#8052BD",
    "property": "#1F6FBF",
    "field": "#1F6FBF",
    "constant": "#0E7BC4",
}

_OUTLINE_ICON_CACHE: dict[tuple[str, str], QIcon] = {}
_CHEVRON_ICON_CACHE: dict[tuple[str, bool], QIcon] = {}


def _kind_color_for(kind: str, *, is_dark: bool) -> str:
    palette = _KIND_COLORS_DARK if is_dark else _KIND_COLORS_LIGHT
    return palette.get(kind, "#888888")


def _make_kind_icon(kind: str, color_hex: str) -> QIcon:
    """Render a 16x16 colored icon for a symbol kind.

    The shape encodes the kind (filled square for constant, rounded box for
    property, circle for class, plain box for the rest) and the colored
    glyph in the center reinforces the meaning.
    """
    glyph = _KIND_GLYPHS.get(kind, "?")
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    color = QColor(color_hex)
    soft = QColor(color)
    soft.setAlpha(40)
    painter.setPen(color)
    painter.setBrush(soft)
    if kind == "class":
        painter.drawEllipse(2, 2, 12, 12)
    elif kind == "constant":
        painter.setBrush(color)
        painter.drawRoundedRect(3, 3, 10, 10, 2, 2)
    elif kind == "property":
        painter.drawRoundedRect(2, 2, 12, 12, 4, 4)
    elif kind == "field":
        painter.drawRoundedRect(2, 4, 12, 8, 2, 2)
    else:
        painter.drawRoundedRect(2, 2, 12, 12, 2, 2)
    glyph_color = QColor(color)
    if kind == "constant":
        glyph_color = QColor("#FFFFFF")
    painter.setPen(glyph_color)
    font = QFont()
    font.setPointSize(8)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), int(Qt.AlignCenter), glyph)
    painter.end()
    return QIcon(pixmap)


def _kind_icon(kind: str, color_hex: str) -> QIcon:
    key = (kind, color_hex)
    cached = _OUTLINE_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    icon = _make_kind_icon(kind, color_hex)
    _OUTLINE_ICON_CACHE[key] = icon
    return icon


def _make_chevron_icon(color_hex: str, *, expanded: bool) -> QIcon:
    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    color = QColor(color_hex)
    painter.setPen(color)
    painter.setBrush(color)
    if expanded:
        # Down-pointing triangle.
        triangle = QPolygon([QPoint(2, 4), QPoint(10, 4), QPoint(6, 9)])
    else:
        # Right-pointing triangle.
        triangle = QPolygon([QPoint(4, 2), QPoint(9, 6), QPoint(4, 10)])
    painter.drawPolygon(triangle)
    painter.end()
    return QIcon(pixmap)


def _chevron_icon(color_hex: str, *, expanded: bool) -> QIcon:
    key = (color_hex, expanded)
    cached = _CHEVRON_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    icon = _make_chevron_icon(color_hex, expanded=expanded)
    _CHEVRON_ICON_CACHE[key] = icon
    return icon


def _make_codicon_text_icon(symbol: str, color_hex: str) -> QIcon:
    """Render a tiny single-glyph icon for action buttons (filter, sort ...)."""
    pixmap = QPixmap(14, 14)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor(color_hex))
    font = QFont()
    font.setPointSize(9)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), int(Qt.AlignCenter), symbol)
    painter.end()
    return QIcon(pixmap)


def clear_icon_caches() -> None:
    """Release cached `QIcon` objects so Shiboken can tear down cleanly."""
    _OUTLINE_ICON_CACHE.clear()
    _CHEVRON_ICON_CACHE.clear()


class _IndentGuideDelegate(QStyledItemDelegate):
    """Paints subtle vertical indent guides at each tree-indent level."""

    def __init__(self, tree: QTreeWidget) -> None:
        super().__init__(tree)
        self._tree = tree

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # type: ignore[override]
        super().paint(painter, option, index)
        depth = self._depth_of(index)
        if depth <= 0:
            return
        indent = self._tree.indentation()
        if indent <= 0:
            return
        palette = self._tree.palette()
        guide_color = QColor(palette.color(QPalette.Mid))
        guide_color.setAlpha(70)
        painter.save()
        painter.setPen(guide_color)
        rect = option.rect
        for level in range(depth):
            x = rect.left() - (depth - level) * indent + indent // 2
            painter.drawLine(x, rect.top(), x, rect.bottom())
        painter.restore()

    def _depth_of(self, index) -> int:  # type: ignore[no-untyped-def]
        depth = 0
        parent = index.parent()
        while parent.isValid():
            depth += 1
            parent = parent.parent()
        return depth


class _OutlineTreeWidget(QTreeWidget):
    """Tree widget that paints an explicit chevron for items with children.

    The default Qt branch indicator on the Linux Fusion style is so subtle that
    parent rows look indistinguishable from leaves. We override `drawBranches`
    to render the same triangle the panel header uses, in the resolved theme
    color, snapped to the right edge of the branch column (just left of the
    kind icon).
    """

    _CHEVRON_SIZE = 10

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._chevron_color: str = "#808080"

    def set_chevron_color(self, color_hex: str) -> None:
        if not color_hex:
            return
        if color_hex == self._chevron_color:
            return
        self._chevron_color = color_hex
        viewport = self.viewport()
        if viewport is not None:
            viewport.update()

    def chevron_color(self) -> str:
        return self._chevron_color

    def drawBranches(self, painter: QPainter, rect, index) -> None:  # type: ignore[no-untyped-def, override]
        item = self.itemFromIndex(index)
        if item is None or item.childCount() == 0:
            super().drawBranches(painter, rect, index)
            return
        icon = _chevron_icon(self._chevron_color, expanded=item.isExpanded())
        size = self._CHEVRON_SIZE
        x = rect.right() - size
        y = rect.top() + (rect.height() - size) // 2
        icon.paint(painter, x, y, size, size)


class _OutlineHeaderBar(QWidget):
    """VS Code-style section header: chevron + title + file label + actions."""

    toggled: Any = Signal(bool)
    filter_toggled: Any = Signal(bool)
    follow_cursor_toggled: Any = Signal(bool)
    sort_mode_changed: Any = Signal(str)
    collapse_all_clicked: Any = Signal()
    expand_all_clicked: Any = Signal()
    hide_clicked: Any = Signal()

    _ACTION_BUTTON_OBJECT_NAMES = (
        "shell.outlinePanel.action.filter",
        "shell.outlinePanel.action.follow",
        "shell.outlinePanel.action.sort",
        "shell.outlinePanel.action.collapseAll",
        "shell.outlinePanel.action.more",
    )

    # Floor for the collapsed strip height. Must clear the natural QToolButton
    # sizeHint plus a couple of pixels of breathing room so the bar reads as a
    # distinct strip rather than fusing into the bottom panel below.
    MIN_HEADER_HEIGHT = 28

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.outlinePanel.header")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(self.MIN_HEADER_HEIGHT)
        self.setProperty("collapsed", False)

        self._collapsed = False
        self._hover = False
        self._sort_mode = SORT_POSITION

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        self._chevron_btn = QToolButton(self)
        self._chevron_btn.setObjectName("shell.outlinePanel.chevron")
        self._chevron_btn.setAutoRaise(True)
        self._chevron_btn.setFocusPolicy(Qt.NoFocus)
        self._chevron_btn.setIconSize(QSize(12, 12))
        self._chevron_btn.setCursor(Qt.PointingHandCursor)
        self._chevron_btn.clicked.connect(self._handle_chevron_clicked)
        layout.addWidget(self._chevron_btn)

        self._title_label = QLabel("OUTLINE", self)
        self._title_label.setObjectName("shell.outlinePanel.title")
        layout.addWidget(self._title_label)

        self._file_label = QLabel("", self)
        self._file_label.setObjectName("shell.outlinePanel.fileLabel")
        self._file_label.setTextInteractionFlags(Qt.NoTextInteraction)
        layout.addWidget(self._file_label, 1)

        self._filter_btn = self._make_action_button(
            "shell.outlinePanel.action.filter",
            tooltip="Filter symbols",
            checkable=True,
        )
        self._filter_btn.toggled.connect(self.filter_toggled)
        layout.addWidget(self._filter_btn)

        self._follow_btn = self._make_action_button(
            "shell.outlinePanel.action.follow",
            tooltip="Follow Cursor",
            checkable=True,
        )
        self._follow_btn.setChecked(True)
        self._follow_btn.toggled.connect(self.follow_cursor_toggled)
        layout.addWidget(self._follow_btn)

        self._sort_btn = self._make_action_button(
            "shell.outlinePanel.action.sort",
            tooltip="Sort By",
            checkable=False,
        )
        self._sort_btn.setPopupMode(QToolButton.InstantPopup)
        self._sort_menu = QMenu(self._sort_btn)
        self._sort_action_group = QActionGroup(self._sort_menu)
        self._sort_action_group.setExclusive(True)
        self._sort_actions: dict[str, QAction] = {}
        for mode, label in (
            (SORT_POSITION, "Sort By: Position"),
            (SORT_NAME, "Sort By: Name"),
            (SORT_CATEGORY, "Sort By: Category"),
        ):
            action = QAction(label, self._sort_menu)
            action.setCheckable(True)
            action.setData(mode)
            self._sort_action_group.addAction(action)
            self._sort_menu.addAction(action)
            self._sort_actions[mode] = action
        self._sort_actions[SORT_POSITION].setChecked(True)
        self._sort_action_group.triggered.connect(self._handle_sort_action_triggered)
        self._sort_btn.setMenu(self._sort_menu)
        layout.addWidget(self._sort_btn)

        self._collapse_all_btn = self._make_action_button(
            "shell.outlinePanel.action.collapseAll",
            tooltip="Collapse All",
            checkable=False,
        )
        self._collapse_all_btn.clicked.connect(self.collapse_all_clicked)
        layout.addWidget(self._collapse_all_btn)

        self._more_btn = self._make_action_button(
            "shell.outlinePanel.action.more",
            tooltip="More Actions",
            checkable=False,
        )
        self._more_btn.setPopupMode(QToolButton.InstantPopup)
        self._more_menu = QMenu(self._more_btn)
        self._expand_all_action = QAction("Expand All", self._more_menu)
        self._expand_all_action.triggered.connect(self.expand_all_clicked)
        self._more_menu.addAction(self._expand_all_action)
        self._collapse_all_action = QAction("Collapse All", self._more_menu)
        self._collapse_all_action.triggered.connect(self.collapse_all_clicked)
        self._more_menu.addAction(self._collapse_all_action)
        self._more_menu.addSeparator()
        self._hide_action = QAction("Hide Outline", self._more_menu)
        self._hide_action.triggered.connect(self.hide_clicked)
        self._more_menu.addAction(self._hide_action)
        self._more_btn.setMenu(self._more_menu)
        layout.addWidget(self._more_btn)

        self._update_chevron_icon()
        self._refresh_action_visibility()

    # -- public API --

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.setProperty("collapsed", bool(collapsed))
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self._update_chevron_icon()
        self._refresh_action_visibility()

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_file_label(self, text: str) -> None:
        self._file_label.setText(text)

    def set_filter_active(self, active: bool) -> None:
        was = self._filter_btn.blockSignals(True)
        self._filter_btn.setChecked(active)
        self._filter_btn.blockSignals(was)
        self._refresh_action_visibility()

    def set_follow_cursor(self, follow: bool) -> None:
        was = self._follow_btn.blockSignals(True)
        self._follow_btn.setChecked(follow)
        self._follow_btn.blockSignals(was)
        self._refresh_action_visibility()

    def set_sort_mode(self, mode: str) -> None:
        if mode not in _VALID_SORT_MODES:
            mode = SORT_POSITION
        if mode == self._sort_mode:
            return
        self._sort_mode = mode
        action = self._sort_actions.get(mode)
        if action is not None:
            was = self._sort_action_group.blockSignals(True)
            action.setChecked(True)
            self._sort_action_group.blockSignals(was)

    def chevron_button(self) -> QToolButton:
        return self._chevron_btn

    def filter_button(self) -> QToolButton:
        return self._filter_btn

    def follow_button(self) -> QToolButton:
        return self._follow_btn

    def sort_button(self) -> QToolButton:
        return self._sort_btn

    def collapse_all_button(self) -> QToolButton:
        return self._collapse_all_btn

    def more_button(self) -> QToolButton:
        return self._more_btn

    def apply_theme_colors(self, *, icon_color: str, accent_color: str) -> None:
        self._icon_color = icon_color
        self._accent_color = accent_color
        self._update_chevron_icon()
        self._update_action_icons()

    # -- events --

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.LeftButton:
            target = self.childAt(event.pos())
            if target is None or target is self._chevron_btn or target is self._title_label or target is self._file_label:
                self._collapsed = not self._collapsed
                self._update_chevron_icon()
                self._refresh_action_visibility()
                self.toggled.emit(self._collapsed)
                event.accept()
                return
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._hover = True
        self._refresh_action_visibility()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._hover = False
        self._refresh_action_visibility()
        super().leaveEvent(event)

    # -- internal --

    def _make_action_button(
        self,
        object_name: str,
        *,
        tooltip: str,
        checkable: bool,
    ) -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName(object_name)
        btn.setAutoRaise(True)
        btn.setCheckable(checkable)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tooltip)
        btn.setIconSize(QSize(14, 14))
        btn.setFocusPolicy(Qt.NoFocus)
        return btn

    def _handle_chevron_clicked(self) -> None:
        self._collapsed = not self._collapsed
        self._update_chevron_icon()
        self._refresh_action_visibility()
        self.toggled.emit(self._collapsed)

    def _handle_sort_action_triggered(self, action: QAction) -> None:
        mode = action.data()
        if not isinstance(mode, str) or mode not in _VALID_SORT_MODES:
            return
        if mode == self._sort_mode:
            return
        self._sort_mode = mode
        self.sort_mode_changed.emit(mode)

    def _resolved_icon_color(self) -> str:
        return getattr(self, "_icon_color", self.palette().color(QPalette.Text).name())

    def _resolved_accent_color(self) -> str:
        return getattr(self, "_accent_color", self.palette().color(QPalette.Highlight).name())

    def _update_chevron_icon(self) -> None:
        color = self._resolved_icon_color()
        self._chevron_btn.setIcon(_chevron_icon(color, expanded=not self._collapsed))

    def _update_action_icons(self) -> None:
        color = self._resolved_icon_color()
        self._filter_btn.setIcon(_make_codicon_text_icon("F", color))
        self._follow_btn.setIcon(_make_codicon_text_icon("\u00b7", color))
        self._sort_btn.setIcon(_make_codicon_text_icon("\u21f5", color))
        self._collapse_all_btn.setIcon(_make_codicon_text_icon("\u2212", color))
        self._more_btn.setIcon(_make_codicon_text_icon("\u22ef", color))

    def _refresh_action_visibility(self) -> None:
        if self._collapsed:
            for btn in self._action_buttons():
                btn.setVisible(False)
            return
        show_all = self._hover
        for btn in self._action_buttons():
            sticky = btn.isCheckable() and btn.isChecked()
            btn.setVisible(show_all or sticky)

    def _action_buttons(self) -> tuple[QToolButton, ...]:
        return (
            self._filter_btn,
            self._follow_btn,
            self._sort_btn,
            self._collapse_all_btn,
            self._more_btn,
        )


class _OutlineFilterRow(QWidget):
    """Inline search box that filters the outline tree by symbol name."""

    text_changed: Any = Signal(str)
    closed: Any = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.outlinePanel.filterRow")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self._line_edit = QLineEdit(self)
        self._line_edit.setObjectName("shell.outlinePanel.filter")
        self._line_edit.setPlaceholderText("Filter symbols")
        self._line_edit.setClearButtonEnabled(True)
        self._line_edit.textChanged.connect(self.text_changed)
        self._line_edit.installEventFilter(self)
        layout.addWidget(self._line_edit, 1)

    def line_edit(self) -> QLineEdit:
        return self._line_edit

    def focus(self) -> None:
        self._line_edit.setFocus(Qt.ShortcutFocusReason)
        self._line_edit.selectAll()

    def text(self) -> str:
        return self._line_edit.text()

    def set_text(self, text: str) -> None:
        if self._line_edit.text() == text:
            return
        self._line_edit.setText(text)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if watched is self._line_edit and event.type() == QEvent.KeyPress:
            assert isinstance(event, QKeyEvent)
            if event.key() == Qt.Key_Escape:
                if self._line_edit.text():
                    self._line_edit.clear()
                else:
                    self.closed.emit()
                return True
        return super().eventFilter(watched, event)


class OutlinePanel(QWidget):
    """Tree of classes/functions/methods/properties for the active editor."""

    symbol_activated: Any = Signal(str, int)
    collapsed_changed: Any = Signal(bool)
    follow_cursor_changed: Any = Signal(bool)
    sort_mode_changed: Any = Signal(str)
    hide_requested: Any = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.outlinePanel")
        self.setAttribute(Qt.WA_StyledBackground, True)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._header = _OutlineHeaderBar(self)
        self._header.toggled.connect(self._handle_header_toggled)
        self._header.filter_toggled.connect(self._handle_filter_toggled)
        self._header.follow_cursor_toggled.connect(self._handle_follow_toggled)
        self._header.sort_mode_changed.connect(self._handle_sort_changed)
        self._header.collapse_all_clicked.connect(self.collapse_all)
        self._header.expand_all_clicked.connect(self.expand_all)
        self._header.hide_clicked.connect(self.hide_requested)
        root_layout.addWidget(self._header)

        self._filter_row = _OutlineFilterRow(self)
        self._filter_row.text_changed.connect(self._handle_filter_text_changed)
        self._filter_row.closed.connect(self._handle_filter_closed)
        self._filter_row.setVisible(False)
        root_layout.addWidget(self._filter_row)

        self._stack_container = QWidget(self)
        self._stack_container.setObjectName("shell.outlinePanel.body")
        self._stack_layout = QStackedLayout(self._stack_container)
        self._stack_layout.setContentsMargins(0, 0, 0, 0)

        self._tree = _OutlineTreeWidget(self._stack_container)
        self._tree.setObjectName("shell.outlinePanel.tree")
        self._tree.setHeaderHidden(True)
        self._tree.setColumnCount(1)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(18)
        self._tree.setUniformRowHeights(True)
        self._tree.setExpandsOnDoubleClick(False)
        self._tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tree.setAnimated(False)
        self._tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tree.setIconSize(QSize(16, 16))
        header = self._tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        self._indent_delegate = _IndentGuideDelegate(self._tree)
        self._tree.setItemDelegate(self._indent_delegate)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemActivated.connect(self._on_item_activated)
        self._tree.itemDoubleClicked.connect(self._on_item_activated)
        self._tree.itemExpanded.connect(self._handle_item_expansion_changed)
        self._tree.itemCollapsed.connect(self._handle_item_expansion_changed)
        self._tree.installEventFilter(self)
        self._stack_layout.addWidget(self._tree)

        self._empty_label = QLabel("Open a Python file to see its outline.", self._stack_container)
        self._empty_label.setObjectName("shell.outlinePanel.emptyLabel")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setContentsMargins(12, 16, 12, 16)
        self._stack_layout.addWidget(self._empty_label)
        self._stack_layout.setCurrentWidget(self._empty_label)

        root_layout.addWidget(self._stack_container, 1)

        self._current_file_path: Optional[str] = None
        self._symbols: tuple[OutlineSymbol, ...] = ()
        self._items_by_qualified_name: dict[str, QTreeWidgetItem] = {}
        self._highlighted_qualified_name: Optional[str] = None
        self._collapsed = False
        self._follow_cursor = True
        self._sort_mode = SORT_POSITION
        self._filter_text = ""
        self._filter_visible = False
        self._pre_filter_expansion: Optional[set[str]] = None
        self._max_height_expanded = self.maximumHeight()

    # -- public API --

    def tree_widget(self) -> QTreeWidget:
        return self._tree

    def empty_label(self) -> QLabel:
        return self._empty_label

    def header_bar(self) -> _OutlineHeaderBar:
        return self._header

    def filter_row(self) -> _OutlineFilterRow:
        return self._filter_row

    def current_file_path(self) -> Optional[str]:
        return self._current_file_path

    def symbols(self) -> tuple[OutlineSymbol, ...]:
        return self._symbols

    def is_collapsed(self) -> bool:
        return self._collapsed

    def is_follow_cursor_enabled(self) -> bool:
        return self._follow_cursor

    def sort_mode(self) -> str:
        return self._sort_mode

    def filter_text(self) -> str:
        return self._filter_text

    def is_filter_visible(self) -> bool:
        return self._filter_visible

    def set_collapsed(self, collapsed: bool) -> None:
        collapsed = bool(collapsed)
        if collapsed == self._collapsed:
            self._header.set_collapsed(collapsed)
            return
        self._collapsed = collapsed
        self._header.set_collapsed(collapsed)
        if collapsed:
            self._filter_row.setVisible(False)
            self._stack_container.setVisible(False)
            header_h = self._collapsed_header_height()
            self.setMinimumHeight(header_h)
            self.setMaximumHeight(header_h)
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self._stack_container.setVisible(True)
            self._filter_row.setVisible(self._filter_visible)
        self.collapsed_changed.emit(collapsed)

    def _collapsed_header_height(self) -> int:
        """Resolve the floor height used when the panel is collapsed.

        Stylesheet `min-height` is not always reflected in `QWidget.sizeHint()`
        (the tool-button row can hint smaller than the QSS value), so combine
        every available signal and clamp to the header's own minimum so the
        collapsed strip never gets squeezed below a usable height.
        """
        candidates = (
            self._header.minimumSizeHint().height(),
            self._header.sizeHint().height(),
            self._header.minimumHeight(),
            _OutlineHeaderBar.MIN_HEADER_HEIGHT,
        )
        return max(candidates)

    def set_follow_cursor(self, follow: bool) -> None:
        follow = bool(follow)
        if follow == self._follow_cursor:
            self._header.set_follow_cursor(follow)
            return
        self._follow_cursor = follow
        self._header.set_follow_cursor(follow)
        self.follow_cursor_changed.emit(follow)

    def set_sort_mode(self, mode: str) -> None:
        if mode not in _VALID_SORT_MODES:
            mode = SORT_POSITION
        if mode == self._sort_mode:
            self._header.set_sort_mode(mode)
            return
        self._sort_mode = mode
        self._header.set_sort_mode(mode)
        if self._symbols:
            self._render_tree(preserve_expansion=True)
            if self._filter_text:
                self._apply_filter()
        self.sort_mode_changed.emit(mode)

    def set_filter_visible(self, visible: bool) -> None:
        visible = bool(visible)
        if visible == self._filter_visible:
            self._header.set_filter_active(visible)
            return
        self._filter_visible = visible
        self._header.set_filter_active(visible)
        if not self._collapsed:
            self._filter_row.setVisible(visible)
        if visible:
            self._filter_row.focus()
        else:
            self._filter_row.set_text("")

    def set_filter_text(self, text: str) -> None:
        text = text or ""
        if text == self._filter_text:
            return
        self._filter_text = text
        self._filter_row.set_text(text)
        self._apply_filter()

    def collapse_all(self) -> None:
        self._tree.collapseAll()

    def expand_all(self) -> None:
        self._tree.expandAll()

    def set_outline(self, symbols: Iterable[OutlineSymbol], file_path: str) -> None:
        """Populate the tree with the given symbols for `file_path`.

        When called repeatedly with the same `file_path`, expansion state for
        symbols whose `qualified_name` survives the rebuild is preserved.
        Switching `file_path` discards the snapshot.
        """
        symbol_tuple = tuple(symbols)
        same_file = self._current_file_path == file_path
        expanded_snapshot: set[str] = set()
        if same_file:
            expanded_snapshot = self._snapshot_expanded()
        self._current_file_path = file_path
        self._symbols = symbol_tuple
        self._header.set_file_label(Path(file_path).name if file_path else "")

        if not symbol_tuple:
            self._tree.clear()
            self._items_by_qualified_name.clear()
            self._empty_label.setText("No symbols in this file.")
            self._stack_layout.setCurrentWidget(self._empty_label)
            return

        self._render_tree(preserve_expansion=same_file, expanded_snapshot=expanded_snapshot)
        self._stack_layout.setCurrentWidget(self._tree)
        if self._filter_text:
            self._apply_filter()

    def clear(self) -> None:
        self._tree.clear()
        self._items_by_qualified_name.clear()
        self._symbols = ()
        self._current_file_path = None
        self._highlighted_qualified_name = None
        self._header.set_file_label("")
        self._empty_label.setText("Open a Python file to see its outline.")
        self._stack_layout.setCurrentWidget(self._empty_label)

    def set_unsupported_language(self, language: str) -> None:
        """Show a placeholder noting that outline isn't supported for the file."""
        self._tree.clear()
        self._items_by_qualified_name.clear()
        self._symbols = ()
        self._current_file_path = None
        self._highlighted_qualified_name = None
        self._header.set_file_label("")
        if language == "python":
            self._empty_label.setText("Open a Python file to see its outline.")
        else:
            self._empty_label.setText(f"No outline available for {language} files.")
        self._stack_layout.setCurrentWidget(self._empty_label)

    def highlight_symbol_at_line(self, line_number: int) -> None:
        """Select the innermost symbol containing `line_number` (1-based)."""
        if not self._symbols:
            return
        match = find_innermost_symbol(self._symbols, line_number)
        if match is None:
            self._tree.clearSelection()
            self._highlighted_qualified_name = None
            return
        if match.qualified_name == self._highlighted_qualified_name:
            return
        item = self._items_by_qualified_name.get(match.qualified_name)
        if item is None:
            return
        self._tree.setCurrentItem(item)
        self._tree.scrollToItem(item)
        self._highlighted_qualified_name = match.qualified_name

    def apply_theme_tokens(self, tokens) -> None:  # type: ignore[no-untyped-def]
        """Inject the active theme colors so icons stay crisp across themes."""
        try:
            icon_color = tokens.icon_primary or tokens.text_primary
            accent_color = tokens.accent or tokens.text_primary
            self._is_dark = bool(getattr(tokens, "is_dark", False))
        except AttributeError:
            return
        self._header.apply_theme_colors(icon_color=icon_color, accent_color=accent_color)
        self._tree.set_chevron_color(icon_color)
        if self._symbols:
            self._render_tree(preserve_expansion=True)
            if self._filter_text:
                self._apply_filter()

    # -- internal --

    def _is_dark_theme(self) -> bool:
        if hasattr(self, "_is_dark"):
            return bool(self._is_dark)
        return self.palette().color(QPalette.Window).lightness() < 128

    def _sort_symbols(
        self, symbols: tuple[OutlineSymbol, ...]
    ) -> tuple[OutlineSymbol, ...]:
        if self._sort_mode == SORT_POSITION:
            return symbols

        def key(sym: OutlineSymbol) -> tuple[int, str, int]:
            if self._sort_mode == SORT_NAME:
                return (0, sym.name.lower(), sym.line_number)
            return (
                _CATEGORY_ORDER.get(sym.kind, 100),
                sym.name.lower(),
                sym.line_number,
            )

        sorted_top = sorted(symbols, key=key)
        return tuple(self._sort_recursive(s) for s in sorted_top)

    def _sort_recursive(self, symbol: OutlineSymbol) -> OutlineSymbol:
        if not symbol.children:
            return symbol
        sorted_children = self._sort_symbols(symbol.children)
        return OutlineSymbol(
            name=symbol.name,
            qualified_name=symbol.qualified_name,
            kind=symbol.kind,
            line_number=symbol.line_number,
            end_line_number=symbol.end_line_number,
            detail=symbol.detail,
            children=sorted_children,
        )

    def _render_tree(
        self,
        *,
        preserve_expansion: bool,
        expanded_snapshot: Optional[set[str]] = None,
    ) -> None:
        if expanded_snapshot is None and preserve_expansion:
            expanded_snapshot = self._snapshot_expanded()
        self._tree.setUpdatesEnabled(False)
        try:
            self._tree.clear()
            self._items_by_qualified_name.clear()
            sorted_symbols = self._sort_symbols(self._symbols)
            for symbol in sorted_symbols:
                self._add_symbol(symbol, parent=None)
            if expanded_snapshot:
                self._restore_expansion(expanded_snapshot)
        finally:
            self._tree.setUpdatesEnabled(True)

    def _add_symbol(
        self,
        symbol: OutlineSymbol,
        *,
        parent: Optional[QTreeWidgetItem],
    ) -> None:
        if parent is None:
            item = QTreeWidgetItem(self._tree)
        else:
            item = QTreeWidgetItem(parent)
        text = symbol.name
        if symbol.detail:
            text = f"{symbol.name}  {symbol.detail}"
        item.setText(0, text)
        color = _kind_color_for(symbol.kind, is_dark=self._is_dark_theme())
        item.setIcon(0, _kind_icon(symbol.kind, color))
        item.setData(0, ROLE_LINE_NUMBER, symbol.line_number)
        item.setData(0, ROLE_END_LINE_NUMBER, symbol.end_line_number)
        item.setData(0, ROLE_QUALIFIED_NAME, symbol.qualified_name)
        item.setData(0, ROLE_KIND, symbol.kind)
        item.setData(0, ROLE_NAME_LOWER, symbol.name.lower())
        item.setToolTip(0, f"{symbol.qualified_name} (Ln {symbol.line_number})")
        self._items_by_qualified_name[symbol.qualified_name] = item
        for child in symbol.children:
            self._add_symbol(child, parent=item)

    def _snapshot_expanded(self) -> set[str]:
        expanded: set[str] = set()
        iterator = self._iter_items(self._tree.invisibleRootItem())
        for item in iterator:
            qualified = item.data(0, ROLE_QUALIFIED_NAME)
            if isinstance(qualified, str) and item.isExpanded():
                expanded.add(qualified)
        return expanded

    def _restore_expansion(self, expanded: set[str]) -> None:
        if not expanded:
            return
        for qualified, item in self._items_by_qualified_name.items():
            if qualified in expanded:
                item.setExpanded(True)

    def _iter_items(self, root: QTreeWidgetItem) -> Iterable[QTreeWidgetItem]:
        stack: list[QTreeWidgetItem] = [root.child(i) for i in range(root.childCount())]
        while stack:
            item = stack.pop()
            if item is None:
                continue
            yield item
            for i in range(item.childCount()):
                stack.append(item.child(i))

    def _apply_filter(self) -> None:
        text = self._filter_text.strip().lower()
        if not text:
            for item in self._iter_items(self._tree.invisibleRootItem()):
                item.setHidden(False)
            if self._pre_filter_expansion is not None:
                self._collapse_all_items()
                self._restore_expansion(self._pre_filter_expansion)
                self._pre_filter_expansion = None
            return
        if self._pre_filter_expansion is None:
            self._pre_filter_expansion = self._snapshot_expanded()
        self._filter_visit(self._tree.invisibleRootItem(), text)

    def _filter_visit(self, parent: QTreeWidgetItem, text: str) -> bool:
        any_visible = False
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child is None:
                continue
            child_visible = self._filter_visit(child, text)
            name = child.data(0, ROLE_NAME_LOWER)
            self_match = isinstance(name, str) and text in name
            visible = bool(child_visible or self_match)
            child.setHidden(not visible)
            if visible:
                any_visible = True
                if child_visible and not self_match:
                    child.setExpanded(True)
                elif self_match and child.childCount() > 0 and child_visible:
                    child.setExpanded(True)
        return any_visible

    def _collapse_all_items(self) -> None:
        for item in self._items_by_qualified_name.values():
            item.setExpanded(False)

    # -- handlers --

    def _handle_header_toggled(self, collapsed: bool) -> None:
        # Header already updated its internal state; mirror externally.
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        if collapsed:
            self._filter_row.setVisible(False)
            self._stack_container.setVisible(False)
            header_h = self._collapsed_header_height()
            self.setMinimumHeight(header_h)
            self.setMaximumHeight(header_h)
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self._stack_container.setVisible(True)
            self._filter_row.setVisible(self._filter_visible)
        self.collapsed_changed.emit(collapsed)

    def _handle_filter_toggled(self, active: bool) -> None:
        self.set_filter_visible(active)

    def _handle_filter_closed(self) -> None:
        self.set_filter_visible(False)

    def _handle_follow_toggled(self, follow: bool) -> None:
        if follow == self._follow_cursor:
            return
        self._follow_cursor = follow
        self.follow_cursor_changed.emit(follow)

    def _handle_sort_changed(self, mode: str) -> None:
        if mode not in _VALID_SORT_MODES:
            return
        if mode == self._sort_mode:
            return
        self._sort_mode = mode
        if self._symbols:
            self._render_tree(preserve_expansion=True)
            if self._filter_text:
                self._apply_filter()
        self.sort_mode_changed.emit(mode)

    def _handle_filter_text_changed(self, text: str) -> None:
        if text == self._filter_text:
            return
        self._filter_text = text
        self._apply_filter()

    # -- signals --

    def _handle_item_expansion_changed(self, _item: QTreeWidgetItem) -> None:
        viewport = self._tree.viewport()
        if viewport is not None:
            viewport.update()

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        self._emit_activated(item)

    def _on_item_activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        self._emit_activated(item)

    def _emit_activated(self, item: QTreeWidgetItem) -> None:
        if item is None or self._current_file_path is None:
            return
        line = item.data(0, ROLE_LINE_NUMBER)
        if line is None:
            return
        try:
            resolved = int(line)
        except (TypeError, ValueError):
            return
        self.symbol_activated.emit(self._current_file_path, resolved)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if watched is self._tree and event.type() == QEvent.KeyPress:
            assert isinstance(event, QKeyEvent)
            if event.key() == Qt.Key_Escape and self._filter_visible:
                self.set_filter_visible(False)
                return True
        return super().eventFilter(watched, event)
