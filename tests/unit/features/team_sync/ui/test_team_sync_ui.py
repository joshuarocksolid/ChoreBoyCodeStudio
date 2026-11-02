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
