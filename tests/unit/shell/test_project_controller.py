"""Unit tests for shell project controller logic."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.core.models import LoadedProject, ProjectFileEntry, ProjectMetadata
from app.shell.menus import MenuStubRegistry
from app.shell.project_controller import ProjectController

pytestmark = pytest.mark.unit


class _FakeAction:
    def __init__(self, text: str) -> None:
        self.text = text
        self.tooltip = ""
        self.enabled = True
        self._trigger_callbacks: list[object] = []
        self.triggered = self

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802 - Qt-compatible method name
        self.enabled = enabled

    def setToolTip(self, tooltip: str) -> None:  # noqa: N802
        self.tooltip = tooltip

    def connect(self, callback) -> None:  # type: ignore[no-untyped-def]
        self._trigger_callbacks.append(callback)


class _FakeMenu:
    def __init__(self) -> None:
        self.actions: list[_FakeAction] = []

    def clear(self) -> None:
        self.actions.clear()

    def addAction(self, text: str) -> _FakeAction:  # noqa: N802
        action = _FakeAction(text)
        self.actions.append(action)
        return action


def _loaded_project(path: str) -> LoadedProject:
    return LoadedProject(
        project_root=path,
        manifest_path=str(Path(path) / "cbcs" / "project.json"),
        metadata=ProjectMetadata(schema_version=1, name="proj"),
        entries=[ProjectFileEntry(relative_path="run.py", absolute_path=str(Path(path) / "run.py"), is_directory=False)],
    )


def test_open_project_by_path_applies_loaded_project(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = ProjectController(state_root="/tmp", logger=logging.getLogger("test"))
    loaded = _loaded_project("/tmp/project")
    monkeypatch.setattr("app.shell.project_controller.open_project_and_track_recent", lambda *_args, **_kwargs: loaded)

    applied: list[LoadedProject] = []
    opened = controller.open_project_by_path(
        "/tmp/project",
        confirm_proceed=lambda _message: True,
        on_loaded=applied.append,
        on_error=lambda _path, _details: pytest.fail("unexpected error callback"),
    )

    assert opened is True
    assert applied == [loaded]


def test_open_project_by_path_respects_unsaved_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = ProjectController(state_root="/tmp", logger=logging.getLogger("test"))
    called = {"value": False}
    monkeypatch.setattr(
        "app.shell.project_controller.open_project_and_track_recent",
        lambda *_args, **_kwargs: called.__setitem__("value", True),
    )

    opened = controller.open_project_by_path(
        "/tmp/project",
        confirm_proceed=lambda _message: False,
        on_loaded=lambda _loaded: pytest.fail("should not load project"),
        on_error=lambda _path, _details: pytest.fail("should not fail with error"),
    )

    assert opened is False
    assert called["value"] is False


def test_refresh_open_recent_menu_populates_items(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = ProjectController(state_root="/tmp", logger=logging.getLogger("test"))
    menu = _FakeMenu()
    registry = MenuStubRegistry(actions={}, menus={"shell.menu.file.openRecent": menu})
    monkeypatch.setattr(
        "app.shell.project_controller.load_recent_projects",
        lambda **_kwargs: ["/tmp/projects/alpha", "/tmp/projects/beta"],
    )

    opened: list[str] = []
    controller.refresh_open_recent_menu(registry, open_project_by_path=opened.append)

    assert [action.text for action in menu.actions] == [
        "alpha — /tmp/projects/alpha",
        "beta — /tmp/projects/beta",
    ]
    assert [action.tooltip for action in menu.actions] == ["/tmp/projects/alpha", "/tmp/projects/beta"]


def test_refresh_open_recent_menu_shows_placeholder_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = ProjectController(state_root="/tmp", logger=logging.getLogger("test"))
    menu = _FakeMenu()
    registry = MenuStubRegistry(actions={}, menus={"shell.menu.file.openRecent": menu})
    monkeypatch.setattr("app.shell.project_controller.load_recent_projects", lambda **_kwargs: [])

    controller.refresh_open_recent_menu(registry, open_project_by_path=lambda _path: True)

    assert len(menu.actions) == 1
    assert menu.actions[0].text == "(No recent projects)"
    assert menu.actions[0].enabled is False
