"""Quick "Go to Symbol in File" dialog (Sublime/VSCode-style).

Themed frameless overlay showing a flat list of symbols from the active file.
The user types to filter by substring (case-insensitive), Enter commits, and
Escape cancels. While navigating, a ``symbol_preview`` signal fires so the
host can scroll the editor without committing the cursor jump.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

from PySide2.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, Qt, Signal
from PySide2.QtGui import QColor, QFont, QFontMetrics, QIcon, QKeyEvent, QPainter, QPen
from PySide2.QtWidgets import (
    QDialog,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QStackedLayout,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from app.intelligence.outline_service import OutlineSymbol
from app.shell.icon_provider import symbol_icon
from app.shell.outline.outline_icons import kind_color_for, kind_icon
from app.shell.theme_tokens import ShellThemeTokens


_ROW_HEIGHT = 28
_ICON_SIZE = 16
_DEPTH_INDENT = 12
_ICON_LEFT_MARGIN = 8
_TEXT_GAP = 8
_RIGHT_MARGIN = 12
_LINE_BADGE_PAD_X = 6
_LINE_BADGE_PAD_Y = 2

SymbolRole = Qt.UserRole + 1
MatchIndicesRole = Qt.UserRole + 2


@dataclass(frozen=True)
class QuickSymbolRow:
    """One row in the quick-symbol list."""

    symbol: OutlineSymbol
    depth: int
    match_indices: frozenset[int]


def _symbol_depth(symbol: OutlineSymbol) -> int:
    return symbol.qualified_name.count(".")


def _index_at_line(symbols: Sequence[OutlineSymbol], line: int) -> int | None:
    best_idx: int | None = None
    best_span: int | None = None
    for index, symbol in enumerate(symbols):
        if symbol.line_number <= line <= symbol.end_line_number:
            span = symbol.end_line_number - symbol.line_number
            if best_span is None or span < best_span:
                best_span = span
                best_idx = index
    return best_idx


def _match_indices_in_name(name: str, needle: str) -> frozenset[int]:
    if not needle:
        return frozenset()
    lower = name.lower()
    start = lower.find(needle)
    if start == -1:
        return frozenset()
    return frozenset(range(start, start + len(needle)))


def _symbol_matches_filter(symbol: OutlineSymbol, needle: str) -> bool:
    if not needle:
        return True
    haystacks = (
        symbol.name.lower(),
        symbol.qualified_name.lower(),
        symbol.detail.lower(),
    )
    return any(needle in haystack for haystack in haystacks)


class QuickSymbolListModel(QAbstractListModel):
    """List model exposing only rows visible under the current filter."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: tuple[QuickSymbolRow, ...] = ()
        self._display_indices: list[int] = []
        self._filter_text = ""

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._display_indices)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> object | None:  # noqa: N802
        if not index.isValid():
            return None
        row = self._row_at(index.row())
        if row is None:
            return None
        if role == Qt.DisplayRole:
            return row.symbol.name
        if role == Qt.ToolTipRole:
            symbol = row.symbol
            return f"{symbol.qualified_name} (Ln {symbol.line_number})"
        if role == SymbolRole:
            return row
        if role == MatchIndicesRole:
            return row.match_indices
        return None

    def set_symbols(self, symbols: Iterable[OutlineSymbol]) -> None:
        self.beginResetModel()
        self._rows = tuple(
            QuickSymbolRow(
                symbol=symbol,
                depth=_symbol_depth(symbol),
                match_indices=frozenset(),
            )
            for symbol in symbols
        )
        self._display_indices = list(range(len(self._rows)))
        self._filter_text = ""
        self.endResetModel()

    def set_filter(self, text: str) -> None:
        needle = text.strip().lower()
        if needle == self._filter_text:
            return
        self._filter_text = needle
        self.beginResetModel()
        if not needle:
            self._display_indices = list(range(len(self._rows)))
            updated_rows: list[QuickSymbolRow] = []
            for row in self._rows:
                updated_rows.append(
                    QuickSymbolRow(symbol=row.symbol, depth=row.depth, match_indices=frozenset())
                )
            self._rows = tuple(updated_rows)
        else:
            display_indices: list[int] = []
            updated_rows = list(self._rows)
            for index, row in enumerate(self._rows):
                if not _symbol_matches_filter(row.symbol, needle):
                    continue
                match_indices = _match_indices_in_name(row.symbol.name, needle)
                if not match_indices and needle in row.symbol.qualified_name.lower():
                    match_indices = _match_indices_in_name(row.symbol.name, needle)
                updated_rows[index] = QuickSymbolRow(
                    symbol=row.symbol,
                    depth=row.depth,
                    match_indices=match_indices,
                )
                display_indices.append(index)
            self._rows = tuple(updated_rows)
            self._display_indices = display_indices
        self.endResetModel()

    def total_count(self) -> int:
        return len(self._rows)

    def visible_count(self) -> int:
        return len(self._display_indices)

    def symbol_at(self, display_row: int) -> OutlineSymbol | None:
        row = self._row_at(display_row)
        return row.symbol if row is not None else None

    def line_at(self, display_row: int) -> int | None:
        row = self._row_at(display_row)
        return row.symbol.line_number if row is not None else None

    def source_index_for_line(self, line: int) -> int | None:
        source_index = _index_at_line([row.symbol for row in self._rows], line)
        if source_index is None:
            return None
        try:
            return self._display_indices.index(source_index)
        except ValueError:
            return None

    def _row_at(self, display_row: int) -> QuickSymbolRow | None:
        if display_row < 0 or display_row >= len(self._display_indices):
            return None
        source_index = self._display_indices[display_row]
        return self._rows[source_index]


