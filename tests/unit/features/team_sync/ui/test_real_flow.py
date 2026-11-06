"""Two projects, one mail tree, the controller the UI calls. No fake."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.features.team_sync.api import RESOLVE_THEIRS, Invite, ShareRequest
from app.features.team_sync.core.service import TeamSyncService
from app.features.team_sync.ui.controller import TeamSyncController
from app.features.team_sync.ui.ports import SyncPorts
from app.features.team_sync.ui.send_sheet import SendToolbarButton
from app.features.team_sync.ui.team_view import TeamView
from app.qt.QtWidgets import QApplication, QLabel, QStatusBar, QWidget
from tests.unit.features.team_sync.conftest import machine, touch_watchdog, write_account
from tests.unit.features.team_sync.faxmail_sim import FaxMailSim


class _Badges:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.active = ""

    def set_badge(self, view_id: str, count: int) -> None:
        self.counts[view_id] = count

    def set_active_view(self, view_id: str) -> None:
        self.active = view_id


def _bind(service: TeamSyncService, root: Path) -> tuple[QWidget, TeamSyncController, TeamView, SendToolbarButton]:
    window = QWidget()
    badges = _Badges()
    window._status_controller = SimpleNamespace(status_bar=QStatusBar(window))  # type: ignore[attr-defined]
    window._status_controller.status_bar.addPermanentWidget(QLabel("diag", window))
    window._status_controller.status_bar.addPermanentWidget(QLabel("Python", window))
    window._activity_bar = badges  # type: ignore[attr-defined]
    window._logger = logging.getLogger("cbcs.team_sync.smoke")  # type: ignore[attr-defined]
    view = TeamView()
    button = SendToolbarButton()
    controller = TeamSyncController(window, service, SyncPorts(), dormant=False)
    controller._project_root = str(root)
    controller.attach(view, button)
    window.resize(900, 700)
    view.resize(420, 640)
    window.show()
    view.show()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    return window, controller, view, button


def _texts(view: TeamView) -> list[str]:
    found = []
    for label in view.findChildren(QLabel):
        if label.objectName() in {"shell.teamSync.feedSystem", "shell.teamSync.feedNote", "shell.teamSync.feedName"}:
            found.append(label.text())
    return found


@pytest.mark.unit
def test_two_projects_share_invite_send_and_combine(qapp: object, tmp_path: Path) -> None:
    del qapp
    mails = tmp_path / ".Mails"
    sam_account = write_account(mails, "default", "sam@example.test")
    ana_account = write_account(mails, "cedar", "ana@example.test")
    touch_watchdog(mails, "sam-pc")
    touch_watchdog(mails, "ana-pc")
    sam_root = tmp_path / "sam"
    ana_root = tmp_path / "ana"
    sam_root.mkdir()
    ana_root.mkdir()
    (sam_root / "invoice.py").write_text("def total(x):\n    return x\n", encoding="utf-8")
    sam = TeamSyncService(
        str(sam_root),
        machine=machine(tmp_path / "sam-box", "sam-pc"),
        mail_roots=[str(sam_account)],
    )
    ana = TeamSyncService(
        str(ana_root),
        machine=machine(tmp_path / "ana-box", "ana-pc"),
        mail_roots=[str(ana_account)],
    )
    sim = FaxMailSim(mails)
    _sam_window, sam_ui, sam_view, sam_send = _bind(sam, sam_root)
    _ana_window, ana_ui, ana_view, ana_send = _bind(ana, ana_root)

    assert sam_view._empty.isVisible() is True
    sam_ui.submit_share(
        ShareRequest(
            project_name="Invoice",
            my_name="Sam Brenneman",
            my_shop="Maple",
            invites=[Invite("Ana Kurtz", "Cedar", "ana@example.test")],
            message="Invoice for the shop",
        )
    )
    assert sam_ui._status.shared is True
    assert sam_view._empty.isVisible() is False
    assert any("shared" in text.lower() for text in _texts(sam_view))
    assert _sam_window._activity_bar.active == "team"  # type: ignore[attr-defined]

    assert sim.tick() >= 1
    ana_ui._poll_after_open()
    invites = ana.pending_invites()
    assert invites
    ana_ui.submit_accept_invite(invites[0].id, str(ana_root))
    assert ana_ui._status.shared is True
    assert any("joined" in text.lower() or "shared" in text.lower() for text in _texts(ana_view))

    assert sim.tick() >= 1
    sam_ui._poll_after_open()
    assert any(member.email == "ana@example.test" for member in sam_ui._status.members)

    (sam_root / "invoice.py").write_text("def total(x):\n    return x + 2\n", encoding="utf-8")
    sam_ui.refresh_status()
    assert sam_send.count() >= 1
    sam_ui._save_only("sam total", [])
    assert sam_send.count() == 0
    (ana_root / "invoice.py").write_text("def total(x):\n    return x * 2\n", encoding="utf-8")
    ana_ui.refresh_status()
    assert ana_send.count() >= 1
    assert "to send" in ana_ui._segment._full_text
    ana_ui._send("ana total", [])
    assert ana_send.count() == 0
    assert sim.tick() >= 1
    sam_ui._poll_after_open()
    assert sam_ui._status.waiting == 1
    assert "from" in sam_ui._segment._full_text
    assert _sam_window._activity_bar.counts.get("team", 0) >= 1  # type: ignore[attr-defined]

    sam_ui.open_review()
    assert sam_ui._review is not None
    sam_ui._review.accept()
    assert sam_ui._combine is not None
    assert sam_ui._status.combine is not None
    assert "to choose" in sam_ui._segment._full_text
    assert sam_send.isEnabled() is False
    assert sam_view._send.isEnabled() is False

    clash_id = sam_ui._status.combine.clashes[0].id
    sam_ui._combine.settle(clash_id, RESOLVE_THEIRS)
    assert sam_ui._combine.finish_button.isEnabled() is True
    sam_ui._combine.finish_button.click()
    assert "return x * 2" in (sam_root / "invoice.py").read_text(encoding="utf-8")
    assert sam_ui._status.combine is None
    assert sam_send.isEnabled() is True
