"""Composite event-handler mixins for SettingsDialog."""

from __future__ import annotations

from app.shell.settings_handlers_files import SettingsFilesHandlersMixin
from app.shell.settings_handlers_keybindings import SettingsKeybindingsHandlersMixin
from app.shell.settings_handlers_linter import SettingsLinterHandlersMixin
from app.shell.settings_handlers_scope import SettingsScopeHandlersMixin
from app.shell.settings_handlers_syntax import SettingsSyntaxHandlersMixin
from app.shell.settings_handlers_validation import SettingsValidationHandlersMixin


class SettingsDialogHandlersMixin(
    SettingsScopeHandlersMixin,
    SettingsKeybindingsHandlersMixin,
    SettingsSyntaxHandlersMixin,
    SettingsLinterHandlersMixin,
    SettingsFilesHandlersMixin,
    SettingsValidationHandlersMixin,
):
    """Composite mixin supplying SettingsDialog handler methods by tab domain."""
