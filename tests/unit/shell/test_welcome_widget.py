"""Unit tests for the WelcomeWidget."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide2.QtCore import Qt

from app.shell.welcome_widget import WelcomeWidget

pytestmark = pytest.mark.unit


@pytest.fixture()
def widget(qtbot):
    w = WelcomeWidget()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


def test_initial_state_shows_empty_label(widget: WelcomeWidget) -> None:
    """With no projects the empty-state label should be visible."""
    assert widget._empty_label.isVisible()
    assert not widget._project_list.isVisible()


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


def test_new_project_signal(widget: WelcomeWidget, qtbot) -> None:
    """Clicking 'New Project' should emit new_project_requested."""
    with qtbot.waitSignal(widget.new_project_requested, timeout=500):
        widget._new_project_btn.click()


def test_open_project_signal(widget: WelcomeWidget, qtbot) -> None:
    """Clicking 'Open Project' should emit open_project_requested."""
    with qtbot.waitSignal(widget.open_project_requested, timeout=500):
        widget._open_project_btn.click()


def test_double_click_emits_project_selected(widget: WelcomeWidget, qtbot) -> None:
    """Double-clicking a project item should emit project_selected with the path."""
    widget.set_recent_projects(["/home/user/proj"])

    with qtbot.waitSignal(widget.project_selected, timeout=500) as blocker:
        item = widget._project_list.item(0)
        widget._project_list.itemDoubleClicked.emit(item)

    assert blocker.args == ["/home/user/proj"]
