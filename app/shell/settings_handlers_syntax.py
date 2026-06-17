"""Syntax colors tab handlers for SettingsDialog."""

from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtGui import QColor
from PySide2.QtWidgets import QColorDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidgetItem, QWidget

from app.editors.syntax_engine import (
    DEFAULT_DARK_PALETTE,
    DEFAULT_HC_DARK_PALETTE,
    DEFAULT_HC_LIGHT_PALETTE,
    DEFAULT_LIGHT_PALETTE,
)
from app.shell.settings_dialog_tables import finalize_settings_table_rows
from app.shell.syntax_color_preferences import (
    SYNTAX_COLOR_TOKENS,
    THEME_DARK,
    THEME_HC_DARK,
    THEME_HC_LIGHT,
    THEME_LIGHT,
    normalize_hex_color,
)

_VALID_SYNTAX_THEME_KEYS = frozenset({THEME_LIGHT, THEME_DARK, THEME_HC_LIGHT, THEME_HC_DARK})


class SettingsSyntaxHandlersMixin:
    """Mixin for settings syntax colors tab handlers."""

    def _syntax_defaults_for_theme(self, theme_key: str) -> dict[str, str]:
        if theme_key == THEME_HC_DARK:
            return dict(DEFAULT_HC_DARK_PALETTE)
        if theme_key == THEME_HC_LIGHT:
            return dict(DEFAULT_HC_LIGHT_PALETTE)
        if theme_key == THEME_DARK:
            return dict(DEFAULT_DARK_PALETTE)
        return dict(DEFAULT_LIGHT_PALETTE)

    def _populate_syntax_color_table(self, theme_key: str) -> None:
        self._active_syntax_theme_key = theme_key
        self._syntax_color_inputs.clear()
        self._syntax_color_swatches.clear()
        self._syntax_color_row_by_token.clear()
        defaults = self._syntax_defaults_for_theme(theme_key)
        overrides = self._syntax_color_overrides_by_theme.setdefault(theme_key, {})
        self._syntax_color_table.setRowCount(0)
        self._syntax_color_table.setRowCount(len(SYNTAX_COLOR_TOKENS))
        for row_index, token in enumerate(SYNTAX_COLOR_TOKENS):
            self._syntax_color_row_by_token[token.key] = row_index
            label_item = QTableWidgetItem(f"{token.category} / {token.label}")
            label_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self._syntax_color_table.setItem(row_index, 0, label_item)

            color_container = QWidget(self._syntax_color_table)
            color_layout = QHBoxLayout(color_container)
            color_layout.setContentsMargins(4, 2, 4, 2)
            color_layout.setSpacing(6)

            swatch = QLabel(color_container)
            swatch.setFixedSize(16, 16)
            color_layout.addWidget(swatch)
            self._syntax_color_swatches[token.key] = swatch

            color_input = QLineEdit(color_container)
            color_input.setMaximumWidth(90)
            color_input.setPlaceholderText(defaults.get(token.key, ""))
            effective_color = overrides.get(token.key, defaults.get(token.key, ""))
            color_input.setText(effective_color)
            color_input.textEdited.connect(
                lambda _text, key=token.key: self._handle_syntax_color_text_edited(key)
            )
            self._syntax_color_inputs[token.key] = color_input
            color_layout.addWidget(color_input)

            self._syntax_color_table.setCellWidget(row_index, 1, color_container)
            self._update_syntax_swatch(token.key, effective_color)

            pick_button = QPushButton("Pick", self._syntax_color_table)
            pick_button.clicked.connect(
                lambda _checked=False, key=token.key: self._handle_pick_syntax_color(key)
            )
            self._syntax_color_table.setCellWidget(row_index, 2, pick_button)

            reset_button = QPushButton("Reset", self._syntax_color_table)
            reset_button.clicked.connect(
                lambda _checked=False, key=token.key: self._handle_reset_syntax_color(key)
            )
            self._syntax_color_table.setCellWidget(row_index, 3, reset_button)

        finalize_settings_table_rows(self._syntax_color_table)
        self._finalize_syntax_columns()
        self._refresh_syntax_validation()

    def _handle_syntax_theme_changed(self, _index: int) -> None:
        theme_key = str(self._syntax_theme_input.currentData())
        if theme_key not in _VALID_SYNTAX_THEME_KEYS:
            theme_key = THEME_LIGHT
        self._populate_syntax_color_table(theme_key)

    def _handle_pick_syntax_color(self, token_key: str) -> None:
        input_widget = self._syntax_color_inputs.get(token_key)
        if input_widget is None:
            return
        current = normalize_hex_color(input_widget.text()) or input_widget.placeholderText()
        chosen = QColorDialog.getColor(
            initial=QColor(current if current else "#FFFFFF"),
            parent=self,
            title="Choose syntax color",
        )
        if not chosen.isValid():
            return
        input_widget.setText(chosen.name().upper())
        self._handle_syntax_color_text_edited(token_key)

    def _handle_reset_syntax_color(self, token_key: str) -> None:
        defaults = self._syntax_defaults_for_theme(self._active_syntax_theme_key)
        overrides = self._syntax_color_overrides_by_theme.setdefault(self._active_syntax_theme_key, {})
        overrides.pop(token_key, None)
        input_widget = self._syntax_color_inputs.get(token_key)
        default_color = defaults.get(token_key, "")
        if input_widget is not None:
            input_widget.setText(default_color)
        self._update_syntax_swatch(token_key, default_color)
        self._refresh_syntax_validation()

    def _handle_syntax_color_text_edited(self, token_key: str) -> None:
        input_widget = self._syntax_color_inputs.get(token_key)
        if input_widget is None:
            return
        overrides = self._syntax_color_overrides_by_theme.setdefault(self._active_syntax_theme_key, {})
        defaults = self._syntax_defaults_for_theme(self._active_syntax_theme_key)
        raw_text = input_widget.text().strip()
        if not raw_text:
            overrides.pop(token_key, None)
            default_color = defaults.get(token_key, "")
            input_widget.setText(default_color)
            self._update_syntax_swatch(token_key, default_color)
            self._refresh_syntax_validation()
            return
        normalized = normalize_hex_color(input_widget.text())
        if normalized is None:
            self._update_syntax_swatch(token_key, raw_text)
            self._refresh_syntax_validation()
            return
        if normalized == defaults.get(token_key):
            overrides.pop(token_key, None)
        else:
            overrides[token_key] = normalized
        input_widget.setText(normalized)
        self._update_syntax_swatch(token_key, normalized)
        self._refresh_syntax_validation()

    def _update_syntax_swatch(self, token_key: str, hex_color: str) -> None:
        swatch = self._syntax_color_swatches.get(token_key)
        if swatch is None:
            return
        normalized = normalize_hex_color(hex_color)
        border = self._tokens.border
        if normalized:
            swatch.setStyleSheet(
                f"background: {normalized}; border: 1px solid {border}; border-radius: 3px;"
            )
        else:
            swatch.setStyleSheet(
                f"background: transparent; border: 1px solid {border}; border-radius: 3px;"
            )

    def _refresh_syntax_validation(self) -> None:
        invalid_entries: list[str] = []
        error_color = self._tokens.diag_error_color
        for token_key, input_widget in self._syntax_color_inputs.items():
            if not input_widget.text().strip():
                input_widget.setStyleSheet("")
                continue
            normalized = normalize_hex_color(input_widget.text())
            if normalized is None:
                input_widget.setStyleSheet(f"border: 1px solid {error_color};")
                invalid_entries.append(token_key)
            else:
                input_widget.setStyleSheet("")
        if invalid_entries:
            preview = ", ".join(invalid_entries[:5])
            self._syntax_validation_label.setText(
                f"Invalid syntax colors for: {preview}. Use #RRGGBB format."
            )
            self._syntax_validation_label.setVisible(True)
            self._has_invalid_syntax_colors = True
        else:
            self._syntax_validation_label.clear()
            self._syntax_validation_label.setVisible(False)
            self._has_invalid_syntax_colors = False
        self._refresh_validation_state()
