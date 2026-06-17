"""Integration performance checks for post-settings apply."""

from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.intelligence.cache_controls import IntelligenceRuntimeSettings  # noqa: E402
from app.persistence.history_retention import default_local_history_retention_policy  # noqa: E402
from app.project.file_excludes import DEFAULT_EXCLUDE_PATTERNS  # noqa: E402
from app.shell.settings_apply_workflow import (  # noqa: E402
    SettingsApplyWorkflow,
    capture_settings_apply_baseline_from_snapshot,
)
from app.shell.settings_models import EditorSettingsSnapshot, parse_main_window_settings  # noqa: E402
from app.shell.shell_preferences import ShellPreferencesBundle  # noqa: E402
from tests.unit.shell.test_settings_apply_workflow import (  # noqa: E402
    FakeSettingsService,
    RecordingSettingsApplyHost,
)

pytestmark = [pytest.mark.integration, pytest.mark.performance, pytest.mark.timeout(180)]


def test_non_theme_settings_apply_completes_under_100ms() -> None:
    host = RecordingSettingsApplyHost()
    settings_service = FakeSettingsService()
    workflow = SettingsApplyWorkflow(settings_service=settings_service, host=host)
    baseline = capture_settings_apply_baseline_from_snapshot(
        effective_snapshot=EditorSettingsSnapshot(auto_save=False),
        effective_excludes=list(DEFAULT_EXCLUDE_PATTERNS),
    )
    bundle = ShellPreferencesBundle(
        main_window=parse_main_window_settings({}),
        effective_editor=EditorSettingsSnapshot(auto_save=True),
        global_editor=EditorSettingsSnapshot(auto_save=True),
        syntax_color_overrides={},
        shortcut_overrides={},
        lint_rule_overrides={},
        selected_linter=constants.LINTER_PROVIDER_DEFAULT,
        theme_mode=constants.UI_THEME_MODE_DEFAULT,
        ui_font_weight=constants.UI_THEME_FONT_WEIGHT_DEFAULT,
        local_history_retention_policy=default_local_history_retention_policy(),
        intelligence_runtime_settings=IntelligenceRuntimeSettings(),
    )

    start = time.perf_counter()
    workflow.apply_after_settings_saved(
        updated_snapshot=EditorSettingsSnapshot(auto_save=True),
        baseline=baseline,
        project_root="/tmp/project",
        preferences_bundle=bundle,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert host.theme_styles_calls == 0
    assert host.editor_preferences_calls == 0
    assert elapsed_ms <= 100.0
