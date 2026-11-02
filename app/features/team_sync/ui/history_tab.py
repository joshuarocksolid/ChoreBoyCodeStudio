"""History tab. Pages of 200. Lanes only when an experiment exists or advanced tools are on."""

from __future__ import annotations

import os
from typing import Callable, Optional

from app.qt.QtCore import Qt
from app.qt.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.features.team_sync.api import MAIN_LINE, Change
from app.features.team_sync.ui.copy import short_date
from app.features.team_sync.ui.ports import SyncPorts
from app.features.team_sync.ui.theme import field_qss, surface_qss
from app.features.team_sync.ui.widgets import Avatar
from app.qt.qt_compat import exec_qt
from app.shell.diff_view import DiffView
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette


class HistoryTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.historyTab")
        self._api = None
        self._ports = SyncPorts()
        self._rows: list[Change] = []
        self._offset = 0
        self._path: Optional[str] = None
        self._show_lanes = False
        self._show_ids = False
        self._advanced = False
        self._on_action: Optional[Callable[[str, Change], None]] = None
        self._tokens: Optional[ShellThemeTokens] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        filters = QHBoxLayout()
        filters.setContentsMargins(12, 8, 12, 8)
        self._search = QLineEdit(self)
        self._search.setObjectName("shell.teamSync.historySearch")
        self._search.setPlaceholderText("Search")
        self._search.textChanged.connect(self.reload)
        self._main_only = QCheckBox("Main", self)
        self._main_only.setObjectName("shell.teamSync.historyFilter")
        self._main_only.setChecked(True)
        self._main_only.toggled.connect(self.reload)
        filters.addWidget(self._search, 1)
        filters.addWidget(self._main_only)
        root.addLayout(filters)

        splitter = QSplitter(Qt.Horizontal, self)
        self._list = QListWidget(splitter)
        self._list.setObjectName("shell.teamSync.historyList")
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._menu)
        self._list.currentRowChanged.connect(self._select)
        self._list.verticalScrollBar().valueChanged.connect(self._maybe_page)
        self._detail = QWidget(splitter)
        detail = QVBoxLayout(self._detail)
        detail.setContentsMargins(8, 8, 8, 8)
        self._files = QLabel("", self._detail)
        self._files.setWordWrap(True)
        detail.addWidget(self._files)
        self._diff = DiffView(tokens_from_palette(self.palette()), self._detail)
        detail.addWidget(self._diff, 1)
        splitter.addWidget(self._list)
        splitter.addWidget(self._detail)
        splitter.setSizes([320, 560])
        root.addWidget(splitter, 1)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        self.setStyleSheet(surface_qss(tokens))
        self._search.setStyleSheet(field_qss(tokens))
        self._diff.apply_theme(tokens)

    def open_history(
        self,
        api: object,
        ports: object,
        *,
        path: Optional[str] = None,
        show_lanes: bool,
        show_ids: bool,
        advanced: bool,
        on_action: Callable[[str, Change], None],
        tokens: Optional[ShellThemeTokens] = None,
    ) -> None:
        self._api = api
        self._ports = ports
        self._path = path
        self._show_lanes = show_lanes
        self._show_ids = show_ids
        self._advanced = advanced
        self._on_action = on_action
        if tokens is not None:
            self.apply_theme(tokens)
        self._offset = 0
        self._rows = []
        self._list.clear()
        self._load_page()

    def reload(self) -> None:
        self._offset = 0
        self._rows = []
        self._list.clear()
        self._load_page()

    def _load_page(self) -> None:
        if self._api is None:
            return
        query = self._search.text().strip()
        offset = self._offset
        path = self._path
        all_lines = not self._main_only.isChecked()

        def task() -> object:
            return self._api.history(  # type: ignore[attr-defined]
                path=path,
                query=query,
                offset=offset,
                limit=200,
                all_lines=all_lines,
            )

        self._ports.run("team-sync-history", task, self._append)  # type: ignore[attr-defined]

    def _append(self, rows: object) -> None:
        batch = list(rows or [])
        if self._offset == 0:
            self._rows = []
            self._list.clear()
        self._rows.extend(batch)
        for change in batch:
            item = QListWidgetItem(self._label(change))
            item.setData(Qt.UserRole, change.id)
            self._list.addItem(item)
        self._offset = len(self._rows)
        if self._rows and self._list.currentRow() < 0:
            self._list.setCurrentRow(0)

    def _label(self, change: Change) -> str:
        lane = ""
        if self._show_lanes:
            lane = "● " if change.line == MAIN_LINE else "○ "
        milestone = f"  {change.milestone}" if change.milestone else ""
        ident = f"  {change.id}" if self._show_ids else ""
        return f"{lane}{change.note}{milestone}  {short_date(change.when)}{ident}"

    def _maybe_page(self, value: int) -> None:
        bar = self._list.verticalScrollBar()
        if value >= bar.maximum() and self._offset and self._offset % 200 == 0:
            self._load_page()

    def _select(self, row: int) -> None:
        if row < 0 or row >= len(self._rows) or self._api is None:
            return
        change = self._rows[row]
        names = ", ".join(f"{item.kind} {item.path}" for item in change.files)
        self._files.setText(names)
        change_id = change.id

        def task() -> object:
            return self._api.change_diff(change_id)  # type: ignore[attr-defined]

        def paint(diffs: object) -> None:
            rows = list(diffs or [])
            if not rows:
                self._diff.set_message("No textual differences found.")
                return
            diff = rows[0]
            self._diff.set_message(None)
            self._diff.set_texts(
                diff.old_text or "",
                diff.new_text or "",
                before_label="Before",
                after_label="After",
            )

        self._ports.run("team-sync-history-diff", task, paint)  # type: ignore[attr-defined]

    def _menu(self, position) -> None:  # type: ignore[no-untyped-def]
        row = self._list.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        change = self._rows[row]
        menu = QMenu(self._list)
        menu.setObjectName("shell.teamSync.historyMenu")
        actions = [
            ("Compare with Current", "compare_current"),
            ("Compare with…", "compare_with"),
            ("Restore This Version", "restore"),
            ("Undo This Change", "undo"),
            ("Start Experiment Here", "experiment"),
            ("Mark as Milestone…", "milestone"),
            ("Copy Change ID", "copy_id"),
        ]
        if self._advanced:
            actions.insert(5, ("Copy into Experiment…", "copy_experiment"))
            actions.insert(6, ("Find when something broke", "bisect"))
        for label, key in actions:
            menu.addAction(label, lambda key=key, change=change: self._run(key, change))
        point = self._list.viewport().mapToGlobal(position)
        if os.environ.get("CBCS_TEAM_SYNC_SHOTS"):
            menu.popup(point)
            return
        exec_qt(menu, point)

    def _run(self, key: str, change: Change) -> None:
        if self._on_action is not None:
            self._on_action(key, change)

    def selected_change(self) -> Optional[Change]:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._rows):
            return None
        return self._rows[row]


__all__ = ["HistoryTab"]
