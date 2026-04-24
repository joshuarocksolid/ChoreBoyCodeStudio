"""Unit tests for the WelcomeWidget."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)
from PySide2.QtCore import Qt
from PySide2.QtWidgets import QApplication

from app.shell.welcome_widget import WelcomeWidget

pytestmark = pytest.mark.unit


@pytest.fixture()
def _ensure_qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


@pytest.fixture()
def widget(_ensure_qapp):  # type: ignore[no-untyped-def]
    w = WelcomeWidget()
    w.show()
    _ensure_qapp.processEvents()
    return w


def test_initial_state_shows_empty_label(widget: WelcomeWidget) -> None:
    """With no projects the empty-state label should be visible."""
    assert widget._empty_label.isVisible()
    assert not widget._project_list.isVisible()
    assert not widget._onboarding_card.isVisible()
    assert widget._project_health_btn.isEnabled() is False


def test_set_recent_projects_populates_list(widget: WelcomeWidget) -> None:
    """Populating projects should show the list and hide the empty label."""
    widget.set_recent_projects(["/home/user/project_a", "/home/user/project_b"])

    assert widget._project_list.count() == 2
    assert widget._project_list.isVisible()
    assert not widget._empty_label.isVisible()


def test_set_recent_projects_shows_name_and_path(widget: WelcomeWidget) -> None:
    """Each list item should display the folder leaf name and the full path."""
    widget.set_recent_projects(["/home/user/my_project"])

    item = widget._project_list.item(0)
    assert "my_project" in item.text()
    assert "/home/user/my_project" in item.text()


def test_search_filters_project_list(widget: WelcomeWidget) -> None:
    """Typing in the search bar should narrow visible projects."""
    widget.set_recent_projects([
        "/home/user/alpha",
        "/home/user/beta",
        "/home/user/gamma",
    ])
    assert widget._project_list.count() == 3

    widget._search_input.setText("beta")
    assert widget._project_list.count() == 1
    assert widget._project_list.item(0).data(Qt.UserRole) == "/home/user/beta"


def test_search_case_insensitive(widget: WelcomeWidget) -> None:
    """Search filtering should be case-insensitive."""
    widget.set_recent_projects(["/home/user/MyProject"])

    widget._search_input.setText("myproject")
    assert widget._project_list.count() == 1


def test_search_no_match_shows_empty_label(widget: WelcomeWidget) -> None:
    """When no projects match the query the empty label should appear."""
    widget.set_recent_projects(["/home/user/alpha"])

    widget._search_input.setText("zzz_no_match")
    assert widget._project_list.count() == 0
    assert widget._empty_label.isVisible()


def test_clearing_search_restores_full_list(widget: WelcomeWidget) -> None:
    """Clearing the search input should restore the complete project list."""
    widget.set_recent_projects(["/home/user/a", "/home/user/b"])
    widget._search_input.setText("a")
    assert widget._project_list.count() == 1

    widget._search_input.setText("")
    assert widget._project_list.count() == 2


def test_new_project_signal(widget: WelcomeWidget) -> None:
    """Clicking 'New Project' should emit new_project_requested."""
    emitted = {"value": False}
    widget.new_project_requested.connect(lambda: emitted.__setitem__("value", True))
    widget._new_project_btn.click()
    assert emitted["value"] is True


def test_open_project_signal(widget: WelcomeWidget) -> None:
    """Clicking 'Open Project' should emit open_project_requested."""
    emitted = {"value": False}
    widget.open_project_requested.connect(lambda: emitted.__setitem__("value", True))
    widget._open_project_btn.click()
    assert emitted["value"] is True


def test_runtime_summary_and_project_health_state_are_updateable(widget: WelcomeWidget) -> None:
    widget.set_runtime_summary("Startup: Runtime ready (7/7 checks)", "All checks passed.")
    widget.set_project_health_available(True)

    assert widget._runtime_summary_label.text() == "Startup: Runtime ready (7/7 checks)"
    assert widget._runtime_summary_label.toolTip() == "All checks passed."
    assert widget._project_health_btn.isEnabled() is True


def test_onboarding_action_signals_emit(widget: WelcomeWidget) -> None:
    widget.set_onboarding_visible(True)
    emitted: list[str] = []
    widget.runtime_center_requested.connect(lambda: emitted.append("runtime_center"))
    widget.getting_started_requested.connect(lambda: emitted.append("getting_started"))
    widget.example_project_requested.connect(lambda: emitted.append("example_project"))
    widget.headless_notes_requested.connect(lambda: emitted.append("headless_notes"))
    widget.dismiss_onboarding_requested.connect(lambda: emitted.append("dismiss"))
    widget.complete_onboarding_requested.connect(lambda: emitted.append("complete"))

    widget._runtime_center_btn.click()
    widget._getting_started_btn.click()
    widget._example_project_btn.click()
    widget._headless_notes_btn.click()
    widget._dismiss_onboarding_btn.click()
    widget._complete_onboarding_btn.click()

    assert emitted == [
        "runtime_center",
        "getting_started",
        "example_project",
        "headless_notes",
        "dismiss",
        "complete",
    ]


def test_double_click_emits_project_selected(widget: WelcomeWidget) -> None:
    """Double-clicking a project item should emit project_selected with the path."""
    widget.set_recent_projects(["/home/user/proj"])
    captured: list[str] = []
    widget.project_selected.connect(lambda path: captured.append(path))
    item = widget._project_list.item(0)
    widget._project_list.itemDoubleClicked.emit(item)
    assert captured == ["/home/user/proj"]
