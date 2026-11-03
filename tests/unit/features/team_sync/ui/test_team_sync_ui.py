"""UI regressions that can fail without a visual change anyone notices."""

from __future__ import annotations

import os

import pytest

from app.features.team_sync.api import RESOLVE_OURS
from app.features.team_sync.core.fake import InMemoryTeamSync
from app.features.team_sync.ui.combine_tab import CombineTab
from app.features.team_sync.ui.ports import SyncPorts
from app.features.team_sync.ui.review_tab import ReviewTab
from app.features.team_sync.ui.send_sheet import SendToolbarButton
from app.features.team_sync.ui.tree_decorations import ExplorerLetterCache
from app.shell.explorer_decorations import decoration_at_paint


@pytest.mark.unit
def test_send_button_follows_pending_and_shared(qapp) -> None:
    del qapp
    service = InMemoryTeamSync()
    button = SendToolbarButton()

    service.scenario("not_shared")
    button.apply_status(service.status())
    assert button.isVisible() is False

    service.scenario("pending")
    button.apply_status(service.status())
    assert button.isVisible() is True
    assert button.count() == 3

    service.scenario("idle")
    button.apply_status(service.status())
    assert button.isVisible() is True
    assert button.count() == 0


@pytest.mark.unit
def test_review_accept_opens_combine_when_fake_returns_clashes(qapp) -> None:
    del qapp
    service = InMemoryTeamSync()
    service.scenario("incoming_clash")
    opened: list[object] = []
    finished: list[object] = []
    tab = ReviewTab()
    tab.open_incoming(
        service,
        SyncPorts(),
        service.incoming()[0],
        on_combine=opened.append,
        on_finished=finished.append,
        on_dismiss=lambda _incoming_id: None,
        on_show_file=lambda _path: None,
    )
    tab.accept()
    assert opened
    assert not finished


@pytest.mark.unit
def test_review_accept_finishes_when_fake_has_no_clashes(qapp) -> None:
    del qapp
    service = InMemoryTeamSync()
    service.scenario("incoming")
    opened: list[object] = []
    finished: list[object] = []
    tab = ReviewTab()
    tab.open_incoming(
        service,
        SyncPorts(),
        service.incoming()[0],
        on_combine=opened.append,
        on_finished=finished.append,
        on_dismiss=lambda _incoming_id: None,
        on_show_file=lambda _path: None,
    )
    tab.accept()
    assert finished
    assert not opened


@pytest.mark.unit
def test_combine_finish_stays_disabled_until_every_clash_is_settled(qapp) -> None:
    del qapp
    service = InMemoryTeamSync()
    service.scenario("combine_several")
    tab = CombineTab()
    tab.open_state(
        service,
        SyncPorts(),
        on_finished=lambda: None,
        on_deleted=lambda _clash: None,
    )
    assert tab.finish_button.isEnabled() is False
    state = service.combine_state()
    assert state is not None
    for clash in state.clashes:
        tab.settle(clash.id, RESOLVE_OURS)
    assert tab.finish_button.isEnabled() is True


@pytest.mark.unit
def test_explorer_decoration_lookup_does_not_touch_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("disk access")

    monkeypatch.setattr(os, "stat", boom)
    monkeypatch.setattr(os, "listdir", boom)
    monkeypatch.setattr(os, "scandir", boom)
    cache = ExplorerLetterCache()
    cache.replace({"invoice.py": ("M", "info"), "legacy_tax.py": ("!", "warn")})

    class Provider:
        """Raises if paint reaches a disk method. Lookup stays on the dict."""

        def __call__(self, relative_path: str):
            return cache.lookup(relative_path)

        def read_disk(self) -> None:
            os.stat("invoice.py")

    provider = Provider()
    assert decoration_at_paint(provider, "invoice.py") == ("M", "info")
    assert decoration_at_paint(provider, "legacy_tax.py") == ("!", "warn")
    assert decoration_at_paint(provider, "missing.py") is None


