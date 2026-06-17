"""Keybindings tab handlers for SettingsDialog."""

from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import QMessageBox, QKeySequenceEdit, QPushButton, QTableWidgetItem

from app.shell.settings_models import EditorSettingsSnapshot
from app.shell.shortcut_preferences import (
    SHORTCUT_COMMANDS,
    build_effective_shortcut_map,
    default_shortcut_map,
    find_shortcut_conflicts,
    normalize_shortcut,
)


class SettingsKeybindingsHandlersMixin:
    """Mixin for settings keybindings tab handlers."""

    def _apply_shortcut_snapshot(self, snapshot: EditorSettingsSnapshot) -> None:
        effective = build_effective_shortcut_map(snapshot.shortcut_overrides)
        self._is_updating_shortcut_editors = True
        try:
            for action_id, editor in self._shortcut_editors.items():
                editor.setKeySequence(QKeySequence(effective.get(action_id, "")))
        finally:
            self._is_updating_shortcut_editors = False

    def _populate_shortcut_table(self, snapshot: EditorSettingsSnapshot) -> None:
        defaults = default_shortcut_map()
        effective = build_effective_shortcut_map(snapshot.shortcut_overrides)
        self._shortcut_table.setRowCount(len(SHORTCUT_COMMANDS))
        for row_index, command in enumerate(SHORTCUT_COMMANDS):
            self._shortcut_rows[command.action_id] = row_index
            command_item = QTableWidgetItem(f"{command.category} / {command.label}")
            command_item.setData(Qt.UserRole, command.action_id)
            self._shortcut_table.setItem(row_index, 0, command_item)

            editor = QKeySequenceEdit(self._shortcut_table)
            current_shortcut = effective.get(command.action_id, "")
            if current_shortcut:
                editor.setKeySequence(QKeySequence(current_shortcut))
            editor.keySequenceChanged.connect(
                lambda _sequence, action_id=command.action_id: self._handle_shortcut_changed(action_id)
            )
            self._shortcut_editors[command.action_id] = editor
            self._shortcut_table.setCellWidget(row_index, 1, editor)

            default_item = QTableWidgetItem(defaults.get(command.action_id, ""))
            self._shortcut_table.setItem(row_index, 2, default_item)

            reset_button = QPushButton("Reset", self._shortcut_table)
            reset_button.clicked.connect(
                lambda _checked=False, action_id=command.action_id: self._handle_reset_shortcut(action_id)
            )
            self._shortcut_table.setCellWidget(row_index, 3, reset_button)

        self._finalize_keybindings_columns()

    def _handle_reset_shortcut(self, action_id: str) -> None:
        editor = self._shortcut_editors.get(action_id)
        if editor is None:
            return
        default_shortcuts = default_shortcut_map()
        self._is_updating_shortcut_editors = True
        editor.setKeySequence(QKeySequence(default_shortcuts.get(action_id, "")))
        self._is_updating_shortcut_editors = False
        self._refresh_shortcut_conflicts()

    def _handle_shortcut_changed(self, action_id: str) -> None:
        if self._is_updating_shortcut_editors:
            self._refresh_shortcut_conflicts()
            return
        editor = self._shortcut_editors.get(action_id)
        if editor is None:
            self._refresh_shortcut_conflicts()
            return
        assigned_shortcut = normalize_shortcut(editor.keySequence().toString())
        if not assigned_shortcut or not editor.hasFocus():
            self._refresh_shortcut_conflicts()
            return
        conflicting_action_ids = [
            conflict_action_id
            for conflict_action_id, shortcut in self._current_shortcut_map().items()
            if conflict_action_id != action_id and normalize_shortcut(shortcut) == assigned_shortcut
        ]
        if not conflicting_action_ids:
            self._refresh_shortcut_conflicts()
            return
        command_labels = {
            command.action_id: f"{command.category} / {command.label}"
            for command in SHORTCUT_COMMANDS
        }
        conflict_names = ", ".join(command_labels.get(item, item) for item in conflicting_action_ids)
        choice = QMessageBox.question(
            self,
            "Shortcut Conflict",
            (
                f"'{assigned_shortcut}' is already assigned to {conflict_names}.\n\n"
                "Do you want to reassign it to this command?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        self._is_updating_shortcut_editors = True
        try:
            if choice == QMessageBox.Yes:
                for conflict_action_id in conflicting_action_ids:
                    conflict_editor = self._shortcut_editors.get(conflict_action_id)
                    if conflict_editor is not None:
                        conflict_editor.setKeySequence(QKeySequence())
            else:
                editor.setKeySequence(QKeySequence())
        finally:
            self._is_updating_shortcut_editors = False
        self._refresh_shortcut_conflicts()

    def _handle_reset_all_shortcuts(self) -> None:
        defaults = default_shortcut_map()
        self._is_updating_shortcut_editors = True
        try:
            for action_id, editor in self._shortcut_editors.items():
                editor.setKeySequence(QKeySequence(defaults.get(action_id, "")))
        finally:
            self._is_updating_shortcut_editors = False
        self._refresh_shortcut_conflicts()

    def _filter_shortcut_rows(self, query: str) -> None:
        lowered = query.strip().lower()
        for action_id, row_index in self._shortcut_rows.items():
            item = self._shortcut_table.item(row_index, 0)
            if item is None:
                continue
            text = item.text().lower()
            should_show = not lowered or lowered in text or lowered in action_id.lower()
            self._shortcut_table.setRowHidden(row_index, not should_show)

    def _current_shortcut_map(self) -> dict[str, str]:
        current: dict[str, str] = {}
        for action_id, editor in self._shortcut_editors.items():
            current[action_id] = normalize_shortcut(editor.keySequence().toString())
        return current

    def _refresh_shortcut_conflicts(self) -> None:
        conflicts = find_shortcut_conflicts(self._current_shortcut_map())
        if conflicts:
            details = [f"{shortcut}: {', '.join(action_ids)}" for shortcut, action_ids in sorted(conflicts.items())]
            self._shortcut_conflict_label.setText("Conflicting shortcuts:\n" + "\n".join(details[:4]))
            self._shortcut_conflict_label.setVisible(True)
            self._has_shortcut_conflicts = True
        else:
            self._shortcut_conflict_label.clear()
            self._shortcut_conflict_label.setVisible(False)
            self._has_shortcut_conflicts = False
        self._refresh_validation_state()

    def _shortcut_overrides_snapshot(self) -> dict[str, str]:
        overrides: dict[str, str] = {}
        defaults = default_shortcut_map()
        for action_id, current_shortcut in self._current_shortcut_map().items():
            default_shortcut = normalize_shortcut(defaults.get(action_id, ""))
            if current_shortcut == default_shortcut:
                continue
            overrides[action_id] = current_shortcut if current_shortcut else ""
        return overrides
