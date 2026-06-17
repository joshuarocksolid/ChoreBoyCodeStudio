"""Validation state handlers for SettingsDialog."""

from __future__ import annotations

from app.shell.settings_models import SETTINGS_SCOPE_PROJECT


class SettingsValidationHandlersMixin:
    """Mixin for settings dialog OK-button validation."""

    def _refresh_validation_state(self) -> None:
        if self._ok_button is None:
            return
        if self._active_scope == SETTINGS_SCOPE_PROJECT:
            self._ok_button.setEnabled(True)
            self._ok_button.setToolTip("")
            if self._validation_banner_label is not None:
                self._validation_banner_label.clear()
                self._validation_banner_label.setVisible(False)
            return

        has_conflicts = self._has_shortcut_conflicts
        has_invalid_colors = self._has_invalid_syntax_colors
        can_save = not (has_conflicts or has_invalid_colors)
        self._ok_button.setEnabled(can_save)

        messages: list[str] = []
        if has_conflicts:
            messages.append("Fix conflicting keybindings on the Keybindings tab before saving.")
        if has_invalid_colors:
            messages.append("Fix invalid syntax colors on the Syntax Colors tab before saving.")
        banner_text = " ".join(messages)
        if self._validation_banner_label is not None:
            if banner_text:
                self._validation_banner_label.setText(banner_text)
                self._validation_banner_label.setVisible(True)
            else:
                self._validation_banner_label.clear()
                self._validation_banner_label.setVisible(False)
        self._ok_button.setToolTip(banner_text if not can_save else "")
