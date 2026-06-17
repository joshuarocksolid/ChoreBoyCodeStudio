"""Outline panel orchestrator: header, filter, and symbol tree."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional

from PySide2.QtCore import QEvent, QSize, Qt, Signal
from PySide2.QtGui import QKeyEvent
from PySide2.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QStackedLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.intelligence.outline_service import OutlineSymbol, find_innermost_symbol
from app.shell.outline.outline_filter import _OutlineFilterRow
from app.shell.outline.outline_header import _OutlineHeaderBar
from app.shell.outline.outline_icons import clear_icon_caches, kind_color_for, kind_icon
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette
from app.shell.outline.outline_tree import (
    ROLE_END_LINE_NUMBER,
    ROLE_KIND,
    ROLE_LINE_NUMBER,
    ROLE_NAME_LOWER,
    ROLE_QUALIFIED_NAME,
    SORT_CATEGORY,
    SORT_NAME,
    SORT_POSITION,
    _CATEGORY_ORDER,
    _IndentGuideDelegate,
    _OutlineTreeWidget,
    _VALID_SORT_MODES,
)


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
        self._theme_tokens: ShellThemeTokens | None = None

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
        self._apply_collapsed_layout(collapsed, emit=True)

    def _apply_collapsed_layout(self, collapsed: bool, *, emit: bool) -> None:
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
        if emit:
            self.collapsed_changed.emit(collapsed)

    def _collapsed_header_height(self) -> int:
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

    def apply_theme_tokens(self, tokens: ShellThemeTokens) -> None:
        icon_color = tokens.icon_primary or tokens.text_primary
        accent_color = tokens.accent or tokens.text_primary
        self._theme_tokens = tokens
        self._header.apply_theme_colors(icon_color=icon_color, accent_color=accent_color)
        self._tree.set_chevron_color(icon_color)
        if self._symbols:
            self._refresh_symbol_icons()

    def _refresh_symbol_icons(self) -> None:
        """Repaint kind icons in place without rebuilding the symbol tree."""
        clear_icon_caches()
        tokens = self._resolve_theme_tokens()
        for item in self._iter_items(self._tree.invisibleRootItem()):
            kind = item.data(0, ROLE_KIND)
            if not isinstance(kind, str):
                continue
            color = kind_color_for(kind, tokens)
            item.setIcon(0, kind_icon(kind, color))
        viewport = self._tree.viewport()
        if viewport is not None:
            viewport.update()

    def _resolve_theme_tokens(self) -> ShellThemeTokens:
        if self._theme_tokens is not None:
            return self._theme_tokens
        return tokens_from_palette(self.palette())

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
        color = kind_color_for(symbol.kind, self._resolve_theme_tokens())
        item.setIcon(0, kind_icon(symbol.kind, color))
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

    def _handle_header_toggled(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._apply_collapsed_layout(collapsed, emit=True)

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
