"""UI entry points stay off the GUI thread, and the shop-day panes show the right text."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.features.team_sync.api import (
    DELIVERY_WAITING_TERMINAL,
    FEED_CHANGE,
    Change,
    CombineState,
    Delivery,
    FeedItem,
    FileChange,
    FileDiff,
    Incoming,
    TeamStatus,
)
from app.features.team_sync.core.fake import InMemoryTeamSync
from app.features.team_sync.ui.controller import TeamSyncController
from app.features.team_sync.ui.dialogs import InviteDialog, ShareDialog
from app.features.team_sync.ui.ports import SchedulerPorts, SyncPorts
from app.features.team_sync.ui.review_tab import ReviewTab
from app.features.team_sync.ui.send_sheet import SendSheet, SendToolbarButton
from app.features.team_sync.ui.status_segment import StatusPopover
from app.features.team_sync.ui.team_view import TeamView
from app.qt.QtCore import QTimer
from app.qt.QtWidgets import QLineEdit, QPlainTextEdit, QStatusBar, QWidget
from app.shell.background_tasks import GeneralTaskScheduler
from app.shell.diff_view import DIFF_VIEW_MODE_SIDE_BY_SIDE
from app.shell.theme_tokens import tokens_from_palette


class _Recording:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _touch(self, name: str) -> None:
        self.calls.append(f"{name}:{threading.current_thread().name}")

    def subscribe(self, _callback: object) -> object:
        return lambda: None

    def status(self) -> TeamStatus:
        self._touch("status")
        return TeamStatus(shared=True, project_name="Invoice", pending=(FileChange("invoice.py", "M"),))

    def feed(self, limit: int = 200) -> list:
        del limit
        self._touch("feed")
        return []

    def incoming(self) -> list:
        self._touch("incoming")
        return []

    def history(self, **_kwargs: object) -> list:
        self._touch("history")
        return []

    def incoming_diff(self, _incoming_id: str) -> list:
        self._touch("incoming_diff")
        return []

    def combine_state(self) -> None:
        self._touch("combine_state")
        return None

    def blame(self, _path: str) -> list:
        self._touch("blame")
        return []

    def working_diff(self, path: str) -> FileDiff:
        self._touch("working_diff")
        return FileDiff(path, "M")

    def mailboxes(self) -> list:
        self._touch("mailboxes")
        return []

    def send(self, note: str, paths: object = None) -> Change:
        del note, paths
        self._touch("send")
        return _change()

    def save_only(self, note: str, paths: object = None) -> Change:
        del note, paths
        self._touch("save_only")
        return _change()


def _change() -> Change:
    return Change(
        id="a" * 40,
        parents=(),
        author_id="a1b2c3d4",
        author_name="Ana Kurtz",
        when=datetime(2026, 11, 2, tzinfo=timezone.utc),
        note="tax",
    )


def _pump(app: QWidget, ready) -> None:  # type: ignore[no-untyped-def]
    for _index in range(200):
        app.processEvents()
        if ready():
            return
        threading.Event().wait(0.01)
    raise AssertionError("background team sync work did not finish")


def test_ui_entry_points_call_the_engine_off_the_gui_thread(qapp) -> None:  # type: ignore[no-untyped-def]
    service = _Recording()
    scheduler = GeneralTaskScheduler(dispatch_to_main_thread=lambda fn: QTimer.singleShot(0, fn))
    window = QWidget()
    controller = TeamSyncController(window, service, SchedulerPorts(scheduler), dormant=False, fake=True)
    controller.refresh_status()
    controller.open_history()
    incoming = Incoming(
        id="b_0123456789abcdef",
        from_id="a1b2c3d4",
        changes=(_change(),),
        arrived=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )
    controller._incoming = [incoming]
    controller.open_review(incoming.id)
    controller._open_combine(CombineState(id="c1", theirs_from="a1b2c3d4", note="tax"))
    editor = QPlainTextEdit()

    class _Page:
        def content(self) -> QPlainTextEdit:
            return editor

    controller._project_root = "/tmp/invoice"
    controller.attach_editor_page(_Page(), "/tmp/invoice/invoice.py")
    before = len(service.calls)
    controller.letters.lookup("invoice.py")
    assert len(service.calls) == before

    def ready() -> bool:
        names = {item.split(":", 1)[0] for item in service.calls}
        return {"status", "history", "incoming_diff", "combine_state", "blame", "working_diff"} <= names

    _pump(qapp, ready)
    main = threading.main_thread().name
    engine = [item for item in service.calls if not item.startswith("subscribe")]
    assert engine
    assert all(item.split(":", 1)[1] != main for item in engine)
    scheduler.shutdown(wait=True)


def test_modified_file_shows_both_sides(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    from app.features.team_sync.core.service import TeamSyncService
    from tests.unit.features.team_sync.conftest import machine

    root = tmp_path / "proj"
    root.mkdir()
    (root / "invoice.py").write_text("def total(x):\n    return x\n", encoding="utf-8")
    sam = TeamSyncService(str(root), machine=machine(tmp_path / "box", "pc"), mail_roots=[])
    from app.features.team_sync.api import ShareRequest

    sam.share(ShareRequest(project_name="Invoice", my_name="Sam Brenneman", my_shop="Maple Ridge"))
    (root / "invoice.py").write_text("def total(x):\n    return x + 1\n", encoding="utf-8")
    diff = sam.working_diff("invoice.py")
    tab = ReviewTab()
    tab._paint_diff(diff)
    tab._diff.set_mode(DIFF_VIEW_MODE_SIDE_BY_SIDE)
    before = tab.findChild(QPlainTextEdit, "shell.diffView.beforePane")
    after = tab.findChild(QPlainTextEdit, "shell.diffView.afterPane")
    assert before is not None and after is not None
    assert "+ 1" not in before.toPlainText()
    assert "return x" in before.toPlainText()
    assert "x + 1" in after.toPlainText()


def test_share_and_invite_dialogs_use_person_names(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    status = TeamStatus(shared=False, project_name="Invoice")
    share = ShareDialog(status, "1 file", lambda *_args: None, my_name="Sam Brenneman", my_shop="Maple Ridge")
    assert share.findChild(QLineEdit, "shell.teamSync.shareMyName").text() == "Sam Brenneman"
    assert share.findChild(QLineEdit, "shell.teamSync.shareMyShop").text() == "Maple Ridge"
    captured: list[tuple] = []
    incoming = Incoming(
        id="b_0123456789abcdef",
        from_id="e5f6a7b8",
        changes=(_change(),),
        arrived=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )
    invite = InviteDialog(
        incoming,
        lambda *args: captured.append(args),
        your_name="Ana Kurtz",
        your_shop="Cedar Hollow",
    )
    invite._location.setText(str(tmp_path / "empty"))
    invite._open()
    assert captured[0][2] == "Ana Kurtz"
    assert captured[0][3] == "Cedar Hollow"


def test_send_and_save_clear_the_note(qapp) -> None:  # type: ignore[no-untyped-def]
    window = QWidget()
    window._status_controller = SimpleNamespace(status_bar=QStatusBar(window))
    service = InMemoryTeamSync()
    service.scenario("pending")
    view = TeamView()
    button = SendToolbarButton()
    controller = TeamSyncController(window, service, SyncPorts(), dormant=False, fake=True)
    controller.attach(view, button)
    view._note.setText("tax line")
    controller._send("tax line", ["invoice.py"])
    assert view.note_text() == ""
    assert view.selected_paths() == []
    sheet = SendSheet()
    controller._send_sheet = sheet
    sheet._note.setPlainText("saved")
    view._note.setText("saved")
    controller._save_only("saved", ["invoice.py"])
    assert view.note_text() == ""
    assert sheet._note.toPlainText() == ""
    del qapp


def test_waiting_badge_uses_the_warning_delivery(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    view = TeamView()
    status = TeamStatus(shared=True, project_name="Invoice")
    item = FeedItem(
        kind=FEED_CHANGE,
        id="c1",
        when=datetime(2026, 11, 2, tzinfo=timezone.utc),
        text="tax",
        change=_change(),
        delivery=Delivery(change_id="a" * 40, to="a1b2c3d4", state=DELIVERY_WAITING_TERMINAL),
    )
    view.apply(status, [item], git_names=False, dormant=False, tidy=False)
    badge = view.findChild(QWidget, "shell.teamSync.feedMark")
    assert badge is not None
    assert badge.text() == "Waiting"
    assert badge.property("delivery") == "waiting"


def test_status_popover_is_an_opaque_popup(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    popover = StatusPopover()
    tokens = tokens_from_palette(popover.palette(), force_mode=None)
    popover.apply_theme(tokens)
    sheet = popover.styleSheet()
    assert popover.autoFillBackground() is True
    assert tokens.popup_bg in sheet
    assert tokens.popup_border in sheet
