"""Edit-menu actions do not notify when the value is already set."""

from __future__ import annotations

import pytest

from app.qt.QtWidgets import QAction, QMenu, QWidget
from app.shell.action_state import assign_action, assign_history_action

pytestmark = pytest.mark.usefixtures("qapp")


def test_assign_action_skips_the_same_text_and_enabled_flag() -> None:
    window = QWidget()
    menu = QMenu(window)
    action = QAction("Undo Paste", menu)
    action.setEnabled(True)
    menu.addAction(action)
    fired = {"n": 0}
    action.changed.connect(lambda: fired.__setitem__("n", fired["n"] + 1))

    assert assign_action(action, text="Undo Paste", enabled=True) is False
    assert fired["n"] == 0

    assert assign_action(action, text="Undo Rename", enabled=True) is True
    assert action.text() == "Undo Rename"
    assert fired["n"] == 1
    window.deleteLater()


def test_history_label_is_current_and_a_repeat_is_silent() -> None:
    window = QWidget()
    menu = QMenu(window)
    action = QAction("Undo", menu)
    action.setEnabled(True)
    menu.addAction(action)
    fired = {"n": 0}
    action.changed.connect(lambda: fired.__setitem__("n", fired["n"] + 1))

    assign_history_action(action, "Undo Paste", True)
    assert action.text() == "Undo Paste"
    assert fired["n"] == 1

    assign_history_action(action, "Undo Paste", True)
    assert fired["n"] == 1
    window.deleteLater()