class QuickSymbolDelegate(QStyledItemDelegate):
    """Paints one symbol row with kind icon, hierarchy indent, and line badge."""

    def __init__(self, tokens: ShellThemeTokens, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.apply_theme(tokens)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        self._text_primary = QColor(tokens.text_primary)
        self._text_muted = QColor(tokens.text_muted)
        self._selected_bg = QColor(tokens.tree_selected_bg)
        self._hover_bg = QColor(tokens.tree_hover_bg)
        self._accent = QColor(tokens.accent)
        self._badge_bg = QColor(tokens.badge_bg)
        self._is_dark = tokens.is_dark

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), _ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # noqa: N802
        row = index.data(SymbolRole)
        if not isinstance(row, QuickSymbolRow):
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        is_selected = bool(option.state & QStyle.State_Selected)
        is_hover = bool(option.state & QStyle.State_MouseOver)
        if is_selected:
            painter.fillRect(option.rect, self._selected_bg)
        elif is_hover:
            painter.fillRect(option.rect, self._hover_bg)

        symbol = row.symbol
        rect = option.rect
        cursor_x = rect.left() + row.depth * _DEPTH_INDENT + _ICON_LEFT_MARGIN

        kind_color = kind_color_for(symbol.kind, is_dark=self._is_dark)
        icon = kind_icon(symbol.kind, kind_color)
        icon_y = rect.top() + (rect.height() - _ICON_SIZE) // 2
        icon.paint(painter, QRect(cursor_x, icon_y, _ICON_SIZE, _ICON_SIZE))
        cursor_x += _ICON_SIZE + _TEXT_GAP

        line_badge = f"Ln {symbol.line_number}"
        badge_font = QFont(painter.font())
        badge_font.setPointSize(9)
        badge_fm = QFontMetrics(badge_font)
        badge_width = badge_fm.horizontalAdvance(line_badge) + _LINE_BADGE_PAD_X * 2
        badge_height = badge_fm.height() + _LINE_BADGE_PAD_Y
        badge_x = rect.right() - _RIGHT_MARGIN - badge_width
        badge_y = rect.top() + (rect.height() - badge_height) // 2
        badge_rect = QRect(badge_x, badge_y, badge_width, badge_height)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._badge_bg)
        painter.drawRoundedRect(badge_rect, 4, 4)
        painter.setPen(self._text_muted)
        painter.setFont(badge_font)
        painter.drawText(
            badge_rect,
            int(Qt.AlignCenter),
            line_badge,
        )

        available_width = badge_x - cursor_x - _TEXT_GAP
        if available_width < 20:
            painter.restore()
            return

        name_font = QFont(painter.font())
        name_font.setPointSize(10)
        name_font.setBold(True)
        name_fm = QFontMetrics(name_font)

        detail_font = QFont(painter.font())
        detail_font.setPointSize(9)
        detail_fm = QFontMetrics(detail_font)

        detail_text = symbol.detail or ""
        detail_display = ""
        if detail_text:
            name_width = name_fm.horizontalAdvance(symbol.name)
            gap = 8
            max_detail_width = available_width - name_width - gap
            if max_detail_width >= 30:
                detail_display = detail_fm.elidedText(detail_text, Qt.ElideRight, max_detail_width)

        text_y_center = rect.top() + rect.height() // 2
        name_y = text_y_center + name_fm.ascent() // 2

        match_indices = index.data(MatchIndicesRole)
        if not isinstance(match_indices, frozenset):
            match_indices = frozenset()

        self._draw_highlighted_text(
            painter,
            cursor_x,
            name_y,
            symbol.name,
            match_indices,
            name_font,
            self._text_primary,
            self._accent,
        )

        if detail_display:
            detail_x = cursor_x + name_fm.horizontalAdvance(symbol.name) + 8
            painter.setFont(detail_font)
            painter.setPen(self._text_muted)
            painter.drawText(detail_x, name_y, detail_display)

        painter.restore()

    def _draw_highlighted_text(
        self,
        painter: QPainter,
        x: int,
        y: int,
        text: str,
        highlight_indices: frozenset[int],
        font: QFont,
        normal_color: QColor,
        highlight_color: QColor,
    ) -> None:
        painter.setFont(font)
        fm = QFontMetrics(font)
        cursor_x = x
        index = 0
        while index < len(text):
            run_start = index
            is_highlighted = index in highlight_indices
            while index < len(text) and (index in highlight_indices) == is_highlighted:
                index += 1
            segment = text[run_start:index]
            if is_highlighted:
                seg_width = fm.horizontalAdvance(segment)
                bg_color = QColor(highlight_color)
                bg_color.setAlpha(30)
                painter.fillRect(cursor_x, y - fm.ascent(), seg_width, fm.height(), bg_color)
                painter.setPen(QPen(highlight_color))
            else:
                painter.setPen(QPen(normal_color))
            painter.drawText(cursor_x, y, segment)
            cursor_x += fm.horizontalAdvance(segment)


