"""Quick-open dialog overlay with fuzzy file-by-name search."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from PySide2.QtCore import QModelIndex, QRect, QSize, Qt, Signal
from PySide2.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QKeyEvent,
    QPainter,
    QPen,
)
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

from app.editors.quick_open import (
    QuickOpenCandidate,
    RankedCandidate,
    rank_candidates,
)
from app.shell.icon_provider import file_icon, search_icon
from app.shell.theme_tokens import ShellThemeTokens


_ROW_HEIGHT = 32
_ICON_SIZE = 16
_ICON_LEFT_MARGIN = 12
_TEXT_LEFT_MARGIN = _ICON_LEFT_MARGIN + _ICON_SIZE + 8
_RIGHT_MARGIN = 14
_OPEN_DOT_RADIUS = 3


class _QuickOpenItemModel:
    """Thin wrapper around a plain list to serve as a virtual model for the delegate."""

    def __init__(self) -> None:
        self.items: List[RankedCandidate] = []

    def set_items(self, items: List[RankedCandidate]) -> None:
        self.items = list(items)


class QuickOpenDelegate(QStyledItemDelegate):

    def __init__(
        self,
        tokens: ShellThemeTokens,
        icon_map: Dict[str, QIcon],
        fallback_icon: QIcon,
        parent: Optional[QWidget] = None,
        filename_icon_map: Optional[Dict[str, QIcon]] = None,
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._icon_map = icon_map
        self._filename_icon_map = filename_icon_map or {}
        self._fallback_icon = fallback_icon
        self._item_model: Optional[_QuickOpenItemModel] = None

    def set_item_model(self, model: _QuickOpenItemModel) -> None:
        self._item_model = model

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), _ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # noqa: N802
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        is_selected = bool(option.state & QStyle.State_Selected)
        is_hover = bool(option.state & QStyle.State_MouseOver)

        if is_selected:
            painter.fillRect(option.rect, QColor(self._tokens.tree_selected_bg))
        elif is_hover:
            painter.fillRect(option.rect, QColor(self._tokens.tree_hover_bg))

        row = index.row()
        ranked: Optional[RankedCandidate] = None
        if self._item_model and 0 <= row < len(self._item_model.items):
            ranked = self._item_model.items[row]

        if ranked is None:
            painter.restore()
            return

        candidate = ranked.candidate
        match_positions = ranked.match_positions
        relative_path = candidate.relative_path
        is_open = candidate.is_open

        filename = os.path.basename(relative_path)
        dir_path = os.path.dirname(relative_path)

        icon = self._filename_icon_map.get(filename.lower())
        if icon is None:
            ext = os.path.splitext(filename)[1].lower()
            icon = self._icon_map.get(ext, self._fallback_icon)

        rect = option.rect
        icon_y = rect.top() + (rect.height() - _ICON_SIZE) // 2
        icon.paint(painter, QRect(_ICON_LEFT_MARGIN + rect.left(), icon_y, _ICON_SIZE, _ICON_SIZE))

        text_left = rect.left() + _TEXT_LEFT_MARGIN
        available_width = rect.width() - _TEXT_LEFT_MARGIN - _RIGHT_MARGIN

        filename_font = QFont(painter.font())
        filename_font.setPointSize(10)
        filename_font.setBold(True)
        filename_fm = QFontMetrics(filename_font)

        dir_font = QFont(painter.font())
        dir_font.setPointSize(9)
        dir_fm = QFontMetrics(dir_font)

        filename_width = filename_fm.horizontalAdvance(filename)
        dir_display = ""
        if dir_path:
            dir_display = dir_path
            max_dir_width = available_width - filename_width - 12
            if max_dir_width < 30:
                dir_display = ""
            elif dir_fm.horizontalAdvance(dir_display) > max_dir_width:
                while dir_display and dir_fm.horizontalAdvance(dir_display + "...") > max_dir_width:
                    dir_display = dir_display[:-1]
                dir_display = dir_display + "..."

        text_y_center = rect.top() + rect.height() // 2
        filename_y = text_y_center + filename_fm.ascent() // 2

        filename_start_in_path = len(relative_path) - len(filename)
        filename_positions = set()
        dir_positions = set()
        for p in match_positions:
            if p >= filename_start_in_path:
                filename_positions.add(p - filename_start_in_path)
            else:
                dir_positions.add(p)

        self._draw_highlighted_text(
            painter, text_left, filename_y, filename, filename_positions,
            filename_font, QColor(self._tokens.text_primary), QColor(self._tokens.accent),
        )

        if dir_display:
            dir_x = text_left + filename_width + 8
            dir_y = filename_y
            display_dir_positions: set[int] = set()
            if dir_display == dir_path:
                display_dir_positions = dir_positions
            self._draw_highlighted_text(
                painter, dir_x, dir_y, dir_display, display_dir_positions,
                dir_font, QColor(self._tokens.text_muted), QColor(self._tokens.accent),
            )

        if is_open:
            dot_x = rect.right() - _RIGHT_MARGIN
            dot_y = text_y_center
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(self._tokens.accent))
            painter.drawEllipse(dot_x - _OPEN_DOT_RADIUS, dot_y - _OPEN_DOT_RADIUS,
                                _OPEN_DOT_RADIUS * 2, _OPEN_DOT_RADIUS * 2)

        painter.restore()

    def _draw_highlighted_text(
        self,
        painter: QPainter,
        x: int,
        y: int,
        text: str,
        highlight_indices: set[int],
        font: QFont,
        normal_color: QColor,
        highlight_color: QColor,
    ) -> None:
        painter.setFont(font)
        fm = QFontMetrics(font)
        cursor_x = x

        i = 0
        while i < len(text):
            run_start = i
            is_highlighted = i in highlight_indices
            while i < len(text) and (i in highlight_indices) == is_highlighted:
                i += 1
            segment = text[run_start:i]

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


class QuickOpenDialog(QDialog):
    """Floating overlay for fuzzy file-by-name search (Ctrl+P)."""

    file_preview_requested: Any = Signal(str)
    file_selected: Any = Signal(str)
    file_preview_at_line_requested: Any = Signal(str, int)
    file_selected_at_line: Any = Signal(str, int)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        tokens: Optional[ShellThemeTokens] = None,
        icon_map: Optional[Dict[str, QIcon]] = None,
        filename_icon_map: Optional[Dict[str, QIcon]] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("shell.quickOpen")
        from PySide2.QtCore import Qt as _Qt
        self.setWindowFlags(_Qt.WindowType(int(_Qt.Popup) | int(_Qt.FramelessWindowHint)))
        self.setMinimumWidth(600)
        self.setMaximumHeight(460)
        self._candidates: List[QuickOpenCandidate] = []
        self._total_count = 0

        self._tokens = tokens or ShellThemeTokens(
            window_bg="#1F2428", panel_bg="#262C33", editor_bg="#1B1F23",
            text_primary="#E9ECEF", text_muted="#ADB5BD", border="#3C434A",
            accent="#5B8CFF", gutter_bg="#1F2428", gutter_text="#6C757D",
            line_highlight="#252B33", is_dark=True,
        )
        icon_color = self._tokens.icon_primary or self._tokens.text_muted
        self._icon_map = icon_map or {}
        self._filename_icon_map = filename_icon_map or {}
        self._fallback_icon = file_icon(icon_color)
        self._item_data = _QuickOpenItemModel()
        self._build_ui()
        self._apply_shadow()

    def _apply_shadow(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 80 if self._tokens.is_dark else 40))
        self.setGraphicsEffect(shadow)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._search_input = QLineEdit(self)
        self._search_input.setObjectName("shell.quickOpen.input")
        self._search_input.setPlaceholderText("Search files by name   (use :line to jump)")

        s_icon = search_icon(self._tokens.text_muted)
        self._search_input.addAction(s_icon, QLineEdit.LeadingPosition)
        self._search_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._search_input)

        self._results_stack = QWidget(self)
        self._results_stack.setObjectName("shell.quickOpen.resultsContainer")
        stack_layout = QStackedLayout(self._results_stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)

        self._results_list = QListView(self)
        self._results_list.setObjectName("shell.quickOpen.results")
        self._results_list.setUniformItemSizes(True)
        self._results_list.setSelectionMode(QListView.SingleSelection)
        self._results_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._results_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        from PySide2.QtCore import QStringListModel
        self._list_model = QStringListModel(self)
        self._results_list.setModel(self._list_model)

        self._delegate = QuickOpenDelegate(
            self._tokens, self._icon_map, self._fallback_icon, self._results_list,
            filename_icon_map=self._filename_icon_map,
        )
        self._delegate.set_item_model(self._item_data)
        self._results_list.setItemDelegate(self._delegate)
        self._results_list.clicked.connect(self._on_item_preview)
        self._results_list.doubleClicked.connect(self._on_item_activated)

        self._empty_label = QLabel("No matching files")
        self._empty_label.setObjectName("shell.quickOpen.empty")
        self._empty_label.setAlignment(Qt.AlignCenter)

        stack_layout.addWidget(self._results_list)
        stack_layout.addWidget(self._empty_label)

        layout.addWidget(self._results_stack, 1)

        self._count_label = QLabel(self)
        self._count_label.setObjectName("shell.quickOpen.count")
        self._count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        count_layout = QHBoxLayout()
        count_layout.setContentsMargins(12, 2, 12, 4)
        count_layout.addWidget(self._count_label)
        layout.addLayout(count_layout)

    def set_candidates(self, candidates: List[QuickOpenCandidate]) -> None:
        self._candidates = list(candidates)
        self._total_count = len(candidates)
        self._refresh_results()

    def open_dialog(self) -> None:
        self._search_input.clear()
        self._refresh_results()
        self._search_input.setFocus()
        if self.parent() is not None:
            parent_widget = self.parent()
            if hasattr(parent_widget, "rect"):
                parent_rect = parent_widget.rect()
                dialog_width = min(max(600, int(parent_rect.width() * 0.45)), 700)
                self.setFixedWidth(dialog_width)
                x = (parent_rect.width() - dialog_width) // 2
                y = parent_rect.height() // 6
                global_pos = parent_widget.mapToGlobal(parent_rect.topLeft())  # type: ignore[union-attr]
                self.move(global_pos.x() + x, global_pos.y() + y)
        self.show()

    def keyPressEvent(self, arg__1: QKeyEvent) -> None:  # noqa: N802
        event = arg__1
        if event.key() == Qt.Key_Escape:
            self.hide()
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._accept_current()
            event.accept()
            return
        if event.key() == Qt.Key_Down:
            idx = self._results_list.currentIndex()
            row = idx.row() if idx.isValid() else -1
            total = self._list_model.rowCount()
            if row < total - 1:
                new_idx = self._list_model.index(row + 1, 0)
                self._results_list.setCurrentIndex(new_idx)
            event.accept()
            return
        if event.key() == Qt.Key_Up:
            idx = self._results_list.currentIndex()
            row = idx.row() if idx.isValid() else 0
            if row > 0:
                new_idx = self._list_model.index(row - 1, 0)
                self._results_list.setCurrentIndex(new_idx)
            event.accept()
            return
        super().keyPressEvent(event)

    def _parse_query_and_line(self) -> tuple:
        raw = self._search_input.text()
        if ":" in raw:
            parts = raw.rsplit(":", 1)
            line_part = parts[1].strip()
            if line_part.isdigit() and int(line_part) > 0:
                return (parts[0], int(line_part))
        return (raw, None)

    def _on_text_changed(self, _text: str) -> None:
        self._refresh_results()

    def _refresh_results(self) -> None:
        query, _line = self._parse_query_and_line()
        ranked = rank_candidates(self._candidates, query, limit=50)
        self._item_data.set_items(ranked)

        labels = [r.candidate.relative_path for r in ranked]
        self._list_model.setStringList(labels)

        stack: QStackedLayout = self._results_stack.layout()  # type: ignore[assignment]

        if ranked:
            stack.setCurrentIndex(0)
            self._results_list.setCurrentIndex(self._list_model.index(0, 0))
        else:
            if query.strip():
                stack.setCurrentIndex(1)
            else:
                stack.setCurrentIndex(0)

        shown = len(ranked)
        if query.strip():
            self._count_label.setText(f"{shown} of {self._total_count} files")
        else:
            self._count_label.setText(f"{self._total_count} files")

    def _on_item_activated(self, index: QModelIndex) -> None:
        row = index.row()
        if 0 <= row < len(self._item_data.items):
            path = self._item_data.items[row].candidate.absolute_path
            _, line = self._parse_query_and_line()
            if line is not None:
                self.file_selected_at_line.emit(path, line)
            else:
                self.file_selected.emit(path)
            self.hide()

    def _on_item_preview(self, index: QModelIndex) -> None:
        row = index.row()
        if 0 <= row < len(self._item_data.items):
            path = self._item_data.items[row].candidate.absolute_path
            _, line = self._parse_query_and_line()
            if line is not None:
                self.file_preview_at_line_requested.emit(path, line)
            else:
                self.file_preview_requested.emit(path)

    def _accept_current(self) -> None:
        idx = self._results_list.currentIndex()
        if idx.isValid():
            self._on_item_activated(idx)
