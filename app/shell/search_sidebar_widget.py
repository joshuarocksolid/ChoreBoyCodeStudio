"""Project-wide search/replace sidebar panel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide2.QtCore import Qt, QTimer, Signal
from PySide2.QtGui import QKeyEvent
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.editors.search_panel import SearchMatch, SearchOptions, SearchWorker, replace_in_files


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
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 4)
        outer.setSpacing(6)

        header = QLabel("SEARCH", self)
        header.setObjectName("shell.searchSidebar.header")
        outer.addWidget(header)

        search_row = QWidget(self)
        search_layout = QHBoxLayout(search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(4)

        self._search_input = QLineEdit(search_row)
        self._search_input.setObjectName("shell.searchSidebar.searchInput")
        self._search_input.setPlaceholderText("Search")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_input_changed)
        self._search_input.returnPressed.connect(self._run_search)
        search_layout.addWidget(self._search_input, 1)

        self._case_btn = QToolButton(search_row)
        self._case_btn.setObjectName("shell.searchSidebar.caseBtn")
        self._case_btn.setText("Aa")
        self._case_btn.setToolTip("Match Case")
        self._case_btn.setCheckable(True)
        self._case_btn.setFixedSize(24, 24)
        self._case_btn.toggled.connect(self._on_option_changed)
        search_layout.addWidget(self._case_btn)

        self._word_btn = QToolButton(search_row)
        self._word_btn.setObjectName("shell.searchSidebar.wordBtn")
        self._word_btn.setText("W")
        self._word_btn.setToolTip("Whole Word")
        self._word_btn.setCheckable(True)
        self._word_btn.setFixedSize(24, 24)
        self._word_btn.toggled.connect(self._on_option_changed)
        search_layout.addWidget(self._word_btn)

        self._regex_btn = QToolButton(search_row)
        self._regex_btn.setObjectName("shell.searchSidebar.regexBtn")
        self._regex_btn.setText(".*")
        self._regex_btn.setToolTip("Use Regular Expression")
        self._regex_btn.setCheckable(True)
        self._regex_btn.setFixedSize(24, 24)
        self._regex_btn.toggled.connect(self._on_option_changed)
        search_layout.addWidget(self._regex_btn)

        outer.addWidget(search_row)

        self._replace_toggle_btn = QToolButton(self)
        self._replace_toggle_btn.setObjectName("shell.searchSidebar.replaceToggle")
        self._replace_toggle_btn.setText("\u25B6 Replace")
        self._replace_toggle_btn.setToolTip("Toggle replace")
        self._replace_toggle_btn.setCheckable(True)
        self._replace_toggle_btn.toggled.connect(self._toggle_replace)
        outer.addWidget(self._replace_toggle_btn)

        self._replace_container = QWidget(self)
        replace_layout = QVBoxLayout(self._replace_container)
        replace_layout.setContentsMargins(0, 0, 0, 0)
        replace_layout.setSpacing(4)

        replace_input_row = QWidget(self._replace_container)
        replace_input_layout = QHBoxLayout(replace_input_row)
        replace_input_layout.setContentsMargins(0, 0, 0, 0)
        replace_input_layout.setSpacing(4)

        self._replace_input = QLineEdit(replace_input_row)
        self._replace_input.setObjectName("shell.searchSidebar.replaceInput")
        self._replace_input.setPlaceholderText("Replace")
        self._replace_input.setClearButtonEnabled(True)
        replace_input_layout.addWidget(self._replace_input, 1)

        self._replace_all_btn = QPushButton("Replace All", replace_input_row)
        self._replace_all_btn.setObjectName("shell.searchSidebar.replaceAllBtn")
        self._replace_all_btn.setToolTip("Replace all matches in all files")
        self._replace_all_btn.clicked.connect(self._on_replace_all)
        replace_input_layout.addWidget(self._replace_all_btn)

        replace_layout.addWidget(replace_input_row)
        outer.addWidget(self._replace_container)
        self._replace_container.setVisible(False)

        filters_row = QWidget(self)
        filters_layout = QVBoxLayout(filters_row)
        filters_layout.setContentsMargins(0, 0, 0, 0)
        filters_layout.setSpacing(2)

        self._include_input = QLineEdit(filters_row)
        self._include_input.setObjectName("shell.searchSidebar.includeInput")
        self._include_input.setPlaceholderText("Files to include (e.g. *.py)")
        self._include_input.setClearButtonEnabled(True)
        self._include_input.textChanged.connect(self._on_input_changed)
        filters_layout.addWidget(self._include_input)

        self._exclude_input = QLineEdit(filters_row)
        self._exclude_input.setObjectName("shell.searchSidebar.excludeInput")
        self._exclude_input.setPlaceholderText("Files to exclude (e.g. tests/*)")
        self._exclude_input.setClearButtonEnabled(True)
        self._exclude_input.textChanged.connect(self._on_input_changed)
        filters_layout.addWidget(self._exclude_input)

        outer.addWidget(filters_row)

        self._summary_label = QLabel("", self)
        self._summary_label.setObjectName("shell.searchSidebar.summary")
        outer.addWidget(self._summary_label)

        self._results_tree = QTreeWidget(self)
        self._results_tree.setObjectName("shell.searchSidebar.results")
        self._results_tree.setHeaderHidden(True)
        self._results_tree.setIndentation(16)
        self._results_tree.itemActivated.connect(self._on_result_activated)
        self._results_tree.itemClicked.connect(self._on_result_activated)
        self._results_tree.itemDoubleClicked.connect(self._on_result_activated)
        outer.addWidget(self._results_tree, 1)

    def set_project_root(self, project_root: str | None) -> None:
        self._project_root = project_root
        if project_root is None:
            self._results_tree.clear()
            self._summary_label.setText("")
            self._last_matches.clear()

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

    def _on_option_changed(self, _checked: bool) -> None:
        self._debounce_timer.start()

    def _toggle_replace(self, checked: bool) -> None:
        self._replace_visible = checked
        self._replace_container.setVisible(checked)
        self._replace_toggle_btn.setText("\u25BC Replace" if checked else "\u25B6 Replace")

    def _run_search(self) -> None:
        if self._active_worker is not None and self._active_worker.is_running():
            self._active_worker.cancel()

        query = self._search_input.text().strip()
        if not query or not self._project_root:
            self._results_tree.clear()
            self._summary_label.setText("")
            self._last_matches.clear()
            return

        self._summary_label.setText("Searching...")
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
        pass

    def _apply_search_results(self) -> None:
        matches = getattr(self, "_pending_results", [])
        self._last_matches = matches
        self._results_tree.clear()

        files: dict[str, list[SearchMatch]] = {}
        for m in matches:
            files.setdefault(m.relative_path, []).append(m)

        total_matches = len(matches)
        total_files = len(files)
        self._summary_label.setText(
            f"{total_matches} result{'s' if total_matches != 1 else ''} "
            f"in {total_files} file{'s' if total_files != 1 else ''}"
        )

        for rel_path, file_matches in sorted(files.items()):
            file_item = QTreeWidgetItem(self._results_tree)
            file_item.setText(0, f"{rel_path} ({len(file_matches)})")
            file_item.setToolTip(0, file_matches[0].absolute_path)
            file_item.setData(0, Qt.UserRole, None)
            file_item.setExpanded(True)

            for m in file_matches:
                line_item = QTreeWidgetItem(file_item)
                display_text = m.line_text.strip()
                if len(display_text) > 120:
                    display_text = display_text[:120] + "..."
                line_item.setText(0, f"  L{m.line_number}: {display_text}")
                line_item.setToolTip(0, m.line_text.strip())
                line_item.setData(0, Qt.UserRole, m.absolute_path)
                line_item.setData(0, Qt.UserRole + 1, m.line_number)

    def _on_result_activated(self, item: QTreeWidgetItem, column: int = 0) -> None:
        abs_path = item.data(0, Qt.UserRole)
        line_number = item.data(0, Qt.UserRole + 1)
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