class QuickSymbolDialog(QDialog):
    """Filterable list of symbols for the active editor."""

    symbol_chosen: Any = Signal(int)
    symbol_preview: Any = Signal(int)

    def __init__(
        self,
        symbols: Iterable[OutlineSymbol],
        *,
        tokens: ShellThemeTokens,
        initial_line: int | None = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("shell.quickSymbolDialog")
        self.setWindowTitle("Go to Symbol in File")
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setMaximumHeight(420)

        self._tokens = tokens
        self._initial_line = initial_line
        self._symbols = tuple(symbols)

        self._list_model = QuickSymbolListModel(self)
        self._list_model.set_symbols(self._symbols)

        self._build_ui()
        self._apply_shadow()

        self._select_initial_row()
        self._update_count_label()
        self._line_edit.setFocus()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._line_edit = QLineEdit(self)
        self._line_edit.setObjectName("shell.quickSymbolDialog.input")
        self._line_edit.setPlaceholderText("Filter symbols in this file…")
        icon_color = self._tokens.text_muted or self._tokens.text_primary
        self._line_edit.addAction(symbol_icon(icon_color), QLineEdit.LeadingPosition)
        self._line_edit.textChanged.connect(self._on_filter_changed)
        self._line_edit.installEventFilter(self)
        layout.addWidget(self._line_edit)

        self._results_stack = QWidget(self)
        stack_layout = QStackedLayout(self._results_stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)

        self._list = QListView(self._results_stack)
        self._list.setObjectName("shell.quickSymbolDialog.list")
        self._list.setUniformItemSizes(True)
        self._list.setSelectionMode(QListView.SingleSelection)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setModel(self._list_model)
        self._delegate = QuickSymbolDelegate(self._tokens, self._list)
        self._list.setItemDelegate(self._delegate)
        self._list.clicked.connect(self._on_item_clicked)
        self._list.doubleClicked.connect(self._commit_index)
        selection_model = self._list.selectionModel()
        if selection_model is not None:
            selection_model.currentChanged.connect(self._on_current_changed)

        self._empty_label = QLabel("No matching symbols", self._results_stack)
        self._empty_label.setObjectName("shell.quickSymbolDialog.empty")
        self._empty_label.setAlignment(Qt.AlignCenter)

        stack_layout.addWidget(self._list)
        stack_layout.addWidget(self._empty_label)
        layout.addWidget(self._results_stack, 1)

        self._count_label = QLabel(self)
        self._count_label.setObjectName("shell.quickSymbolDialog.count")
        self._count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        count_layout = QHBoxLayout()
        count_layout.setContentsMargins(12, 2, 12, 4)
        count_layout.addWidget(self._count_label)
        layout.addLayout(count_layout)

        self._results_stack_layout = stack_layout

    def _apply_shadow(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(self._tokens.popup_shadow or "#000000"))
        self.setGraphicsEffect(shadow)

    def open_dialog(self) -> None:
        parent_widget = self.parent()
        if isinstance(parent_widget, QWidget):
            parent_rect = parent_widget.rect()
            dialog_width = min(max(480, int(parent_rect.width() * 0.45)), 560)
            self.setFixedWidth(dialog_width)
            x = (parent_rect.width() - dialog_width) // 2
            y = parent_rect.height() // 6
            global_pos = parent_widget.mapToGlobal(parent_rect.topLeft())
            self.move(global_pos.x() + x, global_pos.y() + y)

    # -- public API --

    def symbol_count(self) -> int:
        return self._list_model.total_count()

    def visible_count(self) -> int:
        return self._list_model.visible_count()

    def list_widget(self) -> QListView:
        return self._list

    def line_edit(self) -> QLineEdit:
        return self._line_edit

    def current_symbol(self) -> OutlineSymbol | None:
        index = self._list.currentIndex()
        if not index.isValid():
            return None
        return self._list_model.symbol_at(index.row())

    def commit_current(self) -> None:
        index = self._list.currentIndex()
        if not index.isValid():
            return
        self._commit_index(index)

    # -- filter / selection --

    def _on_filter_changed(self, text: str) -> None:
        self._list_model.set_filter(text)
        self._update_stack_visibility()
        self._update_count_label()
        if self._list_model.rowCount() > 0:
            self._list.setCurrentIndex(self._list_model.index(0, 0))
        else:
            self._list.clearSelection()

    def _update_stack_visibility(self) -> None:
        if self._list_model.visible_count() > 0:
            self._results_stack_layout.setCurrentIndex(0)
        elif self._line_edit.text().strip():
            self._results_stack_layout.setCurrentIndex(1)
        else:
            self._results_stack_layout.setCurrentIndex(0)

    def _update_count_label(self) -> None:
        total = self._list_model.total_count()
        visible = self._list_model.visible_count()
        query = self._line_edit.text().strip()
        if query:
            self._count_label.setText(f"{visible} of {total} symbols")
        else:
            label = "symbol" if total == 1 else "symbols"
            self._count_label.setText(f"{total} {label}")

    def _select_initial_row(self) -> None:
        row = 0
        if self._initial_line is not None:
            matched = self._list_model.source_index_for_line(self._initial_line)
            if matched is not None:
                row = matched
        if self._list_model.rowCount() > 0:
            index = self._list_model.index(row, 0)
            self._list.setCurrentIndex(index)
            self._list.scrollTo(index)
            line = self._list_model.line_at(row)
            if line is not None:
                self.symbol_preview.emit(line)
        self._update_stack_visibility()

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            return
        line = self._list_model.line_at(current.row())
        if line is not None:
            self.symbol_preview.emit(line)

    def _on_item_clicked(self, index: QModelIndex) -> None:
        if index.isValid():
            line = self._list_model.line_at(index.row())
            if line is not None:
                self.symbol_preview.emit(line)

    def _commit_index(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        line = self._list_model.line_at(index.row())
        if line is None:
            return
        self.symbol_chosen.emit(line)
        self.accept()

    # -- keyboard handling --

    def _move_current_row(self, delta: int) -> None:
        index = self._list.currentIndex()
        row = index.row() if index.isValid() else -1
        total = self._list_model.rowCount()
        if total <= 0:
            return
        new_row = min(total - 1, max(0, row + delta))
        if new_row != row:
            self._list.setCurrentIndex(self._list_model.index(new_row, 0))

    def eventFilter(self, arg__1: Any, arg__2: Any) -> bool:  # noqa: N802, N803
        if arg__1 is self._line_edit and isinstance(arg__2, QKeyEvent) and arg__2.type() == QKeyEvent.KeyPress:
            key = arg__2.key()
            if key == Qt.Key_Down:
                self._move_current_row(1)
                return True
            if key == Qt.Key_Up:
                self._move_current_row(-1)
                return True
            if key == Qt.Key_PageDown:
                self._move_current_row(5)
                return True
            if key == Qt.Key_PageUp:
                self._move_current_row(-5)
                return True
            if key == Qt.Key_Home:
                if self._list_model.rowCount() > 0:
                    self._list.setCurrentIndex(self._list_model.index(0, 0))
                return True
            if key == Qt.Key_End:
                count = self._list_model.rowCount()
                if count > 0:
                    self._list.setCurrentIndex(self._list_model.index(count - 1, 0))
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self.commit_current()
                return True
        return super().eventFilter(arg__1, arg__2)

    def keyPressEvent(self, arg__1: Any) -> None:  # noqa: N802, N803
        if arg__1.key() == Qt.Key_Escape:
            self.reject()
            return
        if arg__1.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.commit_current()
            return
        super().keyPressEvent(arg__1)
