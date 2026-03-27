"""Unit tests for designer action editor panel."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.designer.actions import ActionEditorPanel
from app.designer.model import ActionGroupModel, ActionModel, AddActionModel, PropertyValue

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_action_editor_panel_emits_action_group_and_placement_events() -> None:
    panel = ActionEditorPanel()
    panel.bind_actions(
        actions=[
            ActionModel(name="actionOpen", properties={"text": PropertyValue(value_type="string", value="Open")}),
            ActionModel(name="actionSave", properties={"text": PropertyValue(value_type="string", value="Save")}),
        ],
        groups=[ActionGroupModel(name="fileGroup", add_actions=[AddActionModel(name="actionOpen")])],
        placement_targets=[("MainWindow", "QMainWindow"), ("menuBar", "QMenuBar")],
        placements_by_target={"MainWindow": ["actionOpen"], "menuBar": ["actionSave"]},
    )

    seen_group_add: list[tuple[str, str]] = []
    seen_group_remove: list[tuple[str, str]] = []
    seen_placement_add: list[tuple[str, str]] = []
    seen_placement_remove: list[tuple[str, str]] = []
    seen_placement_move: list[tuple[str, str, int]] = []
    panel.group_add_action_requested.connect(lambda group, action: seen_group_add.append((group, action)))
    panel.group_remove_action_requested.connect(lambda group, action: seen_group_remove.append((group, action)))
    panel.placement_add_action_requested.connect(lambda target, action: seen_placement_add.append((target, action)))
    panel.placement_remove_action_requested.connect(lambda target, action: seen_placement_remove.append((target, action)))
    panel.placement_move_action_requested.connect(
        lambda target, action, direction: seen_placement_move.append((target, action, direction))
    )

    panel._group_list.setCurrentRow(0)  # type: ignore[attr-defined]
    panel._group_action_combo.setCurrentIndex(panel._group_action_combo.findData("actionSave"))  # type: ignore[attr-defined]
    panel._add_group_action_button.click()  # type: ignore[attr-defined]
    panel._group_members_list.setCurrentRow(0)  # type: ignore[attr-defined]
    panel._remove_group_action_button.click()  # type: ignore[attr-defined]

    panel._placement_target_combo.setCurrentIndex(panel._placement_target_combo.findData("menuBar"))  # type: ignore[attr-defined]
    panel._placement_action_combo.setCurrentIndex(panel._placement_action_combo.findData("actionOpen"))  # type: ignore[attr-defined]
    panel._placement_add_button.click()  # type: ignore[attr-defined]
    panel._placement_list.setCurrentRow(0)  # type: ignore[attr-defined]
    panel._placement_move_down_button.click()  # type: ignore[attr-defined]
    panel._placement_list.setCurrentRow(0)  # type: ignore[attr-defined]
    panel._placement_remove_button.click()  # type: ignore[attr-defined]

    assert seen_group_add == [("fileGroup", "actionSave")]
    assert seen_group_remove == [("fileGroup", "actionOpen")]
    assert seen_placement_add == [("menuBar", "actionOpen")]
    assert seen_placement_move == [("menuBar", "actionSave", 1)]
    assert seen_placement_remove == [("menuBar", "actionSave")]
