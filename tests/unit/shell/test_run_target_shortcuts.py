"""Unit tests for resolving run/debug shortcut display strings."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QAction, QApplication  # noqa: E402

from app.shell.menus import MenuStubRegistry  # noqa: E402
from app.shell.run_target_shortcuts import resolve_run_target_shortcut_labels  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_resolve_without_registry_uses_defaults() -> None:
    labels = resolve_run_target_shortcut_labels(None)
    assert labels.run_file == "F5"
    assert labels.debug_file == "Ctrl+F5"
    assert labels.run_project == "Shift+F5"
    assert labels.debug_project == "Ctrl+Shift+F5"


def test_resolve_reads_action_shortcuts() -> None:
    actions: dict[str, QAction] = {}
    for aid, seq in (
        ("shell.action.run.run", "Ctrl+R"),
        ("shell.action.run.debug", "Ctrl+D"),
        ("shell.action.run.runProject", "Ctrl+T"),
        ("shell.action.run.debugProject", "Ctrl+Y"),
    ):
        act = QAction(aid)
        act.setShortcut(seq)
        actions[aid] = act
    registry = MenuStubRegistry(actions=actions, menus={})

    labels = resolve_run_target_shortcut_labels(registry)
    assert labels.run_file
    assert labels.debug_file
    assert labels.run_project
    assert labels.debug_project
