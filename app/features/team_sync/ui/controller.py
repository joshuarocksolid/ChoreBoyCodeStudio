"""Connects Team Sync widgets to TeamSyncApi. Service calls leave the UI thread."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

from app.qt.QtCore import QObject, QPoint, QTimer, Qt
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
    ShareRequest,
    TeamStatus,
)
from app.features.team_sync.ui.blame import BlameCard, LineSummary
from app.features.team_sync.ui.combine_tab import CombineTab
from app.features.team_sync.core import TeamSyncError
from app.features.team_sync.core.local_state import remember_decision, suppressed_invite_ids
from app.features.team_sync.ui.copy import (
    badge_count,
    deleted_clash_copy,
    explorer_letters,
    first_name,
    status_view,
)
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

_BUSY = "Finish or cancel combining first."


class TeamSyncController(QObject):
    """Holds the latest snapshot and tells each surface what changed."""

    def __init__(
        self,
        window: QWidget,
        service: object,
        ports: object,
        *,
        dormant: bool,
        fake: bool = False,
        watch_invites: bool = False,
        project_factory: Optional[Callable[[str], object]] = None,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._service = service
        self._ports = ports
        self._dormant = dormant
        self._fake = fake
        self._watch_invites = watch_invites
        self._project_factory = project_factory
        self._invite_service: object = None
        self._invite_source: object = None
        self._seen_invites: set[str] = set()
        self._settings = TeamUiSettings()
        self._letters = ExplorerLetterCache()
        self._status = TeamStatus(shared=False, project_name="")
        self._feed: list = []
        self._incoming: list[Incoming] = []
        self._project_root = ""
        self._unsubscribe: Optional[Callable[[], None]] = None
        self._tokens: Optional[ShellThemeTokens] = None
        self._blame: dict[str, dict[int, object]] = {}
        self._blame_paths: set[str] = set()
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
        self._summaries: dict[int, LineSummary] = {}
        self._info_bars: list[TeamInfoBar] = []
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.refresh_status)
        self._poll = QTimer(self)
        self._poll.setInterval(30_000)
        self._poll.timeout.connect(self._poll_once)
        self._invite_timer = QTimer(self)
        self._invite_timer.setInterval(30_000)
        self._invite_timer.timeout.connect(self._poll_invites)
        unsubscribe = service.subscribe(self._on_service_event)  # type: ignore[attr-defined]
        self._unsubscribe = unsubscribe
        if watch_invites and not os.environ.get("CBCS_DISABLE_BACKGROUND_RUNTIME"):
            self._invite_timer.start()
            QTimer.singleShot(0, self._poll_invites)

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
        for summary in self._summaries.values():
            summary.apply_theme(tokens)
        for bar in list(self._info_bars):
            bar.apply_theme(tokens)

    def on_project_opened(self, project_root: str, project_name: str) -> None:
        del project_name
        if self._fake or self._project_factory is None:
            self._project_root = project_root
            self.request_status()
            if not self._fake:
                self._poll_after_open()
            return
        if not project_root:
            self.close_project()
            return
        if project_root == self._project_root and not isinstance(self._service, IdleTeamSync):
            self.request_status()
            self._poll_after_open()
            return
        self.use_service(self._project_factory(project_root), project_root)

    def use_service(self, service: object, project_root: str) -> None:
        """Point the open project at one engine. The previous engine is dropped."""
        self._drop_service()
        self._service = service
        self._project_root = project_root
        self._unsubscribe = service.subscribe(self._on_service_event)  # type: ignore[attr-defined]
        self.refresh_status()
        self._run("team-sync-feed", lambda: self._service.feed(), self._apply_feed)  # type: ignore[attr-defined]
        self._run("team-sync-incoming", lambda: self._service.incoming(), self._apply_incoming)  # type: ignore[attr-defined]
        self._poll_after_open()

    def close_project(self) -> None:
        self._drop_service()
        self._project_root = ""
        self._poll.stop()
        self._service = IdleTeamSync()
        self._unsubscribe = self._service.subscribe(self._on_service_event)
        self._apply_status(TeamStatus(shared=False, project_name=""))

    def _drop_service(self) -> None:
        # Blame belongs to the old project's files.
        self._blame.clear()
        self._blame_paths.clear()
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        if self._fake:
            return
        closer = getattr(self._service, "close", None)
        if callable(closer):
            closer()

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
        remembered_name, remembered_shop = self._remembered_identity()

        def task() -> object:
            boxes = list(self._service.mailboxes())  # type: ignore[attr-defined]
            summary = getattr(self._service, "share_summary", None)
            chip = ""
            if callable(summary):
                result = summary()
                if isinstance(result, tuple) and len(result) == 2:
                    chip = f"{result[0]} files · {result[1]}"
            return (boxes, chip)

        def show(payload: object) -> None:
            boxes, chip = payload if isinstance(payload, tuple) else ([], "")
            name = remembered_name
            shop = remembered_shop
            if boxes:
                name = name or str(getattr(boxes[0], "user_name", "") or "")
                shop = shop or str(getattr(boxes[0], "company_name", "") or "")
            if not chip:
                chip = f"{len(self._status.pending)} files"
            show_share(
                self._status,
                str(chip),
                self.submit_share,
                self._window,
                self._tokens,
                my_name=name,
                my_shop=shop,
            )

        self._run("team-sync-share-defaults", task, show)

    def submit_share(self, request: object, on_ok: Optional[Callable[[], None]] = None, on_err: Optional[Callable[[BaseException], None]] = None) -> None:
        def done(_result: object) -> None:
            if isinstance(request, ShareRequest):
                self._remember_identity(request.my_name, request.my_shop)
            activity = getattr(self._window, "_activity_bar", None)
            if activity is not None and hasattr(activity, "set_active_view"):
                activity.set_active_view("team")
            self.refresh_status()
            self._run("team-sync-feed", lambda: self._service.feed(), self._apply_feed)  # type: ignore[attr-defined]
            if on_ok is not None:
                on_ok()

        self._ports.run(  # type: ignore[attr-defined]
            "team-sync-share",
            lambda: self._service.share(request),  # type: ignore[attr-defined]
            done,
            lambda exc: self._route_error(exc, on_err),
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
            menu.addAction(
                "Share with Team…",
                lambda line=current: self._run(
                    "team-sync-share-exp",
                    lambda: self._service.share_experiment(line),  # type: ignore[attr-defined]
                    lambda _change: self.refresh_status(),
                ),
            )
            menu.addAction(
                "Delete Experiment…",
                lambda: self._run_void(lambda: self._service.delete_experiment(current), key="team-sync-delete-exp"),  # type: ignore[attr-defined]
            )
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
        service = self._service
        if isinstance(service, IdleTeamSync) or not self._project_root:
            watched = self._ensure_invite_service()
            if watched is not None:
                service = watched
        self._invite_source = service

        def task() -> object:
            invites = service.pending_invites()  # type: ignore[attr-defined]
            if not invites:
                return None
            detail: dict[str, str] = {}
            reader = getattr(service, "invite_detail", None)
            if callable(reader):
                try:
                    loaded = reader(invites[0].id)
                except TeamSyncError:
                    loaded = {}
                if isinstance(loaded, dict):
                    detail = {str(key): str(value) for key, value in loaded.items()}
            return (invites[0], detail)

        self._run("team-sync-pending-invites", task, self._present_invite_payload)

    def submit_accept_invite(
        self,
        incoming_id: str,
        folder: str,
        my_name: str = "",
        my_shop: str = "",
        on_ok: Optional[Callable[[], None]] = None,
        on_err: Optional[Callable[[BaseException], None]] = None,
    ) -> None:
        def done(path: object) -> None:
            opened = str(path or folder or "")
            opener = getattr(self._window, "_file_project_commands_workflow", None)
            if opened and opened != self._project_root and not self._fake:
                if opener is not None and hasattr(opener, "open_project_by_path"):
                    opener.open_project_by_path(opened)
                elif self._project_factory is not None:
                    self.use_service(self._project_factory(opened), opened)
                else:
                    self._project_root = opened
                    self.refresh_status()
            else:
                self.refresh_status()
                self._run("team-sync-feed", lambda: self._service.feed(), self._apply_feed)  # type: ignore[attr-defined]
            if on_ok is not None:
                on_ok()

        service = self._invite_source or self._service
        self._ports.run(  # type: ignore[attr-defined]
            "team-sync-invite",
            lambda: service.accept_invite(  # type: ignore[attr-defined]
                incoming_id,
                folder or self._project_root or ".",
                my_name,
                my_shop,
            ),
            done,
            lambda exc: self._route_error(exc, on_err),
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
            editor.set_line_hover_callback(
                lambda line, pos, local, rel=relative, editor=editor: self._hover(editor, rel, line, pos, local)
            )
        if hasattr(editor, "cursorPositionChanged"):
            summary = LineSummary(editor.viewport())
            self._summaries[id(editor)] = summary
            if self._tokens is not None:
                summary.apply_theme(self._tokens)
            editor.cursorPositionChanged.connect(lambda rel=relative, summary=summary: self._place_summary(editor, rel, summary))
        self._blame_paths.add(relative)
        self._load_blame(relative)
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
        status_bar.insertPermanentWidget(1, self._segment, 0)
        status_bar.insertPermanentWidget(2, self._experiment, 0)

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
        if event == EVENT_HISTORY:
            # A new change can move who last changed any line of an open file.
            for relative in sorted(self._blame_paths):
                self._load_blame(relative)
        if event in (EVENT_STATUS, EVENT_FEED, EVENT_INCOMING, EVENT_COMBINE, EVENT_HISTORY):
            self.refresh_status()
            self._run("team-sync-feed", lambda: self._service.feed(), self._apply_feed)  # type: ignore[attr-defined]
            self._run("team-sync-incoming", lambda: self._service.incoming(), self._apply_incoming)  # type: ignore[attr-defined]

    def _apply_status(self, status: object) -> None:
        if not isinstance(status, TeamStatus):
            return
        self._status = status
        if status.combine is None:
            self._close_combine_tab()
        tokens = self._tokens
        view = status_view(status, waiting_name=self._waiting_name())
        if self._segment is not None:
            self._segment.apply(view, tokens)
        if self._experiment is not None:
            self._experiment.apply(status, tokens)
        if self._send_button is not None:
            self._send_button.apply_status(status)
            busy = status.combine is not None and not status.combine.done
            self._send_button.setEnabled(status.shared and not busy)
        if self._review is not None:
            busy = status.combine is not None and not status.combine.done
            self._review._accept.setEnabled(not busy)
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
        theirs_label, theirs_id = self._theirs_identity(state)
        mine = self._status.me
        theirs_name = ""
        for member in self._status.members:
            if member.id == state.theirs_from:
                theirs_name = member.name
        tab.open_state(
            self._service,
            self._ports,
            on_finished=lambda: self._toast("Combined"),
            on_deleted=self._deleted_dialog,
            tokens=self._tokens,
            theirs_label=theirs_label,
            theirs_id=theirs_id,
            theirs_name=theirs_name,
            mine_name=mine.name if mine is not None else "You",
            mine_id=mine.id if mine is not None else "",
        )
        self._show_tab(tab, "Combine")

    def _deleted_dialog(self, clash: Clash) -> None:
        theirs_name = "Someone"
        if self._status.combine is not None:
            for member in self._status.members:
                if member.id == self._status.combine.theirs_from:
                    theirs_name = member.name
        title, chip = deleted_clash_copy(clash.path, clash, theirs_name)
        show_deleted(
            title,
            chip,
            lambda resolution: self._combine.settle(clash.id, resolution) if self._combine is not None else None,
            self._window,
        )

    def _accepted(self, incoming_id: str) -> None:
        del incoming_id
        self._toast("You accepted the change")
        self.refresh_status()

    def _send(self, note: str, paths: list[str]) -> None:
        self._run("team-sync-send", lambda: self._service.send(note, paths or None), lambda _change: self._clear_draft())  # type: ignore[attr-defined]

    def _save_only(self, note: str, paths: list[str]) -> None:
        self._run("team-sync-save", lambda: self._service.save_only(note, paths or None), lambda _change: self._clear_draft())  # type: ignore[attr-defined]

    def _clear_draft(self) -> None:
        if self._team_view is not None:
            self._team_view.clear_draft()
        if self._send_sheet is not None:
            self._send_sheet.clear_draft()

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
            object_name="shell.teamSync.toast",
            timeout_ms=6000,
            word_wrap=False,
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
                self._info_bars.append(bar)
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

    def _hover(self, editor: QWidget, relative: str, line: int, pos: object, local: QPoint) -> bool:
        if not self._pointer_on_team_chrome(editor, line, local):
            if self._card is not None:
                self._card.hide()
            return False
        blame_line = self._blame.get(relative, {}).get(line)
        if blame_line is None:
            if self._card is not None:
                self._card.hide()
            return True
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
            "",
            pos,  # type: ignore[arg-type]
            on_open=lambda: self._open_change(blame_line.change_id),  # type: ignore[attr-defined]
            on_history=lambda: self.open_history(relative),
        )
        return True

    def _pointer_on_team_chrome(self, editor: QWidget, line: int, local: QPoint) -> bool:
        gutter = editor.line_number_area_width() if hasattr(editor, "line_number_area_width") else 0
        if local.x() < gutter:
            return True
        summary = self._summaries.get(id(editor))
        if summary is None or not summary.isVisible() or not hasattr(editor, "textCursor"):
            return False
        if editor.textCursor().blockNumber() + 1 != line:  # type: ignore[attr-defined]
            return False
        viewport = editor.viewport() if hasattr(editor, "viewport") else None
        if viewport is None:
            return False
        return summary.geometry().contains(viewport.mapFrom(editor, local))

    def _theirs_identity(self, state: CombineState) -> tuple[str, str]:
        for member in self._status.members:
            if member.id == state.theirs_from:
                return (f"{first_name(member.name)}'s", member.id)
        label = state.theirs_from
        if label.startswith("exp/"):
            label = label[4:]
        return (f"{label}'s" if label else "Theirs", state.theirs_from)

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

    def _load_blame(self, relative: str) -> None:
        # One key per file: a second editor must not cancel the first file's blame.
        self._run(
            f"team-sync-blame:{relative}",
            lambda: self._service.blame(relative),  # type: ignore[attr-defined]
            lambda rows, rel=relative: self._store_blame(rel, rows),
        )

    def _store_blame(self, relative: str, rows: object) -> None:
        self._blame[relative] = {row.line: row for row in list(rows or [])}

    def _poll_once(self) -> None:
        if not self._project_root or not self._status.shared:
            self._poll_invites()
            return
        self._run("team-sync-poll", lambda: self._service.poll(), lambda _result: self.refresh_status())  # type: ignore[attr-defined]

    def _poll_after_open(self) -> None:
        if not self._project_root or self._dormant:
            return
        self._run("team-sync-poll", lambda: self._service.poll(), lambda _result: self.refresh_status())  # type: ignore[attr-defined]

    def _poll_invites(self) -> None:
        if self._fake or not self._watch_invites:
            return
        if self._project_root and self._status.shared:
            return
        service = self._ensure_invite_service()
        if service is None:
            return
        self._load_seen(service)
        seen = set(self._seen_invites)

        def task() -> object:
            service.poll()  # type: ignore[attr-defined]
            invites = list(service.pending_invites())  # type: ignore[attr-defined]
            fresh = [item for item in invites if str(getattr(item, "id", "")) not in seen]
            if not fresh:
                return None
            detail: dict[str, str] = {}
            reader = getattr(service, "invite_detail", None)
            if callable(reader):
                try:
                    loaded = reader(fresh[0].id)
                except TeamSyncError:
                    loaded = {}
                if isinstance(loaded, dict):
                    detail = {str(key): str(value) for key, value in loaded.items()}
            return (fresh[0], detail)

        def done(payload: object) -> None:
            if not isinstance(payload, tuple):
                return
            item = payload[0]
            ident = str(getattr(item, "id", ""))
            if not ident or ident in self._seen_invites:
                return
            self._mark_invite(service, ident, "seen")
            self._invite_source = service
            self._present_invite_payload(payload, announce=True)

        self._ports.run("team-sync-invite-poll", task, done, self._on_error)  # type: ignore[attr-defined]

    def _ensure_invite_service(self) -> object:
        if self._invite_service is not None:
            return self._invite_service
        if self._project_factory is None:
            return None
        from app.features.shop_sharing.model import Machine

        machine = Machine.current()
        root = Path(machine.local_state) / "team_sync" / "invite_watch"
        root.mkdir(parents=True, exist_ok=True)
        self._invite_service = self._project_factory(str(root))
        return self._invite_service

    def _present_invite_payload(self, payload: object, announce: bool = False) -> None:
        if not isinstance(payload, tuple) or len(payload) != 2:
            return
        incoming, detail = payload
        if not isinstance(incoming, Incoming):
            return
        info = detail if isinstance(detail, dict) else {}
        project_name = str(info.get("project_name") or "Invoice App")
        safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in project_name).strip() or "Project"
        default_location = str(Path.home() / "Projects" / safe)
        sender = str(info.get("sender_name") or "")
        if sender:
            author = first_name(sender)
        elif incoming.changes:
            author = first_name(incoming.changes[0].author_name)
        else:
            author = "Someone"
        if announce:
            self._toast(f"{author} invited you to {project_name}")
        show_invite(
            incoming,
            self.submit_accept_invite,
            self._window,
            self._tokens,
            project_name=project_name,
            default_location=default_location,
            author_name=sender,
            your_name=str(info.get("invitee_name") or ""),
            your_shop=str(info.get("invitee_shop") or ""),
            on_decline=lambda ident, source=self._invite_source: self._mark_invite(source, ident, "declined"),
        )

    def _remembered_identity(self) -> tuple[str, str]:
        service = getattr(self._window, "_settings_service", None)
        loader = getattr(service, "load_global", None)
        if not callable(loader):
            return "", ""
        payload = loader()
        block = payload.get("team_sync") if isinstance(payload, dict) else None
        if not isinstance(block, dict):
            return "", ""
        return str(block.get("my_name") or ""), str(block.get("my_shop") or "")

    def _remember_identity(self, name: str, shop: str) -> None:
        if not name and not shop:
            return
        service = getattr(self._window, "_settings_service", None)
        updater = getattr(service, "update_global", None)
        if not callable(updater):
            return

        def merge(payload: dict) -> dict:
            updated = dict(payload)
            updated["team_sync"] = {"my_name": name, "my_shop": shop}
            return updated

        updater(merge)

    def _load_seen(self, service: object) -> None:
        machine = getattr(service, "machine", None)
        if machine is None:
            return
        self._seen_invites.update(suppressed_invite_ids(machine))

    def _mark_invite(self, service: object, invite_id: str, decision: str) -> None:
        if not invite_id:
            return
        self._seen_invites.add(invite_id)
        machine = getattr(service, "machine", None)
        if machine is not None:
            remember_decision(machine, invite_id, decision)

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

    def _close_combine_tab(self) -> None:
        # Finish and Cancel both end the session; the tab must not linger on "0 of 0 settled".
        tabs = getattr(self._window, "_editor_tabs_widget", None)
        if tabs is None or self._combine is None:
            return
        index = tabs.indexOf(self._combine)
        if index >= 0:
            tabs.removeTab(index)

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

    def _run_void(self, fn: Callable[[], object], key: str = "team-sync") -> None:
        self._run(key, fn, lambda _result: self.refresh_status())

    def _route_error(self, exc: BaseException, inline: Optional[Callable[[BaseException], None]] = None) -> None:
        if str(exc) == _BUSY:
            self.refresh_status()
            return
        if inline is not None:
            inline(exc)
            return
        if isinstance(exc, TeamSyncError):
            self._toast(str(exc))
            return
        logger = getattr(self._window, "_logger", None)
        if logger is not None:
            logger.warning("Team Sync: %s", exc)

    def _on_error(self, exc: Exception) -> None:
        logger = getattr(self._window, "_logger", None)
        if logger is not None and str(exc) != _BUSY:
            logger.warning("Team Sync: %s", exc)
        self._route_error(exc)


class IdleTeamSync:
    """No project is open. The thread shows Not shared and nothing touches a repo."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[str], None]] = []

    def status(self) -> TeamStatus:
        return TeamStatus(shared=False, project_name="")

    def feed(self, limit: int = 200) -> list:
        del limit
        return []

    def incoming(self) -> list:
        return []

    def pending_invites(self) -> list:
        return []

    def poll(self) -> None:
        return None

    def subscribe(self, callback: Callable[[str], None]) -> Callable[[], None]:
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe

    def close(self) -> None:
        self._subscribers.clear()

    def __getattr__(self, name: str) -> Callable[..., None]:
        def missing(*_args: object, **_kwargs: object) -> None:
            raise TeamSyncError("Open a project first.")

        return missing


__all__ = ["IdleTeamSync", "TeamSyncController"]
