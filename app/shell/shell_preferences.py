"""Single-load preferences bundle for shell runtime state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from app.intelligence.cache_controls import IntelligenceRuntimeSettings
from app.persistence.history_retention import LocalHistoryRetentionPolicy
from app.shell.settings_models import (
    EditorSettingsSnapshot,
    MainWindowSettingsSnapshot,
    parse_editor_settings_snapshot,
    parse_effective_editor_settings_snapshot,
    parse_effective_main_window_settings,
)
from app.shell.shortcut_preferences import parse_shortcut_overrides
from app.shell.syntax_color_preferences import parse_syntax_color_overrides


class SettingsReader(Protocol):
    def load_global(self) -> Mapping[str, Any]: ...

    def load_project(self, project_root: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class ShellPreferencesBundle:
    """Effective shell preferences loaded from one global + optional project read."""

    main_window: MainWindowSettingsSnapshot
    effective_editor: EditorSettingsSnapshot
    global_editor: EditorSettingsSnapshot
    syntax_color_overrides: dict[str, dict[str, str]]
    shortcut_overrides: dict[str, str]
    lint_rule_overrides: dict[str, dict[str, object]]
    selected_linter: str
    theme_mode: str
    ui_font_weight: str
    local_history_retention_policy: LocalHistoryRetentionPolicy
    intelligence_runtime_settings: IntelligenceRuntimeSettings


def load_shell_preferences_bundle(
    settings_service: SettingsReader,
    *,
    project_root: str | None,
) -> ShellPreferencesBundle:
    global_settings_payload = settings_service.load_global()
    project_settings_payload: Mapping[str, Any] | None = None
    if project_root is not None:
        project_settings_payload = settings_service.load_project(project_root)

    global_editor = parse_editor_settings_snapshot(global_settings_payload)
    effective_editor = parse_effective_editor_settings_snapshot(
        global_settings_payload,
        project_settings_payload,
    )
    main_window = parse_effective_main_window_settings(
        global_settings_payload,
        project_settings_payload,
    )
    return ShellPreferencesBundle(
        main_window=main_window,
        effective_editor=effective_editor,
        global_editor=global_editor,
        syntax_color_overrides=parse_syntax_color_overrides(global_settings_payload),
        shortcut_overrides=parse_shortcut_overrides(global_settings_payload),
        lint_rule_overrides={
            code: dict(value)
            for code, value in effective_editor.lint_rule_overrides.items()
        },
        selected_linter=effective_editor.selected_linter,
        theme_mode=global_editor.theme_mode,
        ui_font_weight=global_editor.ui_font_weight,
        local_history_retention_policy=main_window.local_history_retention_policy,
        intelligence_runtime_settings=main_window.intelligence_runtime_settings,
    )
