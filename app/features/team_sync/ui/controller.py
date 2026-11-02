"""Connects Team Sync widgets to TeamSyncApi. Service calls leave the UI thread."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

from app.qt.QtCore import QObject, QTimer, Qt
from app.qt.QtGui import QTextCursor
from app.qt.QtWidgets import QCheckBox, QInputDialog, QMenu, QWidget

from app.features.team_sync.api import (
    EVENT_COMBINE,
    EVENT_FEED,
    EVENT_HISTORY,
    EVENT_INCOMING,
    EVENT_STATUS,
    EVENT_TOAST_PREFIX,
    MAIN_LINE,
    Change,
    Clash,
    CombineState,
    Incoming,
    TeamStatus,
)
from app.features.team_sync.ui.blame import BlameCard, LineSummary
from app.features.team_sync.ui.combine_tab import CombineTab
from app.features.team_sync.ui.copy import badge_count, explorer_letters, first_name, status_view
from app.features.team_sync.ui.dialogs import (
    choose_usb_open,
    choose_usb_save,
    show_deleted,
    show_invite,
    show_members,
    show_share,
)
from app.features.team_sync.ui.gutter_peek import GutterPeek
from app.features.team_sync.ui.history_tab import HistoryTab
from app.features.team_sync.ui.info_bar import TeamInfoBar
from app.features.team_sync.ui.ports import SyncPorts
from app.features.team_sync.ui.review_tab import ReviewTab
from app.features.team_sync.ui.send_sheet import SendSheet, SendToolbarButton
from app.features.team_sync.ui.settings_group import TeamSettingsGroup, TeamUiSettings
from app.features.team_sync.ui.status_segment import (
    ExperimentSegment,
    StatusPopover,
    TeamStatusSegment,
    other_shop,
    waiting_rows,
)
from app.features.team_sync.ui.team_view import TeamView
from app.features.team_sync.ui.tree_decorations import ExplorerLetterCache
from app.qt.qt_compat import exec_qt
from app.shell.theme_tokens import ShellThemeTokens
from app.shell.toast import show_toast


class TeamSyncController(QObject):
    """Holds the latest snapshot and tells each surface what changed."""

    def __init__(
        self,
        window: QWidget,
        service: object,
        ports: object,
        *,
        dormant: bool,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._service = service
        self._ports = ports
        self._dormant = dormant
        self._settings = TeamUiSettings()
        self._letters = ExplorerLetterCache()
        self._status = TeamStatus(shared=False, project_name="")
        self._feed: list = []
        self._incoming: list[Incoming] = []
        self._project_root = ""
        self._unsubscribe: Optional[Callable[[], None]] = None
        self._tokens: Optional[ShellThemeTokens] = None
        self._blame: dict[str, dict[int, object]] = {}
        self._team_view: Optional[TeamView] = None
        self._send_button: Optional[SendToolbarButton] = None
        self._send_sheet: Optional[SendSheet] = None
        self._segment: Optional[TeamStatusSegment] = None
        self._experiment: Optional[ExperimentSegment] = None
        self._popover: Optional[StatusPopover] = None
        self._review: Optional[ReviewTab] = None
        self._combine: Optional[CombineTab] = None
        self._history: Optional[HistoryTab] = None
        self._card: Optional[BlameCard] = None
        self._peek: Optional[GutterPeek] = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.refresh_status)
        self._poll = QTimer(self)
        self._poll.setInterval(30_000)
        self._poll.timeout.connect(self._poll_once)
        unsubscribe = service.subscribe(self._on_service_event)  # type: ignore[attr-defined]
        self._unsubscribe = unsubscribe

    @property
    def letters(self) -> ExplorerLetterCache:
        return self._letters

    @property
    def service(self) -> object:
        return self._service

    def attach(
        self,
        team_view: TeamView,
        send_button: SendToolbarButton,
    ) -> None:
        self._team_view = team_view
        self._send_button = send_button
        self._send_sheet = SendSheet(self._window)
        team_view.bind(
            on_share=self.open_share,
            on_send=self._send,
            on_save_only=self._save_only,
            on_set_aside=self._set_aside,
            on_bring_back=self._bring_back,
            on_review=self.open_review,
            on_open_change=self._open_change,
        )
        send_button.clicked.connect(self.open_send_sheet)
        self._mount_status()
        self.apply_theme(self._current_tokens())
        self.refresh_status()
        self._run("team-sync-feed", lambda: self._service.feed(), self._apply_feed)  # type: ignore[attr-defined]
        self._run("team-sync-incoming", lambda: self._service.incoming(), self._apply_incoming)  # type: ignore[attr-defined]

    def apply_theme(self, tokens: object) -> None:
        if not isinstance(tokens, ShellThemeTokens):
            return
        self._tokens = tokens
        if self._team_view is not None:
            self._team_view.apply_theme(tokens)
        if self._send_button is not None:
            self._send_button.apply_theme(tokens)
        if self._send_sheet is not None:
            self._send_sheet.apply_theme(tokens)
        if self._popover is not None:
            self._popover.apply_theme(tokens)
        if self._segment is not None:
            self._segment.apply(status_view(self._status, waiting_name=self._waiting_name()), tokens)
        if self._experiment is not None:
            self._experiment.apply(self._status, tokens)
        for tab in (self._review, self._combine, self._history):
            if tab is not None:
                tab.apply_theme(tokens)
        if self._card is not None:
            self._card.apply_theme(tokens)
        if self._peek is not None:
            self._peek.apply_theme(tokens)

    def on_project_opened(self, project_root: str, project_name: str) -> None:
        del project_name
        self._project_root = project_root
        self.request_status()

    def on_file_saved(self, path: str) -> None:
        del path
        self.request_status()

    def request_status(self) -> None:
        self._debounce.start()

    def refresh_status(self) -> None:
        self._run("team-sync-status", lambda: self._service.status(), self._apply_status)  # type: ignore[attr-defined]

    def open_share(self) -> None:
        if self._dormant:
            return
        summary = getattr(self._service, "share_summary", None)
        chip = f"{len(self._status.pending)} files"
        if callable(summary):
            result = summary()
            if isinstance(result, tuple) and len(result) == 2:
                chip = f"{result[0]} files · {result[1]}"
        show_share(
            self._status,
            chip,
            lambda request: self._run("team-sync-share", lambda: self._service.share(request), lambda _r: self.refresh_status()),  # type: ignore[attr-defined]
            self._window,
            self._tokens,
        )

    def open_send_sheet(self) -> None:
        if self._send_sheet is None or self._send_button is None or not self._status.shared:
            return
        self._send_sheet.present(
            self._send_button,
            self._status,
            other_shop(self._status),
            self._send,
        )

    def open_status_popover(self) -> None:
        if self._popover is None or self._segment is None:
            return
        def _open(payload: object) -> None:
            if isinstance(payload, tuple) and len(payload) == 2:
                self._show_popover(payload[0], payload[1])

        self._run(
            "team-sync-popover",
            lambda: (self._service.history(limit=1), self._service.incoming()),  # type: ignore[attr-defined]
            _open,
        )

    def open_experiment_menu(self) -> None:
        if self._experiment is None:
            return
        menu = QMenu(self._experiment)
        menu.setObjectName("shell.teamSync.experimentMenu")
        lines = (MAIN_LINE,) + tuple(self._status.experiments)
        for line in lines:
            menu.addAction(line, lambda line=line: self._run_void(lambda: self._service.switch_line(line)))  # type: ignore[attr-defined]
        current = self._status.line
        if current != MAIN_LINE:
            menu.addAction("Bring into Main…", lambda: self._bring_experiment(current))
            menu.addAction("Share with Team…", self.open_send_sheet)
            menu.addAction("Delete Experiment…", lambda: self._run_void(lambda: self._service.delete_experiment(current)))  # type: ignore[attr-defined]
        menu.addAction("New Experiment…", self._new_experiment)
        point = self._experiment.mapToGlobal(self._experiment.rect().bottomLeft())
        if os.environ.get("CBCS_TEAM_SYNC_SHOTS"):
            menu.popup(point)
            return
        exec_qt(menu, point)

    def open_review(self, incoming_id: str = "") -> None:
        incoming = self._incoming_by_id(incoming_id) or (self._incoming[0] if self._incoming else None)
        if incoming is None:
            return
        tab = self._ensure_review()
        tab.open_incoming(
            self._service,
            self._ports,
            incoming,
            on_combine=self._open_combine,
            on_finished=self._accepted,
            on_dismiss=lambda ident: self._run_void(lambda: self._service.dismiss(ident)),  # type: ignore[attr-defined]
            on_show_file=self._show_file,
            tokens=self._tokens,
        )
        name = first_name(incoming.changes[0].author_name) if incoming.changes else "Change"
        self._show_tab(tab, f"Review · {name}")

    def open_history(self, path: Optional[str] = None) -> None:
        tab = self._ensure_history()
        tab.open_history(
            self._service,
            self._ports,
            path=path,
            show_lanes=bool(self._status.experiments) or self._settings.copy_into_experiment or self._settings.find_broke,
            show_ids=self._settings.change_ids,
            advanced=self._settings.copy_into_experiment or self._settings.find_broke,
            on_action=self._history_action,
            tokens=self._tokens,
        )
        self._show_tab(tab, "History")

    def open_members(self) -> None:
        show_members(
            self._status,
            lambda member_id: self._run_void(lambda: self._service.remove_member(member_id)),  # type: ignore[attr-defined]
            self._window,
        )

    def open_invite(self) -> None:
        invites = self._service.pending_invites()  # type: ignore[attr-defined]
        if not invites:
            return
        show_invite(
            invites[0],
            lambda ident, folder: self._run(
                "team-sync-invite",
                lambda: self._service.accept_invite(ident, folder or self._project_root or "."),  # type: ignore[attr-defined]
                lambda _path: self.refresh_status(),
            ),
            self._window,
            self._tokens,
        )

    def save_to_usb(self) -> None:
        path = choose_usb_save(self._window)
        if path:
            self._run_void(lambda: self._service.export_bundle(path))  # type: ignore[attr-defined]

    def open_from_usb(self) -> None:
        path = choose_usb_open(self._window)
        if path:
            self._run("team-sync-import", lambda: self._service.import_bundle(path), lambda _item: self.refresh_status())  # type: ignore[attr-defined]

    def settings_group(self, parent: QWidget) -> QWidget:
        return TeamSettingsGroup(self._settings, self._settings_changed, parent)

    def package_extra(self, wizard: object) -> None:
        if not self._status.shared:
            return
        page = getattr(wizard, "metadata_page", None)
        if page is None:
            return
        box = QCheckBox("Mark this version in history", wizard)  # type: ignore[arg-type]
        box.setObjectName("shell.teamSync.packageMilestone")
        box.setChecked(True)
        page.insert_extra(box)
        wizard._team_sync_milestone = box  # type: ignore[attr-defined]

    def on_packaged(self, wizard: object, version: str) -> None:
        box = getattr(wizard, "_team_sync_milestone", None)
        if box is None or not box.isChecked():
            return

        def task() -> None:
            rows = self._service.history(limit=1)  # type: ignore[attr-defined]
            if rows:
                self._service.mark_milestone(rows[0].id, version or "v0")  # type: ignore[attr-defined]

        self._run_void(task)

    def attach_editor_page(self, page: QWidget, path: str) -> None:
        editor = page.content() if hasattr(page, "content") else None
        if editor is None:
            return
        relative = self._relative(path)
        if hasattr(editor, "set_line_hover_callback"):
            editor.set_line_hover_callback(lambda line, pos, rel=relative: self._hover(rel, line, pos))
        if hasattr(editor, "cursorPositionChanged"):
            summary = LineSummary(editor.viewport())
            if self._tokens is not None:
                summary.apply_theme(self._tokens)
            editor.cursorPositionChanged.connect(lambda rel=relative, summary=summary: self._place_summary(editor, rel, summary))
        self._run(
            "team-sync-blame",
            lambda: self._service.blame(relative),  # type: ignore[attr-defined]
            lambda rows, rel=relative: self._store_blame(rel, rows),
        )
        self._run(
            "team-sync-gutter",
            lambda: self._service.working_diff(relative),  # type: ignore[attr-defined]
            lambda diff, editor=editor: self._apply_marks(editor, diff),
        )
        self._refresh_notices()

    def _mount_status(self) -> None:
        status_bar = self._window._status_controller.status_bar  # type: ignore[attr-defined]
        self._segment = TeamStatusSegment(status_bar)
        self._experiment = ExperimentSegment(status_bar)
        self._popover = StatusPopover(self._window)
        self._segment.clicked = self.open_status_popover  # type: ignore[method-assign]
        self._experiment.clicked = self.open_experiment_menu  # type: ignore[method-assign]
        status_bar.addPermanentWidget(self._experiment, 0)
        status_bar.addPermanentWidget(self._segment, 0)

    def _on_service_event(self, event: str) -> None:
        dispatcher = getattr(self._window, "_main_thread_dispatcher", None)
        if dispatcher is None or os.environ.get("CBCS_TEAM_SYNC_SHOTS"):
            self._handle_event(event)
            return
        dispatcher.dispatch(lambda event=event: self._handle_event(event))

    def _handle_event(self, event: str) -> None:
        if event.startswith(EVENT_TOAST_PREFIX):
            self._toast(event[len(EVENT_TOAST_PREFIX) :])
            return
        if event in (EVENT_STATUS, EVENT_FEED, EVENT_INCOMING, EVENT_COMBINE, EVENT_HISTORY):
            self.refresh_status()
            self._run("team-sync-feed", lambda: self._service.feed(), self._apply_feed)  # type: ignore[attr-defined]
            self._run("team-sync-incoming", lambda: self._service.incoming(), self._apply_incoming)  # type: ignore[attr-defined]

    def _apply_status(self, status: object) -> None:
        if not isinstance(status, TeamStatus):
            return
        self._status = status
        tokens = self._tokens
        view = status_view(status, waiting_name=self._waiting_name())
        if self._segment is not None:
            self._segment.apply(view, tokens)
        if self._experiment is not None:
            self._experiment.apply(status, tokens)
        if self._send_button is not None:
            self._send_button.apply_status(status)
        if self._team_view is not None:
            self._team_view.apply(status, self._feed, git_names=self._settings.git_names, dormant=self._dormant, tidy=self._settings.tidy_before_send)
        activity = getattr(self._window, "_activity_bar", None)
        if activity is not None:
            activity.set_badge("team", badge_count(status))
        self._letters.replace(
            explorer_letters(status, self._incoming_paths(), self._clash_paths())
        )
        tree = getattr(self._window, "_project_tree_widget", None)
        if tree is not None:
            tree.viewport().update()
        self._refresh_notices()
        self._ensure_poll()

    def _apply_feed(self, feed: object) -> None:
        self._feed = list(feed or [])
        if self._team_view is not None:
            self._team_view.apply(
                self._status,
                self._feed,
                git_names=self._settings.git_names,
                dormant=self._dormant,
                tidy=self._settings.tidy_before_send,
            )

    def _apply_incoming(self, incoming: object) -> None:
        self._incoming = list(incoming or [])
        self._letters.replace(explorer_letters(self._status, self._incoming_paths(), self._clash_paths()))
        self._refresh_notices()

    def _show_popover(self, history_rows: object, incoming: object) -> None:
        if self._popover is None or self._segment is None:
            return
        rows = list(history_rows or [])
        self._incoming = list(incoming or [])
        self._popover.present(
            self._segment,
            self._status,
            rows[0] if rows else None,
            waiting_rows(self._incoming),
            git_names=self._settings.git_names,
            on_history=self.open_history,
            on_members=self.open_members,
            on_save_usb=self.save_to_usb,
            on_open_usb=self.open_from_usb,
            on_review=self.open_review,
        )

    def _ensure_review(self) -> ReviewTab:
        if self._review is None:
            self._review = ReviewTab(self._window)
            if self._tokens is not None:
                self._review.apply_theme(self._tokens)
        return self._review

    def _ensure_combine(self) -> CombineTab:
        if self._combine is None:
            self._combine = CombineTab(self._window)
        return self._combine

    def _ensure_history(self) -> HistoryTab:
        if self._history is None:
            self._history = HistoryTab(self._window)
        return self._history

    def _open_combine(self, state: object) -> None:
        if not isinstance(state, CombineState):
            return
        tab = self._ensure_combine()
        tab.open_state(
            self._service,
            self._ports,
            on_finished=lambda: self._toast("Combined"),
            on_deleted=self._deleted_dialog,
            tokens=self._tokens,
        )
        self._show_tab(tab, "Combine")

    def _deleted_dialog(self, clash: Clash) -> None:
        show_deleted(
            clash.path,
            lambda resolution: self._combine.settle(clash.id, resolution) if self._combine is not None else None,
            self._window,
        )

    def _accepted(self, incoming_id: str) -> None:
        del incoming_id
        self._toast("You accepted the change")
        self.refresh_status()

    def _send(self, note: str, paths: list[str]) -> None:
        self._run("team-sync-send", lambda: self._service.send(note, paths or None), lambda _change: None)  # type: ignore[attr-defined]

    def _save_only(self, note: str, paths: list[str]) -> None:
        self._run("team-sync-save", lambda: self._service.save_only(note, paths or None), lambda _change: None)  # type: ignore[attr-defined]

    def _set_aside(self, name: str) -> None:
        self._run_void(lambda: self._service.set_aside(name))  # type: ignore[attr-defined]

    def _bring_back(self, index: int) -> None:
        self._run(
            "team-sync-bring-back",
            lambda: self._service.bring_back(index),  # type: ignore[attr-defined]
            lambda state: self._open_combine(state) if isinstance(state, CombineState) else None,
        )

    def _bring_experiment(self, line: str) -> None:
        self._run(
            "team-sync-bring-exp",
            lambda: self._service.bring_experiment_in(line),  # type: ignore[attr-defined]
            lambda state: self._open_combine(state) if isinstance(state, CombineState) else None,
        )

    def _new_experiment(self) -> None:
        name, ok = QInputDialog.getText(self._window, "New Experiment", "Name")
        if ok and name.strip():
            self._run_void(lambda: self._service.start_experiment(name.strip()))  # type: ignore[attr-defined]

    def _history_action(self, key: str, change: Change) -> None:
        if key == "compare_current":
            self.open_history()
            return
        if key == "restore":
            self._run_void(lambda: self._service.restore(change.id))  # type: ignore[attr-defined]
        elif key == "undo":
            self._run(
                "team-sync-undo",
                lambda: self._service.undo_change(change.id),  # type: ignore[attr-defined]
                lambda state: self._open_combine(state) if isinstance(state, CombineState) else None,
            )
        elif key == "experiment":
            self._run_void(lambda: self._service.start_experiment("from here", change.id))  # type: ignore[attr-defined]
        elif key == "milestone":
            version, ok = QInputDialog.getText(self._window, "Milestone", "Version")
            if ok and version.strip():
                self._run_void(lambda: self._service.mark_milestone(change.id, version.strip()))  # type: ignore[attr-defined]
        elif key == "copy_id":
            self._window.clipboard_set(change.id) if hasattr(self._window, "clipboard_set") else self._copy(change.id)
        elif key == "copy_experiment" and self._settings.copy_into_experiment:
            self._run_void(lambda: self._service.start_experiment(change.id[:8], change.id))  # type: ignore[attr-defined]
        elif key == "bisect" and self._settings.find_broke:
            self._toast(change.note)

    def _copy(self, text: str) -> None:
        from app.qt.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def _open_change(self, change_id: str) -> None:
        del change_id
        self.open_history()

    def _show_file(self, relative_path: str) -> None:
        root = self._project_root
        if not root:
            return
        target = str(Path(root) / relative_path)
        opener = getattr(self._window, "_editor_tab_factory", None)
        if opener is not None:
            opener.open_file_in_editor(target)

    def _toast(self, text: str) -> None:
        anchor = getattr(self._window, "_editor_tabs_widget", None) or self._window
        toast = show_toast(
            anchor,
            text,
            action_label="Review",
            on_action=self.open_review,
            tokens=self._tokens,
        )
        toast.setObjectName("shell.teamSync.toast")

    def _refresh_notices(self) -> None:
        tabs = getattr(self._window, "_editor_tabs_widget", None)
        manager = getattr(self._window, "_editor_manager", None)
        if tabs is None or manager is None:
            return
        incoming_paths = self._incoming_paths()
        clash_paths = self._clash_paths()
        for index in range(tabs.count()):
            page = tabs.widget(index)
            if not hasattr(page, "buffer_id") or not hasattr(page, "add_notice_bar"):
                continue
            tab = manager.get_tab_by_id(page.buffer_id)
            if tab is None:
                continue
            relative = self._relative(tab.file_path)
            bar = page.findChild(TeamInfoBar, "shell.teamSync.infoBar")
            if bar is None:
                bar = TeamInfoBar(page)
                if self._tokens is not None:
                    bar.apply_theme(self._tokens)
                page.add_notice_bar(bar)
            if relative in clash_paths and self._status.combine is not None:
                count = sum(1 for clash in self._status.combine.clashes if clash.path == relative and clash.resolution is None)
                bar.show_clash(
                    f"{count} line in {relative} needs your choice",
                    self._cancel_combine,
                    lambda: self._open_combine(self._status.combine),
                )
            elif relative in incoming_paths:
                author = self._incoming_author(relative)
                bar.show_incoming(author[0], author[1], f"{first_name(author[1])} changed this file", self.open_review)
            else:
                bar.clear()

    def _hover(self, relative: str, line: int, pos: object) -> None:
        blame_line = self._blame.get(relative, {}).get(line)
        if blame_line is None:
            return
        if self._card is None:
            self._card = BlameCard(self._window)
            if self._tokens is not None:
                self._card.apply_theme(self._tokens)
        shop = ""
        for member in self._status.members:
            if member.id == blame_line.author_id:  # type: ignore[attr-defined]
                shop = member.shop
        self._card.show_line(
            blame_line,  # type: ignore[arg-type]
            shop,
            blame_line.note,  # type: ignore[attr-defined]
            pos,  # type: ignore[arg-type]
            on_open=lambda: self._open_change(blame_line.change_id),  # type: ignore[attr-defined]
            on_history=lambda: self.open_history(relative),
        )

    def _place_summary(self, editor: QWidget, relative: str, summary: LineSummary) -> None:
        if not self._settings.line_summary:
            summary.hide()
            return
        cursor = editor.textCursor()  # type: ignore[attr-defined]
        line = cursor.blockNumber() + 1
        blame_line = self._blame.get(relative, {}).get(line)
        if blame_line is None:
            summary.hide()
            return
        text = f"{first_name(blame_line.author_name)} · {blame_line.note}"  # type: ignore[attr-defined]
        rect = editor.cursorRect()  # type: ignore[attr-defined]
        summary.show_text(text, rect.right() + 12, rect.top())

    def _apply_marks(self, editor: QWidget, diff: object) -> None:
        if not hasattr(editor, "set_change_marks"):
            return
        lines = set()
        for hunk in getattr(diff, "hunks", ()):
            for offset, _line in enumerate(hunk.new_lines):
                lines.add(hunk.new_start + offset)
        editor.set_change_marks(lines, lambda line, editor=editor, diff=diff: self._peek_at(editor, diff, line))

    def _peek_at(self, editor: QWidget, diff: object, line: int) -> None:
        if self._peek is None:
            parent = editor.viewport() if hasattr(editor, "viewport") else editor
            self._peek = GutterPeek(parent)
            if self._tokens is not None:
                self._peek.apply_theme(self._tokens)
        old_line = ""
        new_line = ""
        for hunk in getattr(diff, "hunks", ()):
            if hunk.new_start <= line < hunk.new_start + len(hunk.new_lines):
                index = line - hunk.new_start
                new_line = hunk.new_lines[index] if index < len(hunk.new_lines) else ""
                old_line = hunk.old_lines[index] if index < len(hunk.old_lines) else ""
        block = editor.cursorRect()  # type: ignore[attr-defined]
        self._peek.show_change(old_line, new_line, 48, block.bottom() + 4, lambda: self._undo_line(editor, line, old_line))

    def _undo_line(self, editor: QWidget, line: int, old_line: str) -> None:
        document = editor.document()  # type: ignore[attr-defined]
        block = document.findBlockByNumber(line - 1)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        cursor.select(QTextCursor.LineUnderCursor)
        cursor.insertText(old_line)
        if self._peek is not None:
            self._peek.hide()

    def _store_blame(self, relative: str, rows: object) -> None:
        self._blame[relative] = {row.line: row for row in list(rows or [])}

    def _poll_once(self) -> None:
        if not self._project_root or not self._status.shared:
            return
        self._run_void(lambda: self._service.poll())  # type: ignore[attr-defined]

    def _ensure_poll(self) -> None:
        if self._status.shared and self._project_root and not self._poll.isActive():
            self._poll.start()
        if not self._status.shared and self._poll.isActive():
            self._poll.stop()

    def _settings_changed(self, settings: TeamUiSettings) -> None:
        self._settings = settings
        self._apply_status(self._status)

    def _cancel_combine(self) -> None:
        self._run_void(lambda: self._service.cancel_combine())  # type: ignore[attr-defined]

    def _show_tab(self, widget: QWidget, title: str) -> None:
        tabs = getattr(self._window, "_editor_tabs_widget", None)
        if tabs is None:
            widget.show()
            return
        index = tabs.indexOf(widget)
        if index < 0:
            index = tabs.addTab(widget, title)
            tabs.tabBar().setTabData(index, {"virtual_tab": True})
        tabs.setCurrentIndex(index)

    def _incoming_by_id(self, incoming_id: str) -> Optional[Incoming]:
        for item in self._incoming:
            if item.id == incoming_id:
                return item
        return None

    def _incoming_paths(self) -> set[str]:
        paths: set[str] = set()
        for item in self._incoming:
            for change in item.changes:
                for file_change in change.files:
                    paths.add(file_change.path)
        return paths

    def _clash_paths(self) -> set[str]:
        if self._status.combine is None:
            return set()
        return {clash.path for clash in self._status.combine.clashes if clash.resolution is None}

    def _incoming_author(self, relative: str) -> tuple[str, str]:
        for item in self._incoming:
            for change in item.changes:
                if any(file_change.path == relative for file_change in change.files):
                    return (item.from_id, change.author_name)
        return ("", "Someone")

    def _waiting_name(self) -> str:
        if not self._incoming or not self._incoming[0].changes:
            return ""
        return first_name(self._incoming[0].changes[0].author_name)

    def _relative(self, path: str) -> str:
        root = self._project_root
        if root:
            try:
                return str(Path(path).resolve().relative_to(Path(root).resolve()))
            except ValueError:
                pass
        return Path(path).name

    def _current_tokens(self) -> Optional[ShellThemeTokens]:
        workflow = getattr(self._window, "_shell_theme_workflow", None)
        if workflow is None:
            return None
        tokens = workflow.resolve_theme_tokens()
        return tokens if isinstance(tokens, ShellThemeTokens) else None

    def _run(self, key: str, fn: Callable[[], object], on_success: Callable[[object], None]) -> None:
        self._ports.run(key, fn, on_success, self._on_error)  # type: ignore[attr-defined]

    def _run_void(self, fn: Callable[[], object]) -> None:
        self._run("team-sync", fn, lambda _result: self.refresh_status())

    def _on_error(self, exc: Exception) -> None:
        logger = getattr(self._window, "_logger", None)
        if logger is not None:
            logger.warning("Team Sync: %s", exc)


__all__ = ["TeamSyncController"]
