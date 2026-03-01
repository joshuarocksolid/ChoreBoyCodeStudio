"""Unit tests for shell toolbar construction."""

from __future__ import annotations

import types

import pytest

import app.shell.toolbar as toolbar_module
from app.shell.menus import MenuStubRegistry

pytestmark = pytest.mark.unit


class _FakeAction:
    def __init__(self, action_id: str) -> None:
        self.action_id = action_id


class _FakeToolBar:
    def __init__(self, title: str, _main_window: object) -> None:
        self.title = title
        self.object_name = ""
        self.actions: list[_FakeAction | str] = []
        self.movable = True

    def setObjectName(self, name: str) -> None:  # noqa: N802 - Qt signature
        self.object_name = name

    def setMovable(self, value: bool) -> None:  # noqa: N802 - Qt signature
        self.movable = value

    def addAction(self, action: _FakeAction) -> None:  # noqa: N802 - Qt signature
        self.actions.append(action)

    def addSeparator(self) -> None:  # noqa: N802 - Qt signature
        self.actions.append("|")


class _FakeMainWindow:
    def __init__(self) -> None:
        self.toolbars: list[_FakeToolBar] = []

    def addToolBar(self, toolbar: _FakeToolBar) -> None:  # noqa: N802 - Qt signature
        self.toolbars.append(toolbar)


def test_build_shell_toolbar_returns_none_without_registry() -> None:
    window = _FakeMainWindow()
    assert toolbar_module.build_shell_toolbar(window, None) is None


def test_build_shell_toolbar_adds_expected_action_order(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_import(_name: str, _globals=None, _locals=None, _fromlist=(), _level=0, **_kwargs):  # type: ignore[no-untyped-def]
        return types.SimpleNamespace(QToolBar=_FakeToolBar)

    monkeypatch.setitem(toolbar_module.__dict__, "__import__", _fake_import)

    actions = {
        "shell.action.run.run": _FakeAction("run"),
        "shell.action.run.debug": _FakeAction("debug"),
        "shell.action.run.stop": _FakeAction("stop"),
        "shell.action.run.restart": _FakeAction("restart"),
        "shell.action.run.pythonConsole": _FakeAction("pythonConsole"),
        "shell.action.run.continue": _FakeAction("continue"),
        "shell.action.run.pause": _FakeAction("pause"),
        "shell.action.run.stepOver": _FakeAction("stepOver"),
        "shell.action.run.stepInto": _FakeAction("stepInto"),
        "shell.action.run.stepOut": _FakeAction("stepOut"),
        "shell.action.run.toggleBreakpoint": _FakeAction("toggleBreakpoint"),
    }
    registry = MenuStubRegistry(actions=actions, menus={})
    window = _FakeMainWindow()

    toolbar = toolbar_module.build_shell_toolbar(window, registry)

    assert toolbar is not None
    assert window.toolbars
    assert toolbar.object_name == "shell.toolbar.runDebug"
    action_ids = [entry.action_id for entry in toolbar.actions if isinstance(entry, _FakeAction)]
    assert action_ids[0:5] == ["run", "debug", "stop", "restart", "pythonConsole"]
    assert action_ids[5:] == ["continue", "pause", "stepOver", "stepInto", "stepOut", "toggleBreakpoint"]
