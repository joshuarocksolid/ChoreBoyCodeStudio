"""Project-wide search/replace sidebar panel."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PySide2.QtCore import Qt, QRect, QSize, QTimer, Signal
from PySide2.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QPainter,
    QPen,
)
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.editors.search_panel import SearchMatch, SearchOptions, SearchWorker, replace_in_files

ROLE_ABS_PATH = Qt.UserRole
ROLE_LINE_NUMBER = Qt.UserRole + 1
ROLE_IS_FILE = Qt.UserRole + 2
ROLE_MATCH_COUNT = Qt.UserRole + 3
ROLE_LINE_TEXT = Qt.UserRole + 4
ROLE_MATCH_COLUMN = Qt.UserRole + 5
ROLE_MATCH_LENGTH = Qt.UserRole + 6


class SearchResultDelegate(QStyledItemDelegate):
    """Custom delegate for rich rendering of search results."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        match_bg: str = "#FFE066",
        text_primary: str = "#212529",
        text_muted: str = "#6C757D",
        badge_bg: str = "#E9ECEF",
    ) -> None:
        super().__init__(parent)
        self._match_bg = match_bg
        self._text_primary = text_primary
        self._text_muted = text_muted
        self._badge_bg = badge_bg

    def update_colors(
        self,
        *,
        match_bg: str,
        text_primary: str,
        text_muted: str,
        badge_bg: str,
    ) -> None:
        self._match_bg = match_bg
        self._text_primary = text_primary
        self._text_muted = text_muted
        self._badge_bg = badge_bg

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: Any,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        style = option.widget.style() if option.widget else None
        if style:
            style.drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, option.widget)

        rect = option.rect
        is_file = index.data(ROLE_IS_FILE)

        if is_file:
            self._paint_file_item(painter, rect, index, option)
        else:
            self._paint_match_item(painter, rect, index, option)

        painter.restore()

    def _paint_file_item(
        self,
        painter: QPainter,
        rect: QRect,
        index: Any,
        option: QStyleOptionViewItem,
    ) -> None:
        text = index.data(Qt.DisplayRole) or ""
        match_count = index.data(ROLE_MATCH_COUNT) or 0

        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        fm = QFontMetrics(font)

        filename = text
        text_color = QColor(self._text_primary)
        if option.state & QStyle.State_Selected:
            text_color = option.palette.color(option.palette.HighlightedText)

        text_rect = rect.adjusted(4, 0, -40, 0)
        elided = fm.elidedText(filename, Qt.ElideMiddle, text_rect.width())
        painter.setPen(QPen(text_color))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)

        if match_count > 0:
            badge_text = str(match_count)
            badge_font = QFont(option.font)
            ps = badge_font.pointSizeF()
            if ps > 0:
                badge_font.setPointSizeF(ps * 0.85)
            else:
                px = badge_font.pixelSize()
                if px > 0:
                    badge_font.setPixelSize(max(1, int(px * 0.85)))
            badge_font.setBold(True)
            painter.setFont(badge_font)
            bfm = QFontMetrics(badge_font)
            badge_w = max(bfm.horizontalAdvance(badge_text) + 10, 20)
            badge_h = 16
            badge_x = rect.right() - badge_w - 6
            badge_y = rect.center().y() - badge_h // 2
            badge_rect = QRect(badge_x, badge_y, badge_w, badge_h)

            painter.setBrush(QColor(self._badge_bg))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(badge_rect, 8, 8)

            painter.setPen(QPen(QColor(self._text_muted)))
            painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

    def _paint_match_item(
        self,
        painter: QPainter,
        rect: QRect,
        index: Any,
        option: QStyleOptionViewItem,
    ) -> None:
        line_number = index.data(ROLE_LINE_NUMBER)
        line_text = index.data(ROLE_LINE_TEXT) or ""
        match_col = index.data(ROLE_MATCH_COLUMN)
        match_len = index.data(ROLE_MATCH_LENGTH)

        font = QFont(option.font)
        fm = QFontMetrics(font)

        text_color = QColor(self._text_primary)
        muted_color = QColor(self._text_muted)
        if option.state & QStyle.State_Selected:
            text_color = option.palette.color(option.palette.HighlightedText)
            muted_color = text_color

        x = rect.left() + 8
        y_center = rect.center().y()

        line_prefix = f"L{line_number}: " if line_number else ""
        painter.setFont(font)

        painter.setPen(QPen(muted_color))
        painter.drawText(
            QRect(x, rect.top(), fm.horizontalAdvance(line_prefix), rect.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            line_prefix,
        )
        x += fm.horizontalAdvance(line_prefix)

        stripped = line_text.strip()
        if len(stripped) > 120:
            stripped = stripped[:120] + "\u2026"

        leading_stripped = len(line_text) - len(line_text.lstrip())

        if match_col is not None and match_len is not None and match_len > 0:
            adj_col = max(0, match_col - leading_stripped)
            before = stripped[:adj_col]
            match = stripped[adj_col : adj_col + match_len]
            after = stripped[adj_col + match_len :]

            available_w = rect.right() - x - 4
            painter.setPen(QPen(text_color))

            before_w = fm.horizontalAdvance(before)
            if before_w <= available_w:
                painter.drawText(
                    QRect(x, rect.top(), before_w, rect.height()),
                    Qt.AlignVCenter | Qt.AlignLeft,
                    before,
                )
                x += before_w

                match_w = fm.horizontalAdvance(match)
                highlight_rect = QRect(x, y_center - fm.height() // 2, match_w, fm.height())
                painter.fillRect(highlight_rect, QColor(self._match_bg))

                bold_font = QFont(font)
                bold_font.setBold(True)
                painter.setFont(bold_font)
                painter.setPen(QPen(text_color))
                painter.drawText(
                    QRect(x, rect.top(), match_w, rect.height()),
                    Qt.AlignVCenter | Qt.AlignLeft,
                    match,
                )
                x += match_w

                painter.setFont(font)
                painter.setPen(QPen(text_color))
                after_w = min(fm.horizontalAdvance(after), rect.right() - x - 4)
                if after_w > 0:
                    elided_after = fm.elidedText(after, Qt.ElideRight, after_w)
                    painter.drawText(
                        QRect(x, rect.top(), after_w, rect.height()),
                        Qt.AlignVCenter | Qt.AlignLeft,
                        elided_after,
                    )
            else:
                elided = fm.elidedText(stripped, Qt.ElideRight, available_w)
                painter.drawText(
                    QRect(x, rect.top(), available_w, rect.height()),
                    Qt.AlignVCenter | Qt.AlignLeft,
                    elided,
                )
        else:
            available_w = rect.right() - x - 4
            elided = fm.elidedText(stripped, Qt.ElideRight, available_w)
            painter.setPen(QPen(text_color))
            painter.drawText(
                QRect(x, rect.top(), available_w, rect.height()),
                Qt.AlignVCenter | Qt.AlignLeft,
                elided,
            )

    def sizeHint(self, option: QStyleOptionViewItem, index: Any) -> QSize:  # noqa: N802
        is_file = index.data(ROLE_IS_FILE)
        h = 26 if is_file else 22
        return QSize(option.rect.width(), h)


class SearchSidebarWidget(QWidget):
    """Sidebar panel for project-wide search and replace."""

    open_file_at_line = Signal(str, int)
    _apply_results_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.searchSidebar")
        self._project_root: str | None = None
        self._active_worker: SearchWorker | None = None
        self._last_matches: list[SearchMatch] = []
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._run_search)
        self._apply_results_requested.connect(self._apply_search_results)
        self._replace_visible = False
        self._filters_visible = False
        self._searching = False
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 4)
        outer.setSpacing(6)

        header_row = QWidget(self)
        header_row.setObjectName("shell.searchSidebar.headerRow")
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        header = QLabel("\U0001F50D SEARCH", self)
        header.setObjectName("shell.searchSidebar.header")
        header_layout.addWidget(header, 1)

        self._filter_toggle_btn = QToolButton(header_row)
        self._filter_toggle_btn.setObjectName("shell.searchSidebar.filterToggle")
        self._filter_toggle_btn.setText("\u2026")
        self._filter_toggle_btn.setToolTip("Toggle file filters")
        self._filter_toggle_btn.setCheckable(True)
        self._filter_toggle_btn.setFixedSize(22, 22)
        self._filter_toggle_btn.toggled.connect(self._toggle_filters)
        header_layout.addWidget(self._filter_toggle_btn)

        outer.addWidget(header_row)

        input_area = QWidget(self)
        input_layout = QHBoxLayout(input_area)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(0)

        self._replace_toggle_btn = QToolButton(input_area)
        self._replace_toggle_btn.setObjectName("shell.searchSidebar.replaceToggle")
        self._replace_toggle_btn.setText("\u25B6")
        self._replace_toggle_btn.setToolTip("Toggle replace")
        self._replace_toggle_btn.setCheckable(True)
        self._replace_toggle_btn.setFixedSize(20, 20)
        self._replace_toggle_btn.toggled.connect(self._toggle_replace)
        input_layout.addWidget(self._replace_toggle_btn)
        input_layout.addSpacing(4)

        input_fields_container = QWidget(input_area)
        input_fields_layout = QVBoxLayout(input_fields_container)
        input_fields_layout.setContentsMargins(0, 0, 0, 0)
        input_fields_layout.setSpacing(4)

        search_row = QWidget(input_fields_container)
        search_layout = QHBoxLayout(search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(2)

        self._search_input = QLineEdit(search_row)
        self._search_input.setObjectName("shell.searchSidebar.searchInput")
        self._search_input.setPlaceholderText("Search")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_input_changed)
        self._search_input.returnPressed.connect(self._on_search_enter)
        search_layout.addWidget(self._search_input, 1)

        self._case_btn = QToolButton(search_row)
        self._case_btn.setObjectName("shell.searchSidebar.caseBtn")
        self._case_btn.setText("Aa")
        self._case_btn.setToolTip("Match Case (Alt+C)")
        self._case_btn.setCheckable(True)
        self._case_btn.setFixedSize(24, 24)
        self._case_btn.toggled.connect(self._on_option_changed)
        search_layout.addWidget(self._case_btn)

        self._word_btn = QToolButton(search_row)
        self._word_btn.setObjectName("shell.searchSidebar.wordBtn")
        self._word_btn.setText("W")
        self._word_btn.setToolTip("Whole Word (Alt+W)")
        self._word_btn.setCheckable(True)
        self._word_btn.setFixedSize(24, 24)
        self._word_btn.toggled.connect(self._on_option_changed)
        search_layout.addWidget(self._word_btn)

        self._regex_btn = QToolButton(search_row)
        self._regex_btn.setObjectName("shell.searchSidebar.regexBtn")
        self._regex_btn.setText(".*")
        self._regex_btn.setToolTip("Use Regular Expression (Alt+R)")
        self._regex_btn.setCheckable(True)
        self._regex_btn.setFixedSize(24, 24)
        self._regex_btn.toggled.connect(self._on_option_changed)
        search_layout.addWidget(self._regex_btn)

        input_fields_layout.addWidget(search_row)

        self._replace_container = QWidget(input_fields_container)
        replace_layout = QHBoxLayout(self._replace_container)
        replace_layout.setContentsMargins(0, 0, 0, 0)
        replace_layout.setSpacing(4)

        self._replace_input = QLineEdit(self._replace_container)
        self._replace_input.setObjectName("shell.searchSidebar.replaceInput")
        self._replace_input.setPlaceholderText("Replace")
        self._replace_input.setClearButtonEnabled(True)
        replace_layout.addWidget(self._replace_input, 1)

        self._replace_all_btn = QPushButton("Replace All", self._replace_container)
        self._replace_all_btn.setObjectName("shell.searchSidebar.replaceAllBtn")
        self._replace_all_btn.setToolTip("Replace all matches in all files")
        self._replace_all_btn.clicked.connect(self._on_replace_all)
        replace_layout.addWidget(self._replace_all_btn)

        input_fields_layout.addWidget(self._replace_container)
        self._replace_container.setVisible(False)

        input_layout.addWidget(input_fields_container, 1)
        outer.addWidget(input_area)

        self._filters_container = QWidget(self)
        self._filters_container.setObjectName("shell.searchSidebar.filtersContainer")
        filters_layout = QVBoxLayout(self._filters_container)
        filters_layout.setContentsMargins(0, 4, 0, 0)
        filters_layout.setSpacing(4)

        self._include_input = QLineEdit(self._filters_container)
        self._include_input.setObjectName("shell.searchSidebar.includeInput")
        self._include_input.setPlaceholderText("Files to include (e.g. *.py)")
        self._include_input.setClearButtonEnabled(True)
        self._include_input.textChanged.connect(self._on_input_changed)
        filters_layout.addWidget(self._include_input)

        self._exclude_input = QLineEdit(self._filters_container)
        self._exclude_input.setObjectName("shell.searchSidebar.excludeInput")
        self._exclude_input.setPlaceholderText("Files to exclude (e.g. tests/*)")
        self._exclude_input.setClearButtonEnabled(True)
        self._exclude_input.textChanged.connect(self._on_input_changed)
        filters_layout.addWidget(self._exclude_input)

        outer.addWidget(self._filters_container)
        self._filters_container.setVisible(False)

        summary_row = QWidget(self)
        summary_layout = QHBoxLayout(summary_row)
        summary_layout.setContentsMargins(0, 2, 0, 2)
        summary_layout.setSpacing(4)

        self._summary_label = QLabel("", self)
        self._summary_label.setObjectName("shell.searchSidebar.summary")
        summary_layout.addWidget(self._summary_label, 1)

        self._clear_btn = QToolButton(summary_row)
        self._clear_btn.setObjectName("shell.searchSidebar.clearBtn")
        self._clear_btn.setText("\u2715")
        self._clear_btn.setToolTip("Clear search results")
        self._clear_btn.setFixedSize(18, 18)
        self._clear_btn.clicked.connect(self._clear_results)
        self._clear_btn.setVisible(False)
        summary_layout.addWidget(self._clear_btn)

        outer.addWidget(summary_row)

        self._no_results_label = QLabel("", self)
        self._no_results_label.setObjectName("shell.searchSidebar.noResults")
        self._no_results_label.setAlignment(Qt.AlignCenter)
        self._no_results_label.setWordWrap(True)
        self._no_results_label.setVisible(False)
        outer.addWidget(self._no_results_label)

        self._results_tree = QTreeWidget(self)
        self._results_tree.setObjectName("shell.searchSidebar.results")
        self._results_tree.setHeaderHidden(True)
        self._results_tree.setIndentation(16)
        self._results_tree.setAlternatingRowColors(True)
        self._results_tree.itemActivated.connect(self._on_result_activated)
        self._results_tree.itemClicked.connect(self._on_result_activated)
        self._results_tree.itemDoubleClicked.connect(self._on_result_activated)

        self._delegate = SearchResultDelegate(self._results_tree)
        self._results_tree.setItemDelegate(self._delegate)

        outer.addWidget(self._results_tree, 1)

    def apply_theme_tokens(
        self,
        *,
        match_bg: str,
        text_primary: str,
        text_muted: str,
        badge_bg: str,
    ) -> None:
        """Update delegate colors when the theme changes."""
        self._delegate.update_colors(
            match_bg=match_bg,
            text_primary=text_primary,
            text_muted=text_muted,
            badge_bg=badge_bg,
        )

    def set_project_root(self, project_root: str | None) -> None:
        self._project_root = project_root
        if project_root is None:
            self._results_tree.clear()
            self._summary_label.setText("")
            self._last_matches.clear()
            self._clear_btn.setVisible(False)
            self._no_results_label.setVisible(False)

    def focus_search(self, initial_text: str = "") -> None:
        if initial_text:
            self._search_input.setText(initial_text)
        self._search_input.setFocus()
        self._search_input.selectAll()

    def _search_options(self) -> SearchOptions:
        include_text = self._include_input.text().strip()
        exclude_text = self._exclude_input.text().strip()
        return SearchOptions(
            case_sensitive=self._case_btn.isChecked(),
            whole_word=self._word_btn.isChecked(),
            regex=self._regex_btn.isChecked(),
            include_globs=include_text.split(",") if include_text else None,
            exclude_globs=exclude_text.split(",") if exclude_text else None,
        )

    def _on_input_changed(self, _text: str = "") -> None:
        self._debounce_timer.start()
        has_filters = bool(
            self._include_input.text().strip() or self._exclude_input.text().strip()
        )
        self._filter_toggle_btn.setProperty("hasActiveFilters", has_filters)
        self._filter_toggle_btn.style().unpolish(self._filter_toggle_btn)
        self._filter_toggle_btn.style().polish(self._filter_toggle_btn)

    def _on_option_changed(self, _checked: bool) -> None:
        self._debounce_timer.start()

    def _toggle_replace(self, checked: bool) -> None:
        self._replace_visible = checked
        self._replace_container.setVisible(checked)
        self._replace_toggle_btn.setText("\u25BC" if checked else "\u25B6")

    def _toggle_filters(self, checked: bool) -> None:
        self._filters_visible = checked
        self._filters_container.setVisible(checked)

    def _on_search_enter(self) -> None:
        """Run search; if results already present, focus the first result."""
        if self._results_tree.topLevelItemCount() > 0:
            first_file = self._results_tree.topLevelItem(0)
            if first_file and first_file.childCount() > 0:
                first_match = first_file.child(0)
                self._results_tree.setCurrentItem(first_match)
                self._results_tree.setFocus()
                return
        self._run_search()

    def _run_search(self) -> None:
        if self._active_worker is not None and self._active_worker.is_running():
            self._active_worker.cancel()

        query = self._search_input.text().strip()
        if not query or not self._project_root:
            self._results_tree.clear()
            self._summary_label.setText("")
            self._last_matches.clear()
            self._clear_btn.setVisible(False)
            self._no_results_label.setVisible(False)
            return

        self._searching = True
        self._summary_label.setText("Searching\u2026")
        self._no_results_label.setVisible(False)
        options = self._search_options()

        self._active_worker = SearchWorker(
            project_root=self._project_root,
            query=query,
            max_results=500,
            options=options,
            on_results=self._on_search_results,
            on_done=self._on_search_done,
        )
        self._active_worker.start()

    def _on_search_results(self, matches: list[SearchMatch], query: str) -> None:
        self._pending_results = matches
        self._pending_query = query
        self._apply_results_requested.emit()

    def _on_search_done(self) -> None:
        self._searching = False

    def _apply_search_results(self) -> None:
        matches = getattr(self, "_pending_results", [])
        self._last_matches = matches
        self._results_tree.clear()

        files: dict[str, list[SearchMatch]] = {}
        for m in matches:
            files.setdefault(m.relative_path, []).append(m)

        total_matches = len(matches)
        total_files = len(files)

        if total_matches == 0:
            self._summary_label.setText("No results found")
            self._clear_btn.setVisible(bool(self._search_input.text().strip()))
            self._no_results_label.setText(
                "No results found.\nTry adjusting your search or filters."
            )
            self._no_results_label.setVisible(True)
            self._results_tree.setVisible(False)
            return

        self._no_results_label.setVisible(False)
        self._results_tree.setVisible(True)
        self._clear_btn.setVisible(True)

        self._summary_label.setText(
            f"{total_matches} result{'s' if total_matches != 1 else ''} "
            f"in {total_files} file{'s' if total_files != 1 else ''}"
        )

        for rel_path, file_matches in sorted(files.items()):
            file_item = QTreeWidgetItem(self._results_tree)
            basename = os.path.basename(rel_path)
            dirname = os.path.dirname(rel_path)
            display = f"{basename}  {dirname}" if dirname else basename
            file_item.setText(0, display)
            file_item.setToolTip(0, file_matches[0].absolute_path)
            file_item.setData(0, ROLE_ABS_PATH, None)
            file_item.setData(0, ROLE_IS_FILE, True)
            file_item.setData(0, ROLE_MATCH_COUNT, len(file_matches))
            file_item.setExpanded(True)

            for m in file_matches:
                line_item = QTreeWidgetItem(file_item)
                display_text = m.line_text.strip()
                if len(display_text) > 120:
                    display_text = display_text[:120] + "\u2026"
                line_item.setText(0, display_text)
                line_item.setToolTip(0, m.line_text.strip())
                line_item.setData(0, ROLE_ABS_PATH, m.absolute_path)
                line_item.setData(0, ROLE_LINE_NUMBER, m.line_number)
                line_item.setData(0, ROLE_IS_FILE, False)
                line_item.setData(0, ROLE_LINE_TEXT, m.line_text)
                line_item.setData(0, ROLE_MATCH_COLUMN, m.column)
                line_item.setData(0, ROLE_MATCH_LENGTH, m.match_length)

    def _clear_results(self) -> None:
        self._results_tree.clear()
        self._summary_label.setText("")
        self._search_input.clear()
        self._last_matches.clear()
        self._clear_btn.setVisible(False)
        self._no_results_label.setVisible(False)
        self._results_tree.setVisible(True)

    def _on_result_activated(self, item: QTreeWidgetItem, column: int = 0) -> None:
        abs_path = item.data(0, ROLE_ABS_PATH)
        line_number = item.data(0, ROLE_LINE_NUMBER)
        if abs_path and line_number:
            self.open_file_at_line.emit(str(abs_path), int(line_number))

    def _on_replace_all(self) -> None:
        query = self._search_input.text().strip()
        replacement = self._replace_input.text()
        if not query or not self._last_matches:
            return

        total_files = len({m.absolute_path for m in self._last_matches})
        result = QMessageBox.question(
            self,
            "Replace All",
            f"Replace all occurrences of '{query}' with '{replacement}' "
            f"in {total_files} file(s)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        options = self._search_options()
        count = replace_in_files(self._last_matches, replacement, query, options=options)
        self._summary_label.setText(f"Replaced {count} occurrence(s).")
        self._run_search()
