"""Unit tests for shell run toolbar widget."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication  # noqa: E402

from app.shell.toolbar import RunToolbarWidget, build_run_toolbar_widget  # noqa: E402
from app.shell.menus import MenuStubRegistry  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(request: pytest.FixtureRequest):  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_registry_with_actions() -> tuple[MenuStubRegistry, dict[str, object]]:
    from PySide2.QtWidgets import QAction

    action_map: dict[str, object] = {}
    for aid in (
        "shell.action.run.run",
        "shell.action.run.debug",
        "shell.action.run.stop",
        "shell.action.run.restart",
        "shell.action.run.pythonConsole",
        "shell.action.run.continue",
        "shell.action.run.pause",
        "shell.action.run.stepOver",
        "shell.action.run.stepInto",
        "shell.action.run.stepOut",
        "shell.action.run.toggleBreakpoint",
    ):
        action = QAction(aid.split(".")[-1])
        action.setEnabled(False)
        action_map[aid] = action
    registry = MenuStubRegistry(actions=action_map, menus={})
    return registry, action_map


def test_build_run_toolbar_widget_returns_none_without_registry() -> None:
    assert build_run_toolbar_widget(None) is None


def test_widget_creates_with_correct_object_name() -> None:
    registry, _ = _make_registry_with_actions()
    widget = RunToolbarWidget(registry)
    assert widget.objectName() == "shell.toolbar.runDebug"


def test_disabled_actions_produce_hidden_buttons() -> None:
    registry, actions = _make_registry_with_actions()
    widget = RunToolbarWidget(registry)
    from PySide2.QtWidgets import QToolButton

    visible_buttons = [
        btn for btn in widget.findChildren(QToolButton)
        if btn.isVisible()
    ]
    assert len(visible_buttons) == 0


def test_enabling_action_shows_button() -> None:
    from PySide2.QtWidgets import QAction, QToolButton

    registry, actions = _make_registry_with_actions()
    widget = RunToolbarWidget(registry)

    run_action: QAction = actions["shell.action.run.run"]  # type: ignore[assignment]
    run_action.setEnabled(True)

    visible_buttons = [
        btn for btn in widget.findChildren(QToolButton)
        if not btn.isHidden()
    ]
    assert len(visible_buttons) == 1


def test_python_console_action_is_not_rendered_in_top_toolbar() -> None:
    from PySide2.QtWidgets import QAction, QToolButton

    registry, actions = _make_registry_with_actions()
    widget = RunToolbarWidget(registry)

    python_console_action: QAction = actions["shell.action.run.pythonConsole"]  # type: ignore[assignment]
    python_console_action.setEnabled(True)

    visible_buttons = [
        btn for btn in widget.findChildren(QToolButton)
        if not btn.isHidden()
    ]
    assert len(visible_buttons) == 0
