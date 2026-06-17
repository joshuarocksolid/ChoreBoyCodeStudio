"""Linter tab handlers for SettingsDialog."""

from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QCheckBox, QComboBox, QPushButton, QTableWidgetItem

from app.intelligence.lint_profile import (
    LINT_RULE_DEFINITIONS,
    LINT_SEVERITY_ERROR,
    LINT_SEVERITY_INFO,
    LINT_SEVERITY_WARNING,
)
from app.shell.settings_dialog_tables import finalize_settings_table_rows, settings_table_control_cell
from app.shell.settings_models import SETTINGS_SCOPE_GLOBAL, SETTINGS_SCOPE_PROJECT

_LINT_RULE_BY_CODE = {definition.code: definition for definition in LINT_RULE_DEFINITIONS}


class SettingsLinterHandlersMixin:
    """Mixin for settings linter tab handlers."""

    def _handle_linter_enabled_toggled(self, _checked: bool) -> None:
        self._sync_linter_control_states()

    def _sync_linter_control_states(self) -> None:
        enabled = self._linter_enabled_input.isChecked()
        self._linter_provider_input.setEnabled(enabled)
        self._linter_table.setEnabled(enabled)

    def _populate_linter_table(self) -> None:
        self._lint_enabled_inputs.clear()
        self._lint_severity_inputs.clear()
        self._linter_table.setRowCount(0)
        self._linter_table.setRowCount(len(LINT_RULE_DEFINITIONS))
        severity_values = [LINT_SEVERITY_ERROR, LINT_SEVERITY_WARNING, LINT_SEVERITY_INFO]
        for row_index, definition in enumerate(LINT_RULE_DEFINITIONS):
            code_item = QTableWidgetItem(definition.code)
            code_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self._linter_table.setItem(row_index, 0, code_item)
            rule_item = QTableWidgetItem(definition.title)
            rule_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self._linter_table.setItem(row_index, 1, rule_item)

            override_payload = self._lint_rule_overrides.get(definition.code, {})
            enabled_value = bool(override_payload.get("enabled", definition.default_enabled))
            enabled_input = QCheckBox(self._linter_table)
            enabled_input.setChecked(enabled_value)
            enabled_input.setEnabled(definition.allow_disable)
            enabled_input.stateChanged.connect(
                lambda _state, code=definition.code: self._handle_lint_enabled_changed(code)
            )
            self._linter_table.setCellWidget(
                row_index, 2, settings_table_control_cell(self._linter_table, enabled_input)
            )
            self._lint_enabled_inputs[definition.code] = enabled_input

            severity_input = QComboBox(self._linter_table)
            for severity in severity_values:
                severity_input.addItem(severity.upper(), severity)
            severity_value = str(override_payload.get("severity", definition.default_severity))
            selected_index = severity_input.findData(severity_value)
            severity_input.setCurrentIndex(selected_index if selected_index >= 0 else 0)
            severity_input.setEnabled(definition.allow_severity_override)
            severity_input.currentIndexChanged.connect(
                lambda _idx, code=definition.code: self._handle_lint_severity_changed(code)
            )
            severity_input.setMinimumContentsLength(len("WARNING"))
            severity_input.setMinimumWidth(severity_input.sizeHint().width())
            self._linter_table.setCellWidget(
                row_index, 3, settings_table_control_cell(self._linter_table, severity_input)
            )
            self._lint_severity_inputs[definition.code] = severity_input

            reset_button = QPushButton("Reset", self._linter_table)
            reset_button.clicked.connect(
                lambda _checked=False, code=definition.code: self._handle_reset_lint_rule(code)
            )
            reset_button.setMinimumWidth(reset_button.sizeHint().width())
            self._linter_table.setCellWidget(
                row_index, 4, settings_table_control_cell(self._linter_table, reset_button)
            )

        finalize_settings_table_rows(self._linter_table)
        self._finalize_linter_columns()

    def _handle_lint_enabled_changed(self, code: str) -> None:
        definition = _LINT_RULE_BY_CODE.get(code)
        if definition is None:
            return
        enabled_input = self._lint_enabled_inputs.get(code)
        if enabled_input is None:
            return
        override = self._lint_rule_overrides.setdefault(code, {})
        if definition.allow_disable:
            override["enabled"] = enabled_input.isChecked()
        self._normalize_lint_rule_override(code)

    def _handle_lint_severity_changed(self, code: str) -> None:
        definition = _LINT_RULE_BY_CODE.get(code)
        if definition is None:
            return
        severity_input = self._lint_severity_inputs.get(code)
        if severity_input is None:
            return
        override = self._lint_rule_overrides.setdefault(code, {})
        if definition.allow_severity_override:
            override["severity"] = str(severity_input.currentData())
        self._normalize_lint_rule_override(code)

    def _handle_reset_lint_rule(self, code: str) -> None:
        definition = _LINT_RULE_BY_CODE.get(code)
        if definition is None:
            return
        self._lint_rule_overrides.pop(code, None)
        baseline_snapshot = self._scope_snapshots.get(SETTINGS_SCOPE_GLOBAL)
        baseline_override = None
        if (
            self._active_scope == SETTINGS_SCOPE_PROJECT
            and baseline_snapshot is not None
            and code in baseline_snapshot.lint_rule_overrides
        ):
            baseline_override = baseline_snapshot.lint_rule_overrides.get(code, {})
        enabled_input = self._lint_enabled_inputs.get(code)
        if enabled_input is not None:
            if isinstance(baseline_override, dict) and "enabled" in baseline_override:
                enabled_input.setChecked(bool(baseline_override.get("enabled")))
            else:
                enabled_input.setChecked(definition.default_enabled)
        severity_input = self._lint_severity_inputs.get(code)
        if severity_input is not None:
            baseline_severity = None
            if isinstance(baseline_override, dict):
                severity_raw = baseline_override.get("severity")
                if isinstance(severity_raw, str):
                    baseline_severity = severity_raw
            index = severity_input.findData(baseline_severity or definition.default_severity)
            severity_input.setCurrentIndex(index if index >= 0 else 0)

    def _normalize_lint_rule_override(self, code: str) -> None:
        definition = _LINT_RULE_BY_CODE.get(code)
        if definition is None:
            self._lint_rule_overrides.pop(code, None)
            return
        override = self._lint_rule_overrides.get(code, {})
        normalized: dict[str, object] = {}
        enabled = override.get("enabled")
        if definition.allow_disable and isinstance(enabled, bool) and enabled != definition.default_enabled:
            normalized["enabled"] = enabled
        severity = override.get("severity")
        if (
            definition.allow_severity_override
            and isinstance(severity, str)
            and severity in {LINT_SEVERITY_ERROR, LINT_SEVERITY_WARNING, LINT_SEVERITY_INFO}
            and severity != definition.default_severity
        ):
            normalized["severity"] = severity
        if normalized:
            self._lint_rule_overrides[code] = normalized
        else:
            self._lint_rule_overrides.pop(code, None)

    def _lint_rule_overrides_snapshot(self) -> dict[str, dict[str, object]]:
        return {code: dict(value) for code, value in self._lint_rule_overrides.items()}

    def _handle_reset_linter_overrides_to_global(self) -> None:
        self._lint_rule_overrides.clear()
        self._populate_linter_table()
        baseline_snapshot = self._scope_snapshots.get(SETTINGS_SCOPE_GLOBAL)
        if self._active_scope != SETTINGS_SCOPE_PROJECT or baseline_snapshot is None:
            return
        for definition in LINT_RULE_DEFINITIONS:
            baseline_override = baseline_snapshot.lint_rule_overrides.get(definition.code, {})
            enabled_input = self._lint_enabled_inputs.get(definition.code)
            if enabled_input is not None:
                if isinstance(baseline_override.get("enabled"), bool):
                    enabled_input.setChecked(bool(baseline_override["enabled"]))
                else:
                    enabled_input.setChecked(definition.default_enabled)
            severity_input = self._lint_severity_inputs.get(definition.code)
            if severity_input is not None:
                baseline_severity = baseline_override.get("severity")
                if not isinstance(baseline_severity, str):
                    baseline_severity = definition.default_severity
                index = severity_input.findData(baseline_severity)
                severity_input.setCurrentIndex(index if index >= 0 else 0)
