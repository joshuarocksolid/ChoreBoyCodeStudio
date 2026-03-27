"""Action editor panel for Designer QAction workflows."""

from __future__ import annotations

from collections.abc import Sequence

from PySide2.QtCore import Signal
from PySide2.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.designer.model import ActionGroupModel, ActionModel


class ActionEditorPanel(QWidget):
    """CRUD surface for action and action-group definitions."""

    add_action_requested = Signal(str)
    remove_action_requested = Signal(str)
    action_property_changed = Signal(str, str, str)
    action_group_changed = Signal(str, str)
    add_group_requested = Signal(str)
    remove_group_requested = Signal(str)
    group_add_action_requested = Signal(str, str)
    group_remove_action_requested = Signal(str, str)
    placement_add_action_requested = Signal(str, str)
    placement_remove_action_requested = Signal(str, str)
    placement_move_action_requested = Signal(str, str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("designer.actions.panel")

        self._actions: list[ActionModel] = []
        self._groups: list[ActionGroupModel] = []
        self._placement_targets: list[tuple[str, str]] = []
        self._placements_by_target: dict[str, list[str]] = {}
        self._active_action_name: str | None = None
        self._active_group_name: str | None = None
        self._active_placement_target: str | None = None
        self._is_populating = False

        self._summary_label = QLabel("No QAction definitions.", self)
        self._summary_label.setObjectName("designer.actions.summary")

        self._action_list = QListWidget(self)
        self._action_list.setObjectName("designer.actions.list")
        self._action_list.currentItemChanged.connect(self._handle_action_selection_changed)

        self._action_name_input = QLineEdit(self)
        self._action_name_input.setObjectName("designer.actions.input.name")
        self._action_name_input.setPlaceholderText("actionName")
        self._action_name_input.returnPressed.connect(self._emit_add_action_from_input)
        self._add_action_button = QPushButton("Add Action", self)
        self._add_action_button.setObjectName("designer.actions.btn.addAction")
        self._add_action_button.clicked.connect(self._emit_add_action_from_input)
        self._remove_action_button = QPushButton("Remove Selected Action", self)
        self._remove_action_button.setObjectName("designer.actions.btn.removeAction")
        self._remove_action_button.clicked.connect(self._emit_remove_selected_action)

        action_buttons = QHBoxLayout()
        action_buttons.setContentsMargins(0, 0, 0, 0)
        action_buttons.setSpacing(6)
        action_buttons.addWidget(self._add_action_button, 0)
        action_buttons.addWidget(self._remove_action_button, 0)
        action_buttons.addStretch(1)

        self._action_text_input = QLineEdit(self)
        self._action_text_input.setObjectName("designer.actions.input.text")
        self._action_text_input.editingFinished.connect(self._emit_action_text_edited)
        self._action_group_combo = QComboBox(self)
        self._action_group_combo.setObjectName("designer.actions.combo.group")
        self._action_group_combo.currentIndexChanged.connect(self._emit_action_group_changed)

        action_form = QFormLayout()
        action_form.setContentsMargins(0, 0, 0, 0)
        action_form.setSpacing(6)
        action_form.addRow("Text", self._action_text_input)
        action_form.addRow("Group", self._action_group_combo)

        self._group_list = QListWidget(self)
        self._group_list.setObjectName("designer.actions.groups.list")
        self._group_list.currentItemChanged.connect(self._handle_group_selection_changed)
        self._group_name_input = QLineEdit(self)
        self._group_name_input.setObjectName("designer.actions.groups.input.name")
        self._group_name_input.setPlaceholderText("groupName")
        self._group_name_input.returnPressed.connect(self._emit_add_group_from_input)
        self._add_group_button = QPushButton("Add Group", self)
        self._add_group_button.setObjectName("designer.actions.groups.btn.add")
        self._add_group_button.clicked.connect(self._emit_add_group_from_input)
        self._remove_group_button = QPushButton("Remove Selected Group", self)
        self._remove_group_button.setObjectName("designer.actions.groups.btn.remove")
        self._remove_group_button.clicked.connect(self._emit_remove_selected_group)

        group_buttons = QHBoxLayout()
        group_buttons.setContentsMargins(0, 0, 0, 0)
        group_buttons.setSpacing(6)
        group_buttons.addWidget(self._add_group_button, 0)
        group_buttons.addWidget(self._remove_group_button, 0)
        group_buttons.addStretch(1)

        self._group_action_combo = QComboBox(self)
        self._group_action_combo.setObjectName("designer.actions.groups.combo.availableAction")
        self._add_group_action_button = QPushButton("Add Action to Group", self)
        self._add_group_action_button.setObjectName("designer.actions.groups.btn.addAction")
        self._add_group_action_button.clicked.connect(self._emit_add_action_to_group)
        self._group_members_list = QListWidget(self)
        self._group_members_list.setObjectName("designer.actions.groups.members")
        self._remove_group_action_button = QPushButton("Remove Selected Group Action", self)
        self._remove_group_action_button.setObjectName("designer.actions.groups.btn.removeAction")
        self._remove_group_action_button.clicked.connect(self._emit_remove_group_action)

        group_member_buttons = QHBoxLayout()
        group_member_buttons.setContentsMargins(0, 0, 0, 0)
        group_member_buttons.setSpacing(6)
        group_member_buttons.addWidget(self._group_action_combo, 1)
        group_member_buttons.addWidget(self._add_group_action_button, 0)

        self._placement_target_combo = QComboBox(self)
        self._placement_target_combo.setObjectName("designer.actions.placement.combo.target")
        self._placement_target_combo.currentIndexChanged.connect(self._handle_placement_target_changed)
        self._placement_action_combo = QComboBox(self)
        self._placement_action_combo.setObjectName("designer.actions.placement.combo.action")
        self._placement_action_combo.addItem("(select action)", "")
        self._placement_add_button = QPushButton("Add Placement", self)
        self._placement_add_button.setObjectName("designer.actions.placement.btn.add")
        self._placement_add_button.clicked.connect(self._emit_add_placement_action)
        self._placement_list = QListWidget(self)
        self._placement_list.setObjectName("designer.actions.placement.list")
        self._placement_remove_button = QPushButton("Remove Placement", self)
        self._placement_remove_button.setObjectName("designer.actions.placement.btn.remove")
        self._placement_remove_button.clicked.connect(self._emit_remove_selected_placement)
        self._placement_move_up_button = QPushButton("Move Up", self)
        self._placement_move_up_button.setObjectName("designer.actions.placement.btn.moveUp")
        self._placement_move_up_button.clicked.connect(lambda: self._emit_move_selected_placement(-1))
        self._placement_move_down_button = QPushButton("Move Down", self)
        self._placement_move_down_button.setObjectName("designer.actions.placement.btn.moveDown")
        self._placement_move_down_button.clicked.connect(lambda: self._emit_move_selected_placement(1))

        placement_controls = QHBoxLayout()
        placement_controls.setContentsMargins(0, 0, 0, 0)
        placement_controls.setSpacing(6)
        placement_controls.addWidget(self._placement_action_combo, 1)
        placement_controls.addWidget(self._placement_add_button, 0)

        placement_reorder_buttons = QHBoxLayout()
        placement_reorder_buttons.setContentsMargins(0, 0, 0, 0)
        placement_reorder_buttons.setSpacing(6)
        placement_reorder_buttons.addWidget(self._placement_move_up_button, 0)
        placement_reorder_buttons.addWidget(self._placement_move_down_button, 0)
        placement_reorder_buttons.addWidget(self._placement_remove_button, 0)
        placement_reorder_buttons.addStretch(1)

        container = QVBoxLayout(self)
        container.setContentsMargins(8, 8, 8, 8)
        container.setSpacing(8)
        container.addWidget(self._summary_label, 0)
        container.addWidget(QLabel("Actions", self), 0)
        container.addWidget(self._action_list, 1)
        container.addWidget(self._action_name_input, 0)
        container.addLayout(action_buttons, 0)
        container.addLayout(action_form, 0)
        container.addWidget(QLabel("Action Groups", self), 0)
        container.addWidget(self._group_list, 1)
        container.addWidget(self._group_name_input, 0)
        container.addLayout(group_buttons, 0)
        container.addLayout(group_member_buttons, 0)
        container.addWidget(self._group_members_list, 1)
        container.addWidget(self._remove_group_action_button, 0)
        container.addWidget(QLabel("Menu/Toolbar Placements", self), 0)
        container.addWidget(self._placement_target_combo, 0)
        container.addLayout(placement_controls, 0)
        container.addWidget(self._placement_list, 1)
        container.addLayout(placement_reorder_buttons, 0)

        self._refresh_summary()

    def bind_actions(
        self,
        actions: Sequence[ActionModel],
        groups: Sequence[ActionGroupModel],
        *,
        placement_targets: Sequence[tuple[str, str]],
        placements_by_target: dict[str, list[str]],
    ) -> None:
        self._is_populating = True
        try:
            self._actions = list(actions)
            self._groups = list(groups)
            self._placement_targets = list(placement_targets)
            self._placements_by_target = {key: list(value) for key, value in placements_by_target.items()}
            self._action_list.clear()
            for action in self._actions:
                item = QListWidgetItem(action.name)
                item.setData(32, action.name)
                self._action_list.addItem(item)
            self._group_list.clear()
            for group in self._groups:
                item = QListWidgetItem(group.name)
                item.setData(32, group.name)
                self._group_list.addItem(item)
            self._rebuild_group_combo()
            self._rebuild_group_action_combo()
            self._rebuild_placement_target_combo()
            self._rebuild_placement_action_combo()
            self._rebind_group_members()
            self._rebind_placement_members()
            self._restore_action_selection()
            self._restore_group_selection()
            self._restore_placement_selection()
        finally:
            self._is_populating = False
        self._refresh_summary()
        self._sync_action_detail_enabled_state()
        self._sync_group_detail_enabled_state()
        self._sync_placement_detail_enabled_state()

    def _refresh_summary(self) -> None:
        action_count = len(self._actions)
        group_count = len(self._groups)
        if action_count == 0 and group_count == 0:
            self._summary_label.setText("No QAction definitions.")
            return
        self._summary_label.setText(f"{action_count} action(s), {group_count} group(s)")

    def _emit_add_action_from_input(self) -> None:
        action_name = self._action_name_input.text().strip()
        if not action_name:
            return
        self.add_action_requested.emit(action_name)
        self._action_name_input.clear()

    def _emit_remove_selected_action(self) -> None:
        if not self._active_action_name:
            return
        self.remove_action_requested.emit(self._active_action_name)

    def _emit_action_text_edited(self) -> None:
        if self._is_populating or not self._active_action_name:
            return
        self.action_property_changed.emit(self._active_action_name, "text", self._action_text_input.text())

    def _emit_action_group_changed(self, _index: int) -> None:
        if self._is_populating or not self._active_action_name:
            return
        self.action_group_changed.emit(self._active_action_name, str(self._action_group_combo.currentData() or ""))

    def _emit_add_group_from_input(self) -> None:
        group_name = self._group_name_input.text().strip()
        if not group_name:
            return
        self.add_group_requested.emit(group_name)
        self._group_name_input.clear()

    def _emit_remove_selected_group(self) -> None:
        if not self._active_group_name:
            return
        self.remove_group_requested.emit(self._active_group_name)

    def _emit_add_action_to_group(self) -> None:
        if not self._active_group_name:
            return
        action_name = str(self._group_action_combo.currentData() or "")
        if not action_name:
            return
        self.group_add_action_requested.emit(self._active_group_name, action_name)

    def _emit_remove_group_action(self) -> None:
        if not self._active_group_name:
            return
        current_item = self._group_members_list.currentItem()
        if current_item is None:
            return
        action_name = current_item.data(32)
        if not action_name:
            return
        self.group_remove_action_requested.emit(self._active_group_name, str(action_name))

    def _emit_add_placement_action(self) -> None:
        if not self._active_placement_target:
            return
        action_name = str(self._placement_action_combo.currentData() or "")
        if not action_name:
            return
        self.placement_add_action_requested.emit(self._active_placement_target, action_name)

    def _emit_remove_selected_placement(self) -> None:
        if not self._active_placement_target:
            return
        current_item = self._placement_list.currentItem()
        if current_item is None:
            return
        action_name = str(current_item.data(32) or "")
        if not action_name:
            return
        self.placement_remove_action_requested.emit(self._active_placement_target, action_name)

    def _emit_move_selected_placement(self, direction: int) -> None:
        if not self._active_placement_target or direction == 0:
            return
        current_item = self._placement_list.currentItem()
        if current_item is None:
            return
        action_name = str(current_item.data(32) or "")
        if not action_name:
            return
        self.placement_move_action_requested.emit(self._active_placement_target, action_name, int(direction))

    def _handle_action_selection_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        self._active_action_name = None if current is None else str(current.data(32) or "")
        self._rebind_action_details()
        self._sync_action_detail_enabled_state()

    def _handle_group_selection_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        self._active_group_name = None if current is None else str(current.data(32) or "")
        self._rebind_group_members()
        self._sync_group_detail_enabled_state()

    def _handle_placement_target_changed(self, _index: int) -> None:
        if self._is_populating:
            return
        self._active_placement_target = str(self._placement_target_combo.currentData() or "")
        self._rebind_placement_members()
        self._sync_placement_detail_enabled_state()

    def _restore_action_selection(self) -> None:
        target = self._active_action_name
        if not target and self._actions:
            target = self._actions[0].name
        if not target:
            self._action_list.setCurrentRow(-1)
            self._rebind_action_details()
            return
        self._set_list_selection(self._action_list, target)
        self._active_action_name = target
        self._rebind_action_details()

    def _restore_group_selection(self) -> None:
        target = self._active_group_name
        if not target and self._groups:
            target = self._groups[0].name
        if not target:
            self._group_list.setCurrentRow(-1)
            self._rebind_group_members()
            return
        self._set_list_selection(self._group_list, target)
        self._active_group_name = target
        self._rebind_group_members()

    def _restore_placement_selection(self) -> None:
        target = self._active_placement_target
        if (not target) and self._placement_targets:
            target = self._placement_targets[0][0]
        if not target:
            if self._placement_target_combo.count() > 0:
                self._placement_target_combo.setCurrentIndex(0)
            self._active_placement_target = ""
            self._rebind_placement_members()
            return
        for index in range(self._placement_target_combo.count()):
            if str(self._placement_target_combo.itemData(index) or "") == target:
                self._placement_target_combo.setCurrentIndex(index)
                break
        self._active_placement_target = target
        self._rebind_placement_members()

    def _set_list_selection(self, list_widget: QListWidget, object_name: str) -> None:
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            if str(item.data(32) or "") == object_name:
                list_widget.setCurrentRow(row)
                return
        list_widget.setCurrentRow(-1)

    def _rebind_action_details(self) -> None:
        self._is_populating = True
        try:
            action = self._action_by_name(self._active_action_name)
            if action is None:
                self._action_text_input.setText("")
                if self._action_group_combo.count() > 0:
                    self._action_group_combo.setCurrentIndex(0)
                return
            text_value = ""
            text_property = action.properties.get("text")
            if text_property is not None:
                text_value = str(text_property.value)
            self._action_text_input.setText(text_value)
            current_group_name = self._group_for_action(action.name)
            self._set_group_combo_selection(current_group_name)
        finally:
            self._is_populating = False

    def _rebind_group_members(self) -> None:
        self._group_members_list.clear()
        group = self._group_by_name(self._active_group_name)
        if group is None:
            return
        for add_action in group.add_actions:
            item = QListWidgetItem(add_action.name)
            item.setData(32, add_action.name)
            self._group_members_list.addItem(item)
        if self._group_members_list.count() > 0:
            self._group_members_list.setCurrentRow(0)

    def _rebuild_group_combo(self) -> None:
        self._action_group_combo.clear()
        self._action_group_combo.addItem("(none)", "")
        for group in self._groups:
            self._action_group_combo.addItem(group.name, group.name)

    def _rebuild_group_action_combo(self) -> None:
        self._group_action_combo.clear()
        self._group_action_combo.addItem("(select action)", "")
        for action in self._actions:
            self._group_action_combo.addItem(action.name, action.name)
        self._group_action_combo.setCurrentIndex(0)

    def _rebuild_placement_target_combo(self) -> None:
        self._placement_target_combo.clear()
        if not self._placement_targets:
            self._placement_target_combo.addItem("(no placement targets)", "")
            return
        for object_name, class_name in self._placement_targets:
            self._placement_target_combo.addItem(f"{object_name} ({class_name})", object_name)

    def _rebuild_placement_action_combo(self) -> None:
        self._placement_action_combo.clear()
        self._placement_action_combo.addItem("(select action)", "")
        for action in self._actions:
            self._placement_action_combo.addItem(action.name, action.name)
        self._placement_action_combo.setCurrentIndex(0)

    def _set_group_combo_selection(self, group_name: str | None) -> None:
        target = group_name or ""
        index = self._action_group_combo.findData(target)
        self._action_group_combo.setCurrentIndex(index if index >= 0 else 0)

    def _group_for_action(self, action_name: str) -> str | None:
        for group in self._groups:
            if any(add_action.name == action_name for add_action in group.add_actions):
                return group.name
        return None

    def _rebind_placement_members(self) -> None:
        self._placement_list.clear()
        target = self._active_placement_target or str(self._placement_target_combo.currentData() or "")
        if not target:
            return
        for action_name in self._placements_by_target.get(target, []):
            item = QListWidgetItem(action_name)
            item.setData(32, action_name)
            self._placement_list.addItem(item)
        if self._placement_list.count() > 0:
            self._placement_list.setCurrentRow(0)

    def _action_by_name(self, action_name: str | None) -> ActionModel | None:
        if not action_name:
            return None
        for action in self._actions:
            if action.name == action_name:
                return action
        return None

    def _group_by_name(self, group_name: str | None) -> ActionGroupModel | None:
        if not group_name:
            return None
        for group in self._groups:
            if group.name == group_name:
                return group
        return None

    def _sync_action_detail_enabled_state(self) -> None:
        has_action = self._action_by_name(self._active_action_name) is not None
        self._remove_action_button.setEnabled(has_action)
        self._action_text_input.setEnabled(has_action)
        self._action_group_combo.setEnabled(has_action)

    def _sync_group_detail_enabled_state(self) -> None:
        has_group = self._group_by_name(self._active_group_name) is not None
        self._remove_group_button.setEnabled(has_group)
        self._group_action_combo.setEnabled(has_group)
        self._add_group_action_button.setEnabled(has_group)
        self._group_members_list.setEnabled(has_group)
        self._remove_group_action_button.setEnabled(has_group and self._group_members_list.count() > 0)

    def _sync_placement_detail_enabled_state(self) -> None:
        target = self._active_placement_target or str(self._placement_target_combo.currentData() or "")
        has_target = bool(target)
        has_actions = len(self._actions) > 0
        has_members = self._placement_list.count() > 0
        self._placement_target_combo.setEnabled(has_target or bool(self._placement_targets))
        self._placement_action_combo.setEnabled(has_target and has_actions)
        self._placement_add_button.setEnabled(has_target and has_actions)
        self._placement_list.setEnabled(has_target)
        self._placement_move_up_button.setEnabled(has_target and has_members)
        self._placement_move_down_button.setEnabled(has_target and has_members)
        self._placement_remove_button.setEnabled(has_target and has_members)