@pytest.mark.unit
def test_intelligence_hover_still_fires_over_code_in_a_team_project(qapp) -> None:
    from app.qt.QtCore import QEvent, QPoint
    from app.qt.QtGui import QHelpEvent
    from app.qt.QtWidgets import QWidget

    from app.editors.code_editor_widget import CodeEditorWidget
    from app.features.team_sync.ui.controller import TeamSyncController
    from app.features.team_sync.ui.ports import SyncPorts

    service = InMemoryTeamSync()
    service.scenario("idle")
    window = QWidget()
    controller = TeamSyncController(window, service, SyncPorts(), dormant=False)
    controller._project_root = "/tmp/invoice-app"
    editor = CodeEditorWidget()
    editor.setPlainText("alpha = 1\nbeta = 2\n")
    editor.resize(480, 220)
    editor.show()
    qapp.processEvents()
    editor._hover_tooltip_enabled = True
    calls: list[tuple[int, int]] = []
    editor.set_hover_requester(lambda _source, position, generation: calls.append((position, generation)))

    class _Page(QWidget):
        def content(self) -> CodeEditorWidget:
            return editor

    controller.attach_editor_page(_Page(), "/tmp/invoice-app/invoice.py")
    local = QPoint(editor.line_number_area_width() + 28, 10)
    handled = editor.event(QHelpEvent(QEvent.ToolTip, local, editor.mapToGlobal(local)))

    assert handled is True
    assert calls
    assert calls[0][1] == 1
    editor.hide()
    editor.deleteLater()


@pytest.mark.unit
def test_avatar_initials_and_stable_colors() -> None:
    from app.features.team_sync.core.fake import ANA, SAM
    from app.features.team_sync.ui.widgets import avatar_color, initials

    assert initials("Sam Brenneman") == "SB"
    assert initials("Ana Kurtz") == "AK"
    assert initials("You") == "YO"
    assert avatar_color(SAM.id) == "#0F766E"
    assert avatar_color(ANA.id) == "#C2410C"
    assert avatar_color(SAM.id) != avatar_color(ANA.id)
    assert avatar_color("m-other") == avatar_color("m-other")


@pytest.mark.unit
def test_deleted_clash_names_who_did_what() -> None:
    from app.features.team_sync.api import CLASH_DELETED, Clash
    from app.features.team_sync.ui.copy import deleted_clash_copy

    title, chip = deleted_clash_copy(
        "old_statement.py",
        Clash(id="k", path="old_statement.py", kind=CLASH_DELETED, line=0, ours=("edited\n",), theirs=()),
        "Sam Brenneman",
    )
    assert title == "old_statement.py"
    assert chip == "Sam deleted it · you edited it"


@pytest.mark.unit
def test_share_experiment_follows_the_contract() -> None:
    from app.features.team_sync.core import TeamSyncError
    from app.features.team_sync.core.fake import InMemoryTeamSync

    service = InMemoryTeamSync()
    service.scenario("experiments")
    try:
        service.share_experiment("main")
    except TeamSyncError as exc:
        assert "not an experiment" in str(exc)
    else:
        raise AssertionError("main is not an experiment")
    change = service.share_experiment(service.status().line)
    assert change.line == "exp/rounding"


@pytest.mark.unit
def test_combine_tab_closes_when_the_session_ends(qapp) -> None:
    from app.qt.QtWidgets import QTabWidget, QWidget

    from app.features.team_sync.ui.controller import TeamSyncController

    service = InMemoryTeamSync()
    service.scenario("combine_several")
    window = QWidget()
    window._editor_tabs_widget = QTabWidget(window)  # type: ignore[attr-defined]
    controller = TeamSyncController(window, service, SyncPorts(), dormant=False)
    controller._open_combine(service.combine_state())
    assert window._editor_tabs_widget.count() == 1  # type: ignore[attr-defined]

    service.cancel_combine()
    controller._apply_status(service.status())

    assert window._editor_tabs_widget.count() == 0  # type: ignore[attr-defined]
