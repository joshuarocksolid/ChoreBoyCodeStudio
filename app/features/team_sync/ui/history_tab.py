"""History tab. Pages of 200. Lanes only when an experiment exists or advanced tools are on."""

from __future__ import annotations

import os
from typing import Callable, Optional

from app.qt.QtCore import QPoint, Qt
from app.qt.QtGui import QColor, QPainter, QPen
from app.qt.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QFrame,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.features.team_sync.api import MAIN_LINE, Change
from app.features.team_sync.ui.copy import first_name, short_date
from app.features.team_sync.ui.ports import SyncPorts
from app.features.team_sync.ui.widgets import Avatar, avatar_color
from app.qt.qt_compat import exec_qt
from app.shell.diff_view import DiffView
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette


class _LanePane(QWidget):
    """Vertical lane lines and dots. One row is 30 px."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lanes: list[tuple[int, str, bool]] = []
        self._colors = ("#3366FF", "#D97706", "#0F766E")
        self._panel = "#FFFFFF"
        self.setFixedWidth(8)

    def set_marks(self, marks: list[tuple[int, str, bool]], colors: tuple[str, str, str], panel: str) -> None:
        self._lanes = marks
        self._colors = colors
        self._panel = panel
        count = max((lane for lane, _kind, _merge in marks), default=0) + 1
        self.setFixedWidth(12 + 14 * max(1, count) if marks else 8)
        self.setMinimumHeight(30 * max(1, len(marks)))
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        del event
        if not self._lanes:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        lanes = {lane for lane, _kind, _merge in self._lanes}
        for lane in lanes:
            rows = [index for index, mark in enumerate(self._lanes) if mark[0] == lane]
            if len(rows) < 2:
                continue
            color = QColor(self._color(self._lanes[rows[0]][1]))
            pen = QPen(color)
            pen.setWidth(2)
            painter.setPen(pen)
            x = 10 + lane * 14
            painter.drawLine(x, rows[0] * 30 + 15, x, rows[-1] * 30 + 15)
        for index, (lane, kind, merge) in enumerate(self._lanes):
            color = QColor(self._color(kind))
            painter.setPen(QPen(color, 2))
            painter.setBrush(QColor(self._panel) if merge else color)
            x = 10 + lane * 14
            y = index * 30 + 15
            painter.drawEllipse(QPoint(x, y), 4, 4)
        painter.end()

    def _color(self, kind: str) -> str:
        if kind == "experiment":
            return self._colors[1]
        if kind == "peer":
            return self._colors[2]
        return self._colors[0]


class HistoryList(QScrollArea):
    """Row list with the methods the history tab and the screenshot script call."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.historyList")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._host = QWidget(self)
        self._host.setObjectName("shell.teamSync.historyHost")
        self.viewport().setObjectName("shell.teamSync.historyViewport")
        self.viewport().setAttribute(Qt.WA_StyledBackground, True)
        self._host.setAttribute(Qt.WA_StyledBackground, True)
        row = QHBoxLayout(self._host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.lanes = _LanePane(self._host)
        self._column = QWidget(self._host)
        self._layout = QVBoxLayout(self._column)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)
        row.addWidget(self.lanes)
        row.addWidget(self._column, 1)
        self.setWidget(self._host)
        self._rows: list[QWidget] = []
        self._current = -1
        self._on_select: Optional[Callable[[int], None]] = None

    def set_select_handler(self, handler: Callable[[int], None]) -> None:
        self._on_select = handler

    def count(self) -> int:
        return len(self._rows)

    def currentRow(self) -> int:  # noqa: N802 - matches QListWidget
        return self._current

    def clear_rows(self) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._rows = []
        self._current = -1

    def add_row(self, widget: QWidget) -> None:
        index = len(self._rows)
        widget.mousePressEvent = lambda event, row=index: self.setCurrentRow(row)  # type: ignore[method-assign]
        for child in widget.findChildren(QWidget):
            child.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._rows.append(widget)
        self._layout.insertWidget(self._layout.count() - 1, widget)

    def setCurrentRow(self, row: int) -> None:  # noqa: N802 - matches QListWidget
        if row < 0 or row >= len(self._rows):
            return
        self._current = row
        for index, widget in enumerate(self._rows):
            widget.setProperty("selected", index == row)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        if self._on_select is not None:
            self._on_select(row)


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
        root.setSpacing(0)
        filters = QWidget(self)
        filters.setObjectName("shell.teamSync.historyTools")
        filter_row = QHBoxLayout(filters)
        filter_row.setContentsMargins(8, 6, 8, 6)
        filter_row.setSpacing(6)
        self._search = QLineEdit(filters)
        self._search.setObjectName("shell.teamSync.historySearch")
        self._search.setPlaceholderText("Search")
        self._search.textChanged.connect(self.reload)
        self._filter = QComboBox(filters)
        self._filter.setObjectName("shell.teamSync.historyFilter")
        self._filter.addItem("Main", "main")
        self._filter.addItem("All lines", "all")
        self._filter.currentIndexChanged.connect(lambda _index: self.reload())
        filter_row.addWidget(self._search, 1)
        filter_row.addWidget(self._filter)
        root.addWidget(filters)

        splitter = QSplitter(Qt.Horizontal, self)
        self._list = HistoryList(splitter)
        self._list.set_select_handler(self._select)
        self._list.verticalScrollBar().valueChanged.connect(self._maybe_page)
        self._detail = QWidget(splitter)
        detail = QVBoxLayout(self._detail)
        detail.setContentsMargins(12, 12, 12, 12)
        detail.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(8)
        self._avatar = Avatar("", "", self._detail, size=20)
        head.addWidget(self._avatar, 0, Qt.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        self._detail_note = QLabel("", self._detail)
        self._detail_note.setObjectName("shell.teamSync.feedName")
        self._detail_note.setWordWrap(True)
        self._detail_meta = QLabel("", self._detail)
        self._detail_meta.setObjectName("shell.teamSync.historyMeta")
        text.addWidget(self._detail_note)
        text.addWidget(self._detail_meta)
        head.addLayout(text, 1)
        detail.addLayout(head)
        self._files = QVBoxLayout()
        self._files.setSpacing(2)
        detail.addLayout(self._files)
        self._diff = DiffView(tokens_from_palette(self.palette()), self._detail)
        self._diff.set_hide_metadata_headers(True)
        detail.addWidget(self._diff, 1)
        splitter.addWidget(self._list)
        splitter.addWidget(self._detail)
        splitter.setSizes([420, 560])
        root.addWidget(splitter, 1)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        self._diff.apply_theme(tokens)
        self.style().unpolish(self)
        self.style().polish(self)

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
        self._list.clear_rows()
        self._load_page()

    def reload(self) -> None:
        self._offset = 0
        self._rows = []
        self._list.clear_rows()
        self._load_page()

    def _load_page(self) -> None:
        if self._api is None:
            return
        query = self._search.text().strip()
        offset = self._offset
        path = self._path
        all_lines = self._filter.currentData() == "all"

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
            self._list.clear_rows()
        self._rows.extend(batch)
        for change in batch:
            self._list.add_row(self._row_widget(change))
        self._paint_lanes()
        self._offset = len(self._rows)
        if self._rows and self._list.currentRow() < 0:
            self._list.setCurrentRow(0)

    def _row_widget(self, change: Change) -> QWidget:
        row = QWidget()
        row.setObjectName("shell.teamSync.historyRow")
        row.setFixedHeight(30)
        row.setAttribute(Qt.WA_StyledBackground, True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 0, 10, 0)
        layout.setSpacing(8)
        layout.addWidget(Avatar(change.author_id, change.author_name, row, size=20))
        if change.milestone:
            chip = QLabel(f"⚑ {change.milestone}", row)
            chip.setObjectName("shell.teamSync.milestoneChip")
            layout.addWidget(chip)
        note = QLabel(change.note, row)
        note.setObjectName("shell.teamSync.feedNote")
        layout.addWidget(note, 1)
        if self._show_ids:
            ident = QLabel(change.id[:8], row)
            ident.setObjectName("shell.teamSync.historyDate")
            layout.addWidget(ident)
        when = QLabel(short_date(change.when), row)
        when.setObjectName("shell.teamSync.historyDate")
        layout.addWidget(when)
        row.setContextMenuPolicy(Qt.CustomContextMenu)
        row.customContextMenuRequested.connect(lambda _pos, change=change: self._menu_for(change))
        return row

    def _paint_lanes(self) -> None:
        if not self._show_lanes:
            self._list.lanes.set_marks([], self._lane_colors(), self._panel())
            self._list.lanes.hide()
            return
        self._list.lanes.show()
        lane_of: dict[str, int] = {MAIN_LINE: 0}
        marks: list[tuple[int, str, bool]] = []
        for change in self._rows:
            key = change.line or MAIN_LINE
            if key not in lane_of:
                lane_of[key] = len(lane_of)
            kind = "main"
            if key != MAIN_LINE:
                kind = "experiment" if key.startswith("exp/") or lane_of[key] == 1 else "peer"
            marks.append((lane_of[key], kind, len(change.parents) > 1))
        self._list.lanes.set_marks(marks, self._lane_colors(), self._panel())

    def _lane_colors(self) -> tuple[str, str, str]:
        tokens = self._tokens
        if tokens is None:
            return ("#3366FF", "#D97706", "#0F766E")
        peer = avatar_color(self._rows[-1].author_id) if self._rows else "#0F766E"
        return (
            tokens.accent,
            tokens.diag_warning_color or "#D97706",
            peer,
        )

    def _panel(self) -> str:
        if self._tokens is None:
            return "#FFFFFF"
        return self._tokens.panel_bg or "#FFFFFF"

    def _maybe_page(self, value: int) -> None:
        bar = self._list.verticalScrollBar()
        if value >= bar.maximum() and self._offset and self._offset % 200 == 0:
            self._load_page()

    def _select(self, row: int) -> None:
        if row < 0 or row >= len(self._rows) or self._api is None:
            return
        change = self._rows[row]
        self._avatar.set_person(change.author_id, change.author_name, 20)
        self._detail_note.setText(change.note)
        self._detail_meta.setText(f"{first_name(change.author_name)} · {short_date(change.when)}")
        while self._files.count():
            item = self._files.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        for file_change in change.files:
            label = QLabel(f"{file_change.kind}  {file_change.path}", self._detail)
            label.setObjectName("shell.teamSync.fileKind")
            label.setProperty("kind", file_change.kind)
            self._files.addWidget(label)
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
        del position
        row = self._list.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        self._menu_for(self._rows[row])

    def _menu_for(self, change: Change) -> None:
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
        point = self._list.mapToGlobal(QPoint(24, 36))
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
