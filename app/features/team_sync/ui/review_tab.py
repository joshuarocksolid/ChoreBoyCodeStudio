"""Review editor tab. Accept opens Combine when the engine returns clashes."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import Qt, QSize, QTimer
from app.qt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.features.team_sync.api import FILE_ADDED, FILE_DELETED, FileDiff, Incoming
from app.features.team_sync.ui.copy import clock, first_name
from app.features.team_sync.ui.form_preview import FormCompare
from app.features.team_sync.ui.ports import SyncPorts
from app.features.team_sync.ui.widgets import Avatar
from app.shell.icon_provider import file_icon, file_type_icon_map
from app.shell.diff_view import DIFF_VIEW_MODE_INLINE, DIFF_VIEW_MODE_SIDE_BY_SIDE, DiffView
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette
from app.ui.segmented_control import SegmentedControl


class ReviewTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.reviewTab")
        self._api = None
        self._ports = SyncPorts()
        self._incoming_id = ""
        self._diffs: list[FileDiff] = []
        self._on_combine: Optional[Callable[[object], None]] = None
        self._on_finished: Optional[Callable[[str], None]] = None
        self._on_dismiss: Optional[Callable[[str], None]] = None
        self._on_show_file: Optional[Callable[[str], None]] = None
        self._tokens: Optional[ShellThemeTokens] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QWidget(self)
        header.setObjectName("shell.teamSync.reviewHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(12, 8, 12, 8)
        self._avatar = Avatar("", "", header)
        header_row.addWidget(self._avatar)
        self._note = QLabel("", header)
        self._note.setObjectName("shell.teamSync.reviewNote")
        self._note.setWordWrap(True)
        header_row.addWidget(self._note, 1)
        self._mode = SegmentedControl(header)
        self._mode.setObjectName("shell.teamSync.reviewMode")
        self._mode.add_segment("Inline", DIFF_VIEW_MODE_INLINE)
        self._mode.add_segment("Side by side", DIFF_VIEW_MODE_SIDE_BY_SIDE)
        self._mode.selection_changed.connect(self._set_mode)
        header_row.addWidget(self._mode)
        self._show_file = QPushButton("Show in File", header)
        self._show_file.setObjectName("shell.teamSync.reviewShowFile")
        self._show_file.clicked.connect(self._show_current_file)
        self._not_now = QPushButton("Not Now", header)
        self._not_now.setObjectName("shell.teamSync.reviewNotNow")
        self._not_now.clicked.connect(self._dismiss)
        self._accept = QPushButton("Accept", header)
        self._accept.setObjectName("shell.teamSync.reviewAccept")
        self._accept.clicked.connect(self.accept)
        header_row.addWidget(self._show_file)
        header_row.addWidget(self._not_now)
        header_row.addWidget(self._accept)
        root.addWidget(header)

        splitter = QSplitter(Qt.Horizontal, self)
        self._files = QListWidget(splitter)
        self._files.setObjectName("shell.teamSync.reviewFiles")
        self._files.currentRowChanged.connect(self._show_row)
        self._stack_host = QWidget(splitter)
        stack = QVBoxLayout(self._stack_host)
        stack.setContentsMargins(0, 0, 0, 0)
        self._diff = DiffView(tokens_from_palette(self.palette()), self._stack_host)
        self._diff.set_hide_metadata_headers(True)
        self._forms = FormCompare(self._stack_host)
        stack.addWidget(self._diff, 1)
        stack.addWidget(self._forms, 1)
        self._forms.hide()
        splitter.addWidget(self._files)
        splitter.addWidget(self._stack_host)
        splitter.setSizes([220, 640])
        root.addWidget(splitter, 1)
        self._mode.set_selected(DIFF_VIEW_MODE_INLINE)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        self._diff.apply_theme(tokens)
        if self._diffs:
            self._diff.emphasize_changed_words()
        self.style().unpolish(self)
        self.style().polish(self)

    def open_incoming(
        self,
        api: object,
        ports: object,
        incoming: Incoming,
        *,
        on_combine: Callable[[object], None],
        on_finished: Callable[[str], None],
        on_dismiss: Callable[[str], None],
        on_show_file: Callable[[str], None],
        tokens: Optional[ShellThemeTokens] = None,
    ) -> None:
        self._api = api
        self._ports = ports
        self._incoming_id = incoming.id
        self._on_combine = on_combine
        self._on_finished = on_finished
        self._on_dismiss = on_dismiss
        self._on_show_file = on_show_file
        change = incoming.changes[0] if incoming.changes else None
        name = first_name(change.author_name) if change is not None else "Someone"
        note = change.note if change is not None else ""
        when = clock(change.when) if change is not None else ""
        self._mode.set_selected(DIFF_VIEW_MODE_INLINE)
        self._diff.set_mode(DIFF_VIEW_MODE_INLINE)
        self._avatar.set_person(incoming.from_id, name)
        self._note.setText(f"{note} · {when}")
        if tokens is not None:
            self.apply_theme(tokens)
        self._ports.run(  # type: ignore[attr-defined]
            "team-sync-review-diff",
            lambda: api.incoming_diff(incoming.id),  # type: ignore[attr-defined]
            self._show_diffs,
        )

    def accept(self) -> None:
        if self._api is None or not self._incoming_id:
            return
        incoming_id = self._incoming_id

        def task() -> object:
            return self._api.accept(incoming_id)  # type: ignore[attr-defined]

        self._ports.run("team-sync-accept", task, self._accepted)  # type: ignore[attr-defined]

    def _accepted(self, state: object) -> None:
        if state is None:
            if self._on_finished is not None:
                self._on_finished(self._incoming_id)
            return
        if self._on_combine is not None:
            self._on_combine(state)

    def _dismiss(self) -> None:
        if self._on_dismiss is not None and self._incoming_id:
            self._on_dismiss(self._incoming_id)

    def _show_diffs(self, diffs: object) -> None:
        self._diffs = list(diffs or [])
        self._files.clear()
        icons = file_type_icon_map()
        fallback = file_icon(self._tokens.icon_primary if self._tokens is not None else "#5A6168")
        for diff in self._diffs:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 26))
            self._files.addItem(item)
            self._files.setItemWidget(item, self._file_row(diff, icons, fallback))
        if self._diffs:
            self._files.setCurrentRow(0)
        else:
            self._diff.set_message("No changes")

    def _file_row(self, diff: FileDiff, icons: dict, fallback) -> QWidget:  # type: ignore[type-arg]
        row = QWidget()
        row.setFixedHeight(26)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)
        ext = diff.path.rsplit(".", 1)[-1].lower() if "." in diff.path else ""
        icon = QLabel(row)
        pixmap = (icons.get(ext) or fallback).pixmap(14, 14)
        icon.setPixmap(pixmap)
        layout.addWidget(icon)
        name = QLabel(diff.path, row)
        name.setObjectName("shell.teamSync.feedNote")
        layout.addWidget(name, 1)
        kind = QLabel(diff.kind, row)
        kind.setObjectName("shell.teamSync.fileKind")
        kind.setProperty("kind", diff.kind)
        kind.style().unpolish(kind)
        kind.style().polish(kind)
        layout.addWidget(kind)
        return row

    def _show_row(self, row: int) -> None:
        if row < 0 or row >= len(self._diffs):
            return
        diff = self._diffs[row]
        if diff.is_form:
            self._diff.hide()
            self._forms.show()
            self._forms.set_forms(diff.old_text or "", diff.new_text or "")
            return
        self._forms.hide()
        self._diff.show()
        self._diff.set_message("Loading")
        QTimer.singleShot(0, lambda diff=diff: self._paint_diff(diff))

    def _paint_diff(self, diff: FileDiff) -> None:
        before = diff.old_text or ""
        after = diff.new_text or ""
        if not before and not after and diff.hunks:
            before = "\n".join(diff.hunks[0].old_lines)
            after = "\n".join(diff.hunks[0].new_lines)
        self._diff.set_message(None)
        removed = "Deleted" if diff.kind == FILE_DELETED else "Before"
        added = "Added" if diff.kind == FILE_ADDED else "After"
        self._diff.set_texts(before, after, before_label=removed, after_label=added)
        if len(before) + len(after) < 80_000:
            self._diff.emphasize_changed_words()

    def _set_mode(self, mode: str) -> None:
        if mode in (DIFF_VIEW_MODE_INLINE, DIFF_VIEW_MODE_SIDE_BY_SIDE):
            self._diff.set_mode(mode)

    def _show_current_file(self) -> None:
        row = self._files.currentRow()
        if row < 0 or row >= len(self._diffs) or self._on_show_file is None:
            return
        self._on_show_file(self._diffs[row].path)

    def current_path(self) -> str:
        row = self._files.currentRow()
        if row < 0 or row >= len(self._diffs):
            return ""
        return self._diffs[row].path


__all__ = ["ReviewTab"]
